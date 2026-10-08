# The Dawn Chorus — morning bird edition (plan)

A static, newspaper-style page published every morning: the birds the ACT
station detected in the last 24 hours, with a highlight on the dawn chorus,
short stories about specific birds (rare ones first, common ones in rotation)
and sourced fun facts. Prose is written by `glm-5.3-flash` from facts the
pipeline computes; the model never supplies numbers or facts of its own.

Status: phase 0 done 2026-10-09; phase 1 next (plan written 2026-10-09). Decided 2026-10-09:
public on GitHub Pages; the Pi joins the tailnet for greg's DB fetch.

## Constraints this must respect

- **Read-only consumer of the Pi.** It never changes `birdnet.conf`, the
  include list or the overlay. The configuration contract and the three
  ACT-only mechanisms in `DEPLOYMENT.md` are untouched.
- **Never inside `avian/`.** The art sync is `rsync --delete avian/`; anything
  this project put under `avian/` on the Pi would be deleted on the next sync.
  Code lives in `morning/`, beside `avian/`.
- **Public page, no location or personal detail.** See [Publishing](#publishing).
- **Secrets** (`GLM_API_KEY`, eBird key, deploy tokens) live in env files on
  the host, never in this repo — which is public.

## Architecture

```
Pi (birds.db) ──ssh snapshot──► greg: run.py   (daily, time set in config.toml)
                                   ├─ analyse    24 h window, dawn window, rarity, firsts
                                   ├─ knowledge/ 197 species, sourced facts
                                   ├─ write      glm-5.3-flash, prose only
                                   └─ render     editions/YYYY-MM-DD.html + index.html
                                                   └─ publish (public static host)
```

The job runs on **greg**, because it's always on, already holds the GLM
credentials and already pushes a static site every morning for
paramedicpapers. The MacBook is the dev box: `run.py --db birdnet` pulls the
DB over the LAN, and `--no-llm` skips the model.

### Source data

`~/BirdNET-Pi/scripts/birds.db`, table `detections` (`Date`, `Time`,
`Sci_Name`, `Com_Name`, `Confidence`, `File_Name`, …), Canberra local time. It
is small (≈2 MB at 7 weeks; ~160 detections/day) and can be copied whole each
run, which keeps all analysis as local SQL in Python.

## Configuration — one file, easy to edit

`morning/config.toml` is the single source of truth. Changing the time means
editing one line and running one command.

```toml
[schedule]
run_time = "08:30"                 # local Canberra time, HH:MM
timezone = "Australia/Sydney"

[windows]
lookback_hours = 24                # ends at the moment the run starts
dawn_start = "civil_dawn"
dawn_end_after_sunrise_min = 90    # clamped to run_time (see below)

[credibility]
min_confidence = 0.75              # or…
min_detections = 3                 # …this many, to be headlined

[llm]
model = "glm-5.3-flash"
attempts = 3

[publish]
target = "github-pages"            # or "lan"
```

`deploy/apply-schedule.py` reads `config.toml` and writes
`~/.config/systemd/user/dawnchorus.timer` with
`OnCalendar=*-*-* 08:30 Australia/Sydney`, then runs `daemon-reload` and
restarts the timer. systemd handles DST itself, so there's no UTC shuffling
(unlike the Hermes jobs' `sync-cron-dst.py`). Changing the time:

```bash
$EDITOR morning/config.toml          # run_time = "07:45"
python3 morning/deploy/apply-schedule.py
systemctl --user list-timers dawnchorus.timer   # confirm next run
```

The timer file is generated, never hand-edited, so the time can't drift
between two places.

**Dawn window vs 08:30.** Dawn runs from civil dawn to sunrise + 90 min, but
never past the run time. In summer it ends ~07:10; in midwinter (sunrise
≈07:13 AEST) it would reach ~08:43, so for a few weeks either side of the June
solstice the window is clipped at 08:30. The edition says "dawn chorus (to
08:30)" when that happens. An earlier `run_time` removes the clipping.

**GLM window.** paramedicpapers' notes keep *bulk* GLM work to 09:00–17:00
Canberra. The daily edition is one call (paramedicpapers makes daily calls at
07:00), so 08:30 is fine; the one-off knowledge build (phase 2) should run
inside 09:00–17:00.

## Repository layout

```
morning/
  PLAN.md
  README.md
  config.toml
  requirements.txt        # astral, jinja2, requests, tomli (py<3.11)
  run.py                  # --date YYYY-MM-DD, --db, --no-llm, --dry-run, --out
  dawnchorus/
    fetch.py              # DB snapshot from the Pi
    analyse.py            # windows, rarity, firsts, hourly profile
    kb.py                 # knowledge loader + fact rotation
    write.py              # GLM call, validation, template fallback
    render.py             # Jinja2 → static HTML
    publish.py            # github-pages | lan
    scrub.py              # public-safety check (see Publishing)
  build_kb.py             # one-off knowledge build
  knowledge/
    species/<genus-species>.json
    seasonal.yaml
  templates/edition.html.j2, index.html.j2, styles.css
  deploy/dawnchorus.service, apply-schedule.py
  tests/
```

## Phases

### 0 · Plumbing

- greg needs to read the Pi's DB. Put the **Pi** on the tailnet (Oscar runs
  `sudo tailscale up` on it, which needs an interactive login). This is
  machine-to-machine only; nobody in the house needs Tailscale to *read* the
  page.
  - Alternative if you'd rather keep the Pi off the tailnet: a Pi cron job
    pushes the snapshot to greg a few minutes before `run_time`.
