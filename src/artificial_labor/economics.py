from __future__ import annotations

from artificial_labor.config import USD_PER_UNIT, Settings
from artificial_labor.models import Assessment, Decision, Economics, Job


def to_usd(amount: float | None, currency: str | None) -> float | None:
    if amount is None or not currency:
        return None
    rate = USD_PER_UNIT.get(currency.upper())
    return None if rate is None else amount * rate


def blended_token_price(settings: Settings) -> float:
    """USD per token for the code model, assuming ~3 input tokens per output token."""
    price_in, price_out = settings.price(settings.code_model)
    return (3 * price_in + price_out) / 4 / 1_000_000


def evaluate(job: Job, assessment: Assessment, settings: Settings) -> Economics:
    cost = assessment.estimated_llm_tokens * blended_token_price(settings) * settings.cost_overhead
    low = to_usd(job.budget_min if job.budget_min is not None else job.budget_max, job.currency)
    high = to_usd(job.budget_max if job.budget_max is not None else job.budget_min, job.currency)
    if low is None or high is None:
        return Economics(
            budget_low_usd=low,
            budget_high_usd=high,
            revenue_usd=None,
            cost_usd=round(cost, 4),
            margin=None,
            bid_usd=None,
            bid_local=None,
            viable=False,
            note="No usable budget in the ad (or unknown currency).",
        )

    hours = max(assessment.estimated_human_hours, 0.5)
    multiplier = hours if job.pricing == "hourly" else 1.0
    revenue = low * multiplier
    lo_local = job.budget_min if job.budget_min is not None else job.budget_max
    hi_local = job.budget_max if job.budget_max is not None else job.budget_min
    bid_local_amount = round((lo_local + hi_local) / 2, 2)
    bid_usd = (low + high) / 2 * multiplier
    margin = (revenue - cost) / revenue if revenue > 0 else None
    unit = f"{job.currency}/hour x ~{hours:g}h" if job.pricing == "hourly" else job.currency
    return Economics(
        budget_low_usd=round(low, 2),
        budget_high_usd=round(high, 2),
        revenue_usd=round(revenue, 2),
        cost_usd=round(cost, 4),
        margin=None if margin is None else round(margin, 4),
        bid_usd=round(bid_usd, 2),
        bid_local=f"{bid_local_amount:g} {unit}",
        viable=margin is not None and margin >= settings.min_margin,
    )


def decide(job: Job, assessment: Assessment, econ: Economics, settings: Settings) -> Decision:
    reasons = []
    if job.status == "awarded":
        reasons.append("Job is already awarded.")
    if assessment.score < settings.min_feasibility:
        reasons.append(
            f"Feasibility {assessment.score:.2f} is below threshold {settings.min_feasibility:.2f}."
        )
    reasons += [f"Blocker: {b}" for b in assessment.blockers]
    if not econ.viable:
        reasons.append(econ.note or f"Margin below {settings.min_margin:.0%}.")
    return Decision(proceed=not reasons, reasons=reasons or ["Feasible and profitable."])
