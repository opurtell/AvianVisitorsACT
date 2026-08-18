# AvianVisitorsACT

Illustration assets and frontend overlay for
[AvianVisitors](https://github.com/Twarner491/AvianVisitors) — a BirdNET-Pi
fork that renders detected birds as a kachō-e style collage — scoped to
Canberra and the Australian Capital Territory.

Built on the [AusVicVisitors](https://github.com/TheWillni/AusVicVisitors)
AU-VIC bundle, with the ACT-specific gap derived independently, generated,
verified and merged.

**403 species · 806 illustrations · `act5`**

---

## Documentation

| | |
|---|---|
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Fresh Pi → birds on the wall. Configuration contract, install, sync, verification, kiosk, operations, and how to change the illustration set later. **Start here to build.** |
| **[RECONCILIATION.md](RECONCILIATION.md)** | Why the species set contains exactly what it does. Set derivation, taxonomy resolutions, per-species verification, cutout defects and fixes, actual spend. **Read before changing the species list.** |
| [avian/assets/references/README.md](avian/assets/references/README.md) | What reference images `pregen.py` needs and where to get them. |

## Contents

```
avian/
  assets/illustrations/    806 PNGs — 403 species, perched + flight
  assets/references/       manifest + README (images themselves gitignored)
  frontend/                apt.js + dims.json + masks.json + index.html
  scripts/                 the four-stage generation pipeline
  api/                     PHP resolvers (cutout.php serves the art)
```

Derived data, all tracked:

| File | Contents |
|---|---|
| `avian/scripts/act-species-canberra.csv` | All 198 species BirdNET will attempt at Canberra, with occurrence scores and coverage status |
| `avian/scripts/act-include-species-list.txt` | The 197 attempted species as a BirdNET-Pi allow-list, ready to drop in as `include_species_list.txt` |
| `avian/scripts/act-targets.txt` | The 5 generated species, under BirdNET label names |
| `avian/scripts/verify-results.csv` | Blind species re-ID and anatomy audit for the 10 new illustrations |
| `avian/assets/references/manifest.csv` | Source, author, licence and local edits for every reference image |

## Coverage

At Canberra (-35.28, 149.13), `SF_THRESH=0.03`, `DATA_MODEL_VERSION=2`,
BirdNET will attempt **197 species**. **All 197 are covered** — the AU-VIC
bundle supplied 192 and the five gaps were generated here:

| Species | Common name |
|---|---|
| *Anthus novaeseelandiae* | Australasian Pipit |
| *Bubulcus ibis* | Cattle Egret |
| *Malurus lamberti* | Variegated Fairywren |
| *Ardea intermedia* | Intermediate Egret |
| *Tyto alba* | Barn Owl |

Blind verification passes 9/10; the single dissent is examined in
[Verification results](RECONCILIATION.md#verification-results).

> **The species set is scoped to a location and two settings.**
> `LATITUDE`/`LONGITUDE`, `SF_THRESH` and `DATA_MODEL_VERSION` all change what
> BirdNET offers, and therefore whether coverage still holds. The installer
> default `DATA_MODEL_VERSION=1` leaves two of the five new illustrations
> permanently undisplayable — see
> [the configuration contract](DEPLOYMENT.md#1-the-configuration-contract).

## Deploy

```bash
rsync -avz --delete avian/ pi@birdnet.local:~/BirdNET-Pi/avian/
scp avian/scripts/act-include-species-list.txt \
  pi@birdnet.local:~/BirdNET-Pi/include_species_list.txt
```

`--delete` is what removes the upstream North American art; the allow-list is
what stops anything outside the 197 reaching the database. Then hard-reload
the kiosk. Bump `SKETCH_VERSION` and `IMG_VERSION` in
`avian/frontend/apt.js` whenever the art changes, or browsers serve stale
images from cache indefinitely. Full procedure and verification checks in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Credits

- Pipeline and frontend — [Twarner491/AvianVisitors](https://github.com/Twarner491/AvianVisitors)
- 398 of the 403 species — [TheWillni/AusVicVisitors](https://github.com/TheWillni/AusVicVisitors)
- Style references — Ohara Koson, public domain, via Wikimedia Commons and the Rijksmuseum
- Anatomy references — Wikimedia Commons contributors; see `avian/assets/references/manifest.csv` for per-file attribution

## Licence

[CC-BY-NC-SA-4.0](LICENSE), inherited from BirdNET-Pi via AvianVisitors.
Non-commercial use only, and the ShareAlike condition carries to anything
derived from this bundle — including a bundle for another region built on top
of it.
