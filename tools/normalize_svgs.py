"""Bake a tight viewBox into exported SVGs.

FFDec writes a pixel-sized canvas with no viewBox; for many sprites the art
occupies a small corner of a huge canvas, so the file displays tiny/clipped
however it's embedded. This rewrites each <svg> with viewBox + width/height set
to the true content bounding box. Idempotent (skips files that already have a
viewBox). Reversible by re-running the export scripts.
"""
import glob
import os
import re
import sys

import generate_preview as gp   # reuse _content_bbox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "wiki_data", "assets")
PAD = 0.04


def normalize(path):
    with open(path, encoding="utf-8") as f:
        s = f.read()
    i = s.find("<svg")
    if i < 0:
        return False
    head, body = s[:i], s[i:]
    m = re.search(r"<svg\b([^>]*)>", body)
    if not m or "viewBox" in m.group(1):
        return False
    try:
        bb = gp._content_bbox(body)
    except Exception:
        bb = None
    if not bb:
        return False
    pad = PAD * max(bb[2]-bb[0], bb[3]-bb[1])
    x, y = bb[0]-pad, bb[1]-pad
    w, h = bb[2]-bb[0]+2*pad, bb[3]-bb[1]+2*pad
    attrs = re.sub(r'\s(?:width|height)="[^"]*"', "", m.group(1))
    tag = (f'<svg{attrs} width="{w:.1f}" height="{h:.1f}" '
           f'viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}" '
           f'preserveAspectRatio="xMidYMid meet">')
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + body[:m.start()] + tag + body[m.end():])
    return True


def main():
    groups = sys.argv[1:] or ["sprites", "icons"]
    patterns = {
        "sprites": [os.path.join(ASSETS, "sprites", "*.svg")],
        "icons": [os.path.join(ASSETS, "icons", "**", "*.svg")],
        "anim": [os.path.join(ASSETS, "sprites_anim", "**", "*.svg")],
    }
    for g in groups:
        files = []
        for p in patterns[g]:
            files += glob.glob(p, recursive=True)
        done = skip = 0
        for fp in files:
            if normalize(fp):
                done += 1
            else:
                skip += 1
        print(f"{g:8s} normalized {done}, skipped {skip} (of {len(files)})")


if __name__ == "__main__":
    main()
