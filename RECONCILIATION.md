# ACT illustration gap — reconciliation

Canberra / Australian Capital Territory deployment of
[AvianVisitors](https://github.com/Twarner491/AvianVisitors), built on the
[AusVicVisitors](https://github.com/TheWillni/AusVicVisitors) AU-VIC
illustration bundle.

**Status: gap derived and merged asset set built. Illustration generation
deliberately halted before any Gemini image call — see
[Environment constraints](#environment-constraints).**

**Gemini spend: $0.00.** No image-generation request was issued. The only
Gemini call made was one unauthenticated `GET /v1beta/models` to confirm the
key and endpoint were reachable, which is not billed.

---

## Summary

| Quantity | Count |
|---|---|
| Species BirdNET will attempt at Canberra (set A) | **198** |
| — already covered by the AU-VIC bundle | **193** |
| — genuine gaps | **5** |
| Coverage as-is | **97.5%** |
| Coverage after generating the 5 | **100%** |
| Images to generate | 10 (5 species × 2 poses) |
| Estimated cost | ~$0.39 |

Of the 7 species in the original `act-generate-targets.txt`: **3 confirmed**,
**1 renamed**, **3 dropped**. One species the prior analysis dismissed as a
covered synonym turned out to be a genuine gap.

---

## Environment constraints

This work ran in a sandbox whose egress policy denies most of the public
internet. Confirmed blocked (gateway answers `403` to `CONNECT`):

| Host | Needed for | Impact |
|---|---|---|
| `api.ebird.org` | Set A, per the brief | **Set A re-derived from another source — see below** |
| `en.wikipedia.org`, `upload.wikimedia.org` | `pregen.py` IMAGE 1 anatomy reference | Generation halted |
| `api.gbif.org`, `biocache-ws.ala.org.au` | independent occurrence cross-check | Cross-check unavailable |
| `huggingface.co` | — | none, BiRefNet came from GitHub |

Confirmed working: **Gemini API** (key valid, `models` endpoint returns 200),
**BiRefNet / `cutout.py`** (973 MB model downloaded successfully), **`verify.py`**
(same Gemini endpoint), **`build_masks.py`**.

The proxy's own README states that policy denials must be reported rather than
routed around, so no workaround was attempted for any blocked host.

### Why generation was halted

`pregen.py` attaches up to three reference images per request. In this
environment it could attach **none**:

- **IMAGE 1 (anatomy)** — auto-fetched from Wikipedia. Host blocked, and the
  repo ships no `assets/references/` directory, so there was no cache to fall
  back on.
- **IMAGE 3 (style)** — the Edo-period kachō-e prints. Upstream deliberately
  does not bundle these ("they are someone else's art"), and they are not in
  the repo.
- **IMAGE 2 (anti-reference)** — not applicable; no ACT target triggers
  `ANTI_REF_TRIGGERS`.

The prompt body in `prompt.template.md` refers to IMAGE 1, IMAGE 2 and IMAGE 3
by name throughout and instructs the model to match their painting technique.
Sending it with no images attached invites exactly the two failure modes the
brief called out as unacceptable — species drift and a style mismatch against
the Victorian set. `prompt.template.md` was not edited, and generating a set
that visibly diverges from the AU-VIC art was judged worse than shipping the
gap. Generation therefore stops here pending references.

Everything that does **not** depend on generation has been completed.

---

## The three source sets

### Set A — species BirdNET will attempt at Canberra: **198**

The brief specified eBird region `AU-ACT`. That host is blocked, so set A was
derived instead from **BirdNET's own bundled species-occurrence model**, which
is a strictly better answer to the operational question:

```
model/BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite      (DATA_MODEL_VERSION=1)
model/BirdNET_GLOBAL_6K_V2.4_MData_Model_V2_FP16.tflite   (DATA_MODEL_VERSION=2)
```

Inputs `[latitude, longitude, week]` → a 6,522-wide occurrence vector, the same
call `scripts/species.py` makes. Evaluated at **-35.28, 149.13** (Canberra, per
the software brief) for **all 52 weeks**, taking each species' peak week, at the
installer default **`SF_THRESH=0.03`** (`scripts/install_config.sh:47`).

| Model | Species ≥ 0.03 | Gaps |
|---|---|---|
| MData v1 | 127 | 3 |
| MData v2 | 197 | 5 |
| **Union (used)** | **198** | **5** |

This is not a proxy for what the Pi will detect — it *is* the filter the Pi
applies. A species below `SF_THRESH` is never offered to the classifier, so an
illustration for it can never be displayed. eBird's checklist, by contrast,
includes birds BirdNET will never emit at this location.

The v1 model is visibly noisier for Australia: it scores Holarctic species such
as *Bombycilla garrulus*, *Lagopus lagopus* and *Surnia ulula* above species
that genuinely occur in the ACT. v2 was treated as primary and v1 kept only to
widen the candidate net.

Full per-species output: [`avian/scripts/act-species-canberra.csv`](avian/scripts/act-species-canberra.csv)
— 198 rows with both occurrence scores and coverage status.

### Set B — BirdNET label set: **6,522**

`model/BirdNET_GLOBAL_6K_V2.4_Model_FP16_Labels.txt`, one scientific name per
line, 6,522 unique slugs (no duplicates).

### Set C — AU-VIC bundle: **398 species / 796 images**

`AusVicVisitors/frontend/dims.json`. 796 keys → 398 unique species after
stripping the `-2` flight-pose suffix. Verified complete and consistent:

- 398 perched + 398 flight, **every** species has both poses
- **zero** bundle slugs that are not BirdNET labels
- rebuilding `dims.json` and `masks.json` from the bundle's own PNGs with
  `build_masks.py` reproduces both files **byte-identically**, confirming the
  bundle was built with this exact pipeline

---

## The derived gap — 5 species

`(A ∩ B) − C`, sorted by occurrence.

| Scientific name (BirdNET label) | Common name | Occ. v1 | Occ. v2 | Note |
|---|---|---|---|---|
| *Anthus novaeseelandiae* | Australasian Pipit | 0.0864 | 0.2121 | No *Anthus* anywhere in the bundle |
| *Bubulcus ibis* | Cattle Egret | 0.0313 | 0.1415 | No *Bubulcus* in the bundle |
| *Malurus lamberti* | Variegated Fairywren | 0.0555 | 0.0529 | **Missed by the prior analysis** — see below |
| *Ardea intermedia* | Intermediate Egret | 0.0082 | 0.0502 | Bundle has only *Ardea alba* |
| *Tyto alba* | Barn Owl | 0.0159 | 0.0411 | **Renamed** from *Tyto javanica* — see below |

Targets in `pregen.py` format: [`avian/scripts/act-targets.txt`](avian/scripts/act-targets.txt)

---

## Taxonomy resolutions

The naming rule that governs every decision below:

> `apt.js` resolves art by `slugify(detection.sci)` (`avian/frontend/apt.js:304`,
> and `cutout.php` does the same server-side). `detection.sci` comes verbatim
> from BirdNET's label file. **Therefore every filename must match a BirdNET
> label, not the current eBird name.** A file named for the current name is
> never found and silently falls through to the photo-cutout path.

### Forward drift — confirmed already covered (6, no action)

Each was checked by locating the congener actually present in the bundle. All
six of the prior analysis's synonym calls are **correct**.

| Name in ALA/eBird | Present in bundle as | Common name |
|---|---|---|
| *Porphyrio porphyrio* | *Porphyrio melanotus* | Australasian Swamphen |
| *Himantopus himantopus* | *Himantopus leucocephalus* | Pied Stilt |
| *Rhipidura fuliginosa* | *Rhipidura albiscapa* | Grey Fantail |
| *Ninox novaeseelandiae* | *Ninox boobook* | Southern Boobook |
| *Acrocephalus stentoreus* | *Acrocephalus australis* | Australian Reed Warbler |
| *Malurus lamberti* | *Malurus assimilis* | **see correction below** |

### Correction — *Malurus lamberti* is a genuine gap, not a synonym

The prior analysis listed *M. lamberti* as covered by *M. assimilis*. That is
correct taxonomically — the ACT's Variegated Fairywrens are the *assimilis*
form — but wrong operationally. BirdNET carries **both** names as separate
labels, and at Canberra it weights them very differently:

| BirdNET label | Occ. v1 | Occ. v2 | In bundle |
|---|---|---|---|
| *Malurus cyaneus* | 0.8458 | 0.8924 | yes |
| **_Malurus lamberti_** | **0.0555** | **0.0529** | **no** |
| *Malurus assimilis* | 0.0057 | 0.0091 | yes |

BirdNET is ~6× more likely to emit `Malurus lamberti` than `Malurus assimilis`
here, and there is no `malurus-lamberti.png`. Detections would fall through to
the photo fallback. **Added to the generate list.**

### Reverse drift — BirdNET's label is the *older* name

Two targets have no BirdNET label under their current name but are detectable
under an older lumped one. The illustration must take the **BirdNET** name.

| Target (current name) | BirdNET label to use | Why |
|---|---|---|
| *Tyto javanica* (Eastern Barn Owl) | **`Tyto alba`** | *T. javanica* was split from *T. alba* after BirdNET's taxonomy vintage. `Tyto alba` scores 0.0411 at Canberra — it is the label Australian barn owls arrive under. |
| *Anthus australis* (Australian Pipit) | **`Anthus novaeseelandiae`** | Already correct in the original target list. Worth noting because it cuts the other way: **a naive eBird intersection would have dropped the pipit entirely**, since eBird's AU-ACT list returns *A. australis*, which matches no BirdNET label. |

### Why the AU-VIC bundle has these gaps at all

Every one of the five gaps is a species that occurs commonly in Victoria. They
are missing from the bundle because a name-matched intersection of eBird's
current `AU-VIC` checklist against BirdNET's older labels silently drops them —
the same drift class the AusVicVisitors README says it corrected for, applied
incompletely. This is a bug in the bundle's derivation, not a real absence, and
the same five illustrations would improve any Australian deployment.

---

## Excluded — and why

### No BirdNET label, and no valid substitute (2)

Per the brief's guardrail: a species BirdNET has no label for can never be
detected, so the illustration is dead weight.

| Species | Common name | Nearest BirdNET label | Occ. at Canberra | Verdict |
|---|---|---|---|---|
| *Elanus axillaris* | Black-shouldered Kite | *Elanus caeruleus* (Black-winged Kite) | **0.0006 / 0.0000** | **Excluded** |
| *Nycticorax caledonicus* | Nankeen Night-Heron | *Nycticorax nycticorax* (Black-crowned Night-Heron) | 0.0139 / 0.0001 | **Excluded** |

Both were rated GENERATE by the prior analysis, and the Black-shouldered Kite
was its highest-value target at 10,043 ACT records. Neither substitution is
sound:

- ***Elanus axillaris*** is a full species long split from *E. caeruleus*; it is
  absent from BirdNET's label set for lack of training audio, exactly like
  *Falco cenchroides*, *Aquila audax* and *Hieraaetus morphnoides*. Filing the
  art under `elanus-caeruleus` would not help — that label scores **0.0006** at
  Canberra, two orders of magnitude below `SF_THRESH`, so the tile could never
  appear. **The Black-shouldered Kite is not detectable in Canberra under any
  name.** This is a limitation of the acoustic model, not of the art set.
- ***Nycticorax caledonicus*** is a distinct species from *N. nycticorax*, which
  does not occur in Australia. Drawing a Nankeen Night-Heron and filing it as
  *N. nycticorax* would put the wrong bird on the wall on a false positive.

### Below the occurrence threshold (1 of the original 7)

| Species | Common name | Occ. v1 | Occ. v2 | Verdict |
|---|---|---|---|---|
| *Butorides striata* | Striated Heron | 0.0075 | 0.0167 | **Excluded** — below `SF_THRESH=0.03` |

In BirdNET's label set and absent from the bundle, but BirdNET will not offer it
at Canberra at the default threshold. Add it if you lower `SF_THRESH` below
0.017; it is 2 images and would then display.

### The 27 "OPTIONAL" species — skip confirmed

The prior analysis's decision to skip these is **independently confirmed**.
Every one scores below `SF_THRESH` at Canberra; the highest are
*Centropus phasianinus* (0.0181), *Alectura lathami* (0.0120),
*Corvus orru* (0.0105) and *Ailuroedus crassirostris* (0.0093). None would ever
be offered to the classifier.

---

## Asset contract — the warning is resolved, and inverted

The brief flagged this as the most likely integration failure: upstream inlines
`DIMS` and `MASKS` inside `apt.js`, while the AU-VIC bundle ships separate
`dims.json` / `masks.json`.

**On the `avian-visitors` branch this is no longer true.** Current `apt.js`
fetches the tables at load:

```js
// avian/frontend/apt.js:217-225
  var DIMS = {}, MASKS = {}, tablesReady = false;
  (function loadTables() {
    var q = '?v=' + SKETCH_VERSION;
    Promise.all([
      fetch('./dims.json' + q).then(function (r) { return r.json(); }),
      fetch('./masks.json' + q).then(function (r) { return r.json(); })
    ]).then(function (t) {
      DIMS = t[0]; MASKS = t[1]; tablesReady = true;
```

`build_masks.py` writes exactly these two files, and its docstring records the
migration ("The tables used to be inlined in apt.js as single ~800KB lines").
**The AU-VIC bundle's format is already correct. No conversion is needed and no
inlining should be attempted** — inlining would now break the fetch.

The remaining real risk is the opposite one: the cache. `dims.json` and
`masks.json` are fetched with `?v=SKETCH_VERSION`, so **the version bump is what
makes new art appear at all**. Both constants have been bumped (below).

---

## What was produced

| Deliverable | Status |
|---|---|
| `avian/assets/illustrations/` — 796 PNGs, 398 species | ✅ built |
| `avian/frontend/dims.json` + `masks.json` — 796 entries each | ✅ rebuilt via `build_masks.py` |
| `avian/frontend/apt.js` — `SKETCH_VERSION` + `IMG_VERSION` → `act1` | ✅ bumped |
| `avian/scripts/act-targets.txt` — 5 targets, BirdNET names | ✅ |
| `avian/scripts/act-species-canberra.csv` — full 198-species set A | ✅ |
| `avian/scripts/species-notes.json` — diagnostic notes for the 5 targets | ✅ added |
| `avian/assets/references/README.md` — what to supply, per slot | ✅ |
| 10 new illustrations | ⏸ **halted — references unavailable** |
| `verify.py` pass/fail table | ⏸ **blocked on generation** |

The North American illustration set (666 files) was removed, per decision: none
of those species clears `SF_THRESH` at Canberra, so they were pure weight in
`dims.json`, `masks.json` and every deploy. `assets/cutouts/` (the photo
fallback cache) was likewise cleared of its North American entries; it
repopulates itself on demand and its absence is handled gracefully by
`cutout.php`'s lookup chain.

### Note on `PLACEHOLDER` in `apt.js`

`apt.js:2` defines a `PLACEHOLDER` array of twelve North American species. It is
**dead code** — the identifier appears nowhere else in the file — so it was left
alone. If a future upstream merge starts using it, it will need an Australian
list.

### Note on the bundle's `tyto-novaehollandiae.png`

The AU-VIC bundle's Masked Owl illustration reads as a **Barn Owl** — clean
heart-shaped white facial disc, pale lightly-spotted underparts. A true Masked
Owl is larger and darker with a chestnut-tinged disc. When `tyto-alba.png` is
generated the two tiles may look near-identical. The `species-notes.json` entry
added for *Tyto alba* pushes it deliberately paler and plainer to keep them
distinguishable; the pre-existing *T. novaehollandiae* render is worth
regenerating separately.

---

## How to resume generation

1. **Supply references.** See [`avian/assets/references/README.md`](avian/assets/references/README.md).
   At minimum, five style prints (`01`, `05`, `06`, `07`, `08`) in
   `avian/assets/references/styles/`. Anatomy photos are fetched automatically
   from Wikipedia on a network that can reach it; on this one they must be
   placed by hand as `avian/assets/references/<slug>.jpg`.

2. **Generate — one `--species` invocation per target.** Never
   `--ebird-region AU-ACT` unfiltered; that regenerates all ~198 detectable
   species at ~40× the cost for no benefit.

   ```bash
   cd avian/scripts
   export GEMINI_API_KEY='...'
   while IFS= read -r s; do
     case "$s" in ''|'#'*) continue ;; esac
     python3 pregen.py --species "$s" --force
   done < act-targets.txt
   ```

   10 images, ~$0.39. Do not edit `prompt.template.md`.

3. **Cut out the cream ground.**

   ```bash
   python3 cutout.py anthus-novaeseelandiae bubulcus-ibis malurus-lamberti ardea-intermedia tyto-alba
   ```

   Passing slugs restricts the run to the new birds — a bare `cutout.py` scans
   all 796 PNGs and, while it skips already-transparent files, there is no
   reason to load them. **Inspect `bubulcus-ibis` and `tyto-alba` individually**:
   both are near-white and are where BiRefNet fringes worst. Re-render any bird
   with visible fringing or alpha holes using `pregen.py ... --force`.

4. **Verify.**

   ```bash
   python3 verify.py --labels act-targets.txt
   ```

   Blind species re-ID plus wing/leg/head/tail counts and a stray-perch check,
   appended to `verify-results.csv`. Regenerate anything flagged.

5. **Rebuild masks and bump the cache versions.**

   ```bash
   python3 build_masks.py          # expect 806 entries (403 species)
   ```

   Then bump `SKETCH_VERSION` and `IMG_VERSION` in `avian/frontend/apt.js` from
   `act1` to `act2`. **Skipping this serves stale art from cache indefinitely.**

---

## Deploy to the Pi

```bash
rsync -avz --delete avian/ pi@birdnet.local:~/BirdNET-Pi/avian/
```

Then hard-reload the kiosk (`Ctrl+Shift+R`). Drop `--delete` if anything else on
the Pi writes into `avian/` — notably `assets/cutouts/`, which `cutout.php`
populates at runtime with photo fallbacks for uncovered species.

Verify after sync:

```bash
curl -s http://birdnet.local/avian/frontend/dims.json | head -c 200
curl -sI "http://birdnet.local/avian/api/cutout.php?sci=Malurus%20cyaneus"
```

---

## Secrets

`GEMINI_API_KEY` and `EBIRD_API_KEY` were supplied out of band and are **not**
committed to this repository, nor written into any tracked file. `.gitignore`
excludes `.env`, `env.txt` and `*.key`. Neither key appears in
`act-targets.txt`, `act-species-canberra.csv`, or this document.
