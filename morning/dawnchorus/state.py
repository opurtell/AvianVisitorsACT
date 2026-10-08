"""What earlier editions featured, so leads and regulars rotate.

state/featured.json: {"YYYY-MM-DD": {"lead": sci, "regular": sci}, ...}

Lookups only consider dates *before* the edition being built, so
re-running a date (or a backtest) gives the same picks.
"""

import json
import os
from datetime import date

from . import config

PATH = config.ROOT / "state" / "featured.json"


class History:
    def __init__(self, entries=None, path=PATH):
        self.entries = entries or {}
        self.path = path

    @classmethod
    def load(cls, path=PATH):
        try:
            with open(path) as f:
                return cls(json.load(f), path)
        except FileNotFoundError:
            return cls({}, path)

    def _before(self, day):
        for k, v in self.entries.items():
            d = date.fromisoformat(k)
            if d < day:
                yield d, v

    def leads_since(self, start, day):
        """Species that led an edition in [start, day)."""
        return {v.get("lead") for d, v in self._before(day) if d >= start}

    def last_featured(self, sci, day):
        """Most recent date before `day` that `sci` was lead or regular."""
        hits = [d for d, v in self._before(day) if sci in (v.get("lead"), v.get("regular"))]
        return max(hits, default=None)

    def record(self, day, lead, regular):
        self.entries[day.isoformat()] = {"lead": lead, "regular": regular}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(dict(sorted(self.entries.items())), f, indent=1)
        os.replace(tmp, self.path)
