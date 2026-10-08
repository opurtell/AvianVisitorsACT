import sqlite3
from datetime import date, datetime, timedelta

import pytest

from dawnchorus import config, scrub
from dawnchorus.analyse import analyse, pick_features, run_end_for, stay_start
from dawnchorus.render import render_edition
from dawnchorus.state import History
from dawnchorus.write import template_prose

CFG = config.load()
REGIONAL = {"Gymnorhina tibicen": (0.99, 0.0), "Oriolus sagittatus": (0.27, 0.4), "Ninox boobook": (0.2, 0.7)}
NAMES = {"Gymnorhina tibicen": "Australian Magpie", "Oriolus sagittatus": "Olive-backed Oriole",
         "Ninox boobook": "Southern Boobook"}


def make_db(path, rows):
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE detections (Date DATE, Time TIME, Sci_Name VARCHAR(100), Com_Name VARCHAR(100), "
                "Confidence FLOAT, Lat FLOAT, Lon FLOAT, Cutoff FLOAT, Week INT, Sens FLOAT, Overlap FLOAT, "
                "File_Name VARCHAR(100))")
    for at, sci, conf in rows:
        con.execute("INSERT INTO detections (Date, Time, Sci_Name, Com_Name, Confidence, File_Name) "
                    "VALUES (?, ?, ?, ?, ?, 'x')", (at.date().isoformat(), at.strftime("%H:%M:%S"),
                                                   sci, NAMES[sci], conf))
    con.commit()
    con.close()
    return path


def edition(tmp_path, rows, day, history=None):
    db = make_db(tmp_path / "birds.db", rows)
    ed = analyse(db, run_end_for(day, CFG), CFG, regional=REGIONAL)
    pick_features(ed, history or History({}, tmp_path / "f.json"))
    return ed


DAY = date(2026, 10, 9)  # run 08:30; civil dawn ~06:03, sunrise ~06:29
MAGPIE, ORIOLE, BOOBOOK = "Gymnorhina tibicen", "Oriolus sagittatus", "Ninox boobook"


def daily_magpies(days):
    return [(datetime(2026, 9, 1, 7) + timedelta(days=k), MAGPIE, 0.95) for k in range(days)]


def test_window_edges_and_first_heard_across_midnight(tmp_path):
    rows = daily_magpies(39) + [
        (datetime(2026, 10, 8, 8, 30), ORIOLE, 0.9),     # exactly at window start: excluded
        (datetime(2026, 10, 8, 17, 0), ORIOLE, 0.9),     # yesterday evening: first heard
        (datetime(2026, 10, 9, 6, 10), ORIOLE, 0.9),
        (datetime(2026, 10, 9, 8, 31), ORIOLE, 0.9),     # after run time: excluded
    ]
    ed = edition(tmp_path, rows, DAY)
    oriole = next(s for s in ed.species if s.sci == ORIOLE)
    assert oriole.n == 2
    assert oriole.first_at == datetime(2026, 10, 8, 17, 0)
    assert oriole.dawn_first_at == datetime(2026, 10, 9, 6, 10)


def test_credibility_gate(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 7, 0), ORIOLE, 0.6)]
    ed = edition(tmp_path, rows, DAY)
    assert [s.sci for s in ed.unconfirmed] == [ORIOLE]
    assert ed.lead.sci == MAGPIE


def test_first_ever_leads_and_is_an_arrival(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 6, 40), ORIOLE, 0.9)]
    ed = edition(tmp_path, rows, DAY)
    assert ed.lead.sci == ORIOLE and ed.lead.first_ever
    assert [s.sci for s in ed.arrivals] == [ORIOLE]
    assert "debut" in template_prose(ed)["headline"]


def test_return_after_long_gap(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 9, 1, 7, 5), ORIOLE, 0.9),
                                (datetime(2026, 10, 9, 6, 40), ORIOLE, 0.9)]
    ed = edition(tmp_path, rows, DAY)
    assert ed.lead.returning_after_days == 38
    assert ed.lead.arrived_after_days == 38


def test_stay_start():
    d = [date(2026, 8, 1), date(2026, 8, 20), date(2026, 10, 1), date(2026, 10, 2)]
    assert stay_start(d) == (date(2026, 10, 1), 42)
    assert stay_start(d[:2]) == (date(2026, 8, 1), None)


def test_night_shift(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 2, 15), BOOBOOK, 0.9)]
    ed = edition(tmp_path, rows, DAY)
    assert [s.sci for s in ed.night_shift] == [BOOBOOK]


def test_winter_dawn_is_clipped_to_run_time(tmp_path):
    rows = [(datetime(2026, 5, 1, 9) + timedelta(days=k), MAGPIE, 0.95) for k in range(51)]
    rows.append((datetime(2026, 6, 21, 7, 30), MAGPIE, 0.95))
    ed = edition(tmp_path, rows, date(2026, 6, 21))
    assert ed.dawn_clipped and ed.dawn_end == datetime(2026, 6, 21, 8, 30)
    assert "went to press" in template_prose(ed)["dawn_paragraph"]


def test_recent_lead_is_held_back_without_fresh_news(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 9, 1, 7, 5) + timedelta(days=k), ORIOLE, 0.9) for k in range(39)]
    first = edition(tmp_path, rows, DAY)
    h = History({(DAY - timedelta(days=1)).isoformat(): {"lead": first.lead.sci, "regular": None}},
                tmp_path / "f.json")
    again = edition(tmp_path, rows, DAY, h)
    assert again.lead.sci != first.lead.sci


@pytest.mark.parametrize("bad", ["-35.28", "149.13", "192.168.1.20", "birdnet.local", "By_Date/x.mp3",
                                 "tailscale", "ssh greg", "/home/oscar"])
def test_scrub_blocks(bad):
    with pytest.raises(scrub.ScrubError):
        scrub.check(f"<p>{bad}</p>", extra_terms=[])


def test_scrub_private_terms_and_clean_text():
    with pytest.raises(scrub.ScrubError):
        scrub.check("<p>heard in Myplace today</p>", extra_terms=["Myplace"])
    scrub.check("<p>BirdNET heard a gregarious Galah at 6:46 am in Canberra.</p>", extra_terms=[])


def test_rendered_page_passes_scrub(tmp_path):
    rows = daily_magpies(39) + [(datetime(2026, 10, 9, 6, 40), ORIOLE, 0.9),
                                (datetime(2026, 10, 9, 2, 15), BOOBOOK, 0.9)]
    ed = edition(tmp_path, rows, DAY)
    out = render_edition(ed, template_prose(ed), tmp_path / "site")
    html = out.read_text()
    assert "Olive-backed Oriole" in html and (tmp_path / "site" / "index.html").exists()
