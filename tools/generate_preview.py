"""Generate a self-contained HTML preview of the extracted wiki data.

Inlines a curated set of sprites + item icons, a display font, and mini
localization tables for all languages, so the page is fully standalone.
"""
import base64
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WD = os.path.join(ROOT, "wiki_data")
SCRATCH = "/tmp/claude-1000/-home-luisca-Programacion-Mewgenics/" \
          "743caa06-9c8e-4ed2-a700-efc118538828/scratchpad"
OUT = os.path.join(SCRATCH, "preview.html")
FONT_TTF = os.path.join(SCRATCH, "anton.ttf")

LANGS = ["en", "es", "fr", "de", "it", "pt"]

# Curated, recognizable showcase (filtered to those that actually have sprites)
CREATURE_PICKS = [
    "Rat", "Fly", "Worm", "Gasser", "Pooter", "Bat", "Amoeba",
    "AstroZombie", "RattleSnake", "SkeletonShambler", "Bear", "Hive",
    "SpiderQueen", "RatKing", "TheCoven", "QueenHippo", "Bumblefoot",
    "Flushmaster", "MotherTumor", "AlienBeast", "Trampy", "Dybbuk",
    "Chubs", "LordBunga", "DustDevil",
]
ITEM_PICKS = [
    "GlassShard", "MeatHook", "Kebab", "ChumBucket", "NailBoard",
    "BonesHat", "AncestorsSkull", "CapAndBells", "ClownMakeup",
    "AsteroidBelt", "StunningChain", "BarbedMask",
]


def load(name):
    return json.load(open(os.path.join(WD, name), encoding="utf-8"))


_ns_ctr = [0]

def _namespace(svg, pfx):
    """Prefix every internal id (and its #/url() references) so multiple
    inlined SVGs don't collide on shared ids like sprite0/shape0."""
    for i in set(re.findall(r'id="([^"]+)"', svg)):
        svg = (svg.replace(f'id="{i}"', f'id="{pfx}{i}"')
                  .replace(f'"#{i}"', f'"#{pfx}{i}"')
                  .replace(f'url(#{i})', f'url(#{pfx}{i})'))
    return svg

# ---- tight bounding box (FFDec canvases are often huge with the art in a
# ---- small corner; use the real content bbox as the viewBox) ---------------
import xml.etree.ElementTree as ET
_SVG = "{http://www.w3.org/2000/svg}"
_XL = "{http://www.w3.org/1999/xlink}"

def _matrix(t):
    if t:
        m = re.search(r"matrix\(([^)]*)\)", t)
        if m:
            v = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", m.group(1))]
            if len(v) == 6:
                return tuple(v)
    return (1, 0, 0, 1, 0, 0)

def _compose(A, B):
    a, b, c, d, e, f = A
    a2, b2, c2, d2, e2, f2 = B
    return (a*a2+c*b2, b*a2+d*b2, a*c2+c*d2, b*c2+d*d2, a*e2+c*f2+e, b*e2+d*f2+f)

def _path_pts(d):
    toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    pts, cmd, cx, cy, i, n = [], None, 0.0, 0.0, 0, len(toks)
    def nv():
        nonlocal i
        v = float(toks[i]); i += 1; return v
    while i < n:
        if toks[i].isalpha():
            cmd = toks[i]; i += 1; continue
        if cmd in ("M", "L", "T"):
            cx, cy = nv(), nv(); pts.append((cx, cy))
        elif cmd in ("m", "l", "t"):
            cx, cy = cx+nv(), cy+nv(); pts.append((cx, cy))
        elif cmd == "H": cx = nv(); pts.append((cx, cy))
        elif cmd == "h": cx += nv(); pts.append((cx, cy))
        elif cmd == "V": cy = nv(); pts.append((cx, cy))
        elif cmd == "v": cy += nv(); pts.append((cx, cy))
        elif cmd in ("Q", "S"):
            x1, y1, cx, cy = nv(), nv(), nv(), nv()
            pts += [(x1, y1), (cx, cy)]
        elif cmd in ("q", "s"):
            x1, y1, x, y = nv(), nv(), nv(), nv()
            pts += [(cx+x1, cy+y1), (cx+x, cy+y)]; cx, cy = cx+x, cy+y
        elif cmd == "C":
            for _ in range(2): pts.append((nv(), nv()))
            cx, cy = nv(), nv(); pts.append((cx, cy))
        elif cmd == "c":
            for _ in range(2): pts.append((cx+nv(), cy+nv()))
            cx, cy = cx+nv(), cy+nv(); pts.append((cx, cy))
        else:
            i += 1
    return pts

