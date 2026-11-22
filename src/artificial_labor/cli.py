from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from artificial_labor import pipeline, report
from artificial_labor.config import ConfigError, Settings
from artificial_labor.llm import LLM

log = logging.getLogger("artificial_labor")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="artificial-labor",
        description="Assess freelance ads, bid on the profitable ones, and do the work.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="List the ads that would be processed.")
    ls.add_argument("--ads", type=Path, default=Path("data/ads"))

    run = sub.add_parser("run", help="Run the full pipeline.")
    run.add_argument("--ads", type=Path, default=Path("data/ads"), help="Directory of ads.")
    run.add_argument("--out", type=Path, default=None, help="Output dir (default: runs/<ts>).")
    run.add_argument(
        "--only", nargs="+", metavar="MATCH", help="Only ads whose folder name contains MATCH."
    )
    run.add_argument("--no-execute", action="store_true", help="Stop after writing proposals.")
    run.add_argument(
        "--force", action="store_true", help="Propose/execute even when the decision is no-go."
    )
    run.add_argument("--workers", type=int, default=4, help="Ads processed in parallel.")
    run.add_argument("--max-attempts", type=int, help="Script attempts per job (default 3).")
    run.add_argument("--timeout", type=int, help="Seconds per script run (default 180).")
    run.add_argument("--min-score", type=float, help="Feasibility threshold (default 0.6).")
    run.add_argument("--min-margin", type=float, help="Margin threshold (default 0.3).")
    run.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    if args.command == "list":
        for ad in pipeline.discover(args.ads):
            print(f"{ad.id:45} inputs={len(ad.inputs):<3} brief={'yes' if ad.brief else 'no'}")
        return 0

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

    ads = pipeline.discover(args.ads, args.only)
    if not ads:
        print(f"error: no ads found in {args.ads}", file=sys.stderr)
        return 1
    out = args.out or Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
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
