# ACT illustration gap — reconciliation

Canberra / Australian Capital Territory deployment of
[AvianVisitors](https://github.com/Twarner491/AvianVisitors), built on the
[AusVicVisitors](https://github.com/TheWillni/AusVicVisitors) AU-VIC
illustration bundle.

**Status: complete. 5 gap species generated, cut out, verified, merged and
mask-rebuilt. 403 species / 806 illustrations, `act5`.**

**Gemini spend: ~$0.48.** 12 images generated (10 initial + 2 regenerations)
at 1290 output tokens each, $30/1M → $0.464, plus ~23 verification vision
calls at roughly $0.02 total. Well under the 40-image hard stop.

---

## Summary

| Quantity | Count |
|---|---|
| Species BirdNET will attempt at Canberra (set A) | **198** |
| — already covered by the AU-VIC bundle | **193** |
| — genuine gaps | **5** |
| Coverage as-is | **97.5%** |
| Coverage after generating the 5 | **100%** |
| Images generated | 12 (10 + 2 regenerations) |
| Actual cost | ~$0.48 |

Of the 7 species in the original `act-generate-targets.txt`: **3 confirmed**,
**1 renamed**, **3 dropped**. One species the prior analysis dismissed as a
covered synonym turned out to be a genuine gap.

> **Coverage is conditional on configuration.** These figures hold at
> -35.28/149.13, `SF_THRESH=0.03`, `DATA_MODEL_VERSION=2`. The installer
> defaults to **v1**, under which *Ardea intermedia* (0.0082) and *Tyto alba*
> (0.0159) fall below threshold and can never be displayed. Set v2 — see
> [the configuration contract](DEPLOYMENT.md#1-the-configuration-contract).

---

## Environment constraints

This work ran in a sandbox whose egress policy denies most of the public
internet. Confirmed blocked (gateway answers `403` to `CONNECT`):

| Host | Needed for | Impact |
|---|---|---|
| `api.ebird.org` | Set A, per the brief | **Set A re-derived from another source — see below** |
| `en.wikipedia.org`, `upload.wikimedia.org` | `pregen.py` IMAGE 1 anatomy reference | **References supplied by hand — see below** |
| `api.gbif.org`, `biocache-ws.ala.org.au` | independent occurrence cross-check | Cross-check unavailable |
| `huggingface.co` | — | none, BiRefNet came from GitHub |

Confirmed working: **Gemini API** (key valid, `models` endpoint returns 200),
**BiRefNet / `cutout.py`** (973 MB model downloaded successfully), **`verify.py`**
(same Gemini endpoint), **`build_masks.py`**.

The proxy's own README states that policy denials must be reported rather than
routed around, so no workaround was attempted for any blocked host.

### Generation was halted, then unblocked by hand-supplied references

`pregen.py` attaches up to three reference images per request. With Wikipedia
blocked and no `assets/references/` directory in the repo, it could initially
attach **none**:

- **IMAGE 1 (anatomy)** — auto-fetched from Wikipedia. Host blocked, no cache
  to fall back on.
- **IMAGE 3 (style)** — the Edo-period kachō-e prints. Upstream deliberately
  does not bundle these ("they are someone else's art").
- **IMAGE 2 (anti-reference)** — not applicable; no ACT target triggers
  `ANTI_REF_TRIGGERS`.

`prompt.template.md` refers to IMAGE 1 and IMAGE 3 by name throughout and
instructs the model to match their painting technique. Sending it with nothing
attached invites the two failure modes the brief called unacceptable — species
drift and style mismatch against the Victorian set. Generation was therefore
**halted rather than attempted blind**, and `prompt.template.md` was never
edited.

Ten reference files were then supplied out of band and placed by hand:
five anatomy photographs and five Koson prints, one per `STYLE_REFS` slot the
ACT targets resolve to (01, 05, 06, 07, 08). Every subsequent generation call
logged `+ref+note`, confirming both the anatomy reference and the per-species
addendum reached the API. Provenance and licensing for all ten are recorded in
[`avian/assets/references/manifest.csv`](avian/assets/references/manifest.csv);
the images themselves are gitignored rather than redistributed.

Two were cropped before use, because `pregen.py` downscales IMAGE 1 to 384 px
on the long side and a bird occupying a small fraction of the frame survives
that as almost nothing: the pipit (~4% of frame) and the Intermediate Egret
(~13%). Both crops are noted in the manifest's `local_edits` column.

One reference was checked rather than trusted. The supplied *Ardea intermedia*
photo showed a long, sharply kinked neck that reads as *Ardea alba*;
magnifying the head resolved it in favour of Intermediate Egret — the gape
line terminates at the eye rather than running behind it, with a rounded crown
and a moderate bill. This mattered because the library already contains
`ardea-alba`, and a Great Egret reference would have guaranteed a duplicate
tile.

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
| [`DEPLOYMENT.md`](DEPLOYMENT.md) — build guide + configuration contract | ✅ |
| `avian/assets/illustrations/` — 796 PNGs, 398 species | ✅ built |
| `avian/frontend/dims.json` + `masks.json` — 796 entries each | ✅ rebuilt via `build_masks.py` |
| `avian/frontend/apt.js` — `SKETCH_VERSION` + `IMG_VERSION` → `act1` | ✅ bumped |
| `avian/scripts/act-targets.txt` — 5 targets, BirdNET names | ✅ |
| `avian/scripts/act-species-canberra.csv` — full 198-species set A | ✅ |
| `avian/scripts/species-notes.json` — diagnostic notes for the 5 targets | ✅ added |
| `avian/assets/references/README.md` — what to supply, per slot | ✅ |
| 10 new illustrations | ✅ generated, cut out, verified |
| `verify.py` pass/fail table | ✅ 9/10 pass — see below |

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

## Verification results

`verify.py` sends each illustration back through Gemini Vision *without*
telling it the target species, then compares the blind guess and checks
anatomy counts. Final pass, all 10 images:

| Image | Blind guess | Result | Notes |
|---|---|---|---|
| `anthus-novaeseelandiae` | Australasian Pipit | ✅ | |
| `anthus-novaeseelandiae-2` | Australasian Pipit | ✅ | regenerated once |
| `bubulcus-ibis` | Cattle Egret | ✅ | |
| `bubulcus-ibis-2` | Cattle Egret | ✅ | |
| `malurus-lamberti` | Variegated Fairywren | ✅ | chestnut shoulder rendered |
| `malurus-lamberti-2` | Variegated Fairywren | ✅ | wings read slightly hirundine |
| `ardea-intermedia` | Little Egret | ❌ | **accepted — see below** |
| `ardea-intermedia-2` | Intermediate Egret | ✅ | |
| `tyto-alba` | Barn Owl | ✅ | no ear tufts despite scops-owl style ref |
| `tyto-alba-2` | Barn Owl | ✅ | |

**9/10 pass.** Raw output in `avian/scripts/verify-results.csv`.

### Two regenerations

- **`anthus-novaeseelandiae-2`** first rendered with long forked tail
  streamers and was blind-identified as a *Eurasian Skylark*. A tail-specific
  anti-drift clause was added to `species-notes.json` and the flight pose
  alone re-rendered (`--poses 2`). Now passes.
- **`ardea-intermedia`** first rendered as a near-duplicate of the
  `ardea-alba` already in the library — same long S-kinked neck, same dagger
  bill. This is the exact failure the species note existed to prevent, and it
  is the one that matters: two indistinguishable tiles on the wall. A
  size/shape anti-drift clause was added (short thick neck, blunt bill,
  rounded head, hunched posture) and the perched pose re-rendered. The two
  are now plainly different birds.

### Why the remaining miss was accepted

`ardea-intermedia` still reads as "Little Egret" to the blind check, but the
verdict is not credible on its own terms:

1. It lists *Little Egret's* diagnostics — yellow feet, black bill base — as
   **missing**, so it is not actually seeing a Little Egret; it is picking the
   nearest small-white-egret label.
2. It penalises the render for "missing: gape line extending behind eye for
   Intermediate Egret". **That diagnostic is inverted.** A gape line running
   behind the eye is the *Great Egret* mark; on *Ardea intermedia* it stops at
   the eye. The image is being marked down for correctly lacking a feature it
   should not have.

White egrets are near-inseparable in a flat 30-brushstroke abstraction, and
the blind checker has little discriminative power across them. The render
meets the requirements that matter: clearly distinct from `ardea-alba`, and
distinct from `egretta-garzetta` in the same set (yellow bill and dark feet
versus garzetta's black bill and yellow feet). Further regeneration would be
chasing a metric rather than the goal.

### On the `wings=1` warnings

Several passing images carry a `wings=1` warning. This is expected, not a
defect: `prompt.template.md` specifies for the perched pose that one wing is
folded against the body and the other tucked behind it, so exactly one wing is
visible by design. The warning fires on every perched render in the library.

### `verify.py` was broken before it could report anything

The first verification run returned `done. 0 mismatch(es)` and exited 0 while
**every single call had failed**. `verify.py` pinned
`models/gemini-2.5-flash`, which now returns HTTP 404 ("no longer available to
new users"); the failures were counted as neither pass nor mismatch, and no
rows were written to the CSV. A green summary with an empty results file is a
silent false pass, and it would have been easy to accept.

Fixed by pointing `GEMINI_URL` at the floating `gemini-flash-latest` alias
rather than a pinned version, so the check degrades to a newer model instead
of to a fake green. `prompt.template.md` was not touched. Upstream anticipates
this class of breakage — `pregen.py` carries the comment "The endpoint changes
occasionally; if you get a 404 here, check Google's model catalog and bump
this" — but only `pregen.py`'s own URL, not `verify.py`'s.

### Cutout quality, and a real defect that was initially missed

Fringing was not the problem — edges are clean on every illustration,
including the two near-white birds. **Holes were.** BiRefNet cut straight
through the pale bodies of the three flight poses, removing most of the chest:

| Image | Body pixels wrongly removed |
|---|---|
| `bubulcus-ibis-2` | 2,305 |
| `malurus-lamberti-2` | 1,992 |
| `ardea-intermedia-2` | 1,317 |

After the final outline-based re-cut the corrections were larger still, and in
both directions — e.g. `bubulcus-ibis` recovered 7,006 body pixels and shed
48,530 pixels of background the matting model had claimed as bird.

This is the failure mode the upstream README warns about — pale bodies against
the pale cream ground give the matting model too little contrast — and it is
**invisible until the illustration is composited over a non-cream
background**, which is exactly what the collage does.

My first audit missed it. It counted only *fully enclosed* transparent
regions, so a chest opening that reaches the outline through a gap scored
zero, and I wrongly reported "interior transparency only where anatomy calls
for it". The defect was caught on visual review over a contrasting ground.
**Compositing over saturated magenta is the check that works**; alpha
statistics alone are not sufficient.

And it has to be done at **full resolution**. The Cattle Egret leak above was
reviewed in a 340 px contact-sheet cell and passed, because at that scale the
holes blend into the surrounding brushwork. It was obvious the moment the
illustration was viewed at its native size. Contact sheets are for spotting
*which* image to look at, never for clearing one.

An automated enclosed-hole count (`binary_fill_holes(alpha) & ~alpha`) is
useful as a pointer but is not a verdict either: it flags legitimate
anatomy — the space between a heron's leg and its belly is genuinely enclosed
background and correctly transparent. Every flag needs an eye on it.

#### The second defect: background kept as body

A colour-based repair fixed the holes but could not fix the mirror-image
error, which review then surfaced on the Intermediate Egret's flight pose: a
slab of **feather-coloured fill between the neck and the raised wing, where
there should be transparency**. That pocket is genuine background, and
BiRefNet had wrongly claimed it as bird. A repair that only ever *raises*
alpha cannot undo that.

The obvious fix — clear pixels that match the ground colour — **destroys this
bird**. A white egret's plumage sits within a few luminance levels of the
cream field, so clearing "background-coloured" pixels dissolves the body and
leaves only ink strokes. Colour cannot separate the two.

#### Fix: take the silhouette from the ink outline

`cutout.py` now derives the silhouette from the drawing's own contour
(`ink_silhouette` + `build_alpha`, on by default):

1. Threshold ink as luminance below the frame's median (the ground dominates).
2. Flood-fill inward from the border through non-ink pixels.
3. The fill reaches all true background — including concave pockets like the
   neck/wing gap — but **cannot cross the outline into the body**.
4. Keep the largest blob, fill enclosed regions, feather by 0.6 px so edges
   stay antialiased.

This is correct precisely where colour fails: the outline is unambiguous even
when plumage and ground are the same colour. It fixes both defects at once —
holes are filled *and* wrongly-kept background is cleared.

**Guarded — and the first guard was not good enough.** If the ink contour has
a gap, the fill leaks through it and eats whatever pale plumage lies beyond.
The first guard compared total area against the matting model's and accepted
anything in [0.5, 2.0]. That passed a leak on the perched **Cattle Egret** at
0.72, which cost it most of its white breast, belly and wing panel while the
darker buff areas held the line — a moth-eaten bird whose *total area* still
looked plausible. Area cannot see this; **coverage** can.

The guard now requires the outline silhouette to retain **≥90% of what the
matting model called bird**. Trimming genuine over-inclusion is still allowed
— the outline is right and the matte was wrong — but losing a tenth of the
body means a leak. Measured across this library:

| Illustration | Coverage | Outcome |
|---|---|---|
| `anthus-novaeseelandiae` | 1.000 | outline |
| `malurus-lamberti-2` | 0.999 | outline |
| `malurus-lamberti` | 0.996 | outline |
| `bubulcus-ibis-2` | 0.993 | outline |
| `ardea-intermedia-2` | 0.953 | outline (trimmed the neck/wing pocket) |
| **`bubulcus-ibis`** | **0.674** | **rejected → matte + colour repair** |

On rejection the fallback cannot restore transparency, but it also cannot
punch holes — the safe direction to fail in.

`scipy` was added to `requirements.txt` for connected components and hole
filling.

#### A bug in `cutout.py`'s slug expansion

Passing a base slug also queues its `-2` flight pose. Naming both `x` and
`x-2` therefore queued `x-2` twice, and the second pass ran over the first
pass's own output — destructive, for the reason in the hazard note below. Now
de-duplicated.

#### The safety commit paid for itself

Repair in place was impossible: rembg **zeroes the RGB channels** under
transparent pixels, so the missing chests were not recoverable from the cut
files. They were recovered from the pre-cutout cream-ground renders preserved
in the WIP safety commit (`14959f6`), and re-cut through the fixed pipeline —
no regeneration, no additional Gemini spend.

Two illustrations have no pre-cutout original in git (`ardea-intermedia` and
`anthus-novaeseelandiae-2` were regenerated and cut in the same step). Both
were checked over a contrasting ground and are clean, so nothing was lost —
but it is worth committing renders before cutting them.

**Related hazard:** re-running `cutout.py --force` over an already-cut file is
lossy. `im.convert("RGB")` discards the alpha channel of an RGBA input,
leaving the zeroed background baked in as black. Always re-cut from the
original render, never from a previous cutout.

---

## Reproducing the generation

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

## Deploy

```bash
rsync -avz --delete avian/ pi@birdnet.local:~/BirdNET-Pi/avian/
```

Full procedure — Pi provisioning, the configuration contract, verification
checks, kiosk setup and operations — is in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

**One thing from that document belongs here**, because it decides whether this
analysis holds at all: the installer ships `DATA_MODEL_VERSION=1`, and under
v1 two of the five species generated here sit below `SF_THRESH` and can never
be displayed (*Ardea intermedia* 0.0082, *Tyto alba* 0.0159). The set assumes
**`DATA_MODEL_VERSION=2`** at `SF_THRESH=0.03` and -35.28/149.13. Change any of
those and the gap must be re-derived.

---

## Secrets

`GEMINI_API_KEY` and `EBIRD_API_KEY` were supplied out of band and are **not**
committed to this repository, nor written into any tracked file. `.gitignore`
excludes `.env`, `env.txt` and `*.key`. Neither key appears in
`act-targets.txt`, `act-species-canberra.csv`, or this document.
