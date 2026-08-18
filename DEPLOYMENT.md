# Deployment — Canberra / ACT

How to take this repository from a fresh Raspberry Pi to birds on the wall.

Two devices, one direction of data flow, no cloud:

```
[USB mic] → [Pi 4B: birdnet.local]                 [Surface: wall]
              BirdNET-Pi analyzer                    kiosk browser
              SQLite detections DB      ←──HTTP──    full-screen
              PHP-FPM + Caddy                        polls collage
              AvianVisitors overlay
              this illustration set
```

This document covers the build. **[RECONCILIATION.md](RECONCILIATION.md)**
covers *why* the illustration set contains what it does — read that before
changing the species list.

---

## 1. The configuration contract

**Read this section before anything else.** The illustration set is scoped to
a specific location and a specific pair of BirdNET settings. Change them and
the coverage guarantee changes with them.

| Setting | Required value | Why |
|---|---|---|
| `LATITUDE` / `LONGITUDE` | **-35.28 / 149.13** | The species set was derived at these coordinates. Moving the location changes which species BirdNET offers. |
| `SF_THRESH` | **0.03** | The installer default, and the threshold the gap analysis assumed. |
| `DATA_MODEL_VERSION` | **2** — *not the default* | See below. |
| `MODEL` | `BirdNET_GLOBAL_6K_V2.4_Model_FP16` | Installer default. The label set the filenames are keyed to. |

### DATA_MODEL_VERSION must be changed to 2

The installer ships `DATA_MODEL_VERSION=1` (`scripts/install_config.sh:48`).
Under v1, two of the five illustrations generated for this deployment sit
below `SF_THRESH` and **will never be displayed**:

| Species | v1 occurrence | v2 occurrence | Displays under v1? | Under v2? |
|---|---|---|---|---|
| *Anthus novaeseelandiae* — Australasian Pipit | 0.0864 | 0.2121 | yes | yes |
| *Bubulcus ibis* — Cattle Egret | 0.0313 | 0.1415 | yes | yes |
| *Malurus lamberti* — Variegated Fairywren | 0.0555 | 0.0529 | yes | yes |
| *Ardea intermedia* — Intermediate Egret | 0.0082 | 0.0502 | **no** | yes |
| *Tyto alba* — Barn Owl | 0.0159 | 0.0411 | **no** | yes |

The two models also disagree sharply on how much of the ACT avifauna is worth
listening for at all — 127 species under v1 against 197 under v2 — and v1 is
visibly noisier for Australia, scoring Holarctic birds like *Bombycilla
garrulus* and *Lagopus lagopus* above species that genuinely occur here.

**Set `DATA_MODEL_VERSION=2`.** Web UI: *Tools → Settings → Model*, the
`data_model_version` checkbox (checked = 2).

| DATA_MODEL_VERSION | Species offered | Covered by this set |
|---|---|---|
| 1 (installer default) | 127 | 127 — 100% |
| **2 (recommended)** | **197** | **197 — 100%** |

Either way coverage is complete; v2 simply listens for 70 more species.

---

## 2. Provision the Pi

1. **Flash Raspberry Pi OS Lite (64-bit).** In Pi Imager set hostname
   `birdnet`, your username, Wi-Fi, SSH on, locale `Australia/Canberra`.

2. **Attach the USB mic before first boot.** The installer configures the
   audio device at install time.

3. **Run the installer** (20–40 min; needs passwordless sudo, which is the
   Lite default):

   ```bash
   ssh <user>@birdnet.local
   curl -s https://raw.githubusercontent.com/Twarner491/AvianVisitors/avian-visitors/newinstaller.sh | bash
   ```

   This clones the fork, installs BirdNET-Pi, symlinks the overlay into the
   Caddy web root, and reboots.

4. **Check both endpoints are alive:**
   - collage — `http://birdnet.local/`
   - stock BirdNET-Pi UI — `http://birdnet.local/index.php`
   - admin drawer — top-right of the collage

5. **Apply the configuration contract** from §1 (*Tools → Settings*).
   Location drives BirdNET's species-occurrence weighting, so it matters as
   much as the illustration set does.

6. **Reserve the Pi's IP in DHCP.** mDNS is the fragile link in an unattended
   kiosk; have a fixed IP as fallback.

---

## 3. Sync the illustration set

The installer ships the upstream North American art. Replace it with this set:

```bash
git clone https://github.com/opurtell/AvianVisitorsACT
cd AvianVisitorsACT

rsync -avz --delete avian/ pi@birdnet.local:~/BirdNET-Pi/avian/
```

