"""Run generated scripts in a separate process with a scrubbed environment.

This is isolation from *accidents* (secrets, cwd, runaway loops), not a security
sandbox. Generated code runs with your user's permissions; use a container or VM
if you point the pipeline at untrusted ads.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_PASSTHROUGH_ENV = ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run_python(script: Path, *, cwd: Path, timeout: int) -> RunResult:
    env = {k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ}
    env.update(
        HOME=str(cwd),
        MPLBACKEND="Agg",
        MPLCONFIGDIR=str(cwd / ".mplconfig"),
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(script.resolve())],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        return RunResult(-1, _s(e.stdout), _s(e.stderr) + f"\nTimed out after {timeout}s", True)
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


def _s(v: str | bytes | None) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v or ""
