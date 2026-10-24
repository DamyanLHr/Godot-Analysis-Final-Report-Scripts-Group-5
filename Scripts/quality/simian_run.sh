#!/usr/bin/env bash
# M4 Duplication: runs Simian per top-level module at two thresholds and summarises to CSV.
#
# Usage:  bash simian_run.sh [GODOT_DIR] [OUT_NAME]
# Tool:   Simian 2.5.10 (Tools/simian.jar), Java 21, -language=cpp, otherwise default options
#         (ignoreCurlyBraces, ignoreIdentifierCase, ignoreModifiers, ignoreStringCase on).
#         -language=cpp makes Simian strip C++ comments from *.inc files too; without it the
#         licence header of every *.compat.inc is reported as a clone (kept in out/simian_nolanguage).
# Scope:  first-party C++ (*.cpp, *.h, *.inc) per module; thirdparty/ and modules/mono/thirdparty
#         excluded. Each module is a separate run, so only clones *within* a module are found.
# Output: out/<OUT_NAME>/<module>_t<threshold>.txt (full reports) and out/<OUT_NAME>_summary.csv
set -euo pipefail

# Windows tools cannot parse MSYS /c/... paths containing an apostrophe -> use C:/... form.
HERE="$(cygpath -m "$(cd "$(dirname "$0")" && pwd)")"
GODOT_DIR="$(cygpath -m "$(cd "${1:-$HERE/../../godot}" && pwd)")"
OUT_NAME="${2:-simian}"
SIMIAN="$(cygpath -m "$HERE/../../Tools/simian.jar")"
OUT="$HERE/out/$OUT_NAME"
SUMMARY="$HERE/out/${OUT_NAME}_summary.csv"
mkdir -p "$OUT"

echo "module,threshold,duplicate_lines,blocks,files_with_dups,significant_lines,raw_lines,files,dup_pct" > "$SUMMARY"

for t in 6 10; do
  for m in core main scene servers editor drivers platform modules tests; do
    report="$OUT/${m}_t${t}.txt"
    # Simian resolves globs against the working directory, and "dir/**/*.cpp" only matches files
    # in sub-folders, so both "dir/*.ext" and "dir/**/*.ext" are passed.
    (cd "$GODOT_DIR" && java -jar "$SIMIAN" -threshold=$t -language=cpp \
      "$m/*.cpp" "$m/*.h" "$m/*.inc" "$m/**/*.cpp" "$m/**/*.h" "$m/**/*.inc" \
      -excludes="modules/mono/thirdparty/**/*") > "$report" 2>&1 || true   # exit 1 = duplicates found
    # "Found 110 duplicate lines in 12 blocks in 6 files"
    # "Processed a total of 2644 significant (9694 raw) lines in 52 files"
    dup=$(grep -oE 'Found [0-9]+ duplicate lines in [0-9]+ blocks in [0-9]+ files' "$report" | grep -oE '[0-9]+' | tr '\n' ' ' || true)
    tot=$(grep -oE 'Processed a total of [0-9]+ significant \([0-9]+ raw\) lines in [0-9]+ files' "$report" | grep -oE '[0-9]+' | tr '\n' ' ')
    read -r dl bl fd <<< "${dup:-0 0 0}"
    read -r sl rl nf <<< "$tot"
    pct=$(awk -v d="$dl" -v s="$sl" 'BEGIN{printf "%.2f", (s>0? 100*d/s : 0)}')
    echo "$m,$t,$dl,$bl,$fd,$sl,$rl,$nf,$pct" | tee -a "$SUMMARY"
  done
done
