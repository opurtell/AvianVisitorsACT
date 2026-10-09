import importlib.util
import json
import subprocess
from datetime import date, datetime

import pytest

from dawnchorus import config, publish
from dawnchorus.render import render_stale

spec = importlib.util.spec_from_file_location("apply_schedule", config.ROOT / "deploy" / "apply-schedule.py")
apply_schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_schedule)


def test_stale_page_names_last_call_and_last_edition(tmp_path):
    (tmp_path / "editions.json").write_text(json.dumps({"2026-10-08": {}, "2026-10-07": {}}))
    path = render_stale(date(2026, 10, 9), datetime(2026, 10, 8, 19, 12), tmp_path)
    html = path.read_text()
    assert path.name == "index.html"
    assert "7:12 pm on Thursday 8 October" in html
    assert 'href="2026-10-08.html"' in html
    assert not (tmp_path / "2026-10-09.html").exists()


def test_stale_page_without_any_data(tmp_path):
    html = render_stale(date(2026, 10, 9), None, tmp_path).read_text()
    assert "hasn't sent in any calls" in html
    assert "last edition" not in html


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def site(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    site = tmp_path / "site"
    git(tmp_path, "clone", "-q", str(remote), str(site))
    git(site, "config", "user.name", "test")
    git(site, "config", "user.email", "test@example.com")
    return site, remote


def test_publish_commits_and_pushes_then_skips_when_unchanged(site):
    site, remote = site
    (site / "index.html").write_text("<p>hi</p>")
    assert publish.publish("github-pages", site, "Edition 2026-10-09") is True
    log = subprocess.run(["git", "-C", str(remote), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "Edition 2026-10-09" in log
    assert (site / ".nojekyll").exists()
    assert publish.publish("github-pages", site, "again") is False


def test_publish_refuses_a_plain_directory(tmp_path):
    with pytest.raises(publish.PublishError, match="not a git checkout"):
        publish.publish("github-pages", tmp_path, "x")


def test_units_follow_config():
    cfg = config.load()
    service, timer = apply_schedule.units(cfg)
    assert f"OnCalendar=*-*-* {cfg['schedule']['run_time']}:00 {cfg['schedule']['timezone']}" in timer
    assert f"WorkingDirectory={config.ROOT}" in service
    assert "{root}" not in service


def test_units_reject_bad_time():
    with pytest.raises(SystemExit):
        apply_schedule.units({"schedule": {"run_time": "8:30", "timezone": "Australia/Sydney"}})
