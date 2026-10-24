#!/usr/bin/env bash
# M1 cross-check: per-function cyclomatic complexity (CCN) and NLOC with lizard, to sanity-check
# Understand's Cyclomatic values on the same files.
#
# Usage:  bash lizard_run.sh [GODOT_DIR] [OUT_CSV]
# Tool:   lizard 1.24.1 (pip, pinned in ../requirements.txt), run from ../.venv
# Scope:  same first-party dirs as und_build.sh; modules/mono/thirdparty excluded.
# Output: CSV, one row per function:
#         NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GODOT_DIR="$(cd "${1:-$HERE/../../godot}" && pwd)"
OUT_CSV="${2:-$HERE/out/lizard_functions.csv}"
LIZARD="$HERE/../.venv/Scripts/lizard"

cd "$GODOT_DIR"
"$LIZARD" --version
"$LIZARD" -l cpp -t 4 --csv -x "./modules/mono/thirdparty/*" \
  core main scene servers editor drivers platform modules tests > "$OUT_CSV"
echo "[lizard_run] $(wc -l < "$OUT_CSV") function rows -> $OUT_CSV"
