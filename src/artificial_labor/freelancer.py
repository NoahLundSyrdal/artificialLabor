"""Fetch active projects from Freelancer.com's public projects API and save them as ads."""

from __future__ import annotations

import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"
SITE = "https://www.freelancer.com/projects/"
USER_AGENT = "artificial-labor (+https://github.com/NoahLundSyrdal/artificialLabor)"

Fetcher = Callable[[str], dict]


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def search(
    query: str | None = None,
    *,
    limit: int = 20,
    project_type: str | None = None,
    min_budget: float | None = None,
    languages: tuple[str, ...] = ("en",),
    fetch: Fetcher | None = None,
) -> list[dict]:
    """One request to the active-projects endpoint, newest first."""
    params: list[tuple[str, str]] = [
        ("limit", str(limit)),
        ("full_description", "true"),
        ("job_details", "true"),
        ("compact", "true"),
        ("sort_field", "time_updated"),
    ]
    if query:
        params.append(("query", query))
    if project_type:
        params.append(("project_types[]", project_type))
    if min_budget is not None:
        params.append(("min_price", f"{min_budget:g}"))
    params += [("languages[]", lang) for lang in languages]
    data = (fetch or _get_json)(f"{API}?{urllib.parse.urlencode(params)}")
    if data.get("status") != "success":
        raise RuntimeError(f"Freelancer API error: {data.get('message') or data}")
    return data["result"]["projects"]


def url(project: dict) -> str:
    return SITE + project["seo_url"] if project.get("seo_url") else f"{SITE}{project['id']}"


def to_markdown(project: dict) -> str:
    budget = project.get("budget") or {}
    code = (project.get("currency") or {}).get("code", "")
    lo, hi = budget.get("minimum"), budget.get("maximum")
    amount = "-".join(f"{v:g}" for v in (lo, hi) if v is not None) or "unspecified"
    per = " per hour" if project.get("type") == "hourly" else " (fixed price)"
    skills = ", ".join(j["name"] for j in project.get("jobs") or [] if j.get("name"))
    bids = project.get("bid_stats") or {}
    lines = [
        f"# {project['title'].strip()}",
        "",
        f"Status: {project.get('status', 'unknown')}",
        f"Budget: {amount} {code}{per}",
        f"Skills: {skills or 'n/a'}",
        f"Bids so far: {bids.get('bid_count', 0)} (avg {bids.get('bid_avg') or 0:g} {code})",
        f"Listing: {url(project)}",
        "",
        (project.get("description") or project.get("preview_description") or "").strip(),
        "",
    ]
    return "\n".join(lines)


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].rstrip("-") or "project"


def save(projects: list[dict], dest: Path) -> list[Path]:
    """Write each new project to `dest/fl-<id>-<slug>/`; already-fetched ids are skipped."""
    dest.mkdir(parents=True, exist_ok=True)
    seen = {p.name.split("-")[1] for p in dest.glob("fl-*-*")}
    new = []
    for project in projects:
        if str(project["id"]) in seen:
            continue
        d = dest / f"fl-{project['id']}-{slug(project['title'])}"
        d.mkdir()
        (d / "ad.md").write_text(to_markdown(project), encoding="utf-8")
        source = {"site": "freelancer.com", "id": project["id"], "url": url(project)}
        source["fetched_at"] = int(time.time())
        (d / "source.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
        new.append(d)
    return new


def prune(dest: Path, max_age_hours: float) -> int:
    """Delete fetched ads older than `max_age_hours` (the API terms ask caches to refresh daily)."""
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for d in dest.glob("fl-*-*"):
        try:
            fetched = json.loads((d / "source.json").read_text())["fetched_at"]
        except (OSError, KeyError, ValueError):
            continue
        if fetched < cutoff:
            shutil.rmtree(d)
            removed += 1
    return removed
