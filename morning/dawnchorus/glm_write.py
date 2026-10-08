"""GLM prose for an edition: brief → one JSON-mode call → validation.

The model sees only a brief built from the edition's computed facts, the
knowledge-base facts picked for the featured birds, and this month's
seasonal notes. It writes prose; it never supplies a number, time, species
or fact of its own. Every reply is checked (`problems`) and, after
`attempts` failures, the caller falls back to the template.

Unconfirmed species are left out of the brief entirely, so naming one is a
validation failure rather than a judgement call.
"""

import html
import json
import re

from . import glm, kb, scrub
from datetime import timedelta

from .write import clock, day_clock, plural, regional_phrase, relative_to, season_phrase

LIMITS = {                       # key: (min, max) words
    "headline": (3, 12),
    "standfirst": (8, 40),
    "lead_story": (90, 200),
    "dawn_paragraph": (25, 110),
    "regular_column": (40, 130),
}
HEADLINE_MAX_CHARS = 80

NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split()) if i >= 2}   # "one" is too idiomatic to check
NUMBER_WORDS.update({w: 10 * i for i, w in enumerate(
    "thirty forty fifty sixty seventy eighty ninety".split(), 3)})
NUMBER_WORDS.update({"hundred": 100, "dozen": 12})
# Characterisations the brief never supports on its own.
COMPARISON = re.compile(r"\b(usual(ly)?|typical(ly)?|normal(ly)?|as ever|as always)\b", re.I)
# Presence words: true of a bird heard on most days, and only allowed then.
PRESENCE = re.compile(r"\b(steadi\w*|reliab\w*|faithful\w*|regular as|dependab\w*|ever-present|"
                      r"stalwart|fixture|constant)\b", re.I)
MOST_DAYS = 0.75            # share of station days that makes a bird "one of the most regular"
# Words that describe the station's surroundings; allowed only if the brief uses them.
PLACE = re.compile(r"\b(garden|backyard|back yard|yard|house|home|street|suburb|neighbou?r\w*|"
                   r"lawn|fence|roof|balcony|veranda\w*|window sill)\b", re.I)
# Claims that need a specific fact behind them.
SUPERLATIVE_PRESENCE = re.compile(r"\bmost (reliable|regular|dependable|faithful|steady|constant|common|"
                                  r"frequent)\b|\b(steadiest|rarest|scarcest|commonest)\b", re.I)
# The model talking about its inputs instead of the birds.
META = re.compile(r"\b(the brief|brief's|its file|from its file|the record (?:does|did|can|could|caught|"
                  r"says|shows|holds)|the data|the dataset|according to the)\b", re.I)
NIGHT = re.compile(r"\b(after dark|overnight|at night|in the dark\w*|nocturnal|after sunset|after the sun "
                   r"(went|had gone|set)|after nightfall|night shift|by night)\b", re.I)
ARRIVAL = re.compile(r"\b(return\w*|arriv\w*|back (in|to|after|for)|is back|comes back|debut|newcomer)\b", re.I)
GUESSWORK = re.compile(r"\b(passing (?:through|over)|passes (?:through|over)|passed (?:through|over)|"
                       r"moved on|moving on|rather than passing)\b", re.I)
# "a minute later", "two minutes on": gaps must be copied from the brief's offsets.
OFFSET = re.compile(r"\b(?:a|an|one|half an|\d+|[a-z]+) (?:minutes?|hours?) (?:later|earlier|after|before|on|"
                    r"behind|ahead|apart)\b", re.I)
TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)\b", re.I)
# A time near one of these is about the sun or the edition, not a bird.
SOLAR_WORDS = ("first light", "sunrise", "sun rose", "sun came up", "dawn", "press", "daybreak",
               "hours to", "hours until", "until", "since", "window", "closed", "ran to", "ended",
               "press time", "went to press")


