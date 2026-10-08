#!/usr/bin/env python3
"""Build the species knowledge base (one-off; re-run to refresh).

    build_kb.py sources            Wikipedia + ALA for every include-list species
                                   → knowledge/.sources/<slug>.json (cache, not tracked)
                                   → knowledge/species/<slug>.json (metadata; facts kept)
    build_kb.py facts              one GLM call per species → grounded facts
                                   (needs GLM_API_KEY; run 09:00–17:00 Canberra)
    build_kb.py report             coverage, fact counts, seasonality table

Options: --only SLUG ... to limit species, --force to redo finished ones.

Both stages are resumable: a species already done is skipped. A GLM quota
error stops the run cleanly; re-run later to continue.
"""

import argparse
import json
import re
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from dawnchorus import glm, kb
from dawnchorus.config import load as load_config

SOURCES = kb.KNOWLEDGE / ".sources"
EFFORT = kb.KNOWLEDGE / "ala-act-effort.json"
OVERRIDES = kb.KNOWLEDGE / "overrides.toml"

UA = "DawnChorus/0.1 (ACT bird station newsletter; https://github.com/opurtell/AvianVisitorsACT)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
ALA_MATCH = "https://api.ala.org.au/namematching/api/search"
ALA_SEARCH = "https://biocache-ws.ala.org.au/ws/occurrences/search"
ACT = 'state:"Australian Capital Territory"'
ALA_YEARS = (2006, 2025)    # 20 complete years; recent enough to reflect today's birds

# Wikipedia sections worth facts, in priority order (matched on the heading path).
SECTION_ORDER = ["", "descr", "appear", "plumage", "identif", "voice", "vocal", "call", "song",
                 "behav", "diet", "feed", "forag", "food", "breed", "nest", "reprod", "ecology",
                 "habitat", "distrib", "range", "migrat", "movement", "taxonom", "etymol", "name",
                 "human", "cultur", "aborig", "indigen", "conserv", "status", "threat", "predat"]
SKIP = ("see also", "references", "notes", "citations", "works cited", "further reading",
        "external links", "bibliography", "sources", "gallery", "footnotes")
SECTION_CAP = 2500
TOTAL_CAP = 14000

TOPICS = ["appearance", "voice", "behaviour", "diet", "breeding", "habitat", "range", "name",
          "people", "conservation", "other"]
MIN_FACTS, MAX_FACTS = 6, 10
STOP = set("""a an the and or of in on at to for from by with as is are was were be been being it its
this that these those their they them which who whom whose than then also into over under about
can may might often usually sometimes very more most less such other some has have had not only
both each one two but when where while during between among up out off""".split())


# ── HTTP ─────────────────────────────────────────────────────────────────

def get_json(url, params, tries=3):
    full = url + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 — network blips; last one raises
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


# ── sources ──────────────────────────────────────────────────────────────

def split_sections(extract):
    """MediaWiki plain-text extract → [(heading path, text)], lead first."""
    out, path, buf = [], [], []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            out.append((" > ".join(path), text))
        buf.clear()

    for line in extract.splitlines():
        s = line.strip()
        if s.startswith("==") and s.endswith("=="):
            flush()
            level = len(s) - len(s.lstrip("="))
            title = s.strip("= ").strip()
            path = path[:max(0, level - 2)] + [title]
        else:
            buf.append(line)
    flush()
    return out


def section_rank(heading):
    h = heading.lower()
    if not h:
        return 0
    for i, key in enumerate(SECTION_ORDER[1:], 1):
        if key in h:
            return i
    return len(SECTION_ORDER)


def choose_sections(sections):
    """Drop boilerplate, order by usefulness, cap lengths. Order kept stable
    within a rank so subsections stay with their parents."""
    keep = [(h, t) for h, t in sections if not any(h.lower().split(" > ")[0].startswith(s) for s in SKIP)]
    keep.sort(key=lambda ht: section_rank(ht[0]))
    out, total = [], 0
    for h, t in keep:
        t = t[:SECTION_CAP]
        if total + len(t) > TOTAL_CAP:
            break
        out.append((h or "Introduction", t))
        total += len(t)
    return out


