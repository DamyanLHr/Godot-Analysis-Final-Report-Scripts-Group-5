"""M6 Change hotspots: files that are both complex and frequently changed.

churn      = number of non-merge commits touching the file, author date inside the window
             ../window.py (same window as the health analysis, end excluded)
complexity = sum of Understand Cyclomatic over the hand-written functions in the file at 57277407
             (und_export.py *_functions.csv, CountLineCode > 0; macro-generated entities excluded)
hotspot    = churn x SumCyclomatic, ranked (Tornhill's "code as a crime scene" idea: effort goes
             where complexity and change meet)

Mechanical commits are excluded from churn because they touch many files without design intent:
translation syncs (Weblate), AUTHORS/DONORS updates, thirdparty bumps, mass style/format passes.
The exclusion patterns are listed below so the filter is reproducible.

Usage:  python hotspots.py [GODOT_DIR] [FILES_CSV] [OUT_CSV]
"""
import csv
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from window import START as SINCE, END as UNTIL  # noqa: E402

MECHANICAL = re.compile(r"(Sync translations with Weblate|Update AUTHORS|Update DONORS|^Style:|clang-format|"
                        r"Apply clang-tidy|[Uu]pdate .* to [0-9]|: Update to [0-9])")
FIRST_PARTY = ("core/", "main/", "scene/", "servers/", "editor/", "drivers/", "platform/", "modules/", "tests/")


def churn(godot):
    # %x1e separates commits; author date (%aI) is used for the window, not the committer date.
    out = subprocess.run(["git", "-C", godot, "log", "--no-merges", "--numstat", "--format=%x1e%H%x1f%aI%x1f%s"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    counts, kept, skipped = Counter(), 0, 0
    for block in out.split("\x1e")[1:]:
        head, *lines = block.strip("\n").split("\n")
        _, date, subject = head.split("\x1f", 2)
        # Compared in UTC: the raw %aI strings carry each author's own offset, so they don't compare
        # as strings against the UTC window.
        if not (SINCE <= datetime.fromisoformat(date).astimezone(timezone.utc) < UNTIL):
            continue
        if MECHANICAL.search(subject):
            skipped += 1
            continue
        kept += 1
        for ln in lines:
            parts = ln.split("\t")
            if len(parts) == 3 and parts[2].startswith(FIRST_PARTY) and "/thirdparty/" not in parts[2]:
                counts[parts[2]] += 1
    return counts, kept, skipped


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    godot = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "godot")
    files_csv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "out", "und_57277407_files.csv")
    out_csv = sys.argv[3] if len(sys.argv) > 3 else os.path.join(here, "out", "hotspots.csv")

    counts, kept, skipped = churn(godot)
    # File complexity = sum of Cyclomatic over HAND-WRITTEN functions (CountLineCode > 0) defined in
    # the file. Understand's own file-level SumCyclomatic also counts macro-generated entities
    # (GDCLASS, binding macros), which made e.g. core/variant/variant_call.cpp look like 12,645.
    funcs_csv = files_csv.replace("_files.csv", "_functions.csv")
    cyclo = Counter()
    with open(funcs_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Cyclomatic"] not in ("", "None") and float(row["CountLineCode"] or 0) > 0:
                cyclo[row["file"]] += int(float(row["Cyclomatic"]))

    rows = [{"file": p, "module": p.split("/")[0], "commits_in_window": c, "SumCyclomatic": cyclo[p],
             "hotspot_score": c * cyclo[p]} for p, c in counts.items() if p in cyclo]
    rows.sort(key=lambda r: r["hotspot_score"], reverse=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"[hotspots] window {SINCE:%Y-%m-%d}..{UNTIL:%Y-%m-%d} (end excluded): {kept} commits kept, {skipped} mechanical commits excluded")
    print(f"[hotspots] {len(rows)} files with churn and complexity -> {out_csv}")
    for r in rows[:15]:
        print(f"{r['hotspot_score']:>8}  churn={r['commits_in_window']:>3}  SumCC={r['SumCyclomatic']:>5}  {r['file']}")


if __name__ == "__main__":
    main()
