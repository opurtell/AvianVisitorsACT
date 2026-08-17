# AvianVisitorsACT

Illustration assets and frontend overlay for
[AvianVisitors](https://github.com/Twarner491/AvianVisitors), scoped to
Canberra / the Australian Capital Territory.

Built on the [AusVicVisitors](https://github.com/TheWillni/AusVicVisitors)
AU-VIC bundle (398 species, 796 illustrations), with the ACT-specific gap
derived independently and documented in **[RECONCILIATION.md](RECONCILIATION.md)**.

## Contents

```
avian/
  assets/illustrations/    806 PNGs — 403 species, perched + flight
  assets/references/       manifest + README (images gitignored)
  frontend/                apt.js + dims.json + masks.json + index.html
  scripts/                 the four-stage generation pipeline
  api/                     PHP resolvers (cutout.php serves the art)
```

## Coverage

BirdNET will attempt **198** species at Canberra (-35.28, 149.13) at the
default `SF_THRESH=0.03`, per its own bundled occurrence model. **193 are
covered** by the illustrations here — 97.5%.

**5 species remain to generate.** They are listed in
[`avian/scripts/act-targets.txt`](avian/scripts/act-targets.txt) and the full
198-species set with occurrence scores is in
[`avian/scripts/act-species-canberra.csv`](avian/scripts/act-species-canberra.csv).

Generation is **not yet done** — the environment this was assembled in could
not reach Wikipedia or supply the kachō-e style references, and generating
without them risks a visible style mismatch against the Victorian set. See
[Environment constraints](RECONCILIATION.md#environment-constraints) for the
full reasoning and [How to resume](RECONCILIATION.md#how-to-resume-generation)
for the commands.

## Deploy

```bash
rsync -avz --delete avian/ pi@birdnet.local:~/BirdNET-Pi/avian/
```

Then hard-reload the kiosk. Bump `SKETCH_VERSION` and `IMG_VERSION` in
`avian/frontend/apt.js` whenever the art changes, or browsers serve stale
images from cache indefinitely.