Then hard-reload the kiosk browser (`Ctrl+Shift+R`).

**On `--delete`:** keep it on every sync. It is what makes this an ACT-only
build rather than an ACT-plus-North-America one — it removes the 622 upstream
illustrations, the 152 bundled North American photo cutouts in
`avian/assets/cutouts/`, and the 76 orphaned files in `avian/assets/sketches/`
(a directory nothing in the codebase reads). None of that is a runtime cache:
`cutout.php` writes its dynamic photo fallbacks to
`~/BirdSongs/Extracted/cutouts/`, which is outside `~/BirdNET-Pi/avian/` and
which rsync never touches.

### How the overlay is served

`scripts/link_webroot.sh` symlinks these into the Caddy web root:

```
avian/                     → /avian
avian/frontend/index.html  → /index.html      (the collage; stock UI stays at /index.php)
avian/frontend/apt.js      → /apt.js
avian/frontend/styles.css  → /styles.css
avian/frontend/dims.json   → /dims.json       ← apt.js fetches these two at load
avian/frontend/masks.json  → /masks.json
avian/frontend/nest.webp   → /nest.webp
avian/assets/favicon.png   → /favicon.png, /favicon.ico
```

Because the links point *into* `~/BirdNET-Pi/avian/`, rsyncing that directory
is all that is needed — the links follow. If they ever break (a stray
directory where a symlink should be), repair with:

```bash
sudo bash ~/BirdNET-Pi/scripts/link_webroot.sh
```

### Cache versions

`apt.js` fetches `dims.json` and `masks.json` with `?v=SKETCH_VERSION`, and
every illustration URL carries `&v=IMG_VERSION`. **Both must be bumped
whenever pixels change**, or the Surface serves stale art from cache
indefinitely. Current value: `act5` (both constants, `avian/frontend/apt.js`).

### Hard-lock the species set

The configuration contract in §1 is a *soft* boundary: `SF_THRESH` and the
occurrence model decide what BirdNET will attempt, and both can drift if
anyone touches Settings. If a species outside the ACT set is ever recorded, it
gets a Wikipedia photo cutout on the wall instead of an illustration.

BirdNET-Pi has a hard allow-list. `scripts/utils/analysis.py:141` loads
`~/BirdNET-Pi/include_species_list.txt`, and **if that file is non-empty, only
the species named in it are ever written to the detections database** — the
check runs after confidence and before the occurrence filter, so it overrides
location, threshold and model version alike.

`avian/scripts/act-include-species-list.txt` in this repo is exactly the 197
species from the coverage table, in the file's required `Scientific
name_Common Name` form, with common names taken from
`model/l18n/labels_en.json` so they match what BirdNET-Pi stores:

```bash
scp avian/scripts/act-include-species-list.txt \
  pi@birdnet.local:~/BirdNET-Pi/include_species_list.txt
ssh pi@birdnet.local 'sudo systemctl restart birdnet_analysis.service'
```

The file is also editable in the web UI at *Tools → Settings → Included
Species*, which reads and writes the same path through the
`scripts/include_species_list.txt` symlink.

Consequences worth accepting deliberately:

- **Nothing outside the 197 is ever recorded**, not even a genuine vagrant.
  The detection is logged as excluded and discarded. Empty the file to hear
  everything the occurrence model offers again.
- The list is keyed to `DATA_MODEL_VERSION=2`. Under v1, 70 of the 197 are
  never attempted anyway, so the list is a superset and harmless.
- Regenerate it if the species set changes:

  ```bash
  python3 - <<'EOF'
  import csv, json
  lab = json.load(open('model/l18n/labels_en.json'))   # from the BirdNET-Pi tree
  rows = csv.DictReader(open('avian/scripts/act-species-canberra.csv'))
  sel = sorted((r for r in rows if float(r['occurrence_v2']) >= 0.03),
               key=lambda r: r['scientific_name'])
  with open('avian/scripts/act-include-species-list.txt', 'w') as f:
      for r in sel:
          f.write(f"{r['scientific_name']}_{lab[r['scientific_name']]}\n")
  EOF
  ```

### What "ACT only" does and does not mean

Three separate sets are in play; conflating them is the easy mistake:

| Set | Size | Controlled by |
|---|---|---|
| Illustrations installed on the Pi | 403 species / 806 PNGs | what `rsync --delete` puts in `avian/assets/illustrations/` |
| Species BirdNET will attempt | 197 | `LATITUDE`/`LONGITUDE`, `SF_THRESH`, `DATA_MODEL_VERSION` |
| Species that can reach the database | 197, if the allow-list is installed | `include_species_list.txt` |

The 206-species surplus in the first row is the rest of the AU-VIC bundle —
Victorian and wider-Australian birds below threshold at Canberra. They cost
about 40 MB of SD card and are never displayed. Keeping them is the right
default: they are the buffer if you lower `SF_THRESH`, move the Pi, or a
species' occurrence score shifts between model versions. Pruning to exactly
197 buys nothing but a re-derivation cost the next time anything changes.

---

## 4. Verify the deployment

```bash
# tables reachable and the right size (expect 806 entries)
curl -s http://birdnet.local/dims.json  | python3 -c "import json,sys;print(len(json.load(sys.stdin)),'entries')"
curl -s http://birdnet.local/masks.json | python3 -c "import json,sys;print(len(json.load(sys.stdin)),'entries')"

