#!/usr/bin/env bash
# Full Mewgenics wiki-data pipeline. Run from anywhere.
#
#   ./tools/build_all.sh          # data + sprites + icons + relink
#   ./tools/build_all.sh --data   # data only (fast; no rendering)
#
# Requires: python3, and (for assets) the bundled JRE+FFDec in tools/vendor/.
set -euo pipefail
cd "$(dirname "$0")/.."          # -> project root

echo "== 1/4  data (gon -> json, localization, inheritance) =="
python3 tools/build_wiki_data.py

if [[ "${1:-}" == "--data" ]]; then
    echo "done (data only)."; exit 0
fi

echo "== 2/4  character/enemy/boss sprites -> svg =="
python3 tools/export_sprites.py

echo "== 3/4  ability / passive / item icons -> svg =="
python3 tools/export_icons.py

echo "==  +   bake tight viewBoxes into the svg assets =="
python3 tools/normalize_svgs.py sprites icons

echo "== 4/4  relink assets into the json (sprite/icon fields) =="
python3 tools/build_wiki_data.py

echo "all done -> wiki_data/"
