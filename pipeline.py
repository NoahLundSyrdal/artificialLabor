#!/usr/bin/env python3
"""
Unified Freelancer Automation Pipeline

Orchestrates three stages:
1. Parser - Extract structured data from raw ad text
2. Assessor - Evaluate feasibility, generate proposal + execution prompt
3. Executor - Execute task and produce deliverables

Model configuration is parametrized via pipeline_config.json
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class StageConfig:
    name: str
    provider: str
    model: str
    tier: str
    max_tokens: int
    temperature: float = 0
    description: str = ""

@dataclass
class PipelineConfig:
    parser: StageConfig
    assessor: StageConfig
    executor: StageConfig
    providers: dict
    cost_tiers: dict
    thresholds: dict
    output_dir: Path
    save_intermediate: bool = True

    @classmethod
    def from_file(cls, config_path: str = "pipeline_config.json") -> "PipelineConfig":
        with open(config_path) as f:
            cfg = json.load(f)

        stages = cfg["stages"]
        return cls(
            parser=StageConfig(name="parser", **stages["parser"]),
            assessor=StageConfig(name="assessor", **stages["assessor"]),
            executor=StageConfig(name="executor", **stages["executor"]),
            providers=cfg["providers"],
            cost_tiers=cfg["cost_tiers"],
            thresholds=cfg["thresholds"],
            output_dir=Path(cfg["output"]["base_dir"]),
            save_intermediate=cfg["output"]["save_intermediate"],
        )


# ============================================================================
# Token Tracking
# ============================================================================

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

    def cost(self, tier: str, cost_tiers: dict) -> float:
        rates = cost_tiers.get(tier, cost_tiers["medium"])
        input_cost = (self.input_tokens / 1_000_000) * rates["input_per_1m"]
        output_cost = (self.output_tokens / 1_000_000) * rates["output_per_1m"]
        return round(input_cost + output_cost, 6)

    def to_dict(self) -> dict:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "total": self.total,
        }


@dataclass
class PipelineTelemetry:
    stages: dict = field(default_factory=dict)
    total: TokenUsage = field(default_factory=TokenUsage)

    def record(self, stage: str, input_tokens: int, output_tokens: int):
        if stage not in self.stages:
            self.stages[stage] = TokenUsage()
        self.stages[stage].add(input_tokens, output_tokens)
        self.total.add(input_tokens, output_tokens)

    def to_dict(self, cost_tiers: dict, stage_tiers: dict) -> dict:
        total_cost = 0
        stages_dict = {}
        for stage, usage in self.stages.items():
            tier = stage_tiers.get(stage, "medium")
            cost = usage.cost(tier, cost_tiers)
            total_cost += cost
            stages_dict[stage] = {**usage.to_dict(), "tier": tier, "cost_usd": cost}

        return {
            "by_stage": stages_dict,
            "total": {**self.total.to_dict(), "cost_usd": round(total_cost, 6)},
        }


# ============================================================================
# LLM Client (Multi-Provider)
# ============================================================================

class LLMClient:
    """Unified client supporting Anthropic, OpenAI, and OpenAI-compatible APIs."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._clients = {}

    def _get_client(self, provider: str):
        if provider in self._clients:
            return self._clients[provider]

        provider_cfg = self.config.providers[provider]
        api_key_env = provider_cfg.get("api_key_env")
        api_key = os.environ.get(api_key_env) if api_key_env else None
        base_url = provider_cfg.get("base_url")

        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        else:
            # OpenAI and OpenAI-compatible (OpenRouter, local)
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=base_url)

        self._clients[provider] = (provider, client)
        return provider, client

    def call(self, stage: StageConfig, system: str, user: str) -> tuple[str, int, int]:
        """
        Make an LLM call.

        Returns: (response_text, input_tokens, output_tokens)
        """
        provider, client = self._get_client(stage.provider)

        if provider == "anthropic":
            response = client.messages.create(
                model=stage.model,
                max_tokens=stage.max_tokens,
                temperature=stage.temperature,
                system=system,
                messages=[{"role": "user", "content": user}]
            )
            text = response.content[0].text if response.content else ""
            return text, response.usage.input_tokens, response.usage.output_tokens
        else:
            # OpenAI-compatible
            response = client.chat.completions.create(
                model=stage.model,
                max_tokens=stage.max_tokens,
                temperature=stage.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            )
            text = response.choices[0].message.content or ""
            usage = response.usage
            return text, usage.prompt_tokens, usage.completion_tokens


# ============================================================================
# Pipeline Stages
# ============================================================================

class Pipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.client = LLMClient(config)
        self.telemetry = PipelineTelemetry()
        self.schemas_dir = Path("data/schemas")

    def _load_schema(self, filename: str) -> str:
        path = self.schemas_dir / filename
        if path.exists():
            return path.read_text()
        return ""

    # ---------- Stage 1: Parser ----------

    def parse(self, raw_ad_text: str) -> dict:
        """Extract structured data from raw ad text."""

        system_prompt = """You are an ad extraction system. Extract information from freelance job postings into structured JSON.

Rules:
- Copy text exactly where specified
- Answer Yes/No questions with true/false
- If information is not found, use null for strings/numbers, empty array [] for lists
- Output ONLY valid JSON, no other text"""

        schema = self._load_schema("ad_extraction_schema_v2.json")

        user_prompt = f"""Extract data from this job posting into JSON matching this schema:

{schema}

Job Posting:
---
{raw_ad_text}
---

Output only the JSON object:"""

        response, in_tok, out_tok = self.client.call(
            self.config.parser, system_prompt, user_prompt
        )
        self.telemetry.record("parser", in_tok, out_tok)

        # Parse JSON from response
        try:
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            return {"_parse_error": str(e), "_raw_response": response}

    # ---------- Stage 2: Assessor ----------

    def assess(self, extracted: dict) -> dict:
        """Evaluate feasibility and generate proposal + execution prompt."""

        system_prompt = self._load_schema("assessor_system_prompt.txt")
        user_template = self._load_schema("assessor_user_template.txt")

        user_prompt = user_template.replace(
            "{{EXTRACTED_AD_JSON}}",
            json.dumps(extracted, indent=2)
        )

        response, in_tok, out_tok = self.client.call(
            self.config.assessor, system_prompt, user_prompt
        )
        self.telemetry.record("assessor", in_tok, out_tok)

        # Parse the three sections
        result = {"_raw_response": response}

        # Extract ===ASSESSMENT===
        if "===ASSESSMENT===" in response:
            assessment_match = re.search(
                r"===ASSESSMENT===\s*(\{.*?\})\s*(?====|$)",
                response,
                re.DOTALL
            )
            if assessment_match:
                try:
                    result["assessment"] = json.loads(assessment_match.group(1))
                except json.JSONDecodeError:
                    pass

        # Extract ===PROPOSAL===
        if "===PROPOSAL===" in response:
            proposal_match = re.search(
                r"===PROPOSAL===\s*(.*?)\s*(?====|$)",
                response,
                re.DOTALL
            )
            if proposal_match:
                result["proposal"] = proposal_match.group(1).strip()

        # Extract ===EXECUTION_PROMPT===
        if "===EXECUTION_PROMPT===" in response:
            exec_match = re.search(
                r"===EXECUTION_PROMPT===\s*(.*?)$",
                response,
                re.DOTALL
            )
            if exec_match:
                result["execution_prompt"] = exec_match.group(1).strip()

        return result

    # ---------- Stage 3: Executor ----------

    def execute(self, execution_prompt: str, context: dict = None) -> dict:
        """Execute the task and produce deliverables."""

        context = context or {}

        system_prompt = """You are a task executor. You receive detailed task instructions and must:
1. Understand the requirements
2. Execute the task step by step
3. Produce the deliverables
4. Verify against success criteria

Output your work as structured sections:
===PLAN===
Your step-by-step plan

===EXECUTION===
Your execution work (code, analysis, etc.)

===DELIVERABLES===
List of files/outputs produced with descriptions

===VERIFICATION===
Check each success criterion"""

        user_prompt = f"""Execute this task:

{execution_prompt}

Additional context: {json.dumps(context)}

Begin execution:"""

        response, in_tok, out_tok = self.client.call(
            self.config.executor, system_prompt, user_prompt
        )
        self.telemetry.record("executor", in_tok, out_tok)

        return {
            "_raw_response": response,
            "execution_output": response,
        }

    # ---------- Full Pipeline ----------

    def run(self, raw_ad_text: str, ad_id: str = None) -> dict:
        """Run the full pipeline on a raw ad."""

        ad_id = ad_id or f"ad_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        started_at = datetime.now(timezone.utc)

        print(f"\n{'='*60}")
        print(f"Pipeline Run: {ad_id}")
        print(f"Started: {started_at.isoformat()}")
        print(f"{'='*60}")

        result = {
            "ad_id": ad_id,
            "started_at": started_at.isoformat(),
            "stages": {},
        }

        # Stage 1: Parse
        print("\n[1/3] PARSER: Extracting structured data...")
        extracted = self.parse(raw_ad_text)
        result["stages"]["parser"] = {"output": extracted}

        if "_parse_error" in extracted:
            print(f"  ERROR: {extracted['_parse_error']}")
            result["status"] = "failed_at_parser"
            return self._finalize(result, started_at)

        print(f"  Extracted: {extracted.get('title', 'Unknown')}")

        # Stage 2: Assess
        print("\n[2/3] ASSESSOR: Evaluating feasibility...")
        assessed = self.assess(extracted)
        result["stages"]["assessor"] = {"output": assessed}

        assessment = assessed.get("assessment", {})
        feasibility = assessment.get("feasibility", {}).get("score", 0)
        proceed = assessment.get("decision", {}).get("proceed", False)

        print(f"  Feasibility: {feasibility}")
        print(f"  Proceed: {proceed}")

        if not proceed:
            reason = assessment.get("decision", {}).get("reason", "Unknown")
            print(f"  Reason: {reason}")
            result["status"] = "rejected_by_assessor"
            return self._finalize(result, started_at)

        # Stage 3: Execute
        print("\n[3/3] EXECUTOR: Executing task...")
        execution_prompt = assessed.get("execution_prompt", "")

        if not execution_prompt:
            print("  ERROR: No execution prompt generated")
            result["status"] = "missing_execution_prompt"
            return self._finalize(result, started_at)

        executed = self.execute(execution_prompt)
        result["stages"]["executor"] = {"output": executed}
        result["status"] = "completed"

        # Store proposal for easy access
        if "proposal" in assessed:
            result["proposal"] = assessed["proposal"]

        return self._finalize(result, started_at)

    def _finalize(self, result: dict, started_at: datetime) -> dict:
        """Add telemetry and save results."""

        completed_at = datetime.now(timezone.utc)
        result["completed_at"] = completed_at.isoformat()
        result["wall_time_seconds"] = (completed_at - started_at).total_seconds()

        # Add telemetry
        stage_tiers = {
            "parser": self.config.parser.tier,
            "assessor": self.config.assessor.tier,
            "executor": self.config.executor.tier,
        }
        result["telemetry"] = self.telemetry.to_dict(
            self.config.cost_tiers, stage_tiers
        )

        # Print summary
        print(f"\n{'='*60}")
        print("PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Wall time: {result['wall_time_seconds']:.2f}s")

        tel = result["telemetry"]
        print(f"\nToken Usage:")
        for stage, data in tel["by_stage"].items():
            print(f"  {stage}: {data['total']:,} tokens (${data['cost_usd']:.4f})")
        print(f"  TOTAL: {tel['total']['total']:,} tokens (${tel['total']['cost_usd']:.4f})")

        # Save results
        if self.config.save_intermediate:
            self._save_results(result)

        return result

    def _save_results(self, result: dict):
        """Save pipeline results to disk."""

        ad_id = result["ad_id"]
        output_dir = self.config.output_dir / ad_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Full result
        with open(output_dir / "pipeline_result.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

        # Individual stage outputs
        for stage, data in result.get("stages", {}).items():
            stage_file = output_dir / f"{stage}_output.json"
            with open(stage_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

        # Proposal as markdown
        if "proposal" in result:
            with open(output_dir / "proposal.md", "w") as f:
                f.write(result["proposal"])

        print(f"\nResults saved to: {output_dir}")


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the freelancer automation pipeline"
    )
    parser.add_argument(
        "input",
        help="Path to raw ad text file, or '-' for stdin"
    )
    parser.add_argument(
        "--config", "-c",
        default="pipeline_config.json",
        help="Path to pipeline config (default: pipeline_config.json)"
    )
    parser.add_argument(
        "--ad-id",
        help="Custom ad ID (default: auto-generated)"
    )
    parser.add_argument(
        "--parser-model",
        help="Override parser model"
    )
    parser.add_argument(
        "--assessor-model",
        help="Override assessor model"
    )
    parser.add_argument(
        "--executor-model",
        help="Override executor model"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show config and exit without running"
    )

    args = parser.parse_args()

    # Load config
    config = PipelineConfig.from_file(args.config)

    # Apply CLI overrides
    if args.parser_model:
        config.parser.model = args.parser_model
    if args.assessor_model:
        config.assessor.model = args.assessor_model
    if args.executor_model:
        config.executor.model = args.executor_model

    if args.dry_run:
        print("Pipeline Configuration:")
        print(f"  Parser:   {config.parser.provider}/{config.parser.model}")
        print(f"  Assessor: {config.assessor.provider}/{config.assessor.model}")
        print(f"  Executor: {config.executor.provider}/{config.executor.model}")
        return

    # Read input
    if args.input == "-":
        raw_ad_text = sys.stdin.read()
    else:
        with open(args.input) as f:
            raw_ad_text = f.read()

    # Run pipeline
    pipeline = Pipeline(config)
    result = pipeline.run(raw_ad_text, args.ad_id)

    # Exit code based on status
    sys.exit(0 if result.get("status") == "completed" else 1)


if __name__ == "__main__":
    main()
