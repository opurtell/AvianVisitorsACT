import json
import tomllib
from datetime import date, timedelta

import pytest

import build_kb
from dawnchorus import kb

KB = kb.load_all()
INCLUDE = kb.include_list()


# ── the built knowledge base ─────────────────────────────────────────────

def test_covers_exactly_the_include_list():
    assert len(INCLUDE) == 197
    assert {s for s, _ in INCLUDE} == set(KB)
    files = {p.stem for p in kb.SPECIES_DIR.glob("*.json")}
    assert files == {kb.slugify(s) for s, _ in INCLUDE}
    for sci, com in INCLUDE:
        assert KB[sci]["com"] == com and KB[sci]["slug"] == kb.slugify(sci)


def test_every_species_has_facts_and_seasonality():
    for sci, d in KB.items():
        assert len(d["facts"]) >= 3, f"{sci}: only {len(d['facts'])} facts"
        assert d["seasonality"]["class"] in ("resident", "summer migrant", "winter visitor", "rare visitor")
        assert d["seasonality"]["confidence"] in ("high", "low")
        assert len(d["ala"]["months"]) == 12


def test_facts_are_well_formed():
    for sci, d in KB.items():
        ids = set()
        for f in d["facts"]:
            assert f["id"] == kb.fact_id(d["slug"], f["quote"]), f
            assert f["id"] not in ids
            ids.add(f["id"])
            assert f["topic"] in build_kb.TOPICS
            assert f["source_url"].startswith(d["wikipedia"]["url"])
            assert kb.numbers(f["text"]) <= kb.numbers(f["quote"]), f


def test_facts_are_grounded_in_the_fetched_source():
    """Quotes appear in the source text. Needs knowledge/.sources (not tracked)."""
    if not build_kb.SOURCES.exists():
        pytest.skip("no source cache; run build_kb.py sources")
    for sci, d in KB.items():
        src = json.loads((build_kb.SOURCES / f"{d['slug']}.json").read_text())
        assert src["wikipedia"]["revid"] == d["facts_built"]["wikipedia_revid"]
        for f in d["facts"]:
            assert kb.find_quote(f["quote"], src["wikipedia"]["chosen"]), f


def test_seasonal_calendar_matches_include_list_and_data():
    with open(kb.SEASONAL, "rb") as fh:
        cal = tomllib.load(fh)["entry"]
    ids = [e["id"] for e in cal]
    assert len(ids) == len(set(ids))
    for e in cal:
        assert e["months"] and all(1 <= m <= 12 for m in e["months"]), e["id"]
        assert e["note"] and e["basis"], e["id"]
        for sci in e["species"]:
            assert sci in KB, f"{e['id']}: {sci} not in the include list"
            if "expect" in e:
                assert KB[sci]["seasonality"]["class"] == e["expect"], f"{e['id']}: {sci}"
    assert {e["id"] for e in kb.seasonal_notes(4)} >= {"yellow-faced-migration", "winter-robins"}


# ── seasonality ──────────────────────────────────────────────────────────

FLAT = [1000] * 12


def test_resident():
    assert kb.seasonality([100] * 12, FLAT)["class"] == "resident"


def test_summer_migrant_and_winter_visitor():
    summer = [100, 75, 30, 3, 0, 0, 0, 3, 20, 75, 100, 110]      # 516 records
    winter = summer[6:] + summer[:6]
    s = kb.seasonality(summer, FLAT)
    assert s["class"] == "summer migrant" and s["confidence"] == "low"
    assert s["peak"] == ["Jan", "Nov", "Dec"]
    assert kb.seasonality([x * 2 for x in winter], FLAT)["class"] == "winter visitor"
    assert kb.seasonality([x * 2 for x in winter], FLAT)["confidence"] == "high"


def test_effort_spike_is_not_a_season():
    """Twice the records in October because twice the observers: still resident."""
    effort = [1000] * 12
    effort[9] = 2000
    counts = [100] * 12
    counts[9] = 200
    s = kb.seasonality(counts, effort)
    assert s["class"] == "resident" and s["rel"][9] == 1.0


def test_few_records_is_rare_visitor():
    assert kb.seasonality([30, 20, 10, 0, 0, 0, 0, 0, 0, 10, 20, 30], FLAT)["class"] == "rare visitor"


# ── grounding ────────────────────────────────────────────────────────────

SECTIONS = [("Introduction", "The bird’s call is a  loud ‘creaky gate’ — heard at dawn."),
            ("Diet", "It eats seeds, 3–4 kinds of berry and insects.")]


def test_quote_matching_tolerates_typography_only():
    assert kb.find_quote("bird's call is a loud 'creaky gate' - heard", SECTIONS) == "Introduction"
    assert kb.find_quote("It eats seeds, 3-4 kinds", SECTIONS) == "Diet"
    assert kb.find_quote("bird's call is a very loud 'creaky gate'", SECTIONS) is None
    assert kb.find_quote("It eats seeds and insects", SECTIONS) is None
    assert kb.find_quote("", SECTIONS) is None


