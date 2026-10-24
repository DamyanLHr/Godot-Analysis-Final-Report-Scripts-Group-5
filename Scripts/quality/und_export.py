"""Exports per-function, per-class and per-file metrics from an Understand database, WITH the
defining file, so results can be grouped by Godot module (core/, scene/, editor/, ...).

The plain `und metrics` CSV lists functions by name only; this script uses Understand's Python
API to attach the file each entity is defined in.

Usage (Understand's bundled interpreter, NOT the venv):
  "C:/Program Files/SciTools/bin/pc-win64/upython.exe" und_export.py <db.und> <godot_dir> <out_prefix>
Tool: SciTools Understand build 1264 (understand.version() == 8.0.1264)
Output: <out_prefix>_functions.csv, <out_prefix>_classes.csv, <out_prefix>_files.csv
"""
import csv
import os
import sys

import understand

FUNC_METRICS = ["Cyclomatic", "CyclomaticModified", "MaxNesting", "CountLineCode", "CountPath", "Essential"]
CLASS_METRICS = ["CountClassCoupled", "PercentLackOfCohesion", "CountDeclMethod", "CountDeclMethodAll",
                 "CountLineCode", "MaxInheritanceTree", "CountClassBase", "CountClassDerived", "SumCyclomatic"]
FILE_METRICS = ["CountLineCode", "CountLineComment", "RatioCommentToCode", "SumCyclomatic", "MaxCyclomatic",
                "CountDeclFunction", "MaxNesting", "GitCommits", "GitAuthors", "GitOwnership"]


def rel(path, root):
    try:
        r = os.path.relpath(path, root)
    except ValueError:
        return None
    return None if r.startswith("..") else r.replace("\\", "/")


def defining_file(ent):
    for kind in ("definein", "declarein"):
        refs = ent.refs(kind)
        if refs:
            return refs[0].file().longname(), refs[0].line()
    return None, None


def dump(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"[und_export] {len(rows):>6} rows -> {path}")


def main():
    db_path, godot_dir, out_prefix = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3]
    db = understand.open(db_path)
    print(f"[und_export] Understand {understand.version()}  db={db_path}")

    rows = []
    for ent in db.ents("function ~unresolved ~unknown ~declaration, method ~unresolved ~unknown ~declaration"):
        f, line = defining_file(ent)
        r = rel(f, godot_dir) if f else None
        if not r:
            continue
        m = ent.metric(FUNC_METRICS)
        rows.append([r.split("/")[0], r, line, ent.longname()] + [m.get(k) for k in FUNC_METRICS])
    dump(out_prefix + "_functions.csv", ["module", "file", "line", "function"] + FUNC_METRICS, rows)

    rows = []
    for ent in db.ents("class ~unresolved ~unknown, struct ~unresolved ~unknown"):
        f, line = defining_file(ent)
        r = rel(f, godot_dir) if f else None
        if not r:
            continue
        m = ent.metric(CLASS_METRICS)
        rows.append([r.split("/")[0], r, line, ent.kindname(), ent.longname()] + [m.get(k) for k in CLASS_METRICS])
    dump(out_prefix + "_classes.csv", ["module", "file", "line", "kind", "class"] + CLASS_METRICS, rows)

    rows = []
    for ent in db.ents("file ~unresolved ~unknown"):
        r = rel(ent.longname(), godot_dir)
        if not r:
            continue
        m = ent.metric(FILE_METRICS)
        rows.append([r.split("/")[0], r] + [m.get(k) for k in FILE_METRICS])
    dump(out_prefix + "_files.csv", ["module", "file"] + FILE_METRICS, rows)


if __name__ == "__main__":
    main()
