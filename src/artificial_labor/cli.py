from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from artificial_labor import freelancer, pipeline, report
from artificial_labor.config import ConfigError, Settings
from artificial_labor.llm import LLM
from artificial_labor.stages import AdSource

log = logging.getLogger("artificial_labor")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="artificial-labor",
        description="Assess freelance ads, bid on the profitable ones, and do the work.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="List the ads that would be processed.")
    ls.add_argument("--ads", type=Path, default=Path("data/ads"))

    fetch = sub.add_parser(
        "fetch", help="Fetch active Freelancer.com projects into an ads directory."
    )
    fetch.add_argument("query", nargs="?", help="Search terms, e.g. 'excel csv'.")
    fetch.add_argument("--limit", type=int, default=20, help="Projects to fetch (default 20).")
    fetch.add_argument("--type", choices=["fixed", "hourly"], dest="project_type")
    fetch.add_argument("--min-budget", type=float, help="Minimum budget in the listing currency.")
    fetch.add_argument("--out", type=Path, default=Path("data/fetched"), help="Ads directory.")
    fetch.add_argument(
        "--max-age-hours",
        type=float,
        default=24,
        help="Delete previously fetched ads older than this (default 24).",
    )
    fetch.add_argument(
        "--run", action="store_true", help="Run the pipeline on the newly fetched ads."
    )

    run = sub.add_parser("run", help="Run the full pipeline.")
    run.add_argument("--ads", type=Path, default=Path("data/ads"), help="Directory of ads.")
    run.add_argument(
        "--only", nargs="+", metavar="MATCH", help="Only ads whose folder name contains MATCH."
    )
    for cmd in (run, fetch):
        cmd.add_argument("--no-execute", action="store_true", help="Stop after proposals.")
        cmd.add_argument(
            "--no-synthetic",
            action="store_true",
            help="Don't generate sample inputs when the client's files are missing.",
        )
        cmd.add_argument(
            "--force", action="store_true", help="Propose/execute even when the decision is no-go."
        )
        cmd.add_argument("--workers", type=int, default=4, help="Ads processed in parallel.")
        cmd.add_argument("--max-attempts", type=int, help="Script attempts per job (default 3).")
        cmd.add_argument("--timeout", type=int, help="Seconds per script run (default 180).")
        cmd.add_argument("--min-score", type=float, help="Feasibility threshold (default 0.6).")
        cmd.add_argument("--min-margin", type=float, help="Margin threshold (default 0.3).")
        cmd.add_argument("-v", "--verbose", action="store_true")
    out_help = "Run output dir (default: runs/<ts>)."
    run.add_argument("--out", type=Path, default=None, dest="run_out", help=out_help)
    fetch.add_argument("--run-out", type=Path, default=None, dest="run_out", help=out_help)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    if args.command == "list":
        for ad in pipeline.discover(args.ads):
            print(f"{ad.id:45} inputs={len(ad.inputs):<3} brief={'yes' if ad.brief else 'no'}")
        return 0

    ads: list | None = None
    if args.command == "fetch":
        pruned = freelancer.prune(args.out, args.max_age_hours)
        try:
            projects = freelancer.search(
                args.query,
                limit=args.limit,
                project_type=args.project_type,
                min_budget=args.min_budget,
            )
        except (OSError, RuntimeError, ValueError) as e:
            print(f"error: fetching from Freelancer.com failed: {e}", file=sys.stderr)
            return 1
        new = freelancer.save(projects, args.out)
        print(
            f"Fetched {len(projects)} project(s), {len(new)} new, {pruned} expired removed "
            f"-> {args.out}"
        )
        for d in new:
            print(f"  {d.name}")
        if not args.run:
            return 0
        if not new:
            print("Nothing new to run.")
            return 0
        ads = [AdSource.load(d) for d in new]

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for arg, attr in [
        ("max_attempts", "max_attempts"),
        ("timeout", "script_timeout"),
        ("min_score", "min_feasibility"),
        ("min_margin", "min_margin"),
    ]:
        if getattr(args, arg) is not None:
            setattr(settings, attr, getattr(args, arg))

    if args.no_synthetic:
        settings.synthetic_inputs = False

    if ads is None:
        ads = pipeline.discover(args.ads, args.only)
        if not ads:
            print(f"error: no ads found in {args.ads}", file=sys.stderr)
            return 1
    out = args.run_out or Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    llm = LLM.from_settings(settings)
    desc = f"{settings.provider}: {settings.model} (analysis), {settings.code_model} (code)"
    log.info("Processing %d ad(s) with %s -> %s", len(ads), desc, out)

    records = pipeline.run(
        llm, ads, out, execute=not args.no_execute, force=args.force, workers=args.workers
    )
    path = report.write(out, records, llm.usage, desc)
    print(f"\nReport: {path}")
    print(report.render(records, llm.usage, desc).split("\n## Details")[0])
    return 1 if any(r.error for r in records) else 0
