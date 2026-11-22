import json

from artificial_labor import pipeline, report
from artificial_labor.stages import AdSource
from tests.conftest import ASSESSMENT, GOOD_SCRIPT, JOB, VERIFICATION, last_text


def responder(script_replies, verifications=None):
    replies = iter(script_replies)
    qa = iter(verifications or [])

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
            return json.dumps(next(qa, VERIFICATION))
        if "acceptance checks" in system:
            return "```python\nprint('PASS: @ prefix - all rows')\n```"
        if "Python 3 script" in system:
            return next(replies)
        if "synthetic sample data" in system:
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


SAMPLE_SCRIPT = """```python
import os
os.makedirs("inputs", exist_ok=True)
open("inputs/data.csv", "w").write("handle,n\\nb,1\\naa,2\\nb,1\\n")
```"""


def test_generates_sample_inputs_when_client_files_missing(make_llm, ad_dir, tmp_path):
    for f in (ad_dir / "inputs").iterdir():
        f.unlink()
    llm = make_llm(responder(["```python\nprint('no files')\n```", SAMPLE_SCRIPT, GOOD_SCRIPT]))
    (r,) = pipeline.run(llm, [AdSource.load(ad_dir)], tmp_path / "run")
    assert r.error is None
    assert r.synthetic_inputs == ["data.csv"]
    assert r.execution.status == "succeeded" and r.verification.passed
    executor_prompt = next(
        m for _, m in llm.backend.requests if "Python 3 script" in m[0]["content"]
    )[1]["content"]
    assert "SYNTHETIC" in executor_prompt and "handle,n" in executor_prompt
    job_dir = tmp_path / "run" / "jobs" / "01-csv-prefix"
    out = (job_dir / "workspace" / "outputs" / "cleaned.csv").read_text().splitlines()
    assert out == ["handle,n", "@b,1", "@aa,2"]
    assert "delivered (sample data)" in report.render([r], llm.usage, "fake")


def test_skips_execution_when_client_files_missing(make_llm, ad_dir, tmp_path):
    for f in (ad_dir / "inputs").iterdir():
        f.unlink()
    llm = make_llm(responder([]))
    llm.settings.synthetic_inputs = False
    (r,) = pipeline.run(llm, [AdSource.load(ad_dir)], tmp_path / "run")
    assert r.execution.status == "skipped"
    assert r.proposal


def test_errors_are_recorded_not_raised(make_llm, ad_dir, tmp_path):
    def broken(messages, model):
        raise ConnectionError("api down")

    (r,) = pipeline.run(make_llm(broken), [AdSource.load(ad_dir)], tmp_path / "run")
    assert r.error == "ConnectionError: api down"


FAIL = {"passed": False, "score": 0.5, "checks": [{"criterion": "sorted", "passed": False,
        "notes": "not sorted by length"}], "summary": "unsorted"}  # fmt: skip
BAD_SCRIPT = """```python
import os
os.makedirs("outputs", exist_ok=True)
open("outputs/cleaned.csv", "w").write("x")
```"""


def test_failed_qa_gets_a_fix_round(make_llm, ad_dir, tmp_path):
    llm = make_llm(responder([GOOD_SCRIPT, GOOD_SCRIPT], [FAIL, VERIFICATION]))
    (r,) = pipeline.run(llm, pipeline.discover(ad_dir.parent), tmp_path / "run")
    assert r.verification.passed and r.qa_history == [0.5, 1.0]
    fix_prompt = [m for _, m in llm.backend.requests if "Python 3 script" in m[0]["content"]][1]
    assert "not sorted by length" in fix_prompt[1]["content"]
    assert "Fix rounds: 1 (QA scores 0.50 -> 1.00)" in report.render([r], llm.usage, "fake")


def test_worse_fix_is_reverted(make_llm, ad_dir, tmp_path):
    worse = {**FAIL, "score": 0.2}
    llm = make_llm(responder([GOOD_SCRIPT, BAD_SCRIPT], [FAIL, worse]))
    (r,) = pipeline.run(llm, pipeline.discover(ad_dir.parent), tmp_path / "run")
    assert r.verification.score == 0.5 and r.qa_history == [0.5, 0.5]
    outputs = tmp_path / "run" / "jobs" / "01-csv-prefix" / "workspace" / "outputs"
    assert (outputs / "cleaned.csv").read_text().splitlines() == ["handle,n", "@b,1", "@aa,2"]
