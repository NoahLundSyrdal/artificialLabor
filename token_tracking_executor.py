#!/usr/bin/env python3
"""
Task Executor with Token Tracking

Executes tasks from execution prompts and captures telemetry.
"""

import json
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Cost table (from model_cost_table.json)
COST_PER_1M_TOKENS = {
    "cheap": {"input": 0.10, "output": 0.10},
    "medium": {"input": 0.50, "output": 0.50},
    "expensive": {"input": 3.00, "output": 15.00},
}

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens: int, output_tokens: int):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def cost(self, tier: str = "medium") -> dict:
        rates = COST_PER_1M_TOKENS.get(tier, COST_PER_1M_TOKENS["medium"])
        input_cost = (self.input_tokens / 1_000_000) * rates["input"]
        output_cost = (self.output_tokens / 1_000_000) * rates["output"]
        return {
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": round(input_cost + output_cost, 6),
        }


@dataclass
class ExecutionTelemetry:
    tokens: TokenUsage = field(default_factory=TokenUsage)
    phases: list = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    external_calls: int = 0
    model_tier: str = "medium"

    def record_phase(self, phase: str, input_tokens: int, output_tokens: int):
        self.phases.append({
            "phase": phase,
            "input": input_tokens,
            "output": output_tokens,
        })
        self.tokens.add(input_tokens, output_tokens)
        self.llm_calls += 1

    def to_dict(self) -> dict:
        return {
            "tokens": {
                "input": self.tokens.input_tokens,
                "output": self.tokens.output_tokens,
                "total": self.tokens.total,
                "by_phase": self.phases,
            },
            "cost": {
                "model_tier": self.model_tier,
                **self.tokens.cost(self.model_tier),
                "external_api_cost_usd": 0,
            },
            "api_calls": {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "external_calls": self.external_calls,
            }
        }


class Executor:
    """Task executor with token tracking."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", tier: str = "medium"):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package required: pip install anthropic")

        self.client = anthropic.Anthropic()
        self.model = model
        self.telemetry = ExecutionTelemetry(model_tier=tier)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def call_llm(self, phase: str, system: str, user: str, max_tokens: int = 4096) -> str:
        """Make an LLM call and track tokens."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}]
        )

        # Extract token usage from response
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        self.telemetry.record_phase(phase, input_tokens, output_tokens)

        # Extract text content
        return response.content[0].text if response.content else ""

    def execute(self, execution_prompt: str, context: dict = None) -> dict:
        """
        Execute a task from an execution prompt.

        Args:
            execution_prompt: The full execution prompt (markdown)
            context: Optional dict with additional context (input files, etc.)

        Returns:
            Execution result with telemetry
        """
        self.started_at = datetime.now(timezone.utc)

        context = context or {}
        deliverables = []
        success_criteria = []
        error = None

        try:
            # Phase 1: Parse and plan
            plan_response = self.call_llm(
                phase="parse_and_plan",
                system="You are a task executor. Given an execution prompt, output a JSON plan with steps to complete the task. Output only valid JSON.",
                user=f"Parse this execution prompt and create a step-by-step plan:\n\n{execution_prompt}\n\nContext: {json.dumps(context)}\n\nOutput JSON with 'steps' array.",
                max_tokens=2048
            )

            # Phase 2: Execute (simplified - real implementation would iterate)
            execute_response = self.call_llm(
                phase="execute_task",
                system="You are a task executor. Execute the task and produce the deliverables. Be thorough and precise.",
                user=f"Execute this task:\n\n{execution_prompt}\n\nContext: {json.dumps(context)}\n\nProduce the deliverables as specified.",
                max_tokens=8192
            )

            # Phase 3: Verify
            verify_response = self.call_llm(
                phase="verify_output",
                system="You are a QA validator. Check if the execution meets success criteria. Output JSON with 'criteria' array containing 'criterion', 'passed' (bool), 'notes'.",
                user=f"Verify this execution:\n\nPrompt:\n{execution_prompt}\n\nOutput:\n{execute_response}\n\nCheck each success criterion. Output only valid JSON.",
                max_tokens=2048
            )

            status = "completed"

        except Exception as e:
            error = str(e)
            status = "failed"

        self.completed_at = datetime.now(timezone.utc)

        return {
            "execution": {
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "wall_time_seconds": (self.completed_at - self.started_at).total_seconds(),
                "success": status == "completed",
                "error": error,
            },
            "telemetry": self.telemetry.to_dict(),
            "deliverables": deliverables,
            "success_criteria": success_criteria,
            "status": status,
        }


def execute_from_file(prompt_path: str, output_path: str = None, tier: str = "medium"):
    """Execute a task from an execution prompt file."""

    with open(prompt_path, 'r') as f:
        execution_prompt = f.read()

    # Extract ad_id from filename
    ad_id = Path(prompt_path).stem.replace("_execution_prompt", "")

    executor = Executor(tier=tier)
    result = executor.execute(execution_prompt)
    result["ad_id"] = ad_id

    # Output
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Output written to: {output_path}")
    else:
        print(json.dumps(result, indent=2))

    # Summary
    t = result["telemetry"]
    print(f"\n=== Token Usage ===")
    print(f"Input:  {t['tokens']['input']:,} tokens")
    print(f"Output: {t['tokens']['output']:,} tokens")
    print(f"Total:  {t['tokens']['total']:,} tokens")
    print(f"Cost:   ${t['cost']['total_cost_usd']:.4f} ({tier} tier)")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python executor.py <execution_prompt.md> [output.json] [tier]")
        print("  tier: cheap, medium, expensive (default: medium)")
        sys.exit(1)

    prompt_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    tier = sys.argv[3] if len(sys.argv) > 3 else "medium"

    execute_from_file(prompt_path, output_path, tier)