def _walk(el, M, idx, bb, depth=0):
    if depth > 80:
        return
    t = _compose(M, _matrix(el.get("transform")))
    tag = el.tag.replace(_SVG, "")
    if tag == "use":
        t = _compose(t, (1, 0, 0, 1, float(el.get("x") or 0), float(el.get("y") or 0)))
        href = el.get(_XL + "href") or el.get("href")
        if href and href.startswith("#") and href[1:] in idx:
            _walk(idx[href[1:]], t, idx, bb, depth+1)
    elif tag == "path":
        a, b, c, d, e, f = t
        for x, y in _path_pts(el.get("d", "")):
            X, Y = a*x+c*y+e, b*x+d*y+f
            bb[0] = min(bb[0], X); bb[1] = min(bb[1], Y)
            bb[2] = max(bb[2], X); bb[3] = max(bb[3], Y)
    else:
        for ch in el:
            if ch.tag.replace(_SVG, "") != "defs":
                _walk(ch, t, idx, bb, depth+1)

def _content_bbox(s):
    root = ET.fromstring(s)
    idx = {el.get("id"): el for el in root.iter() if el.get("id")}
    bb = [1e9, 1e9, -1e9, -1e9]
    for ch in root:
        if ch.tag.replace(_SVG, "") != "defs":
            _walk(ch, (1, 0, 0, 1, 0, 0), idx, bb)
    return bb if bb[2] > bb[0] and bb[3] > bb[1] else None

def _add_viewbox(s):
    """Set viewBox to the true content bbox (art often sits in a small region
    of a huge FFDec canvas) and drop the fixed pixel size so CSS scales it."""
    m = re.search(r"<svg\b([^>]*)>", s)
    if not m or "viewBox" in m.group(1):
        return s
    attrs = m.group(1)
    try:
        bb = _content_bbox(s)
    except Exception:
        bb = None
    if bb:
        pad = 0.06 * max(bb[2]-bb[0], bb[3]-bb[1])
        vb = f"{bb[0]-pad:.1f} {bb[1]-pad:.1f} {bb[2]-bb[0]+2*pad:.1f} {bb[3]-bb[1]+2*pad:.1f}"
    else:
        w = re.search(r'width="([\d.]+)', attrs)
        h = re.search(r'height="([\d.]+)', attrs)
        if not (w and h):
            return s
        vb = f"0 0 {w.group(1)} {h.group(1)}"
    new = re.sub(r'\s(?:width|height)="[^"]*"', "", attrs)
    tag = f'<svg{new} viewBox="{vb}" preserveAspectRatio="xMidYMid meet">'
    return s[:m.start()] + tag + s[m.end():]

def svg_inline(path):
    """Read an SVG file, strip XML prolog, add viewBox, id-namespace it."""
    with open(os.path.join(WD, path), encoding="utf-8") as f:
        s = f.read()
    i = s.find("<svg")
    s = s[i:] if i >= 0 else s
    s = _add_viewbox(s)
    pfx = f"g{_ns_ctr[0]}_"
    _ns_ctr[0] += 1
    return _namespace(s, pfx)


def by_id(records):
    return {r["_id"]: r for r in records}


def _has_asset(r, field):
    """True only if the linked asset file actually exists and isn't empty."""
    p = r.get(field)
    if not isinstance(p, str):
        return False
    fp = os.path.join(WD, p)
    return os.path.exists(fp) and os.path.getsize(fp) > 400