- On the Pi, give greg a key in `authorized_keys` with
  `command="~/bin/birds-snapshot",no-pty,no-port-forwarding`. The script runs
  `sqlite3 birds.db ".backup /tmp/birds-snap.db"` and streams the file out. A
  plain copy isn't safe while BirdNET is writing, and the key gives greg no
  shell.
- **Done when** `fetch.py` on greg yields a DB whose detection count matches
  the live one.

Progress (2026-10-09):

- [x] `deploy/birds-snapshot` installed on the Pi as `~/bin/birds-snapshot`;
      tested: integrity `ok`, all rows, temp file cleaned up.
- [x] greg key `~/.ssh/birdnet_snapshot` created; authorised on the Pi with
      `from="<greg tailnet IP>",command="/home/oscar/bin/birds-snapshot",restrict`
      (previous file kept as `~/.ssh/authorized_keys.bak-2026-10-09`).
- [x] `dawnchorus/fetch.py` + `config.toml`; tested from the Mac over the LAN
      (`--host birdnet`), and a failed fetch leaves the last snapshot intact.
- [x] Pi joined the tailnet as `birdnet` (`--accept-dns=false`, so the Pi's
      own name resolution is unchanged).
- [x] greg `~/.ssh/config`: `Host birdnet-pi` → Pi tailnet IP, key
      `birdnet_snapshot`, `IdentitiesOnly yes`. `fetch.py` on greg: integrity
      `ok`, row count matches live. Verified the key can't get a shell
      (`PTY allocation request failed`) and ignores any requested command.

### 1 · Analysis and layout (no LLM)

Computed per run:

- **24 h** (to run start) and **dawn** windows, using `astral` for civil
  dawn and sunrise at Canberra.
- Per species: count, best confidence, first and last call, calls by hour,
  first call in the dawn window ("first to sing: Australian Magpie, 05:52").
- History: days detected in the last 90, first ever for the station, first in
  30+ days (a returning migrant).
- **Rarity score** from three signals:
  1. the regional occurrence score in `scripts/act-species-canberra.csv`;
  2. how often the species turns up in ACT records on the Atlas of Living
     Australia (stored in the knowledge base);
  3. how often this station has heard it (weight rises as history grows;
     with under ~3 months of data it counts for little).
- **Credibility gate:** a species is headlined only at confidence ≥ 0.75 or
  ≥ 3 detections. Otherwise it goes in "Heard, unconfirmed". BirdNET false
  positives on rare birds are the biggest risk to the paper's credibility.

Sections:

| Section | Content |
|---|---|
| Masthead | Name, date, sunrise time, edition number |
| Lead story | Top-ranked credible bird, kachō-e illustration, ~150 words |
| Dawn Chorus | Species in the dawn window, in order of first call |
| Arrivals & Returns | First ever / first in 30+ days |
| The Regular | A common bird, rotated to whichever has gone longest unfeatured |
| Did You Know | 2–3 short sourced facts |
| Roll call | All species, counts, small hourly charts (inline SVG) |
| Stats corner | Totals vs 7-day average, busiest hour |
| Heard, unconfirmed | Low-confidence detections, flagged honestly |
| Sources | Wikipedia / ALA attribution, illustration licence |

Layout: CSS multi-column, serif type, readable on a phone, print-friendly.
Illustrations are copied from `avian/assets/` (our own CC-BY-NC-SA art) into
the edition's folder.

**Done when** `run.py --no-llm --date D` renders a correct edition for each
of the last 7 days.

### 2 · Knowledge base (one-off, 09:00–17:00 Canberra)

`build_kb.py`, for each of the 197 species in
`scripts/act-include-species-list.txt`:

1. Fetch Wikipedia sections (description, behaviour, diet, breeding, voice)
   via the MediaWiki API, and ACT occurrence counts by month from the Atlas
   of Living Australia.
2. Compute seasonality (resident / summer migrant / winter visitor / vagrant)
   **from the monthly counts**, not from the LLM.
3. One GLM call turns the source text into a fixed format: 6–10 facts, each
   with `id`, `text`, `source_url` and a `quote` copied word-for-word from
   the source.
4. **Grounding check:** a fact is kept only if its quote appears exactly in
   the fetched text.

