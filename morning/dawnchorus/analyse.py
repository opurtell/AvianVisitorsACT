"""Turn the detections DB into the facts for one edition.

Everything the page states as a fact (counts, times, firsts, rarity) is
computed here. The writer (template or GLM) only turns these into prose.

All times are naive Canberra local time, matching the DB's Date/Time
columns.
"""

import csv
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sun

from . import config, kb

SPECIES_CSV = config.ROOT.parent / "avian" / "scripts" / "act-species-canberra.csv"

RETURN_GAP_DAYS = 30        # silent this long, then heard again = a return
ARRIVAL_SHOWN_DAYS = 7      # an arrival stays in "Arrivals & Returns" this long
SITE_LOOKBACK_DAYS = 90     # window for "how often does this station hear it"
SITE_FULL_WEIGHT_DAYS = 60  # station history at which site evidence peaks
SITE_MAX_WEIGHT = 0.7
FIRST_EVER_BONUS = 0.3
RETURN_BONUS = 0.2
RECORD_BONUS = 0.15
RECORD_MIN_DAYS = 3         # a "busiest day yet" needs this much history
RECENT_LEAD_DAYS = 7        # a bird that led within this many days…
RECENT_LEAD_PENALTY = 0.4   # …is held back unless it has fresh news
LEAD_FACTS, REGULAR_FACTS = 3, 2  # facts offered per featured bird (stories + Did You Know)


@dataclass
class Detection:
    at: datetime
    sci: str
    com: str
    conf: float


@dataclass
class SpeciesDay:
    sci: str
    com: str
    slug: str
    n: int = 0
    best_conf: float = 0.0
    first_at: datetime = None
    last_at: datetime = None
    hourly: list = field(default_factory=lambda: [0] * 24)  # by clock hour
    dawn_n: int = 0
    dawn_first_at: datetime = None
    night_n: int = 0                   # last night's civil dusk to civil dawn
    night_first_at: datetime = None
    arrived_on: date = None            # start of the current stay, if within ARRIVAL_SHOWN_DAYS
    arrived_after_days: int = None     # silent gap before arrived_on (None = first ever)
    prior_best_day: int = 0            # most detections on any earlier day
    days_total: int = 0                # distinct dates heard, all time incl. this window
    prior_last_at: datetime = None     # last detection before the window
    prior_days: int = 0                # days detected before the window, all time
    site_days_recent: int = 0          # days detected in the SITE_LOOKBACK before the window
    site_freq: float = 0.0             # site_days_recent / station days in that lookback
    regional_occ: float = None         # BirdNET occurrence score, act-species-canberra.csv
    regional_rarity: float = 0.5       # 0 = commonest in the ACT set, 1 = rarest
    rarity: float = 0.0
    strong_n: int = 0                  # calls at >= suspect_min_confidence in the window
    suspect: bool = False              # rare regionally yet frequent here: stricter bar
    credible: bool = False

    @property
    def first_ever(self):
        return self.prior_last_at is None

    @property
    def returning_after_days(self):
        if self.prior_last_at is None:
            return None
        gap = (self.first_at.date() - self.prior_last_at.date()).days
        return gap if gap >= RETURN_GAP_DAYS else None

    @property
    def arrival(self):
        """First ever, or back after a long gap, in this window."""
        return self.first_ever or self.returning_after_days is not None

    @property
    def record_day(self):
        """Busiest window yet, for a bird with some history."""
        return self.prior_days >= RECORD_MIN_DAYS and self.n > self.prior_best_day

    @property
    def fresh_news(self):
        return self.arrival or self.record_day

    @property
    def lead_score(self):
        bonus = FIRST_EVER_BONUS if self.first_ever else RETURN_BONUS if self.returning_after_days else 0
        if self.record_day:
            bonus += RECORD_BONUS
        return self.rarity + bonus