def pick(records_by_id, wanted, need_field, n):
    out = []
    for wid in wanted:
        r = records_by_id.get(wid)
        if r and _has_asset(r, need_field):
            out.append(r)
    # top up from anything else that has a real asset
    if len(out) < n:
        for r in records_by_id.values():
            if _has_asset(r, need_field) and r not in out:
                out.append(r)
                if len(out) >= n:
                    break
    return out[:n]


RARITY = {
    "common": "#9b8d7d", "uncommon": "#6f9e3f", "rare": "#3f82bb",
    "very_rare": "#9a6fc0", "legendary": "#dca63f", "sidequest": "#c96a2e",
    "quest": "#c96a2e",
}
def rarity_color(r):
    if not isinstance(r, str):
        return RARITY["common"]
    r = r.replace("consumable_", "")
    return RARITY.get(r, "#9b8d7d")


def main():
    chars = by_id(load("characters.json"))
    items = by_id(load("items.json"))
    maps = load("maps.json")
    manifest = load("manifest.json")
    strings = {l: load(f"strings/{l}.json") for l in LANGS}

    creatures = pick(chars, CREATURE_PICKS, "sprite", 24)
    weapons = pick(items, ITEM_PICKS, "icon", 12)

    # collect the localization keys we actually use -> mini tables
    used_keys = set()
    for r in creatures + weapons:
        for f in ("name_key", "desc_key", "tooltip_key"):
            if r.get(f):
                used_keys.add(r[f])
    mini = {l: {k: strings[l].get(k, strings["en"].get(k, k))
                for k in used_keys} for l in LANGS}

    font_b64 = base64.b64encode(open(FONT_TTF, "rb").read()).decode()

    # ---- build creature cards ----
    ccards = []
    for r in creatures:
        p = r.get("properties", {}) if isinstance(r.get("properties"), dict) else {}
        st = r.get("stats", {}) if isinstance(r.get("stats"), dict) else {}
        is_boss = p.get("type") == "boss"
        hp = p.get("health", "—")
        faction = p.get("faction", "")
        statbars = ""
        for s, ab in [("str", "strength"), ("dex", "dexterity"), ("con", "constitution"),
                      ("int", "intelligence"), ("spd", "speed"), ("cha", "charisma")]:
            v = st.get(ab, 0) or 0
            statbars += (f'<div class="stat"><span>{s}</span>'
                         f'<i style="--v:{min(int(v),10)*10}%"></i>'
                         f'<b>{v}</b></div>')
        ccards.append(f'''
        <article class="card {'boss' if is_boss else ''}">
          {'<span class="stamp">BOSS</span>' if is_boss else ''}
          <div class="specimen">{svg_inline(r["sprite"])}</div>
          <div class="plate">
            <h3 data-k="{html.escape(r.get('name_key',''))}">{html.escape(r.get('name_en') or r['_id'])}</h3>
            <div class="meta"><span class="cat">{html.escape(r['_id'])}</span>
              <span class="hp">{hp} HP</span></div>
          </div>
          <div class="stats">{statbars}</div>
          <p class="tip" data-k="{html.escape(r.get('tooltip_key',''))}">{html.escape(r.get('tooltip_en') or '')}</p>
        </article>''')

    # ---- build item cards ----
    icards = []
    for r in weapons:
        col = rarity_color(r.get("rarity"))
        dur = r.get("durability")
        dur = (f"{dur[0]}–{dur[1]}" if isinstance(dur, list) else dur) or "∞"
        icards.append(f'''
        <article class="item" style="--rar:{col}">
          <div class="ico">{svg_inline(r["icon"])}</div>
          <h4 data-k="{html.escape(r.get('name_key',''))}">{html.escape(r.get('name_en') or r['_id'])}</h4>
          <div class="irow"><span class="chip">{html.escape(str(r.get('rarity','')).replace('_',' '))}</span>
            <span class="kind">{html.escape(str(r.get('kind','')))}</span></div>
          <p class="idesc" data-k="{html.escape(r.get('desc_key',''))}">{html.escape(r.get('desc_en') or '')}</p>
        </article>''')

    # ---- area strip ----
    acards = []
    for m in sorted([x for x in maps if x.get("area_name_en")],
                    key=lambda x: (x.get("act", 9), x.get("chapter", 9)))[:12]:
        acards.append(f'''<div class="area"><b data-k="{html.escape(m.get('area_name_key',''))}">{html.escape(m.get('area_name_en') or m['_id'])}</b>
          <span>Act {m.get('act','?')} · Ch {m.get('chapter','?')}</span>
          <em>{html.escape(str(m.get('music','')))}</em></div>''')

    counts = manifest["counts"]
    langpills = "".join(
        f'<button class="lang{" on" if l=="en" else ""}" data-l="{l}">{l.upper()}</button>'
        for l in LANGS)

    html_doc = TEMPLATE.format(
        font_b64=font_b64,
        strings_json=json.dumps(mini, ensure_ascii=False),
        langpills=langpills,
        n_creatures=counts["characters"], n_items=counts["items"],
        n_abilities=counts["abilities"], n_sprites=len(load('sprite_map.json')),
        n_langs=len(LANGS),
        creature_cards="".join(ccards),
        item_cards="".join(icards),
        area_cards="".join(acards),
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print("wrote", OUT, f"({os.path.getsize(OUT)//1024} KB)")
    print(f"creatures={len(creatures)} items={len(weapons)} keys={len(used_keys)}")


TEMPLATE = r"""<title>Mewgenics — Specimen Vault</title>
<style>
@font-face{{font-family:'Anton';src:url(data:font/ttf;base64,{font_b64}) format('truetype');font-display:swap}}
:root{{
  --bg:#15100e; --panel:#1d1512; --panel2:#251a15; --line:#3a2820;
  --ink:#ece1d2; --dim:#a89383; --blood:#d84335; --blood2:#8f221a;
  --bile:#a6b442; --gold:#dca63f;
  --spec:#2a1f1a; --spec2:#1a1310;
}}
@media (prefers-color-scheme:light){{:root{{
  --bg:#e7dccb; --panel:#f3ebdb; --panel2:#ece0cd; --line:#d3c1a8;
  --ink:#231a13; --dim:#6d5b4b; --blood:#b62e22; --blood2:#8f221a;
  --spec:#e5d8c2; --spec2:#f2e9d8;
}}}}
:root[data-theme="dark"]{{
  --bg:#15100e; --panel:#1d1512; --panel2:#251a15; --line:#3a2820;
  --ink:#ece1d2; --dim:#a89383; --blood:#d84335;
  --spec:#2a1f1a; --spec2:#1a1310;
}}
:root[data-theme="light"]{{
  --bg:#e7dccb; --panel:#f3ebdb; --panel2:#ece0cd; --line:#d3c1a8;
  --ink:#231a13; --dim:#6d5b4b; --blood:#b62e22;
  --spec:#e5d8c2; --spec2:#f2e9d8;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:400 16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;position:relative}}
body::before{{content:"";position:fixed;inset:0;pointer-events:none;z-index:9;opacity:.05;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 24px}}
header{{border-bottom:2px solid var(--line);background:
  linear-gradient(180deg,color-mix(in srgb,var(--blood2) 22%,var(--bg)),var(--bg));position:relative;overflow:hidden}}
header .wrap{{padding:38px 24px 26px;position:relative;z-index:2}}
.brand{{font-family:'Anton';font-size:clamp(52px,11vw,120px);line-height:.86;letter-spacing:.01em;
  text-transform:uppercase;margin:0;color:var(--ink);text-wrap:balance}}
.brand em{{color:var(--blood);font-style:normal}}
.sub{{display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;justify-content:space-between;margin-top:14px}}
.tagline{{color:var(--dim);letter-spacing:.14em;text-transform:uppercase;font-size:12.5px}}
.langs{{display:flex;gap:4px;flex-wrap:wrap}}
.lang,.themed{{font:600 12px/1 system-ui;letter-spacing:.08em;color:var(--dim);background:var(--panel);
  border:1px solid var(--line);padding:8px 11px;border-radius:2px;cursor:pointer;transition:.15s}}
.lang:hover,.themed:hover{{color:var(--ink);border-color:var(--blood)}}
.lang.on{{background:var(--blood);color:#fff;border-color:var(--blood)}}
.ribbon{{display:flex;flex-wrap:wrap;gap:0;border-bottom:2px solid var(--line);background:var(--panel)}}
.ribbon .wrap{{display:flex;flex-wrap:wrap;padding:0}}
.stat-cell{{flex:1;min-width:130px;padding:16px 20px;border-right:1px solid var(--line)}}
.stat-cell b{{font-family:'Anton';font-size:30px;display:block;line-height:1;font-variant-numeric:tabular-nums}}
.stat-cell span{{color:var(--dim);font-size:11px;letter-spacing:.14em;text-transform:uppercase}}
section{{padding:44px 0 8px}}
.shead{{display:flex;align-items:baseline;gap:16px;margin:0 0 22px}}
.shead h2{{font-family:'Anton';text-transform:uppercase;font-size:30px;letter-spacing:.02em;margin:0}}
.shead .rule{{flex:1;height:2px;background:
  repeating-linear-gradient(90deg,var(--line) 0 8px,transparent 8px 14px)}}
.shead .n{{color:var(--dim);font-size:13px;font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:14px;position:relative;
  transition:transform .18s,border-color .18s,box-shadow .18s}}
.card:hover{{transform:translateY(-3px);border-color:color-mix(in srgb,var(--blood) 55%,var(--line));
  box-shadow:0 10px 30px -12px rgba(0,0,0,.6)}}
.card.boss{{border-color:color-mix(in srgb,var(--blood) 45%,var(--line))}}
.stamp{{position:absolute;top:10px;right:10px;z-index:3;font:700 10px/1 system-ui;letter-spacing:.16em;
  color:#fff;background:var(--blood);padding:4px 7px;border-radius:2px;transform:rotate(3deg)}}
.specimen{{height:150px;display:grid;place-items:center;border-radius:3px;margin-bottom:12px;padding:16px;
  background:radial-gradient(circle at 50% 42%,var(--spec),var(--spec2));border:1px solid var(--line);overflow:hidden}}
.specimen svg{{width:100%;height:100%;filter:drop-shadow(0 4px 6px rgba(0,0,0,.35));
  transition:transform .25s}}
.card:hover .specimen svg{{transform:translateY(-3px) scale(1.04)}}
.plate h3{{font-family:'Anton';font-size:21px;letter-spacing:.01em;margin:0;line-height:1;text-wrap:balance}}
.meta{{display:flex;justify-content:space-between;align-items:center;margin-top:6px;gap:8px}}
.cat{{font:500 11px/1 ui-monospace,Menlo,monospace;color:var(--dim);opacity:.8}}
.hp{{font:700 11px/1 system-ui;color:var(--blood);font-variant-numeric:tabular-nums;letter-spacing:.03em}}
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;margin:12px 0 4px}}
.stat{{display:flex;align-items:center;gap:6px;font:600 10px/1 system-ui;color:var(--dim)}}
.stat span{{width:20px;text-transform:uppercase;letter-spacing:.05em}}
.stat i{{flex:1;height:4px;border-radius:2px;background:var(--line);position:relative;overflow:hidden}}
.stat i::after{{content:"";position:absolute;inset:0;width:var(--v);background:var(--bile);border-radius:2px}}
.stat b{{width:14px;text-align:right;color:var(--ink);font-variant-numeric:tabular-nums}}
.tip{{color:var(--dim);font-size:12.5px;line-height:1.45;margin:8px 0 0;min-height:1px}}
.igrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}}
.item{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--rar);
  border-radius:4px;padding:14px;transition:transform .18s,box-shadow .18s}}
.item:hover{{transform:translateY(-3px);box-shadow:0 10px 26px -12px rgba(0,0,0,.55)}}
.ico{{height:96px;display:grid;place-items:center;margin-bottom:10px;padding:8px}}
.ico svg{{width:100%;height:100%;filter:drop-shadow(0 3px 4px rgba(0,0,0,.4))}}
.item h4{{font-family:'Anton';font-size:17px;letter-spacing:.02em;margin:0 0 8px;line-height:1.02;text-wrap:balance}}
.irow{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.chip{{font:700 10px/1 system-ui;text-transform:uppercase;letter-spacing:.07em;color:#fff;
  background:var(--rar);padding:4px 7px;border-radius:2px}}
.kind{{font:500 11px/1 ui-monospace,monospace;color:var(--dim)}}
.idesc{{color:var(--dim);font-size:12px;line-height:1.45;margin:0}}
.areas{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}}
.area{{background:var(--panel2);border:1px solid var(--line);border-radius:3px;padding:12px 14px;
  display:flex;flex-direction:column;gap:3px}}
.area b{{font-family:'Anton';font-size:16px;letter-spacing:.02em}}
.area span{{color:var(--dim);font-size:11px;letter-spacing:.06em;text-transform:uppercase}}
.area em{{color:var(--bile);font:500 11px/1 ui-monospace,monospace;font-style:normal}}
footer{{margin-top:44px;border-top:2px solid var(--line);background:var(--panel)}}
footer .wrap{{padding:26px 24px;color:var(--dim);font-size:12.5px;display:flex;
  justify-content:space-between;gap:16px;flex-wrap:wrap}}
footer b{{color:var(--ink)}}
[data-k]{{transition:opacity .12s}}
.fade [data-k]{{opacity:0}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>

<header><div class="wrap">
  <h1 class="brand">Mew<em>genics</em></h1>
  <div class="sub">
    <span class="tagline">Specimen Vault · extracted game data · {n_langs} languages</span>
    <div class="langs"><span style="color:var(--dim);font-size:11px;letter-spacing:.12em;align-self:center;margin-right:4px">LANG</span>{langpills}
      <button class="themed" id="themeBtn" style="margin-left:8px">◐ THEME</button></div>
  </div>
</div></header>

<div class="ribbon"><div class="wrap">
  <div class="stat-cell"><b>{n_creatures}</b><span>Creatures</span></div>
  <div class="stat-cell"><b>{n_items}</b><span>Items</span></div>
  <div class="stat-cell"><b>{n_abilities}</b><span>Abilities</span></div>
  <div class="stat-cell"><b>{n_sprites}</b><span>Sprites (SVG)</span></div>
  <div class="stat-cell"><b>{n_langs}</b><span>Languages</span></div>
</div></div>

<div class="wrap">
  <section>
    <div class="shead"><h2>Bestiary</h2><div class="rule"></div><span class="n">idle sprites · live-localized names</span></div>
    <div class="grid">{creature_cards}</div>
  </section>

  <section>
    <div class="shead"><h2>Armory</h2><div class="rule"></div><span class="n">icons · rarity-graded</span></div>
    <div class="igrid">{item_cards}</div>
  </section>

  <section>
    <div class="shead"><h2>Territories</h2><div class="rule"></div><span class="n">areas · music cue</span></div>
    <div class="areas">{area_cards}</div>
  </section>
</div>

<footer><div class="wrap">
  <span>Rendered from <b>resources.gpak</b> — GON data + vector Flash art, extracted to JSON &amp; SVG.</span>
  <span>Switch <b>LANG</b> to relocalize every name from the string tables.</span>
</div></footer>

<script>
const STRINGS = {strings_json};
let lang = "en";
function relocalize(){{
  document.querySelectorAll("[data-k]").forEach(el=>{{
    const k = el.getAttribute("data-k");
    if(!k) return;
    const t = (STRINGS[lang]&&STRINGS[lang][k]) || (STRINGS.en&&STRINGS.en[k]) || "";
    if(t) el.textContent = t;
  }});
}}
document.querySelectorAll(".lang").forEach(b=>b.addEventListener("click",()=>{{
  document.querySelectorAll(".lang").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); lang=b.dataset.l;
  document.body.classList.add("fade");
  setTimeout(()=>{{relocalize();document.body.classList.remove("fade");}},130);
}}));
const root=document.documentElement, tb=document.getElementById("themeBtn");
tb.addEventListener("click",()=>{{
  const cur=root.getAttribute("data-theme")||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");
  root.setAttribute("data-theme",cur==="dark"?"light":"dark");
}});
</script>
"""


if __name__ == "__main__":
    main()
