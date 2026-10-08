#!/usr/bin/env python3
"""Build The Dawn Chorus.

    run.py                          live: fetch, window ends now, render, record
    run.py --date 2026-10-09        rebuild one edition (window ends at run_time)
    run.py --backtest 7             rebuild the last 7 editions, oldest first
    run.py --no-fetch --dry-run     use the existing snapshot; render to a temp
                                    dir and leave state/featured.json alone
"""

import argparse
import sys
import tempfile
from datetime import date, datetime, timedelta

from dawnchorus import config, fetch
from dawnchorus.analyse import edition_for
from dawnchorus.render import render_edition
from dawnchorus.scrub import ScrubError
from dawnchorus.state import History
from dawnchorus.write import template_prose


def build(day, db, history, out, end=None):
    ed = edition_for(day, db, history, end=end)
    prose = template_prose(ed)
    path = render_edition(ed, prose, out)
    history.record(ed.date, ed.lead and ed.lead.sci, ed.regular and ed.regular.sci,
                   [f["id"] for _, f in ed.facts])
    return ed, prose, path


def main(argv=None):
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Build The Dawn Chorus.")
    when = ap.add_mutually_exclusive_group()
    when.add_argument("--date", type=date.fromisoformat, help="rebuild the edition for this date")
    when.add_argument("--backtest", type=int, metavar="N", help="rebuild the last N editions")
    ap.add_argument("--db", default=str(config.resolve(cfg["source"]["db_path"])))
    ap.add_argument("--host", default=cfg["source"]["ssh_host"], help="ssh alias of the Pi")
    ap.add_argument("--no-fetch", action="store_true", help="use the existing DB snapshot")
    ap.add_argument("--out", default=str(config.ROOT / "editions"))
    ap.add_argument("--dry-run", action="store_true", help="temp output, no state written")
    args = ap.parse_args(argv)

    if not args.no_fetch:
        try:
            rows, latest = fetch.fetch(args.host, args.db, cfg["source"]["snapshot_command"])
            print(f"fetched {rows} detections, latest {latest}")
        except Exception as e:  # stale data is better than no paper; analyse reports staleness
            print(f"fetch failed, using last snapshot: {e}", file=sys.stderr)

    out = tempfile.mkdtemp(prefix="dawnchorus-") if args.dry_run else args.out
    history = History.load()

    if args.backtest:
        today = date.today()
        jobs = [(today - timedelta(days=k), None) for k in range(args.backtest - 1, -1, -1)]
    elif args.date:
        jobs = [(args.date, None)]
    else:
        now = datetime.now().replace(second=0, microsecond=0)
        jobs = [(now.date(), now)]

    for day, end in jobs:
        try:
            ed, prose, path = build(day, args.db, history, out, end)
        except ScrubError as e:
            print(f"{day}: {e}", file=sys.stderr)
            return 2
        print(f"{day} No.{ed.number}: {prose['headline']}  ({len(ed.credible)} species) -> {path}")

    if not args.dry_run:
        history.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
