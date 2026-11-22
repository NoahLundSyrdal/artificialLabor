from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from artificial_labor.config import Settings
from artificial_labor.llm import LLM, Completion

Responder = Callable[[list[dict], str], str]


class FakeBackend:
    """Routes each request to a responder based on keywords in the prompt."""

    def __init__(self, responder: Responder):
        self.responder = responder
        self.requests: list[tuple[str, list[dict]]] = []

    def chat(self, messages, *, model, json_mode, temperature, max_tokens) -> Completion:
        self.requests.append((model, messages))
        return Completion(self.responder(messages, model), 1000, 500, model)


@pytest.fixture
def settings() -> Settings:
    return Settings(api_key="test", base_url=None, model="mistral-medium-latest",
                    code_model="codestral-latest", max_attempts=2, script_timeout=30)  # fmt: skip


@pytest.fixture
def make_llm(settings) -> Callable[[Responder], LLM]:
    return lambda responder: LLM(FakeBackend(responder), settings)


@pytest.fixture
def ad_dir(tmp_path: Path) -> Path:
    d = tmp_path / "ads" / "01-csv-prefix"
    (d / "inputs").mkdir(parents=True)
    (d / "ad.md").write_text("CSV cleanup\nOpen\n$10-30 USD\nPrefix column A with @.\n")
    (d / "inputs" / "data.csv").write_text("handle,n\nb,1\naa,2\nb,1\n")
    (d / "brief.json").write_text(json.dumps({"verification_criteria": ["@ prefix"]}))
    return d


JOB = {
    "title": "CSV cleanup",
    "status": "open",
    "pricing": "fixed",
    "budget_min": 10,
    "budget_max": 30,
    "currency": "USD",
    "summary": "Prefix column A with @, dedupe, sort by length.",
    "deliverables": ["cleaned CSV"],
}

ASSESSMENT = {
    "factors": {
        "task_clarity": 0.9,
        "output_determinism": 0.9,
        "tool_availability": 1,
        "verification_ease": 0.9,
        "scope_boundedness": 1,
    },
    "blockers": [],
    "risks": [],
    "needs_client_files": True,
    "estimated_human_hours": 0.5,
    "estimated_llm_tokens": 20000,
    "reasoning": "Simple pandas job.",
}

GOOD_SCRIPT = """```python
import csv, os
os.makedirs("outputs", exist_ok=True)
rows = list(csv.DictReader(open("inputs/data.csv")))
seen, out = set(), []
for r in rows:
    r["handle"] = "@" + r["handle"]
    key = tuple(r.values())
    if key not in seen:
        seen.add(key)
        out.append(r)
out.sort(key=lambda r: len(r["handle"]))
with open("outputs/cleaned.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["handle", "n"])
    w.writeheader()
    w.writerows(out)
print("done", len(out))
```"""

VERIFICATION = {
    "passed": True,
    "score": 1.0,
    "checks": [{"criterion": "@ prefix", "passed": True}],
    "summary": "ok",
}


def last_text(messages: list[dict]) -> str:
    content = messages[-1]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
