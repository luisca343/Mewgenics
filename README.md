# Mewgenics Wiki Data

Structured, localized, sprite-linked data extracted from the **Mewgenics** game
files (`resources.gpak`), ready to power a wiki. Everything the site needs lives
in [`wiki_data/`](wiki_data/); the extraction tools live in [`tools/`](tools/).

---

## 1. Quick start

```bash
# Data only (fast, no rendering) — regenerates all JSON:
./tools/build_all.sh --data

# Everything (data + sprites + icons + relink) — needs tools/vendor JRE+FFDec:
./tools/build_all.sh
```

The data step is pure Python (stdlib only). The asset steps drive a bundled
Flash decompiler (JRE + FFDec in `tools/vendor/`, ~100 MB, no system install).

---

## 2. What's in `wiki_data/`

| Path | What it is |
|---|---|
| `items.json` | ~1,134 items — weapons, head/face/neck, trinkets, armor, consumables, cursed, parasites, quest items |
| `characters.json` | ~689 enemies, bosses, minibosses, kaijus, familiars, objects |
| `abilities.json` | ~3,076 spells/attacks (variants + templates resolved) |
| `passives.json` | ~511 class passives + disorders |
| `keywords.json` | ~293 status effects / keyword tooltips |
| `events.json` | ~214 map events (branching trees) |
| `maps.json` | 20 areas — act/chapter, tileset, music, weather, enemy & item pools, bosses |
| `classes.json` | 14 classes / advanced classes |
| `music.json` | 111 track-sets (per area + boss/NPC/radio themes) → `.ogg` paths |
| `strings/<code>.json` | Full localization table per language (`en es fr de it pt`) |
| `languages.json` | Language selector list (code + native name) |
| `sprite_map.json` | `movieclip → { svg, frames }` |
| `icon_map.json` | `{ abilities, passives, items } → svg path` |
| `manifest.json` | Counts + languages summary |
| `assets/sprites/` | One idle SVG per character (289) |
| `assets/sprites_anim/<name>/` | Every animation frame per character (for animated sprites; large) |
| `assets/icons/{abilities,passives}/` | Icon SVGs named by entity id |
| `assets/icons/items/<kind>/` | Item icon SVGs named by frame number |

> `wiki_data/_stage*` are temporary render scratch dirs — safe to delete.
> The bulk of `assets/` size is `sprites_anim/`; if you only want static
> sprites, you can drop that folder.

---

## 3. Record schema

Every record in the category files shares these conventions:

| Field | Meaning |
|---|---|
| `_id` | Stable internal id (unique within category). Use as the URL slug. |
| `_source` | Origin `.gon` file (useful for grouping/debugging). |
| `<field>_key` | Localization **key** for a display field (`name_key`, `desc_key`, `tooltip_key`, `title_key`, `area_name_key`). Resolve via the string tables. |
| `<field>_en` | English text for that field — a ready fallback. |
| `sprite` | (characters) path to the idle SVG, e.g. `assets/sprites/Rat.svg`. |
| `sprite_frames` | (characters) frame count available under `assets/sprites_anim/<name>/`. |
| `icon` | (items/abilities/passives) path to the icon SVG. |

All other fields are the game's own data, preserved as-is. `variant_of` and
ability `template` inheritance are already merged into each record, so you get
the full effective stats without chasing parents.

**Example** (`characters.json`):

```json
{
  "_id": "Rat",
  "name_key": "ENEMY_LILRAT_NAME",
  "name_en": "Lil' Rat",
  "tooltip_en": "Dashes in a straight line.",
  "sprite": "assets/sprites/Rat.svg",
  "sprite_frames": 30,
  "stats": { "strength": 4, "dexterity": 5, "constitution": 5, ... },
  "properties": { "faction": "enemies", "health": 5, ... },
  "abilities": { "move": "DefaultMove", "attack": "Dash_Enemy", "spells": [] }
}
```

---

## 4. Localization (multi-language)

Text is **not** stored inline; records carry keys. Resolve them against the
per-language tables so one dataset serves every language.

```js
const strings = await fetch(`wiki_data/strings/${lang}.json`).then(r => r.json());
const en      = await fetch(`wiki_data/strings/en.json`).then(r => r.json());

// resolve, with English fallback:
const t = (key) => strings[key] ?? en[key] ?? key;

t(item.name_key)   // "Fragmento de cristal"  (lang="es")
t(item.desc_key)   // ...
```

`languages.json` drives the language switcher:

