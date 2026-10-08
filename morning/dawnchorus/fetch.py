"""Fetch a snapshot of the Pi's detections DB.

The Pi streams a consistent SQLite backup over ssh (deploy/birds-snapshot).
The download goes to a temp file, is validated, then atomically replaces
the local copy, so a failed fetch never clobbers the last good snapshot.

    python3 -m dawnchorus.fetch [--host birdnet] [--out data/birds.db]
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

SQLITE_MAGIC = b"SQLite format 3\x00"


class FetchError(RuntimeError):
    pass


def validate(path):
    """Return (rows, latest 'Date Time') or raise FetchError."""
    with open(path, "rb") as f:
        if f.read(16) != SQLITE_MAGIC:
            raise FetchError("not a SQLite file (ssh error output?)")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise FetchError(f"integrity_check: {check}")
        rows, latest = con.execute(
            "SELECT COUNT(*), MAX(Date || ' ' || Time) FROM detections"
        ).fetchone()
    except sqlite3.DatabaseError as e:
        raise FetchError(str(e)) from e
    finally:
        con.close()
    if not rows:
        raise FetchError("detections table is empty")
    return rows, latest


def fetch(host, out, command="bin/birds-snapshot", timeout=120):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=".birds-", suffix=".db")
    try:
        with os.fdopen(fd, "wb") as f:
            # The forced command on greg's key ignores `command`; it's
            # needed when fetching with an ordinary key (the Mac).
            proc = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command],
                stdout=f, stderr=subprocess.PIPE, timeout=timeout,
            )
        if proc.returncode != 0:
            raise FetchError(f"ssh {host} exited {proc.returncode}: {proc.stderr.decode().strip()}")
        rows, latest = validate(tmp)
        os.replace(tmp, out)
        return rows, latest
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    cfg = config.load()["source"]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=cfg["ssh_host"])
    ap.add_argument("--out", default=str(config.resolve(cfg["db_path"])))
    args = ap.parse_args(argv)
    try:
        rows, latest = fetch(args.host, args.out, cfg["snapshot_command"])
    except (FetchError, subprocess.TimeoutExpired) as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    print(f"{args.out}: {rows} detections, latest {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
