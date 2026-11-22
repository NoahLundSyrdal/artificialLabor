import pytest

from artificial_labor import economics
from artificial_labor.models import Assessment, Job
from tests.conftest import ASSESSMENT, JOB


def make(job_overrides=None, assessment_overrides=None):
    return (
        Job.model_validate({**JOB, **(job_overrides or {})}),
        Assessment.model_validate({**ASSESSMENT, **(assessment_overrides or {})}),
    )


def test_score_is_weighted_average():
    _, a = make()
    assert a.score == pytest.approx(0.2 * 0.9 + 0.25 * 0.9 + 0.2 * 1 + 0.2 * 0.9 + 0.15 * 1)


def test_fixed_price_economics(settings):
    job, a = make()
    e = economics.evaluate(job, a, settings)
    assert e.revenue_usd == 10
    assert e.bid_usd == 20
    assert e.bid_local == "20 USD"
    assert e.viable and e.margin > 0.9


def test_hourly_converts_currency_and_multiplies_hours(settings):
    job, a = make(
        {"pricing": "hourly", "budget_min": 100, "budget_max": 400, "currency": "INR"},
        {"estimated_human_hours": 3},
    )
    e = economics.evaluate(job, a, settings)
    assert e.revenue_usd == pytest.approx(100 * 0.012 * 3)
    assert "INR/hour" in e.bid_local


def test_missing_budget_is_not_viable(settings):
    job, a = make({"budget_min": None, "budget_max": None})
    e = economics.evaluate(job, a, settings)
    assert not e.viable and e.revenue_usd is None


def test_decision_reasons(settings):
    job, a = make({"status": "awarded"}, {"blockers": ["needs Google account access"]})
    d = economics.decide(job, a, economics.evaluate(job, a, settings), settings)
    assert not d.proceed
    assert any("awarded" in r for r in d.reasons)
    assert any("Google" in r for r in d.reasons)


def test_unprofitable_job_is_rejected(settings):
    job, a = make({"budget_min": 0.01, "budget_max": 0.02}, {"estimated_llm_tokens": 10**6})
    e = economics.evaluate(job, a, settings)
    assert not e.viable
    assert not economics.decide(job, a, e, settings).proceed
