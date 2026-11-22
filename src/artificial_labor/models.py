from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from artificial_labor.llm import Usage

Unit = Field(ge=0.0, le=1.0)


class Job(BaseModel):
    """Structured view of a freelance ad."""

    title: str
    status: Literal["open", "awarded", "unknown"] = "unknown"
    pricing: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = Field(None, description="Lowest budget/rate number in the ad")
    budget_max: float | None = Field(None, description="Highest budget/rate number in the ad")
    currency: str | None = Field(None, description="ISO code, e.g. USD, INR, GBP")
    summary: str = Field(description="2-4 sentence summary of what the client wants")
    requirements: list[str] = []
    deliverables: list[str] = []
    client_provides: list[str] = Field(
        default_factory=list, description="Files or access the client says they will supply"
    )
    recurring: bool = Field(False, description="Ongoing/daily work rather than a one-off job")


class Factors(BaseModel):
    task_clarity: float = Unit
    output_determinism: float = Unit
    tool_availability: float = Unit
    verification_ease: float = Unit
    scope_boundedness: float = Unit


FACTOR_WEIGHTS = {
    "task_clarity": 0.20,
    "output_determinism": 0.25,
    "tool_availability": 0.20,
    "verification_ease": 0.20,
    "scope_boundedness": 0.15,
}


class Assessment(BaseModel):
    factors: Factors
    blockers: list[str] = Field(
        default_factory=list,
        description="Hard reasons an autonomous agent with Python cannot deliver this "
        "(needs physical/visual input it cannot get, account access, live calls, "
        "ongoing human presence, ...). Missing client files are not a blocker (use "
        "needs_client_files). Empty if none.",
    )
    risks: list[str] = []
    needs_client_files: bool = Field(
        description="True if the work cannot start until the client sends files/data"
    )
    estimated_human_hours: float = Field(
        ge=0, description="Hours a competent freelancer would bill for this"
    )
    estimated_llm_tokens: int = Field(
        ge=0, description="Total LLM tokens (in+out) an agent would spend, including retries"
    )
    reasoning: str

    @property
    def score(self) -> float:
        f = self.factors.model_dump()
        return round(sum(f[k] * w for k, w in FACTOR_WEIGHTS.items()), 3)


class Economics(BaseModel):
    budget_low_usd: float | None
    budget_high_usd: float | None
    revenue_usd: float | None
    cost_usd: float
    margin: float | None
    bid_usd: float | None
    bid_local: str | None
    viable: bool
    note: str = ""


class Decision(BaseModel):
    proceed: bool
    reasons: list[str] = []


class Check(BaseModel):
    criterion: str
    passed: bool
    notes: str = ""


class Verification(BaseModel):
    passed: bool
    score: float = Unit
    checks: list[Check] = []
    summary: str
    automated_checks: str = ""


class Execution(BaseModel):
    status: Literal["succeeded", "failed", "skipped"]
    reason: str = ""
    attempts: int = 0
    outputs: list[str] = []
    script: str | None = None
    stdout_tail: str = ""
    error: str | None = None
    seconds: float = 0.0


class JobRecord(BaseModel):
    id: str
    url: str | None = None
    job: Job | None = None
    assessment: Assessment | None = None
    score: float | None = None
    economics: Economics | None = None
    decision: Decision | None = None
    proposal: str | None = None
    synthetic_inputs: list[str] = Field(
        default_factory=list, description="Sample input files generated in place of the client's"
    )
    execution: Execution | None = None
    verification: Verification | None = None
    qa_history: list[float] = Field(
        default_factory=list, description="QA score after the first delivery and each fix round"
    )
    usage: Usage = Field(default_factory=Usage)
    error: str | None = None
