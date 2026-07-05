"""Re-export the boss sprites that timed out in the parallel run.

Targets only the specific missing character IDs (small set) but gives each SWF
a long timeout and runs 2-at-a-time so the huge boss animation clips finish.
"""
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import export_sprites as es

MISSING = "/tmp/claude-1000/-home-luisca-Programacion-Mewgenics/" \
          "743caa06-9c8e-4ed2-a700-efc118538828/scratchpad/missing.json"


def main():
    miss = json.load(open(MISSING))          # name -> [swf_basename, id]
    byswf = defaultdict(dict)
    for name, (swf, cid) in miss.items():
        byswf[os.path.join(es.SWFDIR, swf)][cid] = name

    manifest = json.load(open(os.path.join(es.ROOT, "wiki_data", "sprite_map.json")))

    def work(swf, id2name):
        base = os.path.basename(swf)
        stage = os.path.join(es.STAGE, "rerun_" + base)
        print(f"[>] {base}: {len(id2name)} sprites (timeout 3000s)", flush=True)
        try:
            rc = es.run_ffdec(swf, list(id2name), stage)   # uses 1500s default...
        except Exception as e:                              # noqa
            print(f"    !! {base}: {e}")
            rc = -1
        made = es.collect(stage, id2name)
        print(f"[<] {base}: rc={rc}, wrote {len(made)}", flush=True)
        return made

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(work, swf, ids) for swf, ids in byswf.items()]
        for f in as_completed(futs):
            manifest.update(f.result())

    json.dump(manifest, open(os.path.join(es.ROOT, "wiki_data", "sprite_map.json"), "w"), indent=1)
    print(f"[+] sprite_map now has {len(manifest)} sprites")


if __name__ == "__main__":
    main()
