#!/usr/bin/env bash
# Builds the SciTools Understand database for Godot and exports all metrics to CSV.
#
# Usage:  bash und_build.sh [GODOT_DIR] [DB_NAME]
#   GODOT_DIR  Godot checkout to analyse (default: ../../godot, checked out at 57277407)
#   DB_NAME    database name inside quality/understand/ (default: godot-57277407)
#
# Tool: SciTools Understand build 1264 (`und version`).
# The resulting .und can be opened in the Understand GUI (File > Open > Project) for the
# Metrics Browser, Metrics Treemap and graphs.
set -euo pipefail

# Windows tools (und.exe, git.exe) cannot parse MSYS /c/... paths that contain an apostrophe
# (the profile path "Damyan's laptop"), so every path is converted to C:/... form with cygpath -m.
HERE="$(cygpath -m "$(cd "$(dirname "$0")" && pwd)")"
GODOT_DIR="$(cygpath -m "$(cd "${1:-$HERE/../../godot}" && pwd)")"
DB_NAME="${2:-godot-57277407}"
DB="$HERE/understand/$DB_NAME.und"

echo "[und_build] godot: $GODOT_DIR @ $(git -C "$GODOT_DIR" rev-parse HEAD 2>/dev/null || echo 'not a git checkout')"
echo "[und_build] db:    $DB"
mkdir -p "$HERE/understand"

[ -d "$DB" ] || und create -db "$DB" -languages C++

# First-party code only. thirdparty/ and modules/mono/thirdparty are vendored libraries.
und add -db "$DB" \
  "$GODOT_DIR/core" "$GODOT_DIR/main" "$GODOT_DIR/scene" "$GODOT_DIR/servers" \
  "$GODOT_DIR/editor" "$GODOT_DIR/drivers" "$GODOT_DIR/platform" "$GODOT_DIR/modules" \
  "$GODOT_DIR/tests"
und remove -db "$DB" "$GODOT_DIR/modules/mono/thirdparty" || true

# Godot includes are rooted at the repository root (#include "core/object/object.h").
# TOOLS_ENABLED + DEBUG_ENABLED = the editor build, so editor-only code paths are analysed.
und settings -db "$DB" \
  -C++IncludesAdd "$GODOT_DIR" \
  -C++MacrosAdd TOOLS_ENABLED DEBUG_ENABLED \
  -GitRepositoryDirectory "$GODOT_DIR" \
  -metrics all \
  -MetricsOutputFile "$DB_NAME-metrics.csv"   # resolved relative to the .und folder (workshop gotcha)

und analyze -db "$DB" -all
und metrics -db "$DB"

echo "[und_build] metrics CSV: $HERE/understand/$DB_NAME-metrics.csv"
