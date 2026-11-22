"""The LLM-backed pipeline stages: parse -> assess -> propose -> execute -> verify."""

from __future__ import annotations

import base64
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from importlib.util import find_spec
from pathlib import Path

from artificial_labor.files import describe, list_files
from artificial_labor.llm import LLM, extract_code
from artificial_labor.models import Assessment, Economics, Execution, Job, Verification
from artificial_labor.sandbox import RunResult, run_python


@dataclass
class AdSource:
    """One ad on disk: `<dir>/ad.md`, optional `brief.json`, optional `inputs/`."""

    id: str
    dir: Path
    text: str
    brief: dict | None
    inputs: list[Path]
    source: dict | None = None
    synthetic: bool = False

    @classmethod
    def load(cls, path: Path) -> AdSource:
        brief_path = path / "brief.json"
        source_path = path / "source.json"
        return cls(
            id=path.name,
            dir=path,
            text=(path / "ad.md").read_text(encoding="utf-8"),
            brief=json.loads(brief_path.read_text()) if brief_path.exists() else None,
            inputs=list_files(path / "inputs"),
            source=json.loads(source_path.read_text()) if source_path.exists() else None,
        )

    def context(self) -> str:
        """Everything the client has given us besides the ad itself."""
        parts = []
        if self.brief:
            parts.append(
                "Additional details from the client (brief.json):\n" + json.dumps(self.brief)
            )
        names = [str(p.relative_to(self.dir / "inputs")) for p in self.inputs]
        if self.synthetic:
            parts.append(
                "The client has not sent their files yet. ./inputs/ holds SYNTHETIC sample "
                f"files generated from the ad as stand-ins: {names}. Build the deliverable so it "
                "works unchanged on the client's real files; judge it against the sample data."
            )
        else:
            parts.append(f"Files provided by the client: {names or 'none'}")
        return "\n\n".join(parts)


SYSTEM_ANALYST = (
    "You are the business brain of an autonomous freelancing agent. The agent is an LLM that "
    "can write and run Python scripts with common data libraries (pandas, openpyxl, matplotlib, "
    "python-docx, pdfplumber, reportlab, sqlite3). It cannot browse interactively, see images "
    "unless they are provided, log into client accounts, attend calls, or be present daily. "
    "Missing client files are not a blocker: the agent builds and demonstrates the work on "
    "realistic sample data first, then reruns it on the real files. Be calibrated and skeptical."
)


def parse(llm: LLM, ad: AdSource) -> Job:
    return llm.complete_model(
        [
            {
                "role": "system",
                "content": "Extract structured data from freelance job ads. Copy facts; do not "
                "invent them. Use null when a value is not in the ad.",
            },
            {"role": "user", "content": f"Job ad:\n---\n{ad.text}\n---"},
        ],
        Job,
        temperature=0.0,
    )


def assess(llm: LLM, ad: AdSource, job: Job) -> Assessment:
    return llm.complete_model(
        [
            {"role": "system", "content": SYSTEM_ANALYST},
            {
                "role": "user",
                "content": "Assess whether the agent can deliver this job end-to-end with "
                "acceptable quality. Score each factor from 0 to 1 (1 = clear, deterministic, "
                "standard tools, programmatically verifiable, fixed scope). Be calibrated: 1.0 "
                "means there is nothing left to interpret; most real ads score 0.4-0.9.\n"
                "For estimated_llm_tokens, count the agent's real work: one execution round "
                "trip (the full ad, file previews and a complete script) is ~5k-15k tokens, "
                "plus retries and QA. Large multi-file deliverables cost far more.\n\n"
                f"Job:\n{job.model_dump_json(indent=2)}\n\n{ad.context()}",
            },
        ],
        Assessment,
        temperature=0.0,
    )


def propose(llm: LLM, job: Job, assessment: Assessment, econ: Economics) -> str:
    return llm.complete(
        [
            {
                "role": "system",
                "content": "You write short, specific freelance proposals in Markdown. No "
                "fluff, no fake credentials, no placeholders like [Your Name].",
            },
            {
                "role": "user",
                "content": f"Write a proposal for this job.\n\nJob:\n{job.model_dump_json()}\n\n"
                f"Our bid: {econ.bid_local}. Estimated effort: "
                f"{assessment.estimated_human_hours:g} hours. Known risks: {assessment.risks}\n\n"
                "Sections: Understanding, Approach (bullets), Deliverables, Timeline, Price, "
                "Questions for the client (only if genuinely needed). Under 250 words.",
            },
        ],
        temperature=0.5,
        max_tokens=1200,
    ).strip()


_CANDIDATE_LIBS = [
    "pandas", "numpy", "matplotlib", "openpyxl", "xlsxwriter", "docx", "pdfplumber", "pypdf",
    "reportlab", "bs4", "requests",
]  # fmt: skip


def available_libraries() -> list[str]:
    return ["python stdlib (csv, json, sqlite3, ...)"] + [
        lib for lib in _CANDIDATE_LIBS if find_spec(lib) is not None
    ]