@dataclass
class Edition:
    date: date
    place: str
    window_start: datetime
    window_end: datetime
    last_dusk: datetime
    civil_dawn: datetime
    sunrise: datetime
    dawn_end: datetime
    dawn_clipped: bool
    station_first_date: date
    station_days: int
    species: list
    total_detections: int
    avg7_detections: float
    avg7_species: float
    busiest_hour: int
    busiest_hour_n: int
    lead: SpeciesDay = None
    regular: SpeciesDay = None
    dawn_chorus: list = field(default_factory=list)
    arrivals: list = field(default_factory=list)
    night_shift: list = field(default_factory=list)
    unconfirmed: list = field(default_factory=list)
    facts: list = field(default_factory=list)    # [(SpeciesDay, kb fact dict)]

    @property
    def number(self):
        return (self.date - self.station_first_date).days + 1

    @property
    def credible(self):
        return [s for s in self.species if s.credible]

    @property
    def hour_order(self):
        """Clock hours in window order, starting at the window's first hour."""
        h0 = self.window_start.hour
        return [(h0 + i) % 24 for i in range(24)]

    @property
    def dawn_hours(self):
        hours, t = set(), self.civil_dawn.replace(minute=0, second=0)
        while t < self.dawn_end:
            hours.add(t.hour)
            t += timedelta(hours=1)
        return hours


def slugify(sci):
    return sci.lower().replace(" ", "-")


def load_detections(db_path, until):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT Date, Time, Sci_Name, Com_Name, Confidence FROM detections "
            "WHERE Date <= ? ORDER BY Date, Time", (until.date().isoformat(),)
        ).fetchall()
    finally:
        con.close()
    out = []
    for d, t, sci, com, conf in rows:
        at = datetime.fromisoformat(f"{d} {t}")
        if at <= until:
            out.append(Detection(at, sci, com, float(conf)))
    return out


def load_regional(path=SPECIES_CSV, ala=None):
    """sci -> (occurrence_v2, percentile rarity in [0, 1]).

    Rarity averages two percentiles: BirdNET's occurrence score at Canberra,
    and the species' share of ACT bird records on the Atlas of Living
    Australia (from the knowledge base; skipped if it hasn't been built).
    """
    with open(path, newline="") as f:
        occ = {r["scientific_name"]: float(r["occurrence_v2"]) for r in csv.DictReader(f)}
    ranked = sorted(occ, key=occ.get, reverse=True)  # commonest first
    n = max(1, len(ranked) - 1)
    ala = kb.ala_rarity() if ala is None else ala
    out = {}
    for i, sci in enumerate(ranked):
        r = i / n
        out[sci] = (occ[sci], (r + ala[sci]) / 2 if sci in ala else r)
    return out


def solar(day, cfg):
    """Naive local dawn/sunrise/sunset etc. for `day`."""
    loc = cfg["location"]
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    s = sun(Observer(loc["latitude"], loc["longitude"]), date=day, tzinfo=tz)
    return {k: v.replace(tzinfo=None) for k, v in s.items()}


def stay_start(dates, gap=RETURN_GAP_DAYS):
    """(first day of the latest continuous stay, silent days before it)."""
    dates = sorted(dates)
    start, before = dates[0], None
    for prev, cur in zip(dates, dates[1:]):
        if (cur - prev).days >= gap:
            start, before = cur, (cur - prev).days
    return start, before


def run_end_for(day, cfg):
    hh, mm = map(int, cfg["schedule"]["run_time"].split(":"))
    return datetime.combine(day, time(hh, mm))


