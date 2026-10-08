"""The GLM writer's validation and fallback, without the network."""

from datetime import datetime

import pytest

import run
from dawnchorus import glm, glm_write
from dawnchorus.glm_write import brief, problems, to_html
from test_dawnchorus import BOOBOOK, CFG, DAY, MAGPIE, ORIOLE, daily_magpies, edition

WORDS = "Its call carries across the morning air and the column notes it. "


@pytest.fixture
def ed(tmp_path):
    # Oriole (lead): first ever, yesterday 5:00 pm and today 6:40 am (dawn).
    # Magpie (Regular): daily, today 7:00 am.
    rows = daily_magpies(39) + [(datetime(2026, 10, 8, 17, 0), ORIOLE, 0.9),
                                (datetime(2026, 10, 9, 6, 40), ORIOLE, 0.9)]
    return edition(tmp_path, rows, DAY)


def good(ed):
    lead_words = WORDS * 7
    return {
        "headline": "Olive-backed Oriole makes its debut",
        "standfirst": "A first for the station, among three species in the 24 hours to 8:30 am today.",
        "lead_story": [f"The Olive-backed Oriole was first heard at 5:00 pm yesterday. {lead_words}",
                       f"It called again at 6:40 am, {brief(ed)['lead']['dawn_first_call_vs_sunrise']}."],
        "dawn_paragraph": "First light came at 6:03 am. The Olive-backed Oriole called at 6:40 am, and the "
                          "Australian Magpie at 7:00 am. " + WORDS * 2,
        "regular_column": [f"The Australian Magpie called at 7:00 am. {WORDS * 4}"],
        "facts_used": [],
    }


def check(ed, **changes):
    out = {**good(ed), **changes}
    return problems(out, brief(ed), ed)


def test_good_draft_passes(ed):
    assert ed.lead.sci == ORIOLE and ed.regular.sci == MAGPIE
    assert check(ed) == []


def test_invented_numbers_and_times(ed):
    assert any("number" in p for p in check(ed, standfirst="A first among 17 species in the 24 hours to 8:30 am."))
    assert any("number" in p for p in check(ed, standfirst="A first, an hour and fifty minutes after the magpie."))
    assert any("time(s) 6:41 am" in p for p in check(
        ed, dawn_paragraph="The Olive-backed Oriole called at 6:41 am. " + WORDS * 3))


def test_time_must_belong_to_the_bird_named(ed):
    probs = check(ed, dawn_paragraph="The Australian Magpie called at 6:40 am. " + WORDS * 3)
    assert any("doesn't belong" in p for p in probs)
    # a sentence with no bird in the lead story is about the lead bird
    assert check(ed, lead_story=good(ed)["lead_story"]) == []


def test_yesterday_and_after_dark(ed):
    probs = check(ed, regular_column=[f"The Australian Magpie sang yesterday morning. {WORDS * 4}"])
    assert any("all today" in p for p in probs)
    probs = check(ed, regular_column=[f"The Australian Magpie sang after dark. {WORDS * 4}"])
    assert any("after_dark" in p for p in probs)


def test_after_dark_bird_may_be_called_nocturnal(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 2, 15), BOOBOOK, 0.9)]
    ed = edition(tmp_path, rows, DAY)
    assert [s.sci for s in ed.night_shift] == [BOOBOOK]
    out = {"headline": "A night caller", "standfirst": WORDS, "lead_story": [WORDS * 8],
           "dawn_paragraph": "The Southern Boobook called overnight. " + WORDS * 3,
           "regular_column": [WORDS * 4], "facts_used": []}
    probs = problems(out, brief(ed), ed)
    assert not any("after_dark" in p for p in probs)


def test_species_not_in_brief(ed):
    probs = check(ed, dawn_paragraph="A Superb Lyrebird joined in. " + WORDS * 4)
    assert any("superb lyrebird" in p for p in probs)


