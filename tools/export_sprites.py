"""Render referenced character/enemy/boss movieclips from the SWFs to SVG.

Strategy: one FFDec invocation per SWF, selecting all needed character IDs.
FFDec exports every frame of each sprite; we keep frame 1 as the canonical
idle thumbnail and retain all frames under sprites_anim/ for later animation.
"""
import glob
import json
import os
import re
import struct
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKERS = 6

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = os.path.join(ROOT, "dump")
SWFDIR = os.path.join(DUMP, "swfs")
OUT = os.path.join(ROOT, "wiki_data", "assets")
STAGE = os.path.join(ROOT, "wiki_data", "_stage")
JAVA = os.path.join(ROOT, "tools", "vendor", "jre", "bin", "java")
FFDEC = os.path.join(ROOT, "tools", "vendor", "ffdec", "ffdec.jar")

KEEP_ANIM = "--no-anim" not in sys.argv


def swf_exports(path):
    """Return {name: id} for exported (named) symbols in a SWF."""
    d = open(path, "rb").read()
    pos = 8
    nb = d[pos] >> 3
    pos += (5 + nb * 4 + 7) // 8
    pos += 4
    out = {}
    while pos < len(d) - 2:
        rec = struct.unpack_from("<H", d, pos)[0]
        pos += 2
        tag = rec >> 6
        ln = rec & 0x3F
        if ln == 0x3F:
            ln = struct.unpack_from("<I", d, pos)[0]
            pos += 4
        if tag in (76, 56):                     # SymbolClass / ExportAssets
            b = d[pos:pos + ln]
            cnt = struct.unpack_from("<H", b, 0)[0]
            p = 2
            for _ in range(cnt):
                cid = struct.unpack_from("<H", b, p)[0]
                p += 2
                e = b.index(b"\x00", p)
                nm = b[p:e].decode("utf-8", "ignore")
                p = e + 1
                if "." not in nm:               # skip internal fla names
                    out.setdefault(nm, cid)
        if tag == 0:
            break
        pos += ln
    return out


def needed_names():
    chars = json.load(open(os.path.join(ROOT, "wiki_data", "characters.json")))
    names = set()
    for r in chars:
        g = r.get("graphics")
        if isinstance(g, dict) and isinstance(g.get("movieclip"), str):
            names.add(g["movieclip"])
    return names


def run_ffdec(swf, ids, stage_dir):
    os.makedirs(stage_dir, exist_ok=True)
    cmd = [JAVA, "-Djava.awt.headless=true", "-jar", FFDEC,
           "-selectid", ",".join(str(i) for i in ids),
           "-format", "sprite:svg",
           "-export", "sprite", stage_dir, swf]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
    return r.returncode


FOLDER_RE = re.compile(r"DefineSprite_(\d+)_(.+)")


def collect(stage_dir, id2name):
    sprites_dir = os.path.join(OUT, "sprites")
    anim_dir = os.path.join(OUT, "sprites_anim")
    os.makedirs(sprites_dir, exist_ok=True)
    made = {}
    for folder in os.listdir(stage_dir):
        m = FOLDER_RE.match(folder)
        if not m:
            continue
        name = m.group(2)
        fpath = os.path.join(stage_dir, folder)
        frames = sorted((f for f in os.listdir(fpath) if f.endswith(".svg")),
                        key=lambda x: int(x[:-4]) if x[:-4].isdigit() else 0)
        if not frames:
            continue
        # canonical idle = frame 1
        with open(os.path.join(fpath, frames[0])) as fh:
            svg = fh.read()
        with open(os.path.join(sprites_dir, name + ".svg"), "w") as fh:
            fh.write(svg)
        if KEEP_ANIM and len(frames) > 1:
            dst = os.path.join(anim_dir, name)
            os.makedirs(dst, exist_ok=True)
            for fr in frames:
                os.rename(os.path.join(fpath, fr), os.path.join(dst, fr))
        made[name] = {"svg": f"assets/sprites/{name}.svg", "frames": len(frames)}
    return made


def main():
    os.makedirs(OUT, exist_ok=True)
    want = needed_names()
    print(f"[+] need {len(want)} character sprites")

    # map each needed name to (swf, id)
    per_swf = {}
    resolved = {}
    for swf in sorted(glob.glob(os.path.join(SWFDIR, "*.swf"))):
        exps = swf_exports(swf)
        for name in want:
            if name in exps and name not in resolved:
                resolved[name] = swf
                per_swf.setdefault(swf, {})[exps[name]] = name
    print(f"[+] resolved {len(resolved)}/{len(want)} across {len(per_swf)} SWFs")

    manifest = {}
    lock = threading.Lock()

    def work(swf, id2name):
        base = os.path.basename(swf)
        stage_dir = os.path.join(STAGE, base)
        print(f"[>] {base}: {len(id2name)} sprites ...", flush=True)
        try:
            rc = run_ffdec(swf, list(id2name), stage_dir)
        except subprocess.TimeoutExpired:
            print(f"    !! timeout on {base}")
            rc = -1
        made = collect(stage_dir, id2name)
        with lock:
            manifest.update(made)
            total = len(manifest)
        print(f"[<] {base}: rc={rc}, wrote {len(made)} svgs (total {total})",
              flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(work, swf, ids) for swf, ids in per_swf.items()]
        for f in as_completed(futs):
            f.result()

    with open(os.path.join(ROOT, "wiki_data", "sprite_map.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"[+] DONE: {len(manifest)} sprites -> wiki_data/assets/sprites/")


if __name__ == "__main__":
    main()
