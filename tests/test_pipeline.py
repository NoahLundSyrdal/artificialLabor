import json

from artificial_labor import pipeline, report
from artificial_labor.stages import AdSource
from tests.conftest import ASSESSMENT, GOOD_SCRIPT, JOB, VERIFICATION, last_text


def responder(script_replies):
    replies = iter(script_replies)

    def respond(messages, model):
        system, user = messages[0]["content"], last_text(messages)
        if "Extract structured data" in system:
            return json.dumps(JOB)
        if "business brain" in system:
            return json.dumps(ASSESSMENT)
        if "proposals" in system:
            return "## Understanding\nI will clean your CSV."
        if "QA reviewer" in system:
            assert "cleaned.csv" in user  # the reviewer sees the delivered file
            assert "PASS: @ prefix" in user  # ...and the automated check results
            return json.dumps(VERIFICATION)
        if "acceptance checks" in system:
            return "```python\nprint('PASS: @ prefix - all rows')\n```"
        if "Python 3 script" in system:
            return next(replies)
        raise AssertionError(f"unexpected prompt: {system[:80]}")

    return respond


def test_full_pipeline(make_llm, ad_dir, tmp_path):
    llm = make_llm(responder([GOOD_SCRIPT]))
    ads = pipeline.discover(ad_dir.parent)
    records = pipeline.run(llm, ads, tmp_path / "run")
    (r,) = records
    assert r.error is None
    assert r.decision.proceed
    assert r.execution.status == "succeeded"
    assert r.execution.outputs == ["outputs/cleaned.csv"]
    assert r.verification.passed
    assert r.verification.automated_checks == "PASS: @ prefix - all rows"
    assert r.usage.calls == 6 and llm.usage.calls == 6

    job_dir = tmp_path / "run" / "jobs" / "01-csv-prefix"
    out = (job_dir / "workspace" / "outputs" / "cleaned.csv").read_text().splitlines()
    assert out == ["handle,n", "@b,1", "@aa,2"]
    assert (job_dir / "proposal.md").exists()
    assert json.loads((job_dir / "record.json").read_text())["id"] == "01-csv-prefix"

    path = report.write(tmp_path / "run", records, llm.usage, "fake")
    assert "delivered" in path.read_text()


def test_execution_retries_after_failure(make_llm, ad_dir, tmp_path):
    llm = make_llm(responder(["```python\nraise RuntimeError('oops')\n```", GOOD_SCRIPT]))
    (r,) = pipeline.run(llm, pipeline.discover(ad_dir.parent), tmp_path / "run")
    assert r.execution.status == "succeeded" and r.execution.attempts == 2
    # The traceback was fed back to the model on the second attempt.
    code_requests = [m for model, m in llm.backend.requests if model == "codestral-latest"]
    assert "oops" in code_requests[1][-1]["content"]


def test_skips_execution_when_client_files_missing(make_llm, ad_dir, tmp_path):
    for f in (ad_dir / "inputs").iterdir():
        f.unlink()
    llm = make_llm(responder([]))
    (r,) = pipeline.run(llm, [AdSource.load(ad_dir)], tmp_path / "run")
    assert r.execution.status == "skipped"
    assert r.proposal


def test_errors_are_recorded_not_raised(make_llm, ad_dir, tmp_path):
    def broken(messages, model):
        raise ConnectionError("api down")

    (r,) = pipeline.run(make_llm(broken), [AdSource.load(ad_dir)], tmp_path / "run")
    assert r.error == "ConnectionError: api down"