def test_check_fact():
    excl = build_kb.content_words("Test Bird Testus birdus bird birds species", set())

    def check(text, quote, topic="diet"):
        return build_kb.check_fact({"text": text, "quote": quote, "topic": topic}, SECTIONS, excl)[0]

    assert check("It eats seeds, three or four kinds of berry, and insects too.",
                 "It eats seeds, 3–4 kinds of berry and insects.") is None
    assert "number" in check("It eats seeds and 12 kinds of berry, as well as insects.",
                             "It eats seeds, 3–4 kinds of berry and insects.")
    assert "word-for-word" in check("It eats seeds and berries and many insects.",
                                    "It eats seeds, many kinds of berry and insects.")
    assert "quote doesn't" in check("It migrates to Borneo each winter to breed in mangrove swamps.",
                                    "It eats seeds, 3–4 kinds of berry and insects.")
    assert "source" in check("According to Wikipedia it eats seeds, berries and insects.",
                             "It eats seeds, 3–4 kinds of berry and insects.")
    assert "topic" in check("It eats seeds, three or four kinds of berry, and insects too.",
                            "It eats seeds, 3–4 kinds of berry and insects.", topic="gossip")


def test_split_and_choose_sections():
    text = "Lead para.\n\n== Description ==\nGrey.\n\n=== Voice ===\nLoud.\n\n== References ==\nx\n\n== Breeding ==\nEggs."
    secs = build_kb.split_sections(text)
    assert secs == [("", "Lead para."), ("Description", "Grey."), ("Description > Voice", "Loud."),
                    ("References", "x"), ("Breeding", "Eggs.")]
    chosen = [h for h, _ in build_kb.choose_sections(secs)]
    assert chosen == ["Introduction", "Description", "Description > Voice", "Breeding"]
    assert build_kb.wiki_url("Gang-gang cockatoo", "Behaviour > Breeding habits") == \
        "https://en.wikipedia.org/wiki/Gang-gang_cockatoo#Breeding_habits"


# ── rotation ─────────────────────────────────────────────────────────────

def fake_kb(tmp_path, facts):
    d = tmp_path / "species"
    d.mkdir()
    (d / "testus-birdus.json").write_text(json.dumps({"sci": "Testus birdus", "facts": facts}))
    return d


def test_pick_facts_rotation_and_variety(tmp_path):
    facts = [{"id": f"f{i}", "text": f"Fact {i}.", "topic": t} for i, t in
             enumerate(["diet", "diet", "voice", "breeding"])]
    path = fake_kb(tmp_path, facts)
    day = date(2026, 10, 9)
    first = kb.pick_facts("Testus birdus", {}, day, 2, path)
    assert [f["id"] for f in first] == ["f2", "f0"]            # one per topic, livelier first
    used = {f["id"]: day for f in first}
    second = kb.pick_facts("Testus birdus", used, day + timedelta(days=1), 2, path)
    assert {f["id"] for f in second} == {"f1", "f3"}           # no repeats
    used.update({f["id"]: day + timedelta(days=1) for f in second})
    assert kb.pick_facts("Testus birdus", used, day + timedelta(days=2), 2, path) == []
    later = kb.pick_facts("Testus birdus", used, day + timedelta(days=kb.FACT_REPEAT_DAYS), 2, path)
    assert [f["id"] for f in later] == ["f2", "f0"]            # back after 60 days
    assert kb.pick_facts("Nonexistent", {}, day, 2, path) == []


def test_pick_facts_skips_what_scrub_would_block(tmp_path):
    facts = [{"id": "a", "text": "Its wing is 35.52 cm long.", "topic": "appearance"},
             {"id": "b", "text": "It sings at dawn.", "topic": "voice"}]
    path = fake_kb(tmp_path, facts)
    assert [f["id"] for f in kb.pick_facts("Testus birdus", {}, date(2026, 10, 9), 2, path)] == ["b"]


def test_display_names():
    with open(kb.OVERRIDES, "rb") as fh:
        names = tomllib.load(fh)["name"]
    shown = [kb.display_name(s, c) for s, c in INCLUDE]
    assert len(set(shown)) == len(shown)                     # no two birds share a name
    for sci, au in names.items():
        assert sci in KB, sci
        old = KB[sci]["com"]
        for f in KB[sci]["facts"]:                           # facts use the printed name
            assert old.lower() not in f["text"].lower().replace(au.lower(), ""), f["text"]
    for d in KB.values():
        for f in d["facts"]:
            assert "gray" not in f["text"].lower(), f["text"]
    assert kb.display_name("Rhipidura albiscapa", "Gray Fantail") == "Grey Fantail"
    assert kb.display_name("Gymnorhina tibicen", "Australian Magpie") == "Australian Magpie"
