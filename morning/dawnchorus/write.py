"""Prose for an edition.

`template_prose` builds every text block from the computed facts alone. It
is the phase 1 writer and, from phase 3, the fallback when GLM fails
validation. The GLM writer returns the same keys.
"""

from datetime import datetime

from . import kb

NUMBER_WORDS = "no one two three four five six seven eight nine ten eleven twelve".split()


def clock(t):
    """6:46 am"""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"


def day_clock(t, ed):
    """'6:46 am', or 'yesterday at 5:30 pm' for the evening before."""
    return clock(t) if t.date() == ed.date else f"{clock(t)} yesterday"


def num(n):
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def times(n):
    return "once" if n == 1 else "twice" if n == 2 else f"{num(n)} times"


def plural(n, word, many=None):
    return f"{num(n)} {word if n == 1 else many or word + 's'}"


def join(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def regional_phrase(s):
    if s.regional_occ is None:
        return None
    if s.regional_rarity >= 0.66:
        return "one of the scarcer birds in the Canberra region"
    if s.regional_rarity >= 0.33:
        return "a moderately common bird around Canberra"
    return "one of the most widespread birds around Canberra"


SEASON_PHRASE = {
    "resident": "lives in the Canberra region year-round",
    "summer migrant": "is a summer migrant to the Canberra region",
    "winter visitor": "comes to the Canberra region mainly in winter",
    "rare visitor": "is a rare visitor to the ACT",
}


def season_phrase(s):
    """From ALA records (knowledge base); None when the data is too thin."""
    sp = kb.species(s.sci)
    season = sp and sp["seasonality"]
    if not season or (season["confidence"] != "high" and season["class"] != "rare visitor"):
        return None
    text = SEASON_PHRASE[season["class"]]
    if season["class"] in ("summer migrant", "winter visitor"):
        text += f", most often recorded in {join(kb.MONTH_NAMES[kb.MONTHS.index(m)] for m in season['peak'])}"
    return text


def relative_to(t, ref, ref_name):
    mins = round((t - ref).total_seconds() / 60)
    if mins == 0:
        return f"right at {ref_name}"
    word = "after" if mins > 0 else "before"
    return f"{plural(abs(mins), 'minute')} {word} {ref_name}"


def headline(ed):
    s = ed.lead
    if s is None:
        return "A quiet day at the station"
    if s.first_ever:
        return f"{s.com} makes its station debut"
    if s.returning_after_days:
        return f"{s.com} back after {s.returning_after_days} days"
    if s.record_day:
        return f"Big day for the {s.com}"
    if s.arrived_on:
        return f"{s.com} settles in"
    n = num(len(ed.credible))
    return f"{s.com} heads {'an' if n[0] in 'aeiou' else 'a'} {n}-species day"


def lead_story(ed):
    s = ed.lead
    paras = [
        f"The {s.com} (<i>{s.sci}</i>) was heard {times(s.n)} in the 24 hours to "
        f"{clock(ed.window_end)}, first at {day_clock(s.first_at, ed)}"
        + (f" and last at {day_clock(s.last_at, ed)}." if s.n > 1 else ".")
        + f" Its clearest call scored {round(s.best_conf * 100)}% confidence."
    ]
    history = []
    if s.first_ever:
        history.append("It is the first time the station has recorded one.")
    elif s.returning_after_days:
        history.append(f"The station last heard one {s.returning_after_days} days ago.")
    elif s.record_day:
        history.append(f"That beats its previous best of {plural(s.prior_best_day, 'call')} in a day.")
    if not s.first_ever:
        history.append(f"It has now been heard on {plural(s.days_total, 'day')} "
                       f"of the station's {ed.station_days}.")
    region = regional_phrase(s)
    if region:
        history.append(f"BirdNET's range model rates it {region}.")
    season = season_phrase(s)
    if season:
        history.append(f"Atlas of Living Australia records show it {season}.")
    if history:
        paras.append(" ".join(history))
    if s.dawn_first_at:
        paras.append(f"It joined the dawn chorus at {clock(s.dawn_first_at)}, "
                     f"{relative_to(s.dawn_first_at, ed.sunrise, 'sunrise')}.")
    return paras


def standfirst(ed):
    s = ed.lead
    if s is None:
        return f"Nothing reliable was heard in the 24 hours to {clock(ed.window_end)}."
    return (f"Heard {times(s.n)}, among {plural(len(ed.credible), 'species', 'species')} "
            f"at the station in the last 24 hours.")


def dawn_paragraph(ed):
    first_light = f"First light came at {clock(ed.civil_dawn)} and the sun rose at {clock(ed.sunrise)}."
    chorus = ed.dawn_chorus
    if not chorus:
        return f"{first_light} The dawn was quiet: no bird was heard clearly before {clock(ed.dawn_end)}."
    opener = chorus[0]
    text = f"{first_light} The {opener.com} opened the chorus at {clock(opener.dawn_first_at)}"
    followers = [f"the {s.com}" for s in chorus[1:3]]
    text += f", followed by {join(followers)}." if followers else "."
    if len(chorus) > 3:
        text += f" By {clock(ed.dawn_end)}, {plural(len(chorus), 'species', 'species')} had joined in."
    if ed.dawn_clipped:
        text += f" (This edition went to press at {clock(ed.window_end)}, before the chorus was over.)"
    return text


def regular_column(ed):
    s = ed.regular
    if s is None:
        return []
    paras = [f"Heard {times(s.n)} in the last 24 hours, the {s.com} (<i>{s.sci}</i>) has been "
             f"heard on {plural(s.days_total, 'day')} of the station's {ed.station_days}."]
    if s.dawn_first_at:
        paras.append(f"This morning it was singing by {clock(s.dawn_first_at)}.")
    busiest = max(range(24), key=lambda h: s.hourly[h])
    if s.n >= 3:
        paras.append(f"It was busiest between {clock(datetime(2000, 1, 1, busiest))} and "
                     f"{clock(datetime(2000, 1, 1, (busiest + 1) % 24))}, "
                     f"with {plural(s.hourly[busiest], 'call')}.")
    return paras


def template_prose(ed):
    return {
        "headline": headline(ed),
        "standfirst": standfirst(ed),
        "lead_story": lead_story(ed) if ed.lead else [],
        "dawn_paragraph": dawn_paragraph(ed),
        "regular_column": regular_column(ed),
        "did_you_know": [{"com": s.com, "text": f["text"], "source_url": f["source_url"]} for s, f in ed.facts],
        "source": "template",
    }
