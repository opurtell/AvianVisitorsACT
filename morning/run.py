#!/usr/bin/env python3
"""Build The Dawn Chorus.

    run.py                          live: fetch, window ends now, render, record
    run.py --date 2026-10-09        rebuild one edition (window ends at run_time)
    run.py --backtest 7             rebuild the last 7 editions, oldest first
    run.py --no-fetch --dry-run     use the existing snapshot; render to a temp
                                    dir and leave state/featured.json alone
    run.py --no-llm                 template prose only (no GLM call)
    run.py --publish                commit and push the site (deploy/dawnchorus.service)
"""

import argparse
import sys
import tempfile
from datetime import date, datetime, timedelta

from dawnchorus import config, fetch, glm, publish
from dawnchorus.analyse import edition_for
from dawnchorus.glm_write import glm_prose
from dawnchorus.render import render_edition, render_stale
from dawnchorus.scrub import ScrubError
from dawnchorus.state import History
from dawnchorus.write import finish, template_prose


def write(ed, cfg, use_llm, log=print):
    """GLM prose if it passes validation, else the template. Never raises."""
    if use_llm:
        try:
            prose = glm_prose(ed, cfg, log)
            if prose:
                return finish(ed, prose)
            log("  GLM drafts failed validation; using the template")
        except glm.QuotaError as e:
            log(f"  GLM quota: {e}; using the template")
        except Exception as e:  # noqa: BLE001 — missing key etc.; the paper still goes out
            log(f"  GLM unavailable ({e}); using the template")
    return finish(ed, template_prose(ed))


def build(day, db, history, out, end=None, cfg=None, use_llm=True):
    cfg = cfg or config.load()
    ed = edition_for(day, db, history, cfg, end=end)
    prose = write(ed, cfg, use_llm)
    path = render_edition(ed, prose, out)
    history.record(ed.date, ed.lead and ed.lead.sci, ed.regular and ed.regular.sci, prose["fact_ids"])
    return ed, prose, path


def latest_detection(db):
    """Time of the newest detection in the snapshot, or None."""
    try:
        _, latest = fetch.validate(db)
        return datetime.fromisoformat(latest)
    except (fetch.FetchError, FileNotFoundError, TypeError, ValueError):
        return None


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
    ap.add_argument("--no-llm", action="store_true", help="template prose only")
    ap.add_argument("--publish", action="store_true", help="commit and push the site afterwards")
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

    if not (args.backtest or args.date):
        # Live run: if nothing new has arrived, say so on the front page
        # rather than leaving yesterday's edition up as if it were today's.
        now = jobs[0][1]
        latest = latest_detection(args.db)
        if latest is None or now - latest > timedelta(hours=cfg["source"]["stale_hours"]):
            path = render_stale(now.date(), latest, out)
            print(f"{now.date()}: no detections since {latest}; stale notice -> {path}")
            return finish_run(args, cfg, out, f"No edition {now.date()}: no data since {latest}")

    for day, end in jobs:
        try:
            ed, prose, path = build(day, args.db, history, out, end, cfg, not args.no_llm)
        except ScrubError as e:
            print(f"{day}: {e}", file=sys.stderr)
            return 2
        print(f"{day} No.{ed.number} [{prose['source']}]: {prose['headline']}  "
              f"({len(ed.credible)} species) -> {path}")

    if not args.dry_run:
        history.save()
    days = ", ".join(d.isoformat() for d, _ in jobs)
    return finish_run(args, cfg, out, f"Edition {days}")


def finish_run(args, cfg, out, message):
    if not args.publish or args.dry_run:
        return 0
    try:
        pushed = publish.publish(cfg["publish"]["target"], out, message)
    except (publish.PublishError, OSError) as e:
        print(f"publish failed: {e}", file=sys.stderr)
        return 3
    print("published" if pushed else "nothing changed; not published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