EXECUTOR_RULES = """Rules for the script:
- Read client files from ./inputs/ and write every deliverable into ./outputs/ (create it).
- Use only these libraries: {libs}. No network access, no user input, no GUI.
- Produce real, finished deliverables in the formats the client asked for (e.g. .xlsx, .docx,
  .png, .sql, .html). Use formulas, validation and formatting where the client expects them.
- Do not fabricate client data. If something is ambiguous, make a reasonable assumption.
- Also write ./outputs/NOTES.md: what was delivered, assumptions made, how to use it.
- Check your own work with assertions where possible (row counts, totals, file exists).
- Print a short summary at the end. Exit non-zero on failure.
Reply with one complete Python script in a single ```python code block."""


def _write_and_run(
    llm: LLM,
    messages: list[dict],
    script_path: Path,
    out_dir: Path,
    *,
    produced: Callable[[], bool],
    max_attempts: int,
    timeout: int,
) -> tuple[int, RunResult | None, bool]:
    """Ask for a script, run it in `script_path.parent`, feed errors back; retry until ok."""
    cwd = script_path.parent
    result = None
    for attempt in range(1, max_attempts + 1):
        reply = llm.complete(messages, code=True, temperature=0.2, max_tokens=12000)
        script_path.write_text(extract_code(reply), encoding="utf-8")
        # Each attempt starts from a clean output dir.
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
        result = run_python(script_path, cwd=cwd, timeout=timeout)
        if result.ok and produced():
            return attempt, result, True
        problem = (
            f"The script failed (exit code {result.returncode}"
            f"{', timed out' if result.timed_out else ''}).\nstderr:\n{result.stderr[-4000:]}"
            if not result.ok
            else f"The script exited cleanly but wrote no files to ./{out_dir.name}/."
        )
        if "ModuleNotFoundError" in result.stderr:
            problem += (
                "\nThat module is not installed and cannot be installed. Use only: "
                f"{', '.join(available_libraries())}."
            )
        messages += [
            {"role": "assistant", "content": reply},
            {
                "role": "user",
                "content": f"{problem}\nstdout:\n{result.stdout[-1500:]}\n\nFix the problem and "
                "reply with the complete corrected script.",
            },
        ]
    return max_attempts, result, False


SYNTH_RULES = """Write one Python 3 program that creates realistic SYNTHETIC stand-ins for the
files the client will send, in ./inputs/ (create it).
- Create only the files this client says they will send (usually 1-3), in the format and
  structure the ad describes or implies. Don't add other formats "just in case".
- Use plausible names, dates and amounts from hand-written lists and `random` (seeded);
  never real people's data. Check list lengths match before building tables.
- Include the messiness the job is about (duplicates, inconsistent formats, blanks, typos), so
  the solution is actually exercised. Keep it small: at most a few hundred rows per file.
- Do NOT produce the deliverables themselves, only the client's input files.
- Use only these libraries: {libs}. No network access, no user input.
- Print the files created. Exit non-zero on failure.
Reply with the complete program in a single ```python code block."""