SYSTEM = """You write The Dawn Chorus, a short morning newspaper about the birds a single
microphone in Canberra heard in the last 24 hours. Readers are a household, not birders.

Voice: a warm, plain broadsheet nature column. Australian English (colour, behaviour,
grey). Short sentences, concrete detail, no exclamation marks, no clichés like "feathered
friends", no second person. Charm comes from the detail and the phrasing, never from a
claim: don't guess why a bird called, where it went, whether it is local or passing
through, or how it ranks against other birds.

You get a JSON brief (never mention it, or "the record" or "the data": write as a reporter
who simply knows these things). Use ONLY what it says:
- Every number, time, count and date must come from the brief, written as it is there
  (times like "6:46 am"). Never estimate, total or round anything yourself.
- Name only birds that appear in the brief. Use their names exactly as given.
- A sentence with a clock time must be about the bird (or the sunrise) that time belongs to.
- Facts about a bird's life come only from its "facts" list. Use at most one fact in the lead
  story and one in the column, close to their wording, and add nothing to them.
  List the ids of any facts you used in "facts_used".
- "seasonal_context" is background for this time of year; mention a bird from it only if
  that bird is also in the brief as heard.
- Never mention the microphone's location beyond "Canberra", the equipment, confidence
  scores, or anything about the people of the house.
- If the brief marks the dawn as clipped, say the chorus was still going at press time.
- Read the brief literally. "calls_in_window" is the count: say it as given (four calls are
  not "both"). "station_history" is how long the STATION has been listening, not the paper.
  "today" is the edition's date; calls marked "yesterday" happened on "yesterday".
- Offsets like "three minutes before sunrise" must be copied from vs_sunrise / vs_first_light;
  never work out a gap between two times yourself.
- "After dark" or "overnight" only for birds in "after_dark".
- Don't describe where the station is (garden, house, street, neighbours).
- Banned words, because they rank or compare: most reliable, most regular, steadiest,
  faithful, usual, typical, as ever, rarest. Use "presence" if the brief gives it.
- "Return", "back" or "arrives" only if the lead's "news" says it is new or back.
- "Morning" means the dawn; the species and call totals are for the whole 24 hours.
- No comparisons the brief doesn't make: never call a count high, low, quiet, busy, usual
  or "by its standards" unless "news" or the seven-day averages say so.
- No speculation: nothing about what birds will do next, why they did something, or
  what they "seem" to feel. Nothing about this paper or column's own history.

Return JSON with exactly these keys:
{"headline": "...",                 3–12 words, sentence case (capitals only for the first word
                                    and bird names), no full stop
 "standfirst": "...",               one sentence, 8–40 words
 "lead_story": ["...", "..."],      2–3 paragraphs, 90–200 words in all, about the lead bird
 "dawn_paragraph": "...",           25–110 words on the dawn chorus, in order of first call
 "regular_column": ["..."],         1–2 paragraphs, 40–130 words, about "the_regular"
 "facts_used": ["fact id", ...]}"""


# ── brief ────────────────────────────────────────────────────────────────

def bird(s, ed):
    """A detected species as the model sees it."""
    b = {"name": s.com, "scientific": s.sci, "calls_in_window": s.n,
         "first_heard": day_clock(s.first_at, ed), "last_heard": day_clock(s.last_at, ed),
         "station_history": f"heard on {s.days_total} of the {ed.station_days} days the station "
                            f"has been listening"}
    if ed.station_days and s.days_total / ed.station_days >= MOST_DAYS:
        b["presence"] = "heard on most of the days the station has been listening"
    if s.dawn_first_at:
        b["dawn_first_call"] = clock(s.dawn_first_at)
        b["dawn_first_call_vs_sunrise"] = relative_to(s.dawn_first_at, ed.sunrise, "sunrise")
    if s.night_first_at:
        b["first_call_after_dark"] = day_clock(s.night_first_at, ed)
    if s.first_ever:
        b["news"] = "first time the station has ever recorded it"
    elif s.returning_after_days:
        b["news"] = f"back after {s.returning_after_days} days unheard"
    elif s.record_day:
        b["news"] = f"busiest day yet for it; previous best was {s.prior_best_day} calls in a day"
    elif s.arrived_on:
        b["news"] = f"first heard this stay on {s.arrived_on:%A %-d %B}"
    if regional_phrase(s):
        b["regional_status"] = regional_phrase(s)
    if season_phrase(s):
        b["season"] = season_phrase(s)
    return b