def wiki_url(title, heading=None):
    base = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    if heading and heading != "Introduction":
        base += "#" + urllib.parse.quote(heading.split(" > ")[-1].replace(" ", "_"))
    return base


def fetch_wikipedia(sci, override=None):
    d = get_json(WIKI_API, {"action": "query", "format": "json", "formatversion": 2, "redirects": 1,
                            "titles": override or sci, "prop": "extracts|revisions|pageprops",
                            "explaintext": 1, "exsectionformat": "wiki", "rvprop": "ids"})
    page = d["query"]["pages"][0]
    if page.get("missing") or "disambiguation" in page.get("pageprops", {}):
        raise ValueError(f"no usable Wikipedia article for {override or sci}")
    sections = split_sections(page["extract"])
    return {"title": page["title"], "url": wiki_url(page["title"]), "revid": page["revisions"][0]["revid"],
            "sections": sections, "chosen": choose_sections(sections)}


def ala_months(q):
    d = get_json(ALA_SEARCH, [("q", q), ("fq", ACT), ("fq", f"year:[{ALA_YEARS[0]} TO {ALA_YEARS[1]}]"),
                              ("facets", "month"), ("flimit", 20), ("pageSize", 0)])
    by = {f["label"]: f["count"] for r in d.get("facetResults", []) for f in r["fieldResult"]}
    months = [by.get(m, 0) for m in ("January February March April May June July August "
                                     "September October November December").split()]
    return months, d.get("totalRecords", 0)


def fetch_effort():
    if EFFORT.exists():
        return json.loads(EFFORT.read_text())
    months, total = ala_months("class:Aves")
    data = {"query": f"class:Aves, {ACT}, years {ALA_YEARS[0]}–{ALA_YEARS[1]}",
            "fetched": date.today().isoformat(), "months": months, "total": total}
    EFFORT.write_text(json.dumps(data, indent=1) + "\n")
    return data


def fetch_ala(sci, override=None):
    m = get_json(ALA_MATCH, {"q": override or sci})
    if not m.get("success") or m.get("rank") not in ("species", "subspecies"):
        raise ValueError(f"ALA has no species match for {override or sci}: {m.get('issues')}")
    # A subspecies match can be the wrong race (Chrysococcyx lucidus → the NZ
    # nominate), and would miss records identified only to species: count
    # the whole species.
    name, lsid = m.get("species") or m["scientificName"], m.get("speciesID") or m["taxonConceptID"]
    months, total = ala_months(f'lsid:"{lsid}"')
    return {"name": name, "lsid": lsid, "match": m.get("matchType"),
            "years": list(ALA_YEARS), "months": months, "total": total}


def species_path(slug):
    return kb.SPECIES_DIR / f"{slug}.json"


def write_species(slug, data):
    kb.SPECIES_DIR.mkdir(parents=True, exist_ok=True)
    species_path(slug).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def season_for(sci, months, effort, overrides):
    s = kb.seasonality(months, effort["months"])
    o = overrides.get("season", {}).get(sci)
    if o:
        s.update({"computed": s["class"], "class": o["class"], "reason": o["reason"]})
    return s


def build_sources(todo, force, overrides, log):
    SOURCES.mkdir(parents=True, exist_ok=True)
    effort = fetch_effort()
    failed = []
    for sci, com in todo:
        slug = kb.slugify(sci)
        cache = SOURCES / f"{slug}.json"
        if cache.exists() and not force:
            src = json.loads(cache.read_text())
        else:
            o = overrides.get("taxa", {}).get(sci, {})
            try:
                src = {"sci": sci, "com": com, "fetched": date.today().isoformat(),
                       "wikipedia": fetch_wikipedia(sci, o.get("wikipedia")),
                       "ala": fetch_ala(sci, o.get("ala"))}
            except Exception as e:  # noqa: BLE001
                log(f"  {sci}: FAILED {e}")
                failed.append(sci)
                continue
            cache.write_text(json.dumps(src, ensure_ascii=False))
            time.sleep(0.3)
        w, a = src["wikipedia"], src["ala"]
        old = json.loads(species_path(slug).read_text()) if species_path(slug).exists() else {}
        write_species(slug, {
            "sci": sci, "com": com, "slug": slug,
            "wikipedia": {"title": w["title"], "url": w["url"], "revid": w["revid"]},
            "ala": {"name": a["name"], "years": a["years"], "months": a["months"], "total": a["total"],
                    "share": round(a["total"] / effort["total"], 7)},
            "seasonality": season_for(sci, a["months"], effort, overrides),
            "facts": old.get("facts", []),
            **({"facts_built": old["facts_built"]} if "facts_built" in old else {}),
        })
        log(f"  {com:32} wiki={w['title']!r:34} ala={a['total']:6}  "
            f"{season_for(sci, a['months'], effort, overrides)['class']}")
    return failed


