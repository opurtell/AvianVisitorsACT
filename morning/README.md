# The Dawn Chorus

A newspaper-style morning edition of what the ACT station heard in the last
24 hours. Plan, phases and safety rules: [PLAN.md](PLAN.md).

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python run.py --host birdnet --backtest 7   # Mac, over the LAN
.venv/bin/python run.py --no-fetch --date 2026-10-09  # rebuild one edition
.venv/bin/python run.py --no-fetch --dry-run          # temp output, no state
.venv/bin/python -m dawnchorus.analyse 2026-10-09     # the facts, as text
.venv/bin/python -m pytest
```

Output goes to `editions/` (the future GitHub Pages root): one page per date,
`index.html` (always the newest), `archive.html`, and resized illustrations
in `birds/`. Every page passes `dawnchorus/scrub.py` before it's written.
Add your own terms to block (suburb, street) one per line in
`private-terms.txt`, which is gitignored.

## Settings

Everything adjustable is in [`config.toml`](config.toml): run time, dawn
window, credibility thresholds. Tuning constants for rarity and leads sit at
the top of `dawnchorus/analyse.py`.

## How a day is built

1. `fetch.py`: consistent DB snapshot from the Pi over ssh.
2. `analyse.py`: 24 h window to run time; dawn (civil dawn to sunrise +
   90 min, clipped at run time); after dark (last night's civil dusk to civil
   dawn); per-species counts, firsts, arrivals, busiest-day-yet, and rarity
   (regional percentile from `act-species-canberra.csv` blended with the
   station's own history).
3. `pick_features`: the lead is the top credible bird, but a bird that led in
   the last 7 days is held back unless it has fresh news. The Regular is the
   well-established bird featured least recently (`state/featured.json`).
4. `write.py`: prose. Template-only for now; GLM arrives in phase 3 with the
   same keys, and this becomes its fallback.
5. `render.py`: Jinja2 page, scrub check, archive, index.