def test_claims_and_meta(ed):
    assert any("comparison" in p for p in check(ed, standfirst="A quieter day than usual for the birds today."))
    assert any("rank" in p for p in check(ed, standfirst="The most reliable bird was heard again this morning."))
    assert any("guess" in p for p in check(ed, standfirst="An oriole passing through was heard this morning."))
    assert any("inputs" in p for p in check(ed, standfirst="By the brief's account an oriole was heard today."))
    assert any("inputs" in p for p in check(ed, standfirst="Whether it stays is not something the record can say."))
    assert any("place" in p for p in check(ed, standfirst="An oriole was heard in the garden this morning."))
    assert any("BirdNET" in p for p in check(ed, standfirst="BirdNET heard an oriole at the station this morning."))
    # arrival words are fine for a first-ever lead, not otherwise
    assert check(ed, headline="Olive-backed Oriole arrives") == []


def test_presence_words_need_most_days(ed):
    # The magpie (Regular) is heard every day; the oriole (lead) is not
    assert check(ed, regular_column=[f"The Australian Magpie is a fixture. {WORDS * 4}"]) == []
    probs = check(ed, lead_story=["The Olive-backed Oriole is a fixture. " + WORDS * 8])
    assert any("most days" in p for p in probs)


def test_shape_and_lengths(ed):
    assert any("missing" in p for p in problems({"headline": "x"}, brief(ed), ed))
    assert any("words" in p for p in check(ed, lead_story=["Too short."]))
    assert any("unknown ids" in p for p in check(ed, facts_used=["made-up-id"]))


def test_unconfirmed_birds_are_not_in_the_brief(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 7, 0), ORIOLE, 0.6)]
    ed = edition(tmp_path, rows, DAY)
    b = brief(ed)
    assert ed.unconfirmed and "Olive-backed Oriole" not in str(b)
    probs = problems({**good(ed), "standfirst": "An Olive-backed Oriole may have been heard today too."}, b, ed)
    assert any("olive-backed oriole" in p for p in probs)


def test_html_is_escaped_and_scientific_names_italicised(ed):
    assert to_html(f"<script>x</script> {ORIOLE} & co", ed) == \
        f"&lt;script&gt;x&lt;/script&gt; <i>{ORIOLE}</i> &amp; co"


def test_write_uses_glm_when_valid_and_template_otherwise(ed, monkeypatch):
    calls = []

    def fake(model, system, user, temperature=0.3, timeout=120):
        calls.append(user)
        return good(ed) if len(calls) > 1 else {**good(ed), "standfirst": "Seventeen birds."}

    monkeypatch.setattr(glm_write.glm, "chat_json", fake)
    prose = run.write(ed, CFG, True, log=lambda *_: None)
    assert prose["source"] == "glm" and prose["attempts"] == 2
    assert "problems" in calls[1]                       # feedback reached the second attempt

    monkeypatch.setattr(glm_write.glm, "chat_json", lambda *a, **k: {"headline": "x"})
    assert run.write(ed, CFG, True, log=lambda *_: None)["source"] == "template"

    def quota(*a, **k):
        raise glm.QuotaError("429")

    monkeypatch.setattr(glm_write.glm, "chat_json", quota)
    assert run.write(ed, CFG, True, log=lambda *_: None)["source"] == "template"
    assert run.write(ed, CFG, False)["source"] == "template"


def test_did_you_know_skips_facts_the_stories_used(ed):
    from dawnchorus.write import finish
    lead_facts = [f for s, f in ed.facts if s is ed.lead]
    assert len(lead_facts) == 3
    prose = finish(ed, {"facts_used": [lead_facts[0]["id"]]})
    shown = [d["text"] for d in prose["did_you_know"]]
    assert lead_facts[0]["text"] not in shown and lead_facts[1]["text"] in shown
    assert lead_facts[0]["id"] in prose["fact_ids"] and len(prose["fact_ids"]) == 1 + len(shown)
