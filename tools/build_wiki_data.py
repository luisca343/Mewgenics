"""Build clean per-category JSON for the Mewgenics wiki from dump/data/*.gon.

Resolves: localization keys (via text/combined.csv), `variant_of` inheritance,
and ability `template` inheritance. Emits wiki_data/*.json.
"""
import csv
import glob
import json
import os
from copy import deepcopy

import gon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = os.path.join(ROOT, "dump")
DATA = os.path.join(DUMP, "data")
OUT = os.path.join(ROOT, "wiki_data")
os.makedirs(OUT, exist_ok=True)

# ---- localization ------------------------------------------------------
# wiki language code -> column name in combined.csv.
# To add a language: uncomment/add its row (the CSV already has ru/ko/ja/zh
# columns, currently untranslated). English ("en") is the reference/fallback.
LANGUAGES = {
    "en": "en",
    "es": "sp",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "pt": "pt-br",
    # "ru": "ru", "ko": "ko", "ja": "ja", "zh": "zh",
}

def load_strings():
    """Return ({lang_code: {key: text}}, {lang_code: native_name})."""
    path = os.path.join(DATA, "text", "combined.csv")
    tables = {code: {} for code in LANGUAGES}
    native = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(f)
        header = next(rows)
        col = {name: i for i, name in enumerate(header)}
        for row in rows:
            if not row or not row[0]:
                continue
            key = row[0].strip()
            if key == "CURRENT_LANGUAGE_NAME":
                for code, c in LANGUAGES.items():
                    i = col.get(c)
                    native[code] = row[i] if i is not None and i < len(row) else code
                continue
            if key.startswith("//") or key.startswith("CURRENT_"):
                continue
            for code, c in LANGUAGES.items():
                i = col.get(c)
                if i is not None and i < len(row) and row[i].strip():
                    tables[code][key] = row[i]
    return tables, native

STRINGS, NATIVE_NAMES = load_strings()
STR = STRINGS["en"]                       # English = reference / fallback

def loc(v):
    return STR.get(v, v) if isinstance(v, str) else v

# ---- inheritance -------------------------------------------------------
def deep_merge(base, over):
    out = deepcopy(base)
    for k, v in over.items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out

def resolve_inheritance(index, templates):
    """index: name -> raw entity (mutated in place with resolved copies)."""
    cache = {}

    def rez(name, stack):
        if name in cache:
            return cache[name]
        if name in stack:              # cycle guard
            return index.get(name, {})
        ent = index.get(name)
        if ent is None:
            return {}
        stack = stack | {name}
        merged = {}
        tmpl = ent.get("template")
        if isinstance(tmpl, str) and ("template_" + tmpl) in templates:
            merged = deep_merge(merged, templates["template_" + tmpl])
        parent = ent.get("variant_of")
        if isinstance(parent, str):
            merged = deep_merge(merged, rez(parent, stack))
        merged = deep_merge(merged, ent)
        cache[name] = merged
        return merged

    return {name: rez(name, set()) for name in index}

# ---- display-field resolution -----------------------------------------
DISPLAY = {"name", "desc", "tooltip", "desc_long", "flavor", "area_name",
           "title", "tooltip_stackless", "name_stacks_neg",
           "tooltip_stacks_pos", "tooltip_stacks_neg"}