# ── facts ────────────────────────────────────────────────────────────────

SYSTEM = f"""You turn encyclopedia text about one bird species into short, accurate facts for a
general-audience morning bird newsletter in Canberra, Australia.

Return JSON: {{"facts": [{{"text": "...", "topic": "...", "quote": "..."}}, ...]}}

Rules:
- {MIN_FACTS + 2} to {MAX_FACTS} facts. Each "text" is one plain sentence, 50–200 characters, in the present
  tense, that would interest a curious non-birder. Prefer behaviour, voice, diet, breeding, appearance and
  surprising details; avoid subspecies lists, taxonomic history and measurement tables unless striking.
- "quote" is copied WORD FOR WORD from the source text: one continuous passage, 40–300 characters, that
  states everything the fact says. Do not join passages, fix wording, or drop words in the middle.
- The fact must say nothing the quote does not. Every number in the fact must appear in the quote.
- Name the bird by its common name or "it"; never mention the encyclopedia, an article or "sources".
- "topic" is one of: {", ".join(TOPICS)}.
- Each fact must cover something different."""


def content_words(text, exclude):
    words = {w[:5] for w in re.findall(r"[a-z]+", text.lower())
             if len(w) > 3 and w not in STOP}
    return words - exclude


def check_fact(f, sections, exclude):
    """→ (problem or None, heading)."""
    if not isinstance(f, dict):
        return "not an object", None
    text, quote, topic = str(f.get("text", "")).strip(), str(f.get("quote", "")).strip(), f.get("topic")
    if not 40 <= len(text) <= 230:
        return f"text is {len(text)} characters (50–200)", None
    if not 30 <= len(quote) <= 400:
        return f"quote is {len(quote)} characters (40–300)", None
    if topic not in TOPICS:
        return f"topic {topic!r} not allowed", None
    low = text.lower()
    if any(w in low for w in ("wikipedia", "article", "according to", "encyclop")):
        return "mentions the source instead of stating the fact", None
    heading = kb.find_quote(quote, sections)
    if heading is None:
        return "quote is not word-for-word in the source text", None
    extra = kb.numbers(text) - kb.numbers(quote)
    if extra:
        return f"number(s) {', '.join(sorted(extra))} not in the quote", None
    words = content_words(text, exclude)
    if words:
        overlap = len(words & content_words(quote, set())) / len(words)
        if overlap < 0.5:
            return f"fact says things the quote doesn't (only {overlap:.0%} of its words are in the quote)", None
    return None, heading


def facts_input(src):
    parts = [f"Species: {kb.display_name(src['sci'], src['com'])} ({src['sci']})", ""]
    for heading, text in src["wikipedia"]["chosen"]:
        parts += [f"## {heading}", text, ""]
    return "\n".join(parts)


