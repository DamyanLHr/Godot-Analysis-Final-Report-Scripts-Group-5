"""M3 Layer violations: #include lines that point *up* the documented dependency order.

Godot's docs ("Editor dependencies in scene/ files",
https://docs.godotengine.org/en/latest/engine_details/editor/introduction_to_editor_development.html)
state the allowed direction editor/ -> scene/ -> servers/ -> core/. A file in a lower layer that
includes a header from a higher layer is counted as a violation.

For each violation the script records whether the include sits inside a preprocessor conditional
(e.g. #ifdef TOOLS_ENABLED), because guarded includes disappear from some builds.

Usage:  python layer_violations.py [GODOT_DIR] [OUT_CSV]
Output: CSV with one row per violating include + a summary printed to stdout.
"""
import csv
import os
import re
import sys
from collections import Counter

LAYERS = {"core": 0, "servers": 1, "scene": 2, "editor": 3}
INCLUDE = re.compile(r'^\s*#\s*include\s+"(?P<path>[^"]+)"')
IF_OPEN = re.compile(r"^\s*#\s*(if|ifdef|ifndef)\b(?P<cond>.*)")
IF_CLOSE = re.compile(r"^\s*#\s*endif\b")
EXTS = (".cpp", ".h", ".inc", ".hpp", ".mm")
COMMIT = "57277407e77e61b161f35dbd7aeb510f7a9e26a6"


def layer_of(rel_path):
    top = rel_path.replace("\\", "/").split("/", 1)[0]
    return top if top in LAYERS else None


def scan(godot_dir):
    rows = []
    for layer in LAYERS:
        for root, _, files in os.walk(os.path.join(godot_dir, layer)):
            for name in files:
                if not name.endswith(EXTS):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, godot_dir).replace("\\", "/")
                guards = []  # stack of active #if conditions
                with open(full, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if m := IF_OPEN.match(line):
                            cond = m.group("cond").strip()
                            # Header include guards (#ifndef FOO_H / #pragma once) are not feature guards.
                            guards.append(None if re.fullmatch(r"[A-Z0-9_]+_H(PP)?", cond) else f"#{m.group(1)} {cond}")
                            continue
                        if IF_CLOSE.match(line):
                            if guards:
                                guards.pop()
                            continue
                        m = INCLUDE.match(line)
                        if not m:
                            continue
                        target_layer = layer_of(m.group("path"))
                        if target_layer and LAYERS[target_layer] > LAYERS[layer]:
                            active = [g for g in guards if g]
                            rows.append({
                                "file": rel,
                                "line": lineno,
                                "from_layer": layer,
                                "to_layer": target_layer,
                                "include": m.group("path"),
                                "guard": " && ".join(active),
                                "permalink": f"https://github.com/godotengine/godot/blob/{COMMIT}/{rel}#L{lineno}",
                            })
    return rows


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    godot_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "godot")
    out_csv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "out", "layer_violations.csv")
    rows = scan(godot_dir)
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "line", "from_layer", "to_layer", "include", "guard", "permalink"])
        w.writeheader()
        w.writerows(rows)

    pairs = Counter((r["from_layer"], r["to_layer"], "guarded" if r["guard"] else "unguarded") for r in rows)
    files = Counter((r["from_layer"], r["to_layer"]) for r in {(r["file"], r["from_layer"], r["to_layer"]): r for r in rows}.values())
    print(f"[layer_violations] {len(rows)} upward includes in {len({r['file'] for r in rows})} files -> {out_csv}")
    print("from -> to          includes  guarded  unguarded  files")
    for (a, b) in sorted({(x, y) for x, y, _ in pairs}, key=lambda p: (LAYERS[p[0]], LAYERS[p[1]])):
        g, u = pairs[(a, b, "guarded")], pairs[(a, b, "unguarded")]
        print(f"{a:>7} -> {b:<8} {g + u:>9} {g:>8} {u:>10} {files[(a, b)]:>6}")


if __name__ == "__main__":
    main()
