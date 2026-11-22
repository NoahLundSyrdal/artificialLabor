"""Minimal LLM layer: one OpenAI-compatible backend, token/cost metering, JSON helpers."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from artificial_labor.config import Settings

Message = dict[str, Any]
T = TypeVar("T", bound=BaseModel)


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class Backend(Protocol):
    def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> Completion: ...


class OpenAICompatibleBackend:
    def __init__(self, api_key: str, base_url: str | None):
        from openai import BadRequestError, OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=4, timeout=180)
        self._bad_request = BadRequestError
        self._json_mode_supported = True

    def chat(self, messages, *, model, json_mode, temperature, max_tokens) -> Completion:
        kwargs = dict(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        if json_mode and self._json_mode_supported:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except self._bad_request:
            if "response_format" not in kwargs:
                raise
            # Some OpenAI-compatible servers reject response_format; prompts still ask for JSON.
            self._json_mode_supported = False
            kwargs.pop("response_format")
            resp = self._client.chat.completions.create(**kwargs)
        usage = resp.usage
        return Completion(
            text=resp.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=resp.model or model,
        )


class Usage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLM:
    """Routes requests to the right model and meters usage.

    `child()` returns a view that shares the backend but keeps its own usage
    (rolled up into the parent), so per-job cost works with parallel jobs.
    """

    def __init__(self, backend: Backend, settings: Settings, parent: LLM | None = None):
        self.backend = backend
        self.settings = settings
        self.usage = Usage()
        self._parent = parent
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> LLM:
        return cls(OpenAICompatibleBackend(settings.api_key, settings.base_url), settings)

    def child(self) -> LLM:
        return LLM(self.backend, self.settings, parent=self)

    def _record(self, c: Completion, model: str) -> None:
        price_in, price_out = self.settings.price(model)
        cost = (c.input_tokens * price_in + c.output_tokens * price_out) / 1_000_000
        node: LLM | None = self
        while node is not None:
            with node._lock:
                node.usage.calls += 1
                node.usage.input_tokens += c.input_tokens
                node.usage.output_tokens += c.output_tokens
                node.usage.cost_usd += cost
            node = node._parent

    def complete(
        self,
        messages: list[Message],
        *,
        code: bool = False,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> str:
        model = self.settings.code_model if code else self.settings.model
        c = self.backend.chat(
            messages,
            model=model,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._record(c, model)
        return c.text

    def complete_model(
        self, messages: list[Message], schema: type[T], *, attempts: int = 3, **kwargs
    ) -> T:
        """Ask for JSON matching `schema`, feeding validation errors back on failure."""
        instruction = (
            "\n\nRespond with a single JSON object matching this JSON schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        last = dict(messages[-1])
        if isinstance(last["content"], str):
            last["content"] += instruction
        else:
            last["content"] = [*last["content"], {"type": "text", "text": instruction}]
        messages = [*messages[:-1], last]
        error: Exception | None = None
        for _ in range(attempts):
            text = self.complete(messages, json_mode=True, **kwargs)
            try:
                return schema.model_validate(extract_json(text))
            except (ValueError, ValidationError) as e:
                error = e
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": f"That was not valid. Error:\n{e}\nReturn only the corrected "
                        "JSON object.",
                    },
                ]
        raise ValueError(f"LLM did not return valid {schema.__name__}: {error}")


def extract_json(text: str) -> dict:
    """Parse the first JSON object in `text`, tolerating code fences and chatter."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


def extract_code(text: str, lang: str = "python") -> str:
    """Return the largest fenced code block, or the raw text if there is none.

    The closing fence must start a line, so scripts that write ``` into Markdown survive, and an
    unclosed block (a reply cut off at the token limit) is returned as-is.
    """
    pattern = rf"^```(?:{lang}|py)?[ \t]*\n(.*?)(?:^```[ \t]*$|\Z)"
    blocks = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
    return max(blocks, key=len).strip() + "\n" if blocks else text.strip() + "\n"
