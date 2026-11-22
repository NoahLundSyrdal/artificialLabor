from __future__ import annotations

import json
from pathlib import Path

from artificial_labor.llm import Usage
from artificial_labor.models import JobRecord


def _money(v: float | None, digits: int = 2) -> str:
    return "-" if v is None else f"${v:,.{digits}f}"


def _status(r: JobRecord) -> str:
    if r.error:
        return "error"
    if not r.decision:
        return "-"
    if not r.decision.proceed and not r.proposal:
        return "no bid"
    if r.execution is None:
        return "proposal only"
    if r.execution.status != "succeeded":
        return f"execution {r.execution.status}"
    if r.verification is None:
        return "executed"
    return "delivered" if r.verification.passed else "QA failed"


def render(records: list[JobRecord], total: Usage, settings_desc: str) -> str:
    lines = [
        "# Artificial Labor run report",
        "",
        f"Models: {settings_desc}  ",
        f"LLM usage: {total.calls} calls, {total.total_tokens:,} tokens, "
        f"{_money(total.cost_usd, 4)}",
        "",
        "| Job | Feasibility | Revenue | Est. cost | Margin | Outcome | QA | Actual cost |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        e = r.economics
        title = r.job.title if r.job else r.id
        margin = "-" if not e or e.margin is None else f"{e.margin:.1%}"
        qa = f"{r.verification.score:.2f}" if r.verification else "-"
        lines.append(
            f"| [{title}](jobs/{r.id}/) | {'-' if r.score is None else f'{r.score:.2f}'} "
            f"| {_money(e.revenue_usd if e else None)} | {_money(e.cost_usd if e else None, 4)} "
            f"| {margin} | {_status(r)} | {qa} | {_money(r.usage.cost_usd, 4)} |"
        )
    queue = [r for r in records if r.proposal and not r.error]
    if queue:
        lines += [
            "",
            "## Review queue",
            "",
            "Nothing has been sent. Read the proposal (and deliverables, if any) before bidding.",
            "",
        ]
        for r in queue:
            title = r.job.title if r.job else r.id
            bid = r.economics.bid_local if r.economics and r.economics.bid_local else "-"
            listing = f" - [listing]({r.url})" if r.url else ""
            lines.append(
                f"- **{title}**: bid {bid}, {_status(r)}{listing} - "
                f"[proposal](jobs/{r.id}/proposal.md)"
            )
    lines += ["", "## Details", ""]
    for r in records:
        lines.append(f"### {r.job.title if r.job else r.id}")
        if r.url:
            lines.append(f"- Listing: {r.url}")
        if r.error:
            lines.append(f"- Error: `{r.error}`")
        if r.decision:
            lines.append(f"- Decision: {'; '.join(r.decision.reasons)}")
        if r.assessment:
            lines.append(f"- Assessment: {r.assessment.reasoning}")
        if r.economics and r.economics.bid_local:
            lines.append(f"- Bid: {r.economics.bid_local} (~{_money(r.economics.bid_usd)})")
        if r.execution:
            x = r.execution
            lines.append(
                f"- Execution: {x.status} ({x.attempts} attempt(s), {x.seconds}s) {x.reason}"
            )
            if x.outputs:
                lines.append(f"- Outputs: {', '.join(f'`{o}`' for o in x.outputs)}")
        if r.verification:
            v = r.verification
            lines.append(f"- QA: {'pass' if v.passed else 'fail'} ({v.score:.2f}) - {v.summary}")
            auto = v.automated_checks.splitlines()
            passes = sum(line.startswith("PASS") for line in auto)
            fails = sum(line.startswith("FAIL") for line in auto)
            if passes or fails:
                lines.append(f"- Automated checks (`checks.py`): {passes} passed, {fails} failed")
            lines += [
                f"  - [{'x' if c.passed else ' '}] {c.criterion}"
                + (f" - {c.notes}" if c.notes else "")
                for c in v.checks
            ]
        lines.append("")
    return "\n".join(lines)


def write(out_dir: Path, records: list[JobRecord], total: Usage, settings_desc: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(
            {"usage": total.model_dump(), "jobs": [r.model_dump(mode="json") for r in records]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path = out_dir / "report.md"
    path.write_text(render(records, total, settings_desc), encoding="utf-8")
    return path
