#!/usr/bin/env bash
# M1 (cognitive part): SonarSource cognitive complexity per function for selected files, measured
# with clang-tidy's readability-function-cognitive-complexity check (Threshold 0 = report all).
#
# Usage:  [IGNORE_MACROS=true] bash cognitive_run.sh <SRC_DIR> <OUT_CSV> <file.cpp> [file.cpp ...]
#   IGNORE_MACROS=true skips increments that come from macro expansions (e.g. ERR_FAIL_COND),
#   default false (= what the compiler sees).
#   SRC_DIR  a git-archive copy of Godot (e.g. ../work/src-57277407), NOT the analysis clone:
#            this script generates compile_commands.json and *.gen.h files inside it.
# Tools:  clang-tidy 22.1.3 (bundled with Visual Studio 18, VC/Tools/Llvm/x64/bin),
#         SCons 4.11.1 (../.venv) with MSVC 14.5 / Windows SDK 10.0.26100.0
# Build options: platform=windows target=editor accesskit=no d3d12=no angle=no (these three drivers
#         need extra SDKs and are irrelevant to the measured files).
# Output CSV: file,line,function,cognitive
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$1" && pwd)"; OUT_CSV="$2"; shift 2
CT="/c/Program Files/Microsoft Visual Studio/18/Community/VC/Tools/Llvm/x64/bin/clang-tidy.exe"
SCONS="$HERE/../.venv/Scripts/scons"
OPTS="platform=windows target=editor accesskit=no d3d12=no angle=no"

cd "$SRC"
"$CT" --version | grep -i "version"
[ -f compile_commands.json ] || "$SCONS" $OPTS compiledb=yes compiledb_gen_only=yes

echo "file,line,function,cognitive" > "$OUT_CSV"
for f in "$@"; do
  log="$(mktemp)"
  for attempt in 1 2 3 4 5 6 7 8; do
    "$CT" -p . --checks='-*,readability-function-cognitive-complexity' \
      --config="{CheckOptions: {readability-function-cognitive-complexity.Threshold: 0, readability-function-cognitive-complexity.IgnoreMacros: ${IGNORE_MACROS:-false}}}" "$f" > "$log" 2>&1 || true
    # Generated headers only exist after a build step; build exactly the missing ones and retry.
    missing=$(grep -oE "'[^']+\.gen\.(h|inc)' file not found" "$log" | sed -E "s/'([^']+)'.*/\1/" | sort -u || true)
    [ -z "$missing" ] && break
    echo "[cognitive_run] $f: generating $missing"
    # shellcheck disable=SC2086
    "$SCONS" $OPTS $missing > /dev/null
  done
  errs=$(grep -c ": error:" "$log" || true)
  echo "[cognitive_run] $f: clang errors=$errs"
  base="$(basename "$f")"
  grep -E "${base}:[0-9]+:[0-9]+: warning: function '.*' has cognitive complexity of [0-9]+" "$log" \
    | sed -E "s#.*${base}:([0-9]+):[0-9]+: warning: function '(.*)' has cognitive complexity of ([0-9]+).*#${f//\\/\/},\1,\2,\3#" >> "$OUT_CSV"
  rm -f "$log"
done
echo "[cognitive_run] -> $OUT_CSV"