```json
[ { "code": "en", "name": "English" }, { "code": "es", "name": "Español" }, ... ]
```

**Adding a language.** The source CSV (`dump/data/text/combined.csv`) already
has `ru ko ja zh` columns (currently untranslated). To enable any language, add
one line to the `LANGUAGES` dict in
[`tools/build_wiki_data.py`](tools/build_wiki_data.py) (`wiki_code: csv_column`)
and rerun `./tools/build_all.sh --data`. Coverage today:

| en | es | fr | de | it | pt |
|----|----|----|----|----|----|
| 16,277 | 16,277 | 15,999 | 16,263 | 16,469 | 16,015 |

> Some strings contain HTML (`&nbsp;`, `\n`, `[img:str]` icon tokens). Render
> `desc_en`/resolved text as HTML and decide how to display `[img:...]` tags.

---

## 5. Assets

All art is exported as **SVG** (the game art is vector Flash — crisp at any
size, self-contained, no external refs).

- **Character sprites** — `record.sprite` → `assets/sprites/<movieclip>.svg`
  (idle pose). Full animations, if you want them, are numbered frames under
  `assets/sprites_anim/<movieclip>/1.svg … N.svg`.
- **Item icons** — `record.icon` → `assets/icons/items/<kind>/<frame>.svg`.
  Already linked; kinds are `weapon head face neck trinket`.
- **Ability / passive icons** — `record.icon` → `assets/icons/{abilities,passives}/<id>.svg`.
  Icon file name equals the ability/passive `_id`; variants fall back to their
  base's icon.

Because SVGs are self-contained you can inline them (`<svg>…`), reference them
(`<img src="wiki_data/assets/sprites/Rat.svg">`), or embed as data URIs.

> **viewBox is baked in.** FFDec exports a huge pixel canvas with the art often
> in a small corner (e.g. SpiderQueen's art sat at y≈3800 in a 4255-tall canvas),
> so raw files display tiny/clipped. `tools/normalize_svgs.py` (part of the
> pipeline) rewrites every sprite/icon with a tight content `viewBox` + matching
> `width`/`height`, so `<img src=…>` / `<object>` / background-image all render
> correctly at natural size. Re-run it if you ever re-export.
>
> ⚠️ **Only if you inline raw `<svg>` into one page** (the preview does this, a
> normal wiki doesn't): internal ids (`sprite0`, `shape0`, …) collide across
> SVGs and every sprite renders as the first — namespace ids per-svg. See
> `_namespace()` in `tools/generate_preview.py`. Using `<img>`/files avoids it.

### Music
`music.json` maps each track-set to `.ogg` files under
`dump/audio/music/…`. Areas expose `map` / `battle` / `boss` / `event` / `intro`
stems; radio songs expose `boss` + `intros` + `outros`. The `.ogg` files are
web-playable as-is — serve them and point an `<audio>` tag at them.

---

## 6. The tools

| Script | Role |
|---|---|
| [`tools/gon.py`](tools/gon.py) | Parser for GON (the game's config format): includes, comments, arrays, numeric keys. |
| [`tools/build_wiki_data.py`](tools/build_wiki_data.py) | GON → JSON. Resolves localization, `variant_of`/`template` inheritance, and links assets. Contains the `LANGUAGES` config. |
| [`tools/export_sprites.py`](tools/export_sprites.py) | Renders referenced character movieclips → SVG (parallel across SWFs). |
| [`tools/export_icons.py`](tools/export_icons.py) | Renders ability/passive (by frame label) and item (by frame number) icons → SVG. |
| [`tools/build_all.sh`](tools/build_all.sh) | Runs the whole pipeline in order. |

---

## 7. Notes & caveats

- **Enemy-worn items** (~41 in `enemy_items.gon`) have intentionally blank names
  (`name_en: ""`) — they aren't player-facing loot.
- **Ability icon coverage** is ~51%: internal/enemy-only abilities simply have no
  icon frame. Player-facing abilities are covered.
- **Character sprite coverage** (294 sprites, 477 records linked): modular cats
  (assembled from `catparts.swf`), generic placeholders (`Rock`, statics), and a
  handful of runtime-assembled bosses (the final-boss phases, `Tormentor`,
  `MotherSpike`, `Twister`) have no single standalone movieclip — their frames
  render empty — so they're left unlinked (`sprite` absent) rather than pointing
  at a blank file. Show a placeholder for records without a `sprite`.
- Source of truth is `dump/`. Re-extract the archive with `script.py` if needed;
  the tools always read from `dump/` and write to `wiki_data/`.
