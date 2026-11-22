from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from artificial_labor import economics, stages
from artificial_labor.llm import LLM
from artificial_labor.models import JobRecord
from artificial_labor.stages import AdSource

log = logging.getLogger(__name__)


def discover(ads_dir: Path, only: list[str] | None = None) -> list[AdSource]:
    dirs = sorted(p for p in ads_dir.iterdir() if (p / "ad.md").is_file())
    if only:
        dirs = [d for d in dirs if any(o.lower() in d.name.lower() for o in only)]
    return [AdSource.load(d) for d in dirs]


def process(
    llm: LLM, ad: AdSource, job_dir: Path, *, execute: bool = True, force: bool = False
) -> JobRecord:
    """Run one ad through every stage, saving artifacts to `job_dir`."""
    s = llm.settings
    llm = llm.child()
    record = JobRecord(id=ad.id, url=(ad.source or {}).get("url"))
    job_dir.mkdir(parents=True, exist_ok=True)

    def save() -> JobRecord:
        record.usage = llm.usage.model_copy()
        (job_dir / "record.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    try:
        log.info("[%s] parsing", ad.id)
        record.job = job = stages.parse(llm, ad)

        log.info("[%s] assessing", ad.id)
        record.assessment = assessment = stages.assess(llm, ad, job)
        record.score = assessment.score
        record.economics = econ = economics.evaluate(job, assessment, s)
        record.decision = decision = economics.decide(job, assessment, econ, s)
        log.info(
            "[%s] score=%.2f margin=%s proceed=%s",
            ad.id,
            assessment.score,
            econ.margin,
            decision.proceed,
        )
        if not (decision.proceed or force):
            return save()

        log.info("[%s] writing proposal", ad.id)
        record.proposal = stages.propose(llm, job, assessment, econ)
        (job_dir / "proposal.md").write_text(record.proposal + "\n", encoding="utf-8")

        if not execute:
            return save()
        if assessment.needs_client_files and not ad.inputs:
            record.execution = stages.Execution(
                status="skipped", reason="Waiting for the client's files."
            )
            return save()

        log.info("[%s] executing", ad.id)
        workspace = job_dir / "workspace"
        record.execution = stages.execute(
            llm, ad, job, workspace, max_attempts=s.max_attempts, timeout=s.script_timeout
        )
        log.info(
            "[%s] execution %s after %d attempt(s)",
            ad.id,
            record.execution.status,
            record.execution.attempts,
        )
        if record.execution.status == "succeeded":
            log.info("[%s] verifying", ad.id)
            record.verification = stages.verify(llm, ad, job, workspace, timeout=s.script_timeout)
    except Exception as e:  # one bad ad must not kill the run
        log.exception("[%s] failed", ad.id)
        record.error = f"{type(e).__name__}: {e}"
    return save()


def run(
    llm: LLM,
    ads: list[AdSource],
    out_dir: Path,
    *,
    execute: bool = True,
    force: bool = False,
    workers: int = 1,
    on_done: Callable[[JobRecord], None] | None = None,
) -> list[JobRecord]:
    def one(ad: AdSource) -> JobRecord:
        rec = process(llm, ad, out_dir / "jobs" / ad.id, execute=execute, force=force)
        if on_done:
            on_done(rec)
        return rec

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, ads))