# ---- asset linking -----------------------------------------------------
def _load(name):
    p = os.path.join(OUT, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

SPRITE_MAP = _load("sprite_map.json")     # movieclip -> {svg, frames}
ICON_MAP = _load("icon_map.json")         # {abilities:{}, passives:{}, items:{}}

# ---- ability back-references -------------------------------------------
# Enemy abilities (special_enemy_abilities.gon etc.) have no dedicated UI
# icon; they are only reachable through the enemies that use them. These maps
# are populated in main() before abilities are emitted so every ability gets
# represented (who uses it) and a sensible thumbnail (its projectile/particle
# sprite, or failing that the sprite of an enemy that uses it).
ABILITY_OWNERS = {}     # ability_id -> [character_id, ...]     (enemies/cats)
ABILITY_XREFS = {}      # ability_id -> [ability_id, ...]       (combo chains)
OWNER_SPRITE = {}       # character_id -> {svg, frames} from SPRITE_MAP

def _string_leaves(o):
    """Yield every string value nested anywhere inside o."""
    if isinstance(o, dict):
        for v in o.values():
            yield from _string_leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from _string_leaves(v)
    elif isinstance(o, str):
        yield o

def build_ability_refs(index, ability_ids, drop_self=False):
    """{referenced_ability -> sorted[referrers]} for referrers in `index`.

    A referrer references an ability if any string field anywhere in it equals
    that ability's id (covers abilities/spells/passives plus AI/unlock fields).
    """
    refs = {}
    for referrer, ent in index.items():
        for val in set(_string_leaves(ent)):
            if val in ability_ids and not (drop_self and val == referrer):
                refs.setdefault(val, set()).add(referrer)
    return {k: sorted(v) for k, v in refs.items()}

def build_owner_sprites(char_index):
    out = {}
    for cid, ent in char_index.items():
        g = ent.get("graphics")
        mc = g.get("movieclip") if isinstance(g, dict) else None
        if isinstance(mc, str) and mc in SPRITE_MAP:
            out[cid] = SPRITE_MAP[mc]
    return out

def enrich(rec, category):
    """Attach `sprite`/`icon` asset paths (if the exported assets exist)."""
    if category == "characters":
        g = rec.get("graphics")
        mc = g.get("movieclip") if isinstance(g, dict) else None
        if isinstance(mc, str) and mc in SPRITE_MAP:
            rec["sprite"] = SPRITE_MAP[mc]["svg"]
            rec["sprite_frames"] = SPRITE_MAP[mc]["frames"]
    elif category == "items":
        kind, frame = rec.get("kind"), rec.get("frame")
        if isinstance(kind, str) and isinstance(frame, int):
            icon = ICON_MAP.get("items", {}).get(f"{kind}/{frame}")
            if icon:
                rec["icon"] = icon
    elif category == "abilities":
        icons = ICON_MAP.get("abilities", {})
        g = rec.get("graphics") if isinstance(rec.get("graphics"), dict) else {}
        # reverse links: which enemies/cats use it, and which abilities chain it
        owners = ABILITY_OWNERS.get(rec["_id"], [])
        if owners:
            rec["used_by"] = owners[:60]
            rec["used_by_count"] = len(owners)
        xrefs = ABILITY_XREFS.get(rec["_id"], [])
        if xrefs:
            rec["used_by_abilities"] = xrefs[:60]
        # icon: dedicated UI icon (player abilities) ...
        # try: explicit ability_icon override -> own id -> variant parent id
        for label in (g.get("ability_icon"), rec["_id"], rec.get("variant_of")):
            if isinstance(label, str) and label in icons:
                rec["icon"] = icons[label]
                rec["icon_source"] = "ui"
                break
        # ... else fall back to a real in-world visual: the ability's own
        # projectile/particle sprite, else the sprite of an enemy that uses it.
        if "icon" not in rec:
            proj, part = g.get("projectile"), g.get("particle")
            if isinstance(proj, str) and proj in SPRITE_MAP:
                rec["icon"] = SPRITE_MAP[proj]["svg"]
                rec["icon_source"] = "projectile"
            elif isinstance(part, str) and part in SPRITE_MAP:
                rec["icon"] = SPRITE_MAP[part]["svg"]
                rec["icon_source"] = "particle"
            else:
                for cid in owners:
                    if cid in OWNER_SPRITE:
                        rec["icon"] = OWNER_SPRITE[cid]["svg"]
                        rec["icon_source"] = "owner"
                        rec["icon_owner"] = cid
                        break
    elif category == "passives":
        icon = ICON_MAP.get("passives", {}).get(rec["_id"])
        if icon:
            rec["icon"] = icon
    return rec

def add_display(ent):
    """Surface name/desc/tooltip/title keys found in root/meta/graphics/intro.

    Adds `<field>_key`  -> the localization key (resolve via strings/<lang>.json)
    and  `<field>_en`   -> English reference text (fallback for missing i18n).
    """
    for scope in (ent, ent.get("meta"), ent.get("graphics"), ent.get("intro")):
        if not isinstance(scope, dict):
            continue
        for f in DISPLAY:
            if f in scope and f + "_key" not in ent and isinstance(scope[f], str):
                ent[f + "_key"] = scope[f]
                ent[f + "_en"] = loc(scope[f])
    return ent

# ---- category loaders --------------------------------------------------
def load_dir(subdir):
    """Merge every top-level entry across *.gon in a dir into one namespace."""
    index, source = {}, {}
    for path in sorted(glob.glob(os.path.join(DATA, subdir, "*.gon"))):
        fname = os.path.basename(path)
        try:
            parsed = gon.load(path)
        except Exception as e:                 # noqa
            print(f"  !! parse error {fname}: {e}")
            continue
        for name, ent in parsed.items():
            if isinstance(ent, dict):
                index[name] = ent
                source[name] = fname
    return index, source

def emit(category, index, source, templates=None):
    resolved = resolve_inheritance(index, templates or {})
    records = []
    for name in index:
        rec = add_display(deepcopy(resolved[name]))
        rec["_id"] = name
        rec["_source"] = source[name]
        enrich(rec, category)
        records.append(rec)
    records.sort(key=lambda r: (r["_source"], r["_id"]))
    path = os.path.join(OUT, category + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    print(f"  {category:12s} {len(records):5d}  -> {os.path.relpath(path, ROOT)}")
    return len(records)

def emit_per_file(category, subdir, skip=(), drop=()):
    """One record per *.gon file (for maps: each file is one area)."""
    records = []
    for path in sorted(glob.glob(os.path.join(DATA, subdir, "*.gon"))):
        fname = os.path.basename(path)
        if fname in skip:
            continue
        parsed = gon.load(path)
        rec = {k: v for k, v in parsed.items() if k not in drop}
        rec = add_display(rec)
        rec["_id"] = fname[:-4]
        rec["_source"] = fname
        records.append(rec)
    records.sort(key=lambda r: r["_id"])
    path = os.path.join(OUT, category + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    print(f"  {category:12s} {len(records):5d}  -> {os.path.relpath(path, ROOT)}")
    return len(records)

def emit_single(category, filename):
    parsed = gon.load(os.path.join(DATA, filename))
    records = []
    for name, ent in parsed.items():
        if not isinstance(ent, dict):
            continue
        rec = add_display(deepcopy(ent))
        rec["_id"] = name
        records.append(rec)
    path = os.path.join(OUT, category + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    print(f"  {category:12s} {len(records):5d}  -> {os.path.relpath(path, ROOT)}")
    return len(records)

# ---- run ---------------------------------------------------------------
def main():
    print(f"[+] loaded {len(STR)} english strings")

    tmpl_index, _ = load_dir("ability_templates")

    counts = {}
    char_index = {}
    print("[+] categories:")
    for cat, sub in [("items", "items"), ("characters", "characters"),
                     ("passives", "passives"), ("classes", "classes"),
                     ("events", "events")]:
        idx, src = load_dir(sub)
        if cat == "characters":
            char_index = idx
        counts[cat] = emit(cat, idx, src)

    # maps: one record per area file (skip the shared include fragment)
    counts["maps"] = emit_per_file(
        "maps", "maps",
        skip={"standard_nodes.gon", "world.gon"},
        drop={"nodes"})

    # abilities need the template namespace
    idx, src = load_dir("abilities")
    # reverse-link every ability so even enemy-only ones are represented, and
    # so icon-less enemy abilities can borrow their owner's sprite as a thumb.
    ability_ids = set(idx)
    ABILITY_OWNERS.update(build_ability_refs(char_index, ability_ids))
    ABILITY_XREFS.update(build_ability_refs(idx, ability_ids, drop_self=True))
    OWNER_SPRITE.update(build_owner_sprites(char_index))
    orphans = sum(1 for a in ability_ids
                  if a not in ABILITY_OWNERS and a not in ABILITY_XREFS)
    print(f"    ability refs: {len(ABILITY_OWNERS)} used by a character, "
          f"{len(ABILITY_XREFS)} chained by another ability, {orphans} orphan")
    counts["abilities"] = emit("abilities", idx, src, tmpl_index)

    # single-file categories
    counts["keywords"] = emit_single("keywords", "keyword_tooltips.gon")

    # music index (lives under dump/audio, not dump/data)
    music = gon.load(os.path.join(DUMP, "audio", "music", "music_info.gon"))
    mrecs = []
    for name, tracks in music.items():
        if isinstance(tracks, dict):
            rec = dict(tracks)
            rec["_id"] = name
            rec["title"] = name.replace("_", " ").title()
            mrecs.append(rec)
    with open(os.path.join(OUT, "music.json"), "w", encoding="utf-8") as f:
        json.dump(mrecs, f, ensure_ascii=False, indent=1)
    counts["music"] = len(mrecs)
    print(f"  {'music':12s} {len(mrecs):5d}  -> wiki_data/music.json")

    # per-language string tables: wiki_data/strings/<code>.json
    strings_dir = os.path.join(OUT, "strings")
    os.makedirs(strings_dir, exist_ok=True)
    lang_meta = []
    for code, table in STRINGS.items():
        with open(os.path.join(strings_dir, code + ".json"), "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=1)
        lang_meta.append({"code": code, "name": NATIVE_NAMES.get(code, code),
                          "strings": len(table)})
        print(f"  strings/{code:8s} {len(table):5d}")

    with open(os.path.join(OUT, "languages.json"), "w", encoding="utf-8") as f:
        json.dump(lang_meta, f, ensure_ascii=False, indent=1)

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "languages": lang_meta}, f,
                  ensure_ascii=False, indent=1)
    print("[+] done ->", os.path.relpath(OUT, ROOT))

if __name__ == "__main__":
    main()