def brief(ed):
    facts = {}
    for s, f in ed.facts:
        facts.setdefault(s.sci, []).append({"id": f["id"], "text": f["text"]})
    lead = ed.lead and {**bird(ed.lead, ed), "facts": facts.get(ed.lead.sci, [])}
    regular = ed.regular and {**bird(ed.regular, ed), "facts": facts.get(ed.regular.sci, [])}
    heard = {s.sci for s in ed.credible}
    seasonal = [e["note"] for e in kb.seasonal_notes(ed.date.month)
                if not e["species"] or heard & set(e["species"])]
    busiest = ed.busiest_hour
    b = {
        "today": f"{ed.date:%A %-d %B %Y} (the edition's date; times without 'yesterday' are today)",
        "yesterday": f"{ed.date - timedelta(days=1):%A %-d %B}",
        "edition_number": ed.number,
        "window": f"the 24 hours to {clock(ed.window_end)} today",
        "first_light": clock(ed.civil_dawn),
        "sunrise": clock(ed.sunrise),
        "dawn_window_ends": clock(ed.dawn_end),
        "dawn_clipped_at_press_time": ed.dawn_clipped,
        "species_heard": len(ed.credible),
        "calls_heard": ed.total_detections,
        "species_heard_phrase": plural(len(ed.credible), "species", "species"),
        "busiest_hour": f"{clock_hour(busiest)} to {clock_hour((busiest + 1) % 24)}",
        "busiest_hour_calls": ed.busiest_hour_n,
        "lead": lead,
        "the_regular": regular,
        "dawn_chorus_in_order": [{"name": s.com, "first_call": clock(s.dawn_first_at),
                                  "vs_first_light": relative_to(s.dawn_first_at, ed.civil_dawn, "first light"),
                                  "vs_sunrise": relative_to(s.dawn_first_at, ed.sunrise, "sunrise")}
                                 for s in ed.dawn_chorus],
        "after_dark": [{"name": s.com, "first_call": day_clock(s.night_first_at, ed), "calls": s.night_n}
                       for s in ed.night_shift],
        "arrivals_this_week": [s.com for s in ed.arrivals],
        "all_species_heard": [{"name": s.com, "calls": s.n} for s in ed.credible],
        "seasonal_context": seasonal,
    }
    if ed.avg7_detections is not None:
        b["seven_day_average_calls"] = round(ed.avg7_detections)
        b["seven_day_average_species"] = round(ed.avg7_species)
    return b


def clock_hour(h):
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


# ── validation ───────────────────────────────────────────────────────────

UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine".split())}


def digits(text):
    """'sixteen minutes', 'twenty-six minutes', 'a minute' → '16 minutes', '26 minutes', '1 minute'."""
    def tens_units(m):
        return str(NUMBER_WORDS[m.group(1).lower()] + UNITS[m.group(2).lower()])
    text = re.sub(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ](one|two|three|four|five|six|"
                  r"seven|eight|nine)\b", tens_units, text, flags=re.I)
    text = re.sub(r"\b(a|an|one) (minute|hour)\b", r"1 \2", text, flags=re.I)
    return re.sub(r"\b[a-z]+\b", lambda m: str(NUMBER_WORDS.get(m.group(0).lower(), m.group(0))),
                  text, flags=re.I)


def words(text):
    return len(re.findall(r"[A-Za-z0-9'’-]+", text))


def numbers_in(text):
    """Digits, plus number words from two to twenty, as strings."""
    out = set(kb.numbers(TIME.sub(" ", text)))
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in NUMBER_WORDS:
            out.add(str(NUMBER_WORDS[w]))
    return out


def times_in(text):
    return {f"{int(h)}:{m} {ap.lower()}" for h, m, ap in TIME.findall(text)}


def name_pattern(name):
    return re.compile(r"\b" + re.escape(name.lower()) + r"(?:s|es)?\b")


def time_owners(ed):
    """clock time → names of the birds it belongs to ('' for the solar times).
    Keys are "6:46 am" and also "6:46 am yesterday" for calls before the
    edition's date."""
    owners = {}

    def add(t, who):
        if t:
            owners.setdefault(clock(t), set()).add(who)
            if t.date() < ed.date:
                owners.setdefault(clock(t) + " yesterday", set()).add(who)

    for s in ed.credible:
        for t in (s.first_at, s.last_at, s.dawn_first_at, s.night_first_at):
            add(t, s.com.lower())
    for t in (ed.civil_dawn, ed.sunrise, ed.dawn_end, ed.window_end, ed.window_start):
        add(t, "")
    return owners


def sentences(text):
    return re.split(r"(?<=[.;?!])\s+", text)