def analyse(db_path, end, cfg, regional=None):
    """Facts for the edition whose 24 h window ends at `end` (naive local)."""
    win = cfg["windows"]
    cred = cfg["credibility"]
    regional = regional if regional is not None else load_regional()

    start = end - timedelta(hours=win["lookback_hours"])
    today = solar(end.date(), cfg)
    civil_dawn, sunrise = today["dawn"], today["sunrise"]
    last_dusk = solar(end.date() - timedelta(days=1), cfg)["dusk"]
    natural_dawn_end = sunrise + timedelta(minutes=win["dawn_end_after_sunrise_min"])
    dawn_end = min(natural_dawn_end, end)

    dets = load_detections(db_path, end)
    if not dets:
        raise ValueError(f"no detections on or before {end}")
    station_first = dets[0].at.date()

    in_window = [d for d in dets if d.at > start]
    before = [d for d in dets if d.at <= start]

    # station history before the window
    prior_days = defaultdict(set)
    prior_last = {}
    prior_daily = defaultdict(Counter)
    for d in before:
        prior_days[d.sci].add(d.at.date())
        prior_last[d.sci] = d.at
        prior_daily[d.sci][d.at.date()] += 1
    lookback_from = start.date() - timedelta(days=SITE_LOOKBACK_DAYS)
    station_days_recent = len({d.at.date() for d in before if d.at.date() > lookback_from})
    history_days = (start.date() - station_first).days
    w_site = SITE_MAX_WEIGHT * min(1.0, history_days / SITE_FULL_WEIGHT_DAYS)

    species = {}
    for d in in_window:
        s = species.get(d.sci)
        if s is None:
            s = species[d.sci] = SpeciesDay(d.sci, kb.display_name(d.sci, d.com), slugify(d.sci))
        s.n += 1
        s.best_conf = max(s.best_conf, d.conf)
        s.strong_n += d.conf >= cred["suspect_min_confidence"]
        s.first_at = s.first_at or d.at
        s.last_at = d.at
        s.hourly[d.at.hour] += 1
        if civil_dawn <= d.at <= dawn_end:
            s.dawn_n += 1
            s.dawn_first_at = s.dawn_first_at or d.at
        elif last_dusk <= d.at < civil_dawn:
            s.night_n += 1
            s.night_first_at = s.night_first_at or d.at

    for s in species.values():
        s.prior_last_at = prior_last.get(s.sci)
        days = prior_days.get(s.sci, set())
        s.prior_days = len(days)
        s.site_days_recent = sum(1 for x in days if x > lookback_from)
        s.prior_best_day = max(prior_daily[s.sci].values(), default=0)
        window_days = {d.at.date() for d in in_window if d.sci == s.sci}
        s.days_total = len(days | window_days)
        arrived, gap = stay_start(days | window_days)
        if arrived > end.date() - timedelta(days=ARRIVAL_SHOWN_DAYS) and arrived >= station_first + timedelta(days=1):
            s.arrived_on, s.arrived_after_days = arrived, gap
        s.site_freq = s.site_days_recent / station_days_recent if station_days_recent else 0.0
        if s.sci in regional:
            s.regional_occ, s.regional_rarity = regional[s.sci]
        s.rarity = (1 - w_site) * s.regional_rarity + w_site * (1 - s.site_freq)
        # A bird that's rare in the ACT but turns up here most days is more
        # likely a recurring misidentification than a resident (the Caspian
        # Tern: 1–2 calls a day at any hour). It needs repeated strong calls.
        s.suspect = (s.regional_rarity >= cred["suspect_regional_rarity"]
                     and s.site_freq >= cred["suspect_site_freq"])
        if s.suspect:
            s.credible = s.strong_n >= cred["suspect_min_strong"]
        else:
            s.credible = s.best_conf >= cred["min_confidence"] or s.n >= cred["min_detections"]

    ranked = sorted(species.values(), key=lambda s: (-s.n, s.com))

    # daily averages over the 7 windows before this one
    prev = []
    for k in range(1, 8):
        a, b = start - timedelta(days=k), end - timedelta(days=k)
        if a.date() < station_first:
            break
        w = [d for d in before if a < d.at <= b]
        prev.append((len(w), len({d.sci for d in w})))

    by_hour = [0] * 24
    for d in in_window:
        by_hour[d.at.hour] += 1
    busiest = max(range(24), key=lambda h: by_hour[h])

    ed = Edition(
        date=end.date(),
        place=cfg["location"]["name"],
        window_start=start,
        window_end=end,
        civil_dawn=civil_dawn,
        sunrise=sunrise,
        dawn_end=dawn_end,
        dawn_clipped=natural_dawn_end > end,
        last_dusk=last_dusk,
        station_first_date=station_first,
        station_days=(end.date() - station_first).days + 1,
        species=ranked,
        total_detections=len(in_window),
        avg7_detections=sum(p[0] for p in prev) / len(prev) if prev else None,
        avg7_species=sum(p[1] for p in prev) / len(prev) if prev else None,
        busiest_hour=busiest,
        busiest_hour_n=by_hour[busiest],
    )
    return ed