def facts_for(src, model, attempts, log):
    """→ list of grounded facts (possibly fewer than MIN_FACTS). Raises QuotaError."""
    sections = src["wikipedia"]["chosen"]
    slug, title = kb.slugify(src["sci"]), src["wikipedia"]["title"]
    name = kb.display_name(src["sci"], src["com"])
    exclude = content_words(f"{src['com']} {name} {src['sci']} {title} bird birds species", set())
    base = facts_input(src)
    kept, feedback = {}, ""
    for attempt in range(1, attempts + 1):
        user = base
        if feedback:
            user += (f"\n\nAlready accepted ({len(kept)}): " + " | ".join(f["text"] for f in kept.values())
                     + f"\nRejected last time:\n{feedback}\nGive {MIN_FACTS + 2 - len(kept)} or more NEW facts, "
                     "different from the accepted ones, following every rule.")
        try:
            reply = glm.chat_json(model, SYSTEM, user)
        except glm.QuotaError:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"    attempt {attempt}: {e}")
            time.sleep(5)
            continue
        rejects = []
        for f in reply.get("facts", []) if isinstance(reply, dict) else []:
            problem, heading = check_fact(f, sections, exclude)
            if problem:
                rejects.append(f"- {str(f.get('text', ''))[:120]!r}: {problem}" if isinstance(f, dict) else f"- {problem}")
                continue
            fid = kb.fact_id(slug, f["quote"])
            if fid in kept or any(x["text"].lower() == f["text"].strip().lower() for x in kept.values()):
                continue
            kept[fid] = {"id": fid, "text": f["text"].strip(), "topic": f["topic"],
                         "source_url": wiki_url(title, heading), "quote": f["quote"].strip()}
        log(f"    attempt {attempt}: kept {len(kept)}, rejected {len(rejects)}")
        if len(kept) >= MIN_FACTS + 2:
            break
        feedback = "\n".join(rejects[:8]) or "- (none rejected; there were too few facts)"
    return list(kept.values())[:MAX_FACTS]


def build_facts(todo, force, cfg, log, workers=2):
    model, attempts = cfg["llm"]["model"], cfg["llm"]["attempts"]
    jobs = []
    for sci, com in todo:
        slug = kb.slugify(sci)
        path, cache = species_path(slug), SOURCES / f"{slug}.json"
        if not path.exists() or not cache.exists():
            log(f"  {com}: no sources yet — run `build_kb.py sources` first")
            continue
        if json.loads(path.read_text()).get("facts") and not force:
            continue
        jobs.append((slug, path, cache))
    log(f"{len(jobs)} species to do")
    stop = []

    def one(job):
        slug, path, cache = job
        if stop:
            return
        src = json.loads(cache.read_text())
        lines = []
        try:
            facts = facts_for(src, model, attempts, lines.append)
        except glm.QuotaError as e:
            stop.append(str(e))
            log(f"  {src['com']}: GLM quota — stopping. {e}")
            return
        data = json.loads(path.read_text())
        data["facts"] = facts
        data["facts_built"] = {"model": model, "date": date.today().isoformat(),
                               "wikipedia_revid": src["wikipedia"]["revid"]}
        write_species(slug, data)
        flag = "" if len(facts) >= MIN_FACTS else "  ← SHORT"
        log(f"  {src['com']:32} {len(facts):2} facts{flag}\n" + "\n".join(lines))

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, jobs))
    return 1 if stop else 0


# ── report ───────────────────────────────────────────────────────────────

def report(todo, log):
    by_class, short, missing = {}, [], []
    for sci, com in todo:
        p = species_path(kb.slugify(sci))
        if not p.exists():
            missing.append(sci)
            continue
        d = json.loads(p.read_text())
        s = d["seasonality"]
        by_class.setdefault(s["class"], []).append(com + ("" if s["confidence"] == "high" else "°"))
        if len(d["facts"]) < MIN_FACTS:
            short.append(f"{com} ({len(d['facts'])})")
    log(f"{len(todo) - len(missing)}/{len(todo)} species files; missing: {missing or 'none'}")
    log(f"fewer than {MIN_FACTS} facts: {len(short)}: {', '.join(short) or 'none'}")
    log("° = low confidence (under %d ACT records)" % kb.CONFIDENT_RECORDS)
    for cls, coms in sorted(by_class.items()):
        log(f"\n{cls} ({len(coms)}): {', '.join(sorted(coms))}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["sources", "facts", "report"])
    ap.add_argument("--only", nargs="+", metavar="SLUG")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args(argv)

    todo = kb.include_list()
    if args.only:
        todo = [(s, c) for s, c in todo if kb.slugify(s) in args.only]
    with open(OVERRIDES, "rb") as f:
        overrides = tomllib.load(f)

    def log(msg):
        print(msg, flush=True)

    if args.stage == "sources":
        failed = build_sources(todo, args.force, overrides, log)
        if failed:
            log(f"\n{len(failed)} failed: {failed}")
            return 1
        return 0
    if args.stage == "facts":
        return build_facts(todo, args.force, load_config(), log, args.workers)
    report(todo, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
