"""The species knowledge base: loader, seasonality, grounding, fact rotation.

knowledge/species/<slug>.json, one per species in the include list:

    {"sci", "com", "slug",
     "wikipedia": {"title", "url", "revid"},
     "ala": {"years", "months": [12 counts], "total", "share"},
     "seasonality": {"class", "peak", "low", "rel": [12]},
     "facts": [{"id", "text", "topic", "source_url", "quote"}]}

Built by build_kb.py. Everything here except fact *wording* is computed:
seasonality comes from ALA counts, URLs from the section the quote was found
in, ids from the quote. A fact is kept only if its quote appears in the
fetched source text (`grounded`).
"""

import hashlib
import json
import re
import tomllib
import unicodedata
from datetime import date

from . import config, scrub

KNOWLEDGE = config.ROOT / "knowledge"
SPECIES_DIR = KNOWLEDGE / "species"
SEASONAL = KNOWLEDGE / "seasonal.toml"
OVERRIDES = KNOWLEDGE / "overrides.toml"
INCLUDE_LIST = config.ROOT.parent / "avian" / "scripts" / "act-include-species-list.txt"

FACT_REPEAT_DAYS = 60
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
MONTH_NAMES = ("January February March April May June July August September October "
               "November December").split()
# Did You Know prefers the livelier topics; range and habitat facts come last.
TOPIC_ORDER = ["behaviour", "voice", "diet", "breeding", "people", "name", "appearance",
               "other", "conservation", "habitat", "range"]

# Seasonality thresholds, on each month's share of all ACT bird records
# relative to the species' own yearly mean (1.0 = an average month).
RARE_MAX_RECORDS = 300      # fewer ACT records than this over the ALA years = rare visitor
                            # (below this, one twitchable bird makes the "season")
CONFIDENT_RECORDS = 1000    # below this the class is a guess: confidence "low"
RESIDENT_MIN_REL = 0.45     # quietest 3-month stretch at least this = resident
WARM = {10, 11, 12, 1, 2, 3}


def include_list(path=INCLUDE_LIST):
    """[(sci, com)] in file order."""
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            sci, com = line.strip().split("_", 1)
            out.append((sci, com))
    return out


def slugify(sci):
    return sci.lower().replace(" ", "-")


_names = None


def display_name(sci, fallback):
    """The common name to print: overrides.toml [name], else BirdNET's label."""
    global _names
    if _names is None:
        with open(OVERRIDES, "rb") as f:
            _names = tomllib.load(f).get("name", {})
    return _names.get(sci, fallback)


# ── seasonality ──────────────────────────────────────────────────────────

def seasonality(counts, effort):
    """Class from monthly ACT counts, corrected for monthly recording effort.

    counts, effort: 12 numbers (Jan..Dec); effort is all bird records that
    month. Returns {"class", "confidence", "peak", "low", "rel"}: class is
    resident, summer migrant, winter visitor or rare visitor; confidence is
    "high" or "low" (few records); peak/low are month names; rel is each
    month's effort-corrected rate over the yearly mean.
    """
    total = sum(counts)
    share = [c / e if e else 0.0 for c, e in zip(counts, effort)]
    mean = sum(share) / 12 or 1.0
    rel = [s / mean for s in share]
    # 3-month circular smoothing so one odd month doesn't decide the class
    smooth = [(rel[i - 1] + rel[i] + rel[(i + 1) % 12]) / 3 for i in range(12)]
    peak = [MONTHS[i] for i in sorted(range(12), key=lambda i: -smooth[i])[:3]]
    low = [MONTHS[i] for i in sorted(range(12), key=lambda i: smooth[i])[:3]]
    if total < RARE_MAX_RECORDS:
        cls = "rare visitor"
    elif min(smooth) >= RESIDENT_MIN_REL:
        cls = "resident"
    else:
        warm = sum(rel[m - 1] for m in WARM) / 6
        cool = sum(rel[m - 1] for m in range(1, 13) if m not in WARM) / 6
        cls = "summer migrant" if warm > cool else "winter visitor"
    return {"class": cls, "confidence": "high" if total >= CONFIDENT_RECORDS else "low",
            "peak": sorted(peak, key=MONTHS.index), "low": sorted(low, key=MONTHS.index),
            "rel": [round(r, 2) for r in rel]}


# ── grounding ────────────────────────────────────────────────────────────

_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                       "–": "-", "—": "-", " ": " "})


def norm(text):
    """Comparison form: NFC, straight quotes and hyphens, collapsed spaces.
    Nothing that changes meaning — the quote must still be the source's words."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).translate(_FOLD)).strip()


def find_quote(quote, sections):
    """Heading of the first section containing `quote` verbatim, else None.
    sections: [(heading, text)]."""
    q = norm(quote)
    if not q:
        return None
    for heading, text in sections:
        if q in norm(text):
            return heading
    return None


NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text):
    return {n.replace(",", "") for n in NUM.findall(text)}


def fact_id(slug, quote):
    return f"{slug}-{hashlib.sha1(norm(quote).encode()).hexdigest()[:6]}"


# ── loading and rotation ─────────────────────────────────────────────────

_cache = {}


def load_all(path=SPECIES_DIR):
    """sci -> species dict, for every file in knowledge/species/."""
    if path not in _cache:
        out = {}
        for f in sorted(path.glob("*.json")):
            d = json.loads(f.read_text())
            out[d["sci"]] = d
        _cache[path] = out
    return _cache[path]


def species(sci, path=SPECIES_DIR):
    return load_all(path).get(sci)


def ala_rarity(path=SPECIES_DIR):
    """sci -> percentile rarity in [0, 1] from ALA's ACT record share
    (0 = most recorded). Species without ALA records count as rarest."""
    kb = load_all(path)
    shares = {sci: (d.get("ala") or {}).get("share") or 0.0 for sci, d in kb.items()}
    ranked = sorted(shares, key=shares.get, reverse=True)
    n = max(1, len(ranked) - 1)
    return {sci: i / n for i, sci in enumerate(ranked)}


def seasonal_notes(month, path=SEASONAL):
    """Hand-written Canberra calendar entries for a month number (1–12)."""
    try:
        with open(path, "rb") as f:
            cal = tomllib.load(f)
    except FileNotFoundError:
        return []
    return [e for e in cal.get("entry", []) if month in e.get("months", [])]


def scrub_ok(text):
    try:
        scrub.check(text)
        return True
    except scrub.ScrubError:
        return False


def pick_facts(sci, used, day, n=2, path=SPECIES_DIR):
    """Up to n facts for `sci` not used in the FACT_REPEAT_DAYS before `day`.

    used: {fact_id: last-used date}. Prefers topics not already chosen,
    then facts used longest ago (never-used first), then livelier topics
    (TOPIC_ORDER), then file order. Facts
    the public-safety scrub would block (a "35.5 cm" reads as a coordinate)
    are skipped rather than allowed to stop the publish.
    """
    sp = species(sci, path)
    if not sp:
        return []
    fresh = [f for f in sp["facts"]
             if (f["id"] not in used or (day - used[f["id"]]).days >= FACT_REPEAT_DAYS) and scrub_ok(f["text"])]
    fresh.sort(key=lambda f: (used.get(f["id"], date.min), TOPIC_ORDER.index(f["topic"])))
    out, topics = [], set()
    for f in fresh:                      # one per topic first…
        if len(out) < n and f["topic"] not in topics:
            out.append(f)
            topics.add(f["topic"])
    for f in fresh:                      # …then fill
        if len(out) < n and f not in out:
            out.append(f)
    return out
