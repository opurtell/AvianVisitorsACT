"""Render an edition to static HTML.

Output layout (the GitHub Pages site root):

    editions/
      index.html          latest edition
      YYYY-MM-DD.html     each edition
      archive.html        list of editions
      editions.json       date -> headline, number, species (feeds the archive)
      styles.css
      birds/<slug>.webp   resized illustrations

Every page passes scrub.check before anything is written.
"""

import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from PIL import Image

from . import config, scrub
from .write import clock

TEMPLATES = config.ROOT / "templates"
ILLUSTRATIONS = config.ROOT.parent / "avian" / "assets" / "illustrations"
ART_WIDTH = 560


def env():
    e = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    e.filters["clock"] = clock
    e.filters["pct"] = lambda x: f"{round(x * 100)}%"
    return e


def hour_label(h):
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


def hour_range(h):
    """7–8 am, 11 am–12 pm"""
    a, b = hour_label(h), hour_label((h + 1) % 24)
    if a[-2:] == b[-2:]:
        a = a[:-3]
    return f"{a}–{b}"


def when(t, ed):
    """6:46 am today, 'Thu 5:30 pm' otherwise."""
    return clock(t) if t.date() == ed.date else f"{t:%a} {clock(t)}"


def sparkline(s, ed, width=120, height=20):
    """24 bars in window order; dawn hours shaded."""
    order = ed.hour_order
    peak = max(s.hourly) or 1
    bw = width / 24
    parts = [f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
             f'role="img" aria-label="{s.com}: calls by hour, from {hour_label(order[0])}">']
    for i, h in enumerate(order):
        x = i * bw
        if h in ed.dawn_hours:
            parts.append(f'<rect class="dawn" x="{x:.1f}" y="0" width="{bw:.1f}" height="{height}"/>')
        n = s.hourly[h]
        if n:
            bh = max(1.5, (height - 2) * n / peak)
            parts.append(f'<rect class="bar" x="{x + 0.6:.1f}" y="{height - bh:.1f}" '
                         f'width="{bw - 1.2:.1f}" height="{bh:.1f}"><title>{hour_label(h)}: {n}</title></rect>')
    parts.append("</svg>")
    return Markup("".join(parts))


def ensure_art(slug, out_dir):
    """Resized WebP copy of the perched illustration; None if there isn't one."""
    src = ILLUSTRATIONS / f"{slug}.png"
    dst = out_dir / "birds" / f"{slug}.webp"
    if not src.exists():
        return None
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            if im.width > ART_WIDTH:
                im = im.resize((ART_WIDTH, round(im.height * ART_WIDTH / im.width)), Image.LANCZOS)
            im.save(dst, "WEBP", quality=82, method=6)
    return f"birds/{slug}.webp"


def load_index(out_dir):
    try:
        with open(out_dir / "editions.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def render_edition(ed, prose, out_dir):
    out_dir = Path(out_dir)
    e = env()
    art = {s.slug: ensure_art(s.slug, out_dir) for s in ed.species}
    html = e.get_template("edition.html.j2").render(
        ed=ed, prose=prose, art=art, sparkline=sparkline, hour_label=hour_label,
        hour_range=hour_range, when=lambda t: when(t, ed),
        prose_html=lambda t: Markup(t),  # template/GLM prose may carry <i>; GLM output is sanitised in write.py
    )
    scrub.check(html)

    name = f"{ed.date.isoformat()}.html"
    (out_dir / name).write_text(html)
    shutil.copy(TEMPLATES / "styles.css", out_dir / "styles.css")

    index = load_index(out_dir)
    index[ed.date.isoformat()] = {
        "number": ed.number,
        "headline": prose["headline"],
        "species": len(ed.credible),
        "lead": ed.lead.com if ed.lead else None,
    }
    index = dict(sorted(index.items(), reverse=True))
    (out_dir / "editions.json").write_text(json.dumps(index, indent=1))

    archive = e.get_template("archive.html.j2").render(editions=index)
    scrub.check(archive)
    (out_dir / "archive.html").write_text(archive)

    # index.html is always the newest edition, so backtesting an old date
    # never replaces today's front page.
    latest = next(iter(index))
    shutil.copy(out_dir / f"{latest}.html", out_dir / "index.html")
    return out_dir / name


def render_stale(today, latest, out_dir):
    """Front page for a morning with no fresh data: says so instead of
    leaving yesterday's edition up. No dated page and no archive entry,
    so the next good run puts a real edition back on index.html."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = load_index(out_dir)
    html = env().get_template("stale.html.j2").render(
        today=today, latest=latest, last_edition=next(iter(index), None))
    scrub.check(html)
    shutil.copy(TEMPLATES / "styles.css", out_dir / "styles.css")
    (out_dir / "index.html").write_text(html)
    return out_dir / "index.html"
