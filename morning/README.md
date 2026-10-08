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

## Knowledge base

`knowledge/species/<genus-species>.json` holds, for each of the 197 species in
the include list: grounded facts from Wikipedia, ACT monthly record counts from
the Atlas of Living Australia, and a seasonality class computed from them.
`knowledge/seasonal.toml` is the hand-written Canberra calendar.

```bash
.venv/bin/python build_kb.py sources     # Wikipedia + ALA → cache + species files (any machine)
python3 build_kb.py facts                # GLM → facts; on greg (keys in ~/.hermes/.env), 09:00–17:00
.venv/bin/python build_kb.py report      # coverage, short species, seasonality classes
```

A fact survives only if its `quote` appears word-for-word in the fetched
article, every number in it appears in the quote, and most of its words come
from the quote. URLs and ids are computed, never written by the model.
Taxonomy and seasonality corrections, each with a reason, go in
`knowledge/overrides.toml`. Seasonality is each month's share of *all* ACT
bird records (so busy survey months aren't mistaken for migration); under
300 records a species is a "rare visitor", and under 1,000 its class is
marked low-confidence and the paper doesn't print it.

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
   (regional percentile, the mean of BirdNET's Canberra occurrence score in
   `act-species-canberra.csv` and ALA's ACT record share, blended with the
   station's own history).
3. `pick_features`: the lead is the top credible bird, but a bird that led in
   the last 7 days is held back unless it has fresh news. The Regular is the
   well-established bird featured least recently (`state/featured.json`).
   Did You Know takes 2 facts for the lead and 1 for the Regular from the
   knowledge base, skipping any printed in the last 60 days.
4. `write.py`: prose. Template-only for now; GLM arrives in phase 3 with the
   same keys, and this becomes its fallback.
5. `render.py`: Jinja2 page, scrub check, archive, index.