def problems(out, b, ed):
    """→ list of problems with a reply (empty = publishable)."""
    p = []
    if not isinstance(out, dict):
        return ["reply is not a JSON object"]
    for key in LIMITS:
        if key not in out:
            p.append(f"missing {key}")
    if p:
        return p
    for key in ("lead_story", "regular_column"):
        if isinstance(out[key], str):
            out[key] = [out[key]]
        if not isinstance(out[key], list) or not all(isinstance(x, str) for x in out[key]):
            p.append(f"{key} must be a list of paragraph strings")
    for key in ("headline", "standfirst", "dawn_paragraph"):
        if not isinstance(out[key], str):
            p.append(f"{key} must be a string")
    if p:
        return p
    if ed.regular is None:
        out["regular_column"] = []
    texts = {k: (" ".join(v) if isinstance(v, list) else v) for k, v in out.items() if k in LIMITS}

    for key, (lo, hi) in LIMITS.items():
        if key == "regular_column" and ed.regular is None:
            continue
        n = words(texts[key])
        if not lo <= n <= round(hi * 1.1):          # 10% grace over the stated limit
            p.append(f"{key} is {n} words; it must be {lo}–{hi}")
    if len(out["headline"]) > HEADLINE_MAX_CHARS:
        p.append(f"headline is {len(out['headline'])} characters; keep it under {HEADLINE_MAX_CHARS}")

    source = json.dumps(b, ensure_ascii=False)
    # fact ids end in a hex hash; their digits mustn't count as allowed numbers
    allowed_numbers = numbers_in(re.sub(r'"id": "[^"]*"', "", source))
    allowed_times = times_in(source)
    owners = time_owners(ed)
    night_birds = {s.com.lower() for s in ed.night_shift}
    # a sentence that names no bird ("It was first heard at…") is about the section's bird
    section_bird = {"lead_story": ed.lead and ed.lead.com.lower(),
                    "regular_column": ed.regular and ed.regular.com.lower()}
    detected = {s.com.lower() for s in ed.credible}
    in_brief = source.lower()
    brief_digits = digits(in_brief)
    used_ids = out.get("facts_used") if isinstance(out.get("facts_used"), list) else []
    used_text = " ".join(f["text"] for _, f in ed.facts if f["id"] in used_ids).lower()
    all_names = {kb.display_name(sci, com).lower() for sci, com in kb.include_list()} | \
                {com.lower() for _, com in kb.include_list()}

    for key, text in texts.items():
        low = text.lower()
        extra = numbers_in(text) - allowed_numbers
        if extra:
            p.append(f"{key}: number(s) {', '.join(sorted(extra))} are not in the brief")
        bad_times = times_in(text) - allowed_times
        if bad_times:
            p.append(f"{key}: time(s) {', '.join(sorted(bad_times))} are not in the brief")
        for name in all_names:
            if name_pattern(name).search(low) and name not in detected and name not in in_brief:
                p.append(f"{key}: names the {name}, which isn't in the brief")
        for sent in sentences(text):
            sl = sent.lower()
            named = {w for w in detected if name_pattern(w).search(sl)}
            subject = named or ({section_bird[key]} if section_bird.get(key) else set())
            if NIGHT.search(sent) and not any(m.group(0).lower() in used_text for m in NIGHT.finditer(sent)):
                if not subject & night_birds:
                    p.append(f"{key}: \"{sent.strip()[:90]}\" says after dark/overnight, but that bird "
                             f"isn't in after_dark")
            if "yesterday" in sl and subject and not times_in(sent):
                birds = [s for s in ed.credible if s.com.lower() in subject]
                if birds and all(s.first_at.date() == ed.date for s in birds):
                    p.append(f"{key}: \"{sent.strip()[:90]}\" says yesterday, but those calls were all today")
            for t in times_in(sent):
                who = owners.get(t, set())
                if "" in who and any(w in sl for w in SOLAR_WORDS):
                    continue
                named = {w for w in detected if name_pattern(w).search(sl)}
                if not named and section_bird.get(key):
                    named = {section_bird[key]}
                if not named & who:
                    p.append(f"{key}: \"{sent.strip()[:90]}\" gives {t}, which doesn't belong to "
                             f"the bird named there")
        if re.search(r"\bconfiden|\bbirdnet\b|\balgorithm|\bAI\b", text, re.I):
            p.append(f"{key}: don't mention confidence, BirdNET or the algorithm")
        for m in OFFSET.finditer(text):
            if digits(m.group(0)).lower() not in brief_digits and m.group(0).lower() not in used_text:
                p.append(f"{key}: \"{m.group(0)}\" is a gap you worked out; copy offsets from vs_sunrise / "
                         f"vs_first_light or leave them out")
        for m in META.finditer(text):
            p.append(f"{key}: \"{m.group(0)}\" talks about your inputs; write about the birds")
        for m in SUPERLATIVE_PRESENCE.finditer(text):
            if m.group(0).lower() in used_text:
                continue
            p.append(f"{key}: \"{m.group(0)}\" — the brief doesn't rank birds by how often they're heard")
        for m in GUESSWORK.finditer(text):
            p.append(f"{key}: \"{m.group(0)}\" is a guess about where the bird went")
        if key in ("headline", "standfirst") and ARRIVAL.search(text) and not (ed.lead and ed.lead.arrival):
            p.append(f"{key}: \"{ARRIVAL.search(text).group(0)}\" — the lead bird isn't an arrival or return")
        for m in COMPARISON.finditer(text):
            if m.group(0).lower() in used_text:      # the fact itself says "usually"
                continue
            p.append(f"{key}: \"{m.group(0)}\" is a comparison the brief doesn't make")
        regular = {"lead_story": ed.lead, "regular_column": ed.regular}.get(key)
        presence_ok = regular is not None and ed.station_days and \
            regular.days_total / ed.station_days >= MOST_DAYS
        for m in PRESENCE.finditer(text):
            if not presence_ok and m.group(0).lower() not in used_text:
                p.append(f"{key}: \"{m.group(0)}\" — the brief doesn't say this bird is heard on most days")
        for m in PLACE.finditer(text):
            if m.group(0).lower() not in in_brief:
                p.append(f"{key}: don't describe the place (\"{m.group(0)}\")")
        try:
            scrub.check(text)
        except scrub.ScrubError as e:
            p.append(f"{key}: {str(e).splitlines()[1].strip()}")

    ids = {f["id"] for s, f in ed.facts}
    used = out.get("facts_used", [])
    if not isinstance(used, list) or not all(isinstance(x, str) for x in used):
        p.append("facts_used must be a list of fact ids")
    else:
        unknown = [x for x in used if x not in ids]
        if unknown:
            p.append(f"facts_used has unknown ids: {unknown}")
    return p


