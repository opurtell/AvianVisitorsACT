"""Public-safety check: refuse to publish a page that leaks location or setup.

Runs on every rendered page. Any hit raises ScrubError and nothing is
written. Extra terms (suburb, street, names) can go one per line in
morning/private-terms.txt, which is gitignored so the terms themselves
never reach the public repo.
"""

import re

from . import config

PRIVATE_TERMS = config.ROOT / "private-terms.txt"

PATTERNS = {
    "coordinates": r"-?\b35\.\d{2}|\b149\.\d{2}",
    "IP address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "LAN hostname": r"\.local\b|\.nbn\b|birdnet-pi",
    "recording path": r"BirdSongs|By_Date|\.(?:mp3|wav|flac)\b",
    "host path": r"/home/|/Users/|authorized_keys",
    "infrastructure": r"tailscale|tailnet|\bgreg\b",
}


class ScrubError(ValueError):
    pass


def private_terms(path=PRIVATE_TERMS):
    try:
        with open(path) as f:
            return [t.strip() for t in f if t.strip() and not t.startswith("#")]
    except FileNotFoundError:
        return []


def check(html, extra_terms=None):
    terms = private_terms() if extra_terms is None else extra_terms
    hits = []
    rules = dict(PATTERNS)
    for t in terms:
        rules[f"private term {t!r}"] = re.escape(t)
    for name, pattern in rules.items():
        for m in re.finditer(pattern, html, re.IGNORECASE):
            context = html[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            hits.append(f"{name}: …{context}…")
    if hits:
        raise ScrubError("refusing to publish:\n  " + "\n  ".join(hits))
