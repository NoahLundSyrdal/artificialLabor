import json
import time

from artificial_labor import cli, freelancer, report
from artificial_labor.llm import Usage
from artificial_labor.models import Decision, Economics, Job, JobRecord
from artificial_labor.stages import AdSource

PROJECT = {
    "id": 123,
    "title": "Clean my CSV / Excel file!",
    "seo_url": "excel/Clean-CSV",
    "status": "active",
    "type": "fixed",
    "budget": {"minimum": 10.0, "maximum": 30.0},
    "currency": {"code": "USD"},
    "bid_stats": {"bid_count": 4, "bid_avg": 22.5},
    "jobs": [{"name": "Excel"}, {"name": "Data Entry"}],
    "description": "Prefix column A with @ and remove duplicates.",
}


def fake_fetch(calls):
    def fetch(url):
        calls.append(url)
        return {"status": "success", "result": {"projects": [PROJECT]}}

    return fetch


def test_search_builds_query():
    calls = []
    (p,) = freelancer.search(
        "excel csv", limit=5, project_type="fixed", min_budget=20, fetch=fake_fetch(calls)
    )
    assert p["id"] == 123
    assert "query=excel+csv" in calls[0] and "limit=5" in calls[0]
    assert "project_types%5B%5D=fixed" in calls[0] and "min_price=20" in calls[0]


def test_to_markdown():
    md = freelancer.to_markdown(PROJECT)
    assert md.startswith("# Clean my CSV / Excel file!")
    assert "Budget: 10-30 USD (fixed price)" in md
    assert "Skills: Excel, Data Entry" in md
    assert "Listing: https://www.freelancer.com/projects/excel/Clean-CSV" in md
    assert "Prefix column A" in md


def test_save_skips_known_ids_and_prune(tmp_path):
    (d,) = freelancer.save([PROJECT], tmp_path)
    assert d.name == "fl-123-clean-my-csv-excel-file"
    assert freelancer.save([PROJECT], tmp_path) == []
    ad = AdSource.load(d)
    assert ad.source["url"].endswith("excel/Clean-CSV") and not ad.inputs

    assert freelancer.prune(tmp_path, 24) == 0
    src = json.loads((d / "source.json").read_text())
    src["fetched_at"] = int(time.time()) - 25 * 3600
    (d / "source.json").write_text(json.dumps(src))
    assert freelancer.prune(tmp_path, 24) == 1 and not d.exists()


def test_cli_fetch_without_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(freelancer, "_get_json", fake_fetch([]))
    assert cli.main(["fetch", "csv", "--out", str(tmp_path)]) == 0
    assert "1 new" in capsys.readouterr().out
    assert (tmp_path / "fl-123-clean-my-csv-excel-file" / "ad.md").exists()


def test_report_lists_review_queue():
    job = Job.model_validate(
        {"title": "CSV", "status": "open", "pricing": "fixed", "summary": "s", "deliverables": []}
    )
    econ = Economics(
        budget_low_usd=10,
        budget_high_usd=30,
        revenue_usd=10,
        cost_usd=0.01,
        margin=0.99,
        bid_usd=20,
        bid_local="20 USD",
        viable=True,
    )
    rec = JobRecord(
        id="fl-1-csv",
        url="https://www.freelancer.com/projects/x",
        job=job,
        economics=econ,
        decision=Decision(proceed=True),
        proposal="Hi",
    )
    text = report.render([rec], Usage(), "fake")
    assert "## Review queue" in text
    assert "[listing](https://www.freelancer.com/projects/x)" in text
    assert "[proposal](jobs/fl-1-csv/proposal.md)" in text
