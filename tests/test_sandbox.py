import os

from artificial_labor.sandbox import run_python


def test_runs_in_cwd_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "super-secret")
    script = tmp_path / "s.py"
    script.write_text(
        "import os, pathlib\n"
        "print(os.environ.get('MISTRAL_API_KEY'))\n"
        "pathlib.Path('out.txt').write_text('hi')\n"
    )
    result = run_python(script, cwd=tmp_path, timeout=30)
    assert result.ok
    assert result.stdout.strip() == "None"
    assert (tmp_path / "out.txt").read_text() == "hi"
    assert os.environ["MISTRAL_API_KEY"] == "super-secret"


def test_timeout_and_failure(tmp_path):
    script = tmp_path / "s.py"
    script.write_text("import time; time.sleep(5)")
    result = run_python(script, cwd=tmp_path, timeout=1)
    assert result.timed_out and not result.ok

    script.write_text("raise SystemExit('boom')")
    result = run_python(script, cwd=tmp_path, timeout=10)
    assert result.returncode == 1 and "boom" in result.stderr
