"""Grab ONLY frame 1 of huge boss movieclips.

Some final-boss clips have thousands of animation frames, so FFDec's
"export every frame" never finishes. We only need the idle frame: launch the
export, watch for `1.svg`, then kill FFDec the instant it lands.
"""
import json
import os
import shutil
import signal
import subprocess
import time

import export_sprites as es

STILL = "/tmp/claude-1000/-home-luisca-Programacion-Mewgenics/" \
        "743caa06-9c8e-4ed2-a700-efc118538828/scratchpad/still_missing.json"
SPRITES = os.path.join(es.ROOT, "wiki_data", "assets", "sprites")
ANIM = os.path.join(es.ROOT, "wiki_data", "assets", "sprites_anim")
MAXWAIT = 300      # seconds to allow for SWF load + first frame


def grab(swf, cid, name):
    stage = os.path.join(es.STAGE, "f1_" + name)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)
    target = os.path.join(stage, f"DefineSprite_{cid}_{name}", "1.svg")
    cmd = [es.JAVA, "-Djava.awt.headless=true", "-jar", es.FFDEC,
           "-selectid", str(cid), "-format", "sprite:svg",
           "-export", "sprite", stage, swf]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    ok = False
    start = time.time()
    while time.time() - start < MAXWAIT:
        if os.path.exists(target) and os.path.getsize(target) > 200:
            time.sleep(0.4)                     # let it finish writing
            ok = True
            break
        if proc.poll() is not None:             # process ended on its own
            ok = os.path.exists(target) and os.path.getsize(target) > 200
            break
        time.sleep(1)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    if ok:
        shutil.copyfile(target, os.path.join(SPRITES, name + ".svg"))
        # also stash frame 1 as the (single-frame) animation
        d = os.path.join(ANIM, name)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(target, os.path.join(d, "1.svg"))
    shutil.rmtree(stage, ignore_errors=True)
    return ok


def main():
    still = json.load(open(STILL))
    smap = json.load(open(os.path.join(es.ROOT, "wiki_data", "sprite_map.json")))
    for name, (swf_base, cid) in still.items():
        if name == "test2x2":
            continue
        swf = os.path.join(es.SWFDIR, swf_base)
        print(f"[>] {name} (id {cid}, {swf_base}) ...", flush=True)
        if grab(swf, cid, name):
            smap[name] = {"svg": f"assets/sprites/{name}.svg", "frames": 1}
            print(f"    ok -> assets/sprites/{name}.svg", flush=True)
        else:
            print(f"    FAILED", flush=True)
    json.dump(smap, open(os.path.join(es.ROOT, "wiki_data", "sprite_map.json"), "w"), indent=1)
    print(f"[+] sprite_map now {len(smap)}")


if __name__ == "__main__":
    main()
