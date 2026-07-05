"""Export ability, passive, and item icons to SVG.

Icons live as frames inside single movieclips:
  - ability_icons.swf: AbilityIcon (1346) / PassiveIcon (515) -> frames are
    LABELLED; the label is the value abilities use in `ability_icon`.
  - catparts.swf: WeaponIcon/HeadItemIcon/FaceItemIcon/NeckItemIcon/TrinketIcon
    -> items index these by numeric `frame`.
"""
import json
import os
import struct
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = os.path.join(ROOT, "dump")
SWFDIR = os.path.join(DUMP, "swfs")
OUT = os.path.join(ROOT, "wiki_data", "assets", "icons")
STAGE = os.path.join(ROOT, "wiki_data", "_stage_icons")
JAVA = os.path.join(ROOT, "tools", "vendor", "jre", "bin", "java")
FFDEC = os.path.join(ROOT, "tools", "vendor", "ffdec", "ffdec.jar")

LABEL_CLIPS = {  # ability_icons.swf
    "abilities": ("ability_icons.swf", 1346),
    "passives": ("ability_icons.swf", 515),
}
ITEM_CLIPS = {   # catparts.swf, keyed by item `kind`
    "weapon": ("catparts.swf", 1353),
    "head": ("catparts.swf", 1356),
    "face": ("catparts.swf", 1355),
    "neck": ("catparts.swf", 1354),
    "trinket": ("catparts.swf", 1352),
}


def sprite_labels(path, target_id):
    """frame_number(1-based) -> label for a DefineSprite's timeline."""
    d = open(path, "rb").read()
    pos = 8
    nb = d[pos] >> 3
    pos += (5 + nb * 4 + 7) // 8
    pos += 4
    while pos < len(d) - 2:
        rec = struct.unpack_from("<H", d, pos)[0]
        pos += 2
        tag = rec >> 6
        ln = rec & 0x3F
        if ln == 0x3F:
            ln = struct.unpack_from("<I", d, pos)[0]
            pos += 4
        body = d[pos:pos + ln]
        if tag == 39 and struct.unpack_from("<H", body, 0)[0] == target_id:
            p, frame, labels = 4, 1, {}
            while p < len(body) - 2:
                r = struct.unpack_from("<H", body, p)[0]
                p += 2
                t, l = r >> 6, r & 0x3F
                if l == 0x3F:
                    l = struct.unpack_from("<I", body, p)[0]
                    p += 4
                b = body[p:p + l]
                if t == 1:
                    frame += 1
                elif t == 43:
                    labels[frame] = b[:b.index(b"\x00")].decode("utf-8", "ignore")
                elif t == 0:
                    break
                p += l
            return labels
        if tag == 0:
            break
        pos += ln
    return {}


def ffdec_frames(swf, cid, stage_dir):
    os.makedirs(stage_dir, exist_ok=True)
    cmd = [JAVA, "-Djava.awt.headless=true", "-jar", FFDEC,
           "-selectid", str(cid), "-format", "sprite:svg",
           "-export", "sprite", stage_dir, swf]
    # Some icon frames contain text with a null font -> FFDec raises an
    # interactive Abort/Retry/Ignore prompt. Feed "I" (ignore) so it renders
    # the graphics and skips the bad text instead of aborting after frame 1.
    subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                   input="I\n" * 20000)
    # find the produced frame folder
    for folder in os.listdir(stage_dir):
        if folder.startswith(f"DefineSprite_{cid}_"):
            return os.path.join(stage_dir, folder)
    return None


def export_labelled(kind, swf_name, cid):
    swf = os.path.join(SWFDIR, swf_name)
    labels = sprite_labels(swf, cid)
    print(f"[>] {kind}: {len(labels)} labelled frames in {swf_name}")
    folder = ffdec_frames(swf, cid, os.path.join(STAGE, kind))
    dst = os.path.join(OUT, kind)
    os.makedirs(dst, exist_ok=True)
    manifest = {}
    for frame_svg in os.listdir(folder):
        if not frame_svg.endswith(".svg"):
            continue
        n = int(frame_svg[:-4])
        label = labels.get(n)
        if not label or label == "unknown":
            continue
        with open(os.path.join(folder, frame_svg)) as fh:
            svg = fh.read()
        with open(os.path.join(dst, label + ".svg"), "w") as fh:
            fh.write(svg)
        manifest[label] = f"assets/icons/{kind}/{label}.svg"
    print(f"    wrote {len(manifest)} {kind} icons")
    return manifest


def export_items():
    dst_root = os.path.join(OUT, "items")
    manifest = {}
    for kind, (swf_name, cid) in ITEM_CLIPS.items():
        swf = os.path.join(SWFDIR, swf_name)
        folder = ffdec_frames(swf, cid, os.path.join(STAGE, "item_" + kind))
        dst = os.path.join(dst_root, kind)
        os.makedirs(dst, exist_ok=True)
        count = 0
        for frame_svg in os.listdir(folder):
            if not frame_svg.endswith(".svg"):
                continue
            n = int(frame_svg[:-4])
            with open(os.path.join(folder, frame_svg)) as fh:
                svg = fh.read()
            with open(os.path.join(dst, f"{n}.svg"), "w") as fh:
                fh.write(svg)
            manifest[f"{kind}/{n}"] = f"assets/icons/items/{kind}/{n}.svg"
            count += 1
        print(f"[>] item {kind}: wrote {count} icon frames")
    return manifest


def main():
    os.makedirs(OUT, exist_ok=True)
    result = {}
    for kind, (swf_name, cid) in LABEL_CLIPS.items():
        result[kind] = export_labelled(kind, swf_name, cid)
    result["items"] = export_items()
    with open(os.path.join(ROOT, "wiki_data", "icon_map.json"), "w") as f:
        json.dump(result, f, indent=1)
    print("[+] icons done -> wiki_data/assets/icons/")


if __name__ == "__main__":
    main()