# a bundled illustration resolves (expect 200, image/png)
curl -sI "http://birdnet.local/avian/api/cutout.php?sci=Malurus%20cyaneus" | head -3

# one of the new ACT species
curl -sI "http://birdnet.local/avian/api/cutout.php?sci=Tyto%20alba" | head -3

# cache version actually served
curl -s http://birdnet.local/apt.js | grep -m2 "_VERSION = "

# no North American art left behind (expect 806, and no upstream slugs)
ssh pi@birdnet.local 'ls ~/BirdNET-Pi/avian/assets/illustrations | wc -l;
  ls ~/BirdNET-Pi/avian/assets/illustrations | grep -c "^junco-\|^turdus-migratorius\|^cyanocitta-"'

# allow-list in place (expect 197)
ssh pi@birdnet.local 'wc -l < ~/BirdNET-Pi/include_species_list.txt'

# what BirdNET will listen for at this location
cd ~/BirdNET-Pi/scripts && ~/BirdNET-Pi/birdnet/bin/python3 species.py --threshold 0.03 | head -30
```

That last command must run from `scripts/` under the BirdNET venv python — the system `python3` has no `tflite_runtime`, and `utils.helpers` only imports with `scripts/` as the working directory. It is the real acceptance test: it prints the species list
BirdNET will attempt, straight from the occurrence model. Every species in it
should have art — cross-check against
[`avian/scripts/act-species-canberra.csv`](avian/scripts/act-species-canberra.csv).

---

## 5. Surface kiosk

1. **Confirm the Surface model and generation first** — it determines whether
   a UEFI battery limit exists and whether Linux drivers are viable.

2. **Try Windows Assigned Access before reinstalling.** *Settings → Accounts →
   Other users → Set up a kiosk* → Edge, full-screen, `http://birdnet.local/`.
   Reversible, keeps the ambient light sensor, zero driver risk.

3. **Suppress interruptions:** never sleep on AC, display never off, wide
   active hours, defer feature updates, disable the lock screen and
   notifications on the kiosk account.

4. **Set portrait orientation.** 3:2 rotated is close to A4 — the reason a
   Surface suits this better than any 16:9 panel.

5. **Fall back to Porteus Kiosk only if Windows fights you.** Read-only,
   auto-reconnects on network loss. Verify Wi-Fi and touch from the live image
   before committing.

---

## 6. Operations

| # | Task | Why |
|---|---|---|
| 1 | **Cap the battery** — UEFI 50% limit if available, smart-plug schedule otherwise | Non-negotiable. A swollen cell behind glass on a wall is a hazard. |
| 2 | **Schedule display-off overnight** | A backlit panel in a dark room is far more intrusive than expected. |
| 3 | **Back up the detections DB** — weekly `rsync` to the NAS | SQLite on an SD card. |
| 4 | **Watch SD wear** | Continuous audio analysis plus SQLite writes. Move the DB and recordings to a USB SSD if the card starts throwing errors. |
| 5 | **Review detections weekly for the first month** | Tune `CONFIDENCE` (default 0.7). False positives are the normal failure mode, and each one puts a wrong bird on the wall. |

### Tuning the confidence threshold

`CONFIDENCE` (default `0.7`) is separate from `SF_THRESH` and is the one to
adjust from real data. Raising it reduces false positives at the cost of
missing quiet birds. **Do not lower `SF_THRESH` to chase more species** — that
widens the candidate set to birds the occurrence model says are not here, and
those are exactly the detections most likely to be wrong. It would also pull
in species this set has no art for, which fall back to photo cutouts.

---

