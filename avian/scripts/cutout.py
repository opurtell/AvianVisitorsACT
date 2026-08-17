#!/usr/bin/env python3
"""AvianVisitors - cut the cream ground off the generated illustrations.

Step 2 of the illustration pipeline (after pregen.py, before build_masks.py).

pregen.py renders each bird on a flat cream ground because the image model
can't cut a clean transparent background on its own (it leaves holes and
fringes). A flat known ground, by contrast, removes cleanly. This runs each
illustration through the BiRefNet matting model (via rembg), then crops to
the bird's bounding box with a small even margin, and saves an RGBA cutout
back in place.

Idempotent: an illustration that already has a transparent background is
skipped unless you pass --force.

Requires rembg + onnxruntime (see requirements.txt). The first run downloads
the BiRefNet model (~1 GB) to ~/.u2net/.

Usage:
    python3 cutout.py                      # process every illustration
    python3 cutout.py calypte-anna         # one slug (both poses)
    python3 cutout.py calypte-anna-2 --force
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def ink_silhouette(rgb, margin: float = 8.0):
    """Silhouette taken from the drawing's own ink outline, not from colour.

    Every bird is drawn with a closed ink contour on a flat cream ground.
    Flood-filling inward from the frame border through non-ink pixels reaches
    all true background - including concave pockets a matting model tends to
    swallow, such as the gap between a tucked neck and a raised wing - but it
    cannot cross the outline into the body.

    This is the only test that works when the plumage is the same colour as
    the ground. A white egret's body sits within a few levels of the cream
    field, so a colour test either keeps the background (leaving a
    feather-coloured slab where there should be a hole) or dissolves the bird
    outright. The outline is unambiguous where colour is not.

    Returns a boolean mask of the bird.
    """
    import numpy as np
    from scipy import ndimage

    g = rgb.mean(axis=2).astype(np.float32)
    ground = float(np.median(g))          # the ground dominates the frame
    ink = g < (ground - margin)
    lab, _ = ndimage.label(~ink)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    border.discard(0)
    outside = np.isin(lab, list(border))
    bird = ndimage.binary_fill_holes(~outside)

    # Largest blob only - drops paper-edge strips and scan noise, which would
    # otherwise inflate the crop box to the whole frame.
    lab2, n = ndimage.label(bird)
    if n:
        sizes = ndimage.sum(bird, lab2, range(1, n + 1))
        bird = lab2 == (int(np.argmax(sizes)) + 1)
    return bird


def build_alpha(rgb, matte, margin: float = 8.0, tol: float = 42.0):
    """Final alpha: outline silhouette when it is plausible, else matte repair.

    The outline fill is trusted only if it keeps nearly all of what the
    matting model called bird. Where the ink contour has a gap, the fill leaks
    through it and eats whatever pale plumage lies beyond - a cattle egret's
    white breast and belly, say, while the darker buff areas hold the line.
    The result is a moth-eaten bird whose *total area* can still look
    reasonable, so area alone does not catch it: coverage does.

    Trimming genuine over-inclusion is expected and allowed (the outline is
    right and the matte was wrong), so the bar is set to tolerate a modest
    loss but reject a leak. Measured on this library: sound cuts keep
    0.95-1.00 of the matte silhouette, a leak kept 0.67.

    On rejection we fall back to the matting model plus the raise-only colour
    repair, which cannot restore transparency but also cannot punch holes.

    Returns (alpha, mode, filled, cleared).
    """
    import numpy as np
    from scipy import ndimage
    from PIL import Image, ImageFilter

    bird = ink_silhouette(rgb, margin)
    matte_mask = matte > 127
    matte_area = int(matte_mask.sum())
    ratio = bird.sum() / max(matte_area, 1)
    coverage = float((bird & matte_mask).sum()) / max(matte_area, 1)
    if coverage < 0.90 or ratio > 2.0:
        alpha, filled = repair_alpha(rgb, matte, tol)
        return (alpha, f"matte+repair (outline coverage {coverage:.2f})",
                filled, 0)

    filled = int(((matte < 128) & bird).sum())
    cleared = int(((matte > 128) & ~bird).sum())
    # Feather the hard mask by a sub-pixel blur so edges stay antialiased.
    alpha = np.array(Image.fromarray((bird * 255).astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(0.6)))
    return alpha, "outline", filled, cleared


def repair_alpha(rgb, alpha, tol: float = 42.0):
    """Restore opacity to body areas the matting model wrongly cut away.

    BiRefNet judges the bird by contrast against the ground. Where a pale
    body sits against the pale cream field - a white egret's chest, a
    fairywren's buff breast - it can punch a hole straight through the
    bird, sometimes taking the whole breast with it. The README warns that
    pale birds fare worst; this is that failure, and it is invisible until
    the collage composites the illustration over a non-cream background.

    The ground is a flat, uniform, border-connected field and the bird is
    ringed by ink outlines, so a border-seeded fill through cream-like
    pixels physically cannot leak into the body. Whatever the fill does not
    reach is bird, however pale it is. Enclosed cream regions are never
    reached either, so they are filled rather than punched out.

    Soft edges from the matting model are preserved: this only ever raises
    alpha, and only inside the recovered silhouette.

    Returns (repaired_alpha, pixels_recovered).
    """
    import numpy as np
    from scipy import ndimage

    ring = np.concatenate([rgb[0:6].reshape(-1, 3), rgb[-6:].reshape(-1, 3),
                           rgb[:, 0:6].reshape(-1, 3), rgb[:, -6:].reshape(-1, 3)])
    ground = ring.mean(axis=0)
    creamish = np.linalg.norm(rgb.astype(np.float32) - ground, axis=2) < tol

    lab, _ = ndimage.label(creamish)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    border.discard(0)
    fg = ~np.isin(lab, list(border))

    # Drop paper-noise specks floating in the ground; they are not the bird
    # and would otherwise inflate the crop box to the whole frame.
    lab2, n = ndimage.label(fg)
    if n:
        sizes = ndimage.sum(fg, lab2, range(1, n + 1))
        keep = np.where(sizes >= sizes.max() * 0.01)[0] + 1
        fg = np.isin(lab2, keep)
    fg = ndimage.binary_fill_holes(fg)

    recovered = int(((alpha < 128) & fg).sum())
    return np.where(fg, 255, alpha).astype(np.uint8), recovered


def main() -> int:
    here = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*",
                    help="Slugs to process (e.g. calypte-anna). Default: all.")
    ap.add_argument("--dir", type=Path, default=here / "assets" / "illustrations",
                    help="Illustration directory (default: avian/assets/illustrations/)")
    ap.add_argument("--model", default="birefnet-general",
                    help="rembg model name (default: birefnet-general)")
    ap.add_argument("--margin", type=float, default=0.02,
                    help="Even margin around the bird, as a fraction of its "
                         "long side (default: 0.02)")
    ap.add_argument("--force", action="store_true",
                    help="Re-cut illustrations that already have transparency")
    ap.add_argument("--no-repair", action="store_true",
                    help="Skip alpha correction entirely (raw matting output)")
    ap.add_argument("--ink-margin", type=float, default=8.0,
                    help="How far below the ground's luminance a pixel counts "
                         "as ink, for the outline silhouette (default: 8)")
    ap.add_argument("--ground-tol", type=float, default=42.0,
                    help="Colour distance from the cream ground still counted as "
                         "background, for the repair pass (default: 42)")
    args = ap.parse_args()

    try:
        from PIL import Image
        from rembg import new_session, remove
    except ImportError:
        print("error: needs Pillow + rembg (pip install -r requirements.txt)",
              file=sys.stderr)
        return 2

    if args.slugs:
        paths = []
        for slug in args.slugs:
            paths.append(args.dir / f"{slug}.png")
            flight = args.dir / f"{slug}-2.png"
            if not slug.endswith("-2") and flight.exists():
                paths.append(flight)
        # Dedupe: naming both "x" and "x-2" would otherwise queue x-2 twice,
        # and the second pass would run over the first pass's own output.
        paths = list(dict.fromkeys(paths))
        missing = [p for p in paths if not p.exists()]
        if missing:
            print("error: not found: " + ", ".join(p.name for p in missing), file=sys.stderr)
            return 2
    else:
        paths = sorted(args.dir.glob("*.png"))
    if not paths:
        print("error: no illustrations found", file=sys.stderr)
        return 1

    session = new_session(args.model)
    done = skipped = 0
    for p in paths:
        im = Image.open(p)
        if not args.force and im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 0:
            skipped += 1
            continue
        src = im.convert("RGB")
        cut = remove(src, session=session)  # RGBA, ground -> transparent
        note = ""
        if not args.no_repair:
            import numpy as np
            rgb = np.array(src)
            alpha, mode, filled, cleared = build_alpha(
                rgb, np.array(cut.getchannel("A")),
                margin=args.ink_margin, tol=args.ground_tol)
            cut = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
            bits = [b for b in (f"+{filled}px" if filled > 200 else "",
                                f"-{cleared}px" if cleared > 200 else "") if b]
            note = f"  [{mode}{' ' + ' '.join(bits) if bits else ''}]"
        bbox = cut.getchannel("A").getbbox()
        if bbox:
            pad = round(args.margin * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
            x0, y0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
            x1, y1 = min(cut.width, bbox[2] + pad), min(cut.height, bbox[3] + pad)
            cut = cut.crop((x0, y0, x1, y1))
        cut.save(p)
        done += 1
        print(f"  [cut]  {p.name}  -> {cut.width}x{cut.height}{note}")

    print(f"\ncut {done} · skipped {skipped} (already transparent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