def synthesize(
    llm: LLM, ad: AdSource, job: Job, dest: Path, *, max_attempts: int, timeout: int
) -> AdSource | None:
    """Generate sample client files under `dest/inputs/`; returns the ad pointing at them."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    messages = [
        {
            "role": "system",
            "content": "You generate realistic synthetic sample data files for software "
            "demos by writing a single Python program.",
        },
        {
            "role": "user",
            "content": f"Job:\n{job.model_dump_json(indent=2)}\n\nOriginal ad:\n---\n{ad.text}\n"
            f"---\n\nThe client will provide: {job.client_provides or 'see the ad'}\n\n"
            + SYNTH_RULES.format(libs=", ".join(available_libraries())),
        },
    ]
    _, _, ok = _write_and_run(
        llm,
        messages,
        dest / "make_inputs.py",
        dest / "inputs",
        produced=lambda: bool(list_files(dest / "inputs")),
        max_attempts=max_attempts,
        timeout=timeout,
    )
    if not ok:
        return None
    return replace(ad, dir=dest, inputs=list_files(dest / "inputs"), synthetic=True)


def execute(
    llm: LLM,
    ad: AdSource,
    job: Job,
    workspace: Path,
    *,
    max_attempts: int,
    timeout: int,
) -> Execution:
    started = time.monotonic()
    if workspace.exists():
        shutil.rmtree(workspace)
    (workspace / "inputs").mkdir(parents=True)
    (workspace / "outputs").mkdir()
    for f in ad.inputs:
        dest = workspace / "inputs" / f.relative_to(ad.dir / "inputs")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    messages = [
        {
            "role": "system",
            "content": "You are a senior freelancer who completes jobs by writing a single, "
            "self-contained Python 3 script that produces the deliverables.",
        },
        {
            "role": "user",
            "content": f"Job:\n{job.model_dump_json(indent=2)}\n\nOriginal ad:\n---\n{ad.text}\n"
            f"---\n\n{ad.context()}\n\nContents of ./inputs/:\n"
            f"{describe(list_files(workspace / 'inputs'), workspace / 'inputs')}\n\n"
            + EXECUTOR_RULES.format(libs=", ".join(available_libraries())),
        },
    ]
    script_path = workspace / "solution.py"
    attempts, result, ok = _write_and_run(
        llm,
        messages,
        script_path,
        workspace / "outputs",
        produced=lambda: bool(deliverables(workspace)),
        max_attempts=max_attempts,
        timeout=timeout,
    )
    return Execution(
        status="succeeded" if ok else "failed",
        attempts=attempts,
        outputs=[str(p.relative_to(workspace)) for p in list_files(workspace / "outputs")],
        script=str(script_path),
        stdout_tail=result.stdout[-2000:] if result else "",
        error=None if ok else (result and result.stderr[-2000:]) or "No deliverables produced.",
        seconds=round(time.monotonic() - started, 1),
    )


IMAGE_SUFFIXES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _image_part(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    mime = IMAGE_SUFFIXES[path.suffix.lower()]
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


CHECKS_RULES = """Write a Python 3 script that checks the delivery against every deliverable and
acceptance criterion: counts, sort orders, totals, formats, required sheets/columns/formulas,
values traced back to the inputs. Only ./inputs/ and ./outputs/ exist (the job details above
are not files); read them, never modify them.
Libraries: {libs}. For each criterion print exactly one line: `PASS: <criterion> - <evidence>` or
`FAIL: <criterion> - <evidence>`. Catch exceptions per check so one failure doesn't stop the rest.
Reply with one complete Python script in a single ```python code block."""


def automated_checks(llm: LLM, ad: AdSource, job: Job, workspace: Path, *, timeout: int) -> str:
    """Have the code model write acceptance checks and run them; returns their output."""
    outputs = deliverables(workspace)
    reply = llm.complete(
        [
            {
                "role": "system",
                "content": "You write automated acceptance checks for freelance deliveries.",
            },
            {
                "role": "user",
                "content": f"Job:\n{job.model_dump_json(indent=2)}\n\n{ad.context()}\n\n"
                f"Client input files:\n"
                f"{describe(list_files(workspace / 'inputs'), workspace / 'inputs', 1500)}\n\n"
                f"Delivered files:\n{describe(outputs, workspace / 'outputs', 1500)}\n\n"
                + CHECKS_RULES.format(libs=", ".join(available_libraries())),
            },
        ],
        code=True,
        temperature=0.0,
        max_tokens=6000,
    )
    script = workspace / "checks.py"
    script.write_text(extract_code(reply), encoding="utf-8")
    result = run_python(script, cwd=workspace, timeout=timeout)
    out = result.stdout[-6000:]
    if not result.ok:
        out += f"\n[checks.py exited with {result.returncode}]\n{result.stderr[-1500:]}"
    return out.strip()


def deliverables(workspace: Path) -> list[Path]:
    return [p for p in list_files(workspace / "outputs") if p.name != "NOTES.md"]


def verify(
    llm: LLM, ad: AdSource, job: Job, workspace: Path, *, timeout: int = 120, max_images: int = 4
) -> Verification:
    checks = automated_checks(llm, ad, job, workspace, timeout=timeout)
    outputs = list_files(workspace / "outputs")
    script = workspace / "solution.py"
    images = [p for p in outputs if p.suffix.lower() in IMAGE_SUFFIXES][:max_images]
    text = (
        f"Job:\n{job.model_dump_json(indent=2)}\n\n{ad.context()}\n\n"
        f"Client input files (previews):\n"
        f"{describe(list_files(workspace / 'inputs'), workspace / 'inputs', 4000)}\n\n"
        f"Script that produced the delivery:\n```python\n"
        f"{script.read_text() if script.exists() else ''}\n```\n\n"
        f"Delivered files (previews):\n{describe(outputs, workspace / 'outputs', 3000)}\n\n"
        + (f"The {len(images)} image deliverable(s) are attached.\n\n" if images else "")
        + f"Output of automated checks run on the delivered files (checks.py):\n{checks}\n\n"
        "NOTES.md is the freelancer's handover note: it is allowed and is not a deliverable.\n"
        "The automated checks executed real code against the files, so trust them for counts, "
        "orderings and values over your own reading of previews, unless the check itself is "
        "clearly wrong. "
        + "Check every requested deliverable and every acceptance/verification criterion "
        "against the evidence. Previews are truncated: do not treat data missing from a "
        "preview as missing from the file; use the column profiles and the script. "
        "`passed` is true only if the client would accept the delivery as is; "
        "`score` is the fraction of criteria met."
    )
    content: str | list = text
    if images:
        content = [{"type": "text", "text": text}, *(_image_part(p) for p in images)]
    verification = llm.complete_model(
        [
            {
                "role": "system",
                "content": "You are a strict QA reviewer for a freelance client. Judge only what "
                "the evidence shows. A deliverable that is missing, in the wrong format, or "
                "contains made-up data fails.",
            },
            {"role": "user", "content": content},
        ],
        Verification,
        temperature=0.0,
    )
    verification.automated_checks = checks
    return verification
