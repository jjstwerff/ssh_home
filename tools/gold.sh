#!/usr/bin/env bash
# ssh_home golden-image runner (PLAN Step 0.2).
#   tools/gold.sh [name]          compare a fresh capture to golden/<name>.png
#   BLESS=1 tools/gold.sh [name]  regenerate the golden
# The GL clear/text render is deterministic on a given GPU, so a solid frame
# compares byte-exact (text goldens get a tolerance pass at Step 0.3).
set -euo pipefail
name="${1:-clear}"
here="$(cd "$(dirname "$0")/.." && pwd)"
d="$(mktemp -d)"; tmp="$d/cap.png"
# graphics emits many pre-existing `not null` deprecation warnings; hide them,
# but show loft's stderr if the run actually fails.
if ! loft --interpret "$here/src/main.loft" "$tmp" "$name" >/dev/null 2>"$d/err"; then
  cat "$d/err" >&2; echo "FAIL $name (loft run errored)"; exit 1
fi
gold="$here/golden/$name.png"
if [ "${BLESS:-0}" = 1 ]; then mkdir -p "$here/golden"; cp "$tmp" "$gold"; echo "BLESSED $name"; exit 0; fi
[ -f "$gold" ] || { echo "no golden '$name' — run: BLESS=1 tools/gold.sh $name"; exit 1; }
if cmp -s "$tmp" "$gold"; then echo "PASS $name"; else echo "FAIL $name (capture != golden)"; exit 1; fi
