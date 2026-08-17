# Reference images

`pregen.py` attaches up to three reference images per Gemini request. This
directory is where it looks for them. It was left empty by the ACT gap-fill
run because `en.wikipedia.org` and every biodiversity API were blocked by the
generating environment's egress policy — see RECONCILIATION.md.

Nothing here is committed art. Drop your own files in and `pregen.py` picks
them up automatically; a missing reference is skipped, not fatal.

## What goes where

### `<slug>.jpg` or `<slug>.png` — IMAGE 1, anatomy (per species)

A photo of the target species. Anchors identity, markings, plumage. Slug is
`slugify(scientific_name)`, matching the illustration filename.

`pregen.py` auto-fetches these from the Wikipedia REST summary endpoint and
caches them here. A file you place yourself is always preferred over the
fetch, so on a network without Wikipedia access this is the manual override.

For the five ACT targets:

| File | Species | Note |
|---|---|---|
| `anthus-novaeseelandiae.jpg` | Australasian Pipit | photograph the Australian bird (*A. australis* in current eBird) |
| `bubulcus-ibis.jpg` | Cattle Egret | use **breeding** plumage — buff crown/breast, not the plain white non-breeding bird |
| `malurus-lamberti.jpg` | Variegated Fairywren | male; ACT birds are the *assimilis* form |
| `ardea-intermedia.jpg` | Intermediate Egret | shorter bill and gape line than *A. alba* is the diagnostic |
| `tyto-alba.jpg` | Barn Owl | the Australian *javanica* form if possible |

### `_anti_<key>.jpg` — IMAGE 2, anti-reference (per genus)

A look-alike the model drifts toward, attached so the prompt can say what
NOT to copy. Only `bluejay` and `barnswallow` are wired in `pregen.py`'s
`ANTI_REFS`; neither triggers for any ACT target, so none is needed here.

### `styles/<filename>` — IMAGE 3, style (per genus + pose)

Edo-period kachō-e prints by Ohara Koson and Hiroshi Yoshida. Deliberately
not bundled by upstream — they are someone else's art. `pregen.py`'s
`STYLE_REFS` maps genus and pose to these ten filenames, all findable on the
public web by name:

```
01-sparrows-on-bamboo-Koson.jpg      06-goose-flying-in-moonlight-Koson.jpg
02-cawing-crow-Koson.jpg             07-swallows-in-flight-Koson.jpg
03-jays-on-berry-tree-Koson.jpg      08-crane-in-small-water-Koson.jpg
04-kingfisher-Koson.jpg              09-cockatoo-Yoshida.jpg
05-owl-on-ginkgo-Koson.jpg           10-mandarin-ducks-Yoshida.jpg
```

The five ACT targets resolve to four of them:

| Target | Pose 1 (perched) | Pose 2 (flight) |
|---|---|---|
| *Ardea intermedia*, *Bubulcus ibis* | `08-crane-in-small-water-Koson.jpg` | `06-goose-flying-in-moonlight-Koson.jpg` |
| *Tyto alba* | `05-owl-on-ginkgo-Koson.jpg` | `06-goose-flying-in-moonlight-Koson.jpg` |
| *Anthus novaeseelandiae*, *Malurus lamberti* | `01-sparrows-on-bamboo-Koson.jpg` | `07-swallows-in-flight-Koson.jpg` |

So you need at most **five** style files, not all ten: 01, 05, 06, 07, 08.

The style reference is the single biggest lever on matching the Victorian
set. Generating without it is what the upstream README warns produces
"stylistic drift", and a mismatch is more visible on a wall than a gap.
