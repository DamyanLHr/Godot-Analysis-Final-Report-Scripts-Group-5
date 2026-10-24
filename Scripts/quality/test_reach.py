"""M5 Test reach: how much of each module is touched by Godot's unit tests (static proxy).

Two numbers per module:
  * test_cases  - TEST_CASE / TEST_CASE_TEMPLATE macros in the module's dedicated test folder
                  (tests/<module>/, or <module>/**/tests/ for modules/).
  * class_reach - share of classes declared in the module's headers whose name appears as a whole
                  word in ANY test source (tests/** and modules/*/tests/**).

This is NOT line or branch coverage: a class that is only used as a fixture counts as "reached",
and a reached class may have most of its methods untested. Real coverage needs an instrumented
build and a test run, which the brief's static scope (and our tooling) does not include.

Usage:  python test_reach.py [GODOT_DIR] [OUT_CSV]
"""
import csv
import os
import re
import sys

MODULES = ["core", "main", "scene", "servers", "editor", "drivers", "platform", "modules"]
CLASS_DECL = re.compile(r"^\s*class\s+(?:[A-Z_]+_API\s+)?(?P<name>[A-Z]\w+)\s*(?:final\s*)?(?::|\{)", re.M)
TEST_MACRO = re.compile(r"\bTEST_CASE(?:_TEMPLATE)?\s*\(")
EXTS = (".cpp", ".h", ".inc")


def walk(base, exts=EXTS, skip=()):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if os.path.join(root, d).replace("\\", "/") not in skip]
        for f in files:
            if f.endswith(exts):
                yield os.path.join(root, f)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def is_test_path(rel):
    parts = rel.replace("\\", "/").split("/")
    return parts[0] == "tests" or "tests" in parts[1:-1]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    godot = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "godot"))
    out_csv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "out", "test_reach.csv")
    skip = {os.path.join(godot, "modules", "mono", "thirdparty").replace("\\", "/")}

    # All test sources (dedicated tests/ tree + per-module tests folders).
    test_files = [p for p in walk(os.path.join(godot, "tests"))]
    test_files += [p for p in walk(os.path.join(godot, "modules"), skip=skip) if is_test_path(os.path.relpath(p, godot))]
    test_text = "\n".join(read(p) for p in test_files)
    test_words = set(re.findall(r"\b[A-Z]\w+\b", test_text))

    rows = []
    for m in MODULES:
        base = os.path.join(godot, m)
        headers = [p for p in walk(base, (".h",), skip) if not is_test_path(os.path.relpath(p, godot))]
        classes = set()
        for h in headers:
            classes.update(c.group("name") for c in CLASS_DECL.finditer(read(h)))
        reached = sorted(c for c in classes if c in test_words)

        if m == "modules":
            dedicated = [p for p in test_files if os.path.relpath(p, godot).replace("\\", "/").startswith("modules/")]
        else:
            dedicated = [p for p in test_files if os.path.relpath(p, godot).replace("\\", "/").startswith(f"tests/{m}/")]
        cases = sum(len(TEST_MACRO.findall(read(p))) for p in dedicated)
        rows.append({
            "module": m,
            "headers": len(headers),
            "classes": len(classes),
            "classes_reached": len(reached),
            "class_reach_pct": round(100 * len(reached) / len(classes), 1) if classes else 0.0,
            "dedicated_test_files": len(dedicated),
            "test_cases": cases,
        })

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"[test_reach] {len(test_files)} test sources scanned -> {out_csv}")
    for r in rows:
        print(f"{r['module']:<9} classes={r['classes']:>5} reached={r['classes_reached']:>5} "
              f"({r['class_reach_pct']:>5}%)  test_files={r['dedicated_test_files']:>4} TEST_CASEs={r['test_cases']:>5}")


if __name__ == "__main__":
    main()