`knowledge/seasonal.yaml` is a short, hand-written Canberra calendar (spring
migrant arrivals Sep–Nov, the Yellow-faced Honeyeater's autumn migration,
Gang-gang breeding, …) that gives the writer seasonal context.

A test asserts that the knowledge base covers exactly the 197 species in the
include list, so it can't drift from the include list or `RECONCILIATION.md`.
Spot-check ~20 species by eye before relying on it.

### 3 · GLM writer

- **One call per edition, JSON mode.** Input: the computed facts plus 2–3
  unused knowledge-base facts per featured species, plus the month's
  `seasonal.yaml` entry. Output: headline, standfirst, lead story, dawn
  paragraph, column, Did You Know items.
- **Validation:**
  - every species named was detected or appears in the input;
  - every number in the prose appears in the input;
  - each section is within its length limit;
  - no location finer than "Canberra" (shares `scrub.py`).
- 3 attempts, then fall back to the phase 1 template prose. The edition still
  publishes.
- Tables, counts and times always come from templates, never the model.
- `state/featured.json` records which facts and species were used, so no fact
  repeats within 60 days and common birds take turns.
- **Done when** a 7-day backtest has been read through and judged free of
  invented facts.

### 4 · Deploy on greg

- `deploy/dawnchorus.service` (oneshot, runs `run.py`) plus the timer
  generated from `config.toml`. Keys come from an env file on greg
  (`GLM_API_KEY`, `GLM_BASE_URL`, and later the eBird key).
- Output: `editions/YYYY-MM-DD.html`, `index.html` (the latest edition plus an
  archive list), `feed.xml` (optional).
- **Pi unreachable:** publish a short "no data since …" edition instead of
  silently keeping yesterday's.
- Log to `~/backups/dawnchorus.log`. Optionally add a "Dawn Chorus:" line to
  paramedicpapers' `morning-health-check.py`.
- Add a short section to the project `CLAUDE.md`.

### 5 · Later, optional

- Weather line (overnight low, rain) from Open-Meteo, for Canberra only.
- "Around the ACT" from eBird's notable recent sightings for `AU-ACT`.
- Show the edition on the Surface kiosk in the morning.
- Audio clips: **LAN mode only** (see below).

## Publishing

Two targets, chosen by `publish.target` in `config.toml`.

### Public (recommended) — GitHub Pages

The same pattern as the paramedicpapers dashboard: greg commits the rendered
files to a dedicated public Pages repo (e.g. `opurtell/dawnchorus`) and pushes.
Anyone in the house opens a normal URL, with no Tailscale and no login. A
custom domain can be added later.

What makes it safe to be public, enforced by `scrub.py` before every publish
(the publish aborts on any hit):

- Location is only ever "Canberra". No coordinates, suburb, street, Pi
  hostname, LAN or tailnet address, or `birdnet.conf` values.
- **No audio.** Garden recordings can pick up voices; clips never go public.
- Raw `File_Name`s are never included (they encode paths and timestamps).
- Times appear only as clock times on bird lines ("first heard 05:52"). These
  say when birds sang, not when anyone is home.
- Attribution: Wikipedia (CC BY-SA), ALA, and the illustrations (CC-BY-NC-SA,
  non-commercial; the page has no ads or tracking).

### LAN-only — served by the Pi

If you'd rather keep it in the house: greg (or the Mac) copies the rendered
site to the Pi at `~/BirdSongs/morning/`. That folder is outside the synced
`avian/` tree, so `--delete` can't remove it. Caddy gets one extra route,
`/morning/*`, on the existing site. Anyone on the home Wi-Fi opens
`http://birdnet.local/morning/`, with no Tailscale. This mode can embed the
top audio clip for each featured bird. Downsides: it's unreadable away from
home, and it adds one Caddy change to the Pi (recorded in `DEPLOYMENT.md`).

Both modes use the same render output, so switching is a one-line config
change.

## Risks

| Risk | Mitigation |
|---|---|
| A false-positive rare bird gets headlined | Credibility gate plus the "Heard, unconfirmed" box |
| The LLM invents facts or numbers | Facts only from grounded knowledge-base entries; checks on names and numbers; template fallback |
| Short station history inflates "firsts" | Labelled "first for this station" (true, and apt in spring); history weight in the rarity score grows over time |
| Pi offline or GLM down | Stale-data edition; template prose |
| Something private leaks onto the public page | `scrub.py` blocks the publish; no audio and no file names in public mode |
| Output put under `avian/` gets wiped by the sync | Code in `morning/`; LAN output in `~/BirdSongs/morning/` |

## Open decisions

1. ~~Public or LAN-only~~ — public on GitHub Pages (2026-10-09).
2. ~~Pi on the tailnet or Pi push~~ — Pi on the tailnet (2026-10-09).
3. Masthead name. "The Dawn Chorus" is a placeholder.