def pick_features(ed, history):
    """Choose lead, regular and section lists. `history` is a state.History."""
    credible = ed.credible
    ed.unconfirmed = [s for s in ed.species if not s.credible]
    ed.dawn_chorus = sorted((s for s in credible if s.dawn_first_at), key=lambda s: s.dawn_first_at)
    ed.night_shift = sorted((s for s in credible if s.night_first_at), key=lambda s: s.night_first_at)
    ed.arrivals = sorted((s for s in credible if s.arrived_on), key=lambda s: s.arrived_on, reverse=True)

    recent_leads = history.leads_since(ed.date - timedelta(days=RECENT_LEAD_DAYS), ed.date)

    def lead_rank(s):
        held_back = s.sci in recent_leads and not s.fresh_news
        return (s.lead_score - (RECENT_LEAD_PENALTY if held_back else 0), s.n)

    if credible:
        ed.lead = max(credible, key=lead_rank)

    # The Regular: a well-established bird; whichever has gone longest
    # without being featured, so the common birds take turns.
    pool = [s for s in credible if s is not ed.lead and s.site_freq >= 0.5] or \
           [s for s in credible if s is not ed.lead]
    if pool:
        ed.regular = min(pool, key=lambda s: (history.last_featured(s.sci, ed.date) or date.min, s.sci))

    used = history.facts_used(ed.date)
    for s, n in ((ed.lead, LEAD_FACTS), (ed.regular, REGULAR_FACTS)):
        if s:
            ed.facts += [(s, f) for f in kb.pick_facts(s.sci, used, ed.date, n)]


def edition_for(day, db_path, history, cfg=None, end=None):
    cfg = cfg or config.load()
    ed = analyse(db_path, end or run_end_for(day, cfg), cfg)
    pick_features(ed, history)
    return ed


if __name__ == "__main__":
    import sys
    from .state import History
    cfg = config.load()
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    ed = edition_for(day, config.resolve(cfg["source"]["db_path"]), History.load(), cfg)
    print(f"{ed.date} No.{ed.number}  window {ed.window_start:%d %H:%M}–{ed.window_end:%d %H:%M}")
    print(f"dawn {ed.civil_dawn:%H:%M}  sunrise {ed.sunrise:%H:%M}  dawn ends {ed.dawn_end:%H:%M}"
          f"{' (clipped)' if ed.dawn_clipped else ''}")
    print(f"{ed.total_detections} detections, {len(ed.species)} species; 7-day avg "
          f"{ed.avg7_detections and round(ed.avg7_detections)} / {ed.avg7_species and round(ed.avg7_species, 1)}")
    for s in ed.species:
        tag = ("NEW " if s.first_ever else f"RET{s.returning_after_days} " if s.returning_after_days else "") + \
              (f"arr{s.arrived_on:%d/%m} " if s.arrived_on else "") + ("REC" if s.record_day else "")
        print(f"  {s.com:28} n={s.n:3} conf={s.best_conf:.2f} {'✓' if s.credible else '?'} "
              f"site={s.site_freq:.2f} reg={s.regional_rarity:.2f} rarity={s.rarity:.2f} "
              f"dawn={s.dawn_first_at and s.dawn_first_at.strftime('%H:%M')} {tag}")
    print("lead:", ed.lead and ed.lead.com, "| regular:", ed.regular and ed.regular.com)
    print("dawn order:", ", ".join(f"{s.com} {s.dawn_first_at:%H:%M}" for s in ed.dawn_chorus))
    print("night:", ", ".join(f"{s.com} {s.night_first_at:%H:%M}×{s.night_n}" for s in ed.night_shift))
    print("arrivals:", [s.com for s in ed.arrivals], "| unconfirmed:", [s.com for s in ed.unconfirmed])