## 7. Changing the illustration set later

The full pipeline lives in `avian/scripts/`. See
[`avian/assets/references/README.md`](avian/assets/references/README.md) for
what reference images to supply.

Adding one species:

```bash
cd avian/scripts
pip install -r requirements.txt
export GEMINI_API_KEY='...'

python3 pregen.py --species "Genus species|Common Name" --force   # ~$0.08 for 2 poses
python3 cutout.py genus-species                                    # both poses
python3 verify.py --labels act-targets.txt genus-species genus-species-2
python3 build_masks.py
# then bump SKETCH_VERSION and IMG_VERSION in avian/frontend/apt.js
```

### Rules that are not optional

- **Filenames must match BirdNET labels, not current eBird names.** `apt.js`
  resolves art by `slugify(detection.sci)`, and that string comes verbatim
  from BirdNET's label file. This is why the Eastern Barn Owl is filed as
  `tyto-alba` and the Eastern Cattle Egret as `bubulcus-ibis`. A file named
  for the modern name is never found.
- **Never run `pregen.py --ebird-region` without `--species`.** It regenerates
  the whole regional set — ~200 species at Canberra, roughly 40× the cost.
- **Never edit `prompt.template.md`.** Style divergence from the rest of the
  library is more visible on a wall than a missing bird. Per-species
  corrections belong in `species-notes.json`, which is appended to the prompt
  for that species and carries forward to every future regeneration.
- **Bump both cache constants** after any pixel change.

### Cutout hazards

These cost real time during this build; they are documented at length in
RECONCILIATION.md and summarised here.

- **Commit the cream-ground renders before cutting them.** `cutout.py`
  overwrites in place, and the matting model zeroes RGB under transparent
  pixels — a bad cut is unrecoverable without the original. A WIP commit
  between `pregen.py` and `cutout.py` saved this build twice.
- **Never re-cut an already-cut file.** `im.convert("RGB")` discards alpha and
  bakes the zeroed background in as black. Always re-cut from the original
  render.
- **Passing a base slug also queues its `-2` pose.** Naming both `x` and `x-2`
  used to process `x-2` twice, the second pass running over the first pass's
  output. De-duplicated now, but worth knowing.
- **Review cutouts at full resolution over a contrasting background.** Alpha
  statistics miss holes, and GitHub renders PNG alpha on white — so a hole in
  a white egret is invisible there. Compositing over saturated magenta is the
  check that works, and a contact sheet is for choosing which image to open,
  never for clearing one.

### If `verify.py` returns 404

Its model endpoint is pinned and Google retires models. A failed run still
prints `0 mismatch(es)` and exits 0 while writing no rows — a silent false
pass. If the results CSV is empty, check the model name in `verify.py`'s
`GEMINI_URL` against the current catalogue:

```bash
curl -s -H "x-goog-api-key: $GEMINI_API_KEY" \
  "https://generativelanguage.googleapis.com/v1beta/models" | grep '"name"'
```

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Collage renders but no birds are packed | `dims.json` / `masks.json` not reachable. Check `curl http://birdnet.local/dims.json`; repair links with `link_webroot.sh`. |
| Old art persists after a sync | `SKETCH_VERSION` / `IMG_VERSION` not bumped, or the kiosk was not hard-reloaded. |
| A detected bird shows a photo, not an illustration | No illustration for that BirdNET label — the `cutout.php` fallback chain is working as designed. Check the label against `act-species-canberra.csv`. |
| A species never appears despite being present locally | Below `SF_THRESH` at this location, or absent from BirdNET's 6,522-label set. ~110 ACT species are simply not in the model, mostly raptors that rarely vocalise. |
| Two tiles look like the same bird | Genuine risk with close congeners. Add a `species-notes.json` entry naming the diagnostic difference and regenerate. |
| Collage unreachable but `/index.php` works | The overlay symlinks are broken. `sudo bash ~/BirdNET-Pi/scripts/link_webroot.sh`. |

---

## 9. What is *not* in this build

| Component | Why omitted |
|---|---|
| `frame/` directory | Paints a PNG onto an e-ink panel via `fbi`. The Surface runs a real browser. |
| Cloudflare Tunnel / Worker | LAN-only; no public HTTPS URL needed. |
| Second Pi | The display device is not compute-constrained. |
| Screenshot / PNG render step | The browser hits the live page. |

`avian/forwarding/` ships a Home Assistant REST sensor and an MQTT bridge that
poll `birdnet-api.php?action=recent`. Both are optional and deferred.