# ── HTML and the call ────────────────────────────────────────────────────

def to_html(text, ed):
    """Escape model text, then italicise the scientific names we know."""
    out = html.escape(text, quote=False)
    for s in ed.species:
        out = out.replace(s.sci, f"<i>{s.sci}</i>")
    return out


def glm_prose(ed, cfg, log=print):
    """→ prose dict (source "glm") or None after cfg llm.attempts failures.
    Raises glm.QuotaError so the caller can note it; never anything else."""
    if ed.lead is None:
        return None
    b = brief(ed)
    base = "Brief:\n" + json.dumps(b, ensure_ascii=False, indent=1)
    model, attempts = cfg["llm"]["model"], cfg["llm"]["attempts"]
    feedback = ""
    for attempt in range(1, attempts + 1):
        user = base
        if feedback:
            user += f"\n\nYour last draft had problems:\n{feedback}\nWrite it again, fixing every one."
        try:
            out = glm.chat_json(model, SYSTEM, user, temperature=0.6)
        except glm.QuotaError:
            raise
        except Exception as e:  # noqa: BLE001 — network, bad JSON
            log(f"  glm attempt {attempt}: {e}")
            continue
        probs = problems(out, b, ed)
        if not probs:
            return {
                "headline": out["headline"].strip().rstrip("."),
                "standfirst": out["standfirst"].strip(),
                "lead_story": [to_html(x.strip(), ed) for x in out["lead_story"] if x.strip()],
                "dawn_paragraph": out["dawn_paragraph"].strip(),
                "regular_column": [to_html(x.strip(), ed) for x in out["regular_column"] if x.strip()],
                "facts_used": list(dict.fromkeys(out.get("facts_used", []))),
                "source": "glm",
                "attempts": attempt,
            }
        log(f"  glm attempt {attempt} rejected: " + "; ".join(probs))
        feedback = "\n".join(f"- {x}" for x in probs[:10])
    return None
