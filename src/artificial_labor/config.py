from __future__ import annotations

import os
from dataclasses import dataclass, field

# Approximate list prices in USD per 1M tokens (input, output). Override with
# LLM_PRICE_INPUT / LLM_PRICE_OUTPUT for models not listed here.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "mistral-small-latest": (0.1, 0.3),
    "mistral-medium-latest": (0.4, 2.0),
    "mistral-large-latest": (2.0, 6.0),
    "codestral-latest": (0.3, 0.9),
    "gpt-4.1-nano": (0.1, 0.4),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4o": (2.5, 10.0),
}

PROVIDERS: dict[str, dict[str, str | None]] = {
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "model": "mistral-medium-latest",
        "code_model": "codestral-latest",
    },
    "openai": {
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
        "model": "gpt-4.1-mini",
        "code_model": "gpt-4.1",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "openai/gpt-4.1-mini",
        "code_model": "openai/gpt-4.1",
    },
}

# Rough conversion rates to USD; good enough for go/no-go bidding decisions.
USD_PER_UNIT: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "AUD": 0.65,
    "CAD": 0.73,
    "NZD": 0.6,
    "INR": 0.012,
}


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    api_key: str
    base_url: str | None
    model: str
    code_model: str
    provider: str = "custom"
    price_override: tuple[float, float] | None = None

    # Decision thresholds
    min_feasibility: float = 0.6
    min_margin: float = 0.3
    cost_overhead: float = 1.3

    # Execution
    max_attempts: int = 3
    script_timeout: int = 180
    extra: dict[str, str] = field(default_factory=dict)

    def price(self, model: str) -> tuple[float, float]:
        if self.price_override:
            return self.price_override
        name = model.split("/")[-1]
        return MODEL_PRICES.get(name, MODEL_PRICES["mistral-medium-latest"])

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        provider = env.get("LLM_PROVIDER", "").strip().lower()
        if not provider and not env.get("LLM_BASE_URL"):
            provider = next(
                (name for name, p in PROVIDERS.items() if env.get(str(p["key_env"]))), ""
            )
        if provider and provider not in PROVIDERS:
            raise ConfigError(f"Unknown LLM_PROVIDER {provider!r}; use one of {list(PROVIDERS)}")
        preset = PROVIDERS.get(provider, {})

        api_key = env.get("LLM_API_KEY") or (env.get(str(preset["key_env"])) if preset else None)
        if not api_key:
            raise ConfigError(
                "No LLM API key found. Set MISTRAL_API_KEY, OPENAI_API_KEY or OPENROUTER_API_KEY "
                "(or LLM_BASE_URL + LLM_API_KEY). See .env.example."
            )
        model = env.get("LLM_MODEL") or preset.get("model")
        if not model:
            raise ConfigError("LLM_MODEL is required when using a custom LLM_BASE_URL")
        price_override = None
        if env.get("LLM_PRICE_INPUT") and env.get("LLM_PRICE_OUTPUT"):
            price_override = (float(env["LLM_PRICE_INPUT"]), float(env["LLM_PRICE_OUTPUT"]))
        return cls(
            api_key=api_key,
            base_url=env.get("LLM_BASE_URL") or preset.get("base_url"),
            model=model,
            code_model=env.get("LLM_CODE_MODEL") or preset.get("code_model") or model,
            provider=provider or "custom",
            price_override=price_override,
        )
