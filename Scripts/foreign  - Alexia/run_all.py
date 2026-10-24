"""Run every metric (or a subset) and write CSVs + out/summary.md.

    python run_all.py                       # everything
    python run_all.py commits reviews       # just these
    python run_all.py --list                # show metric names
"""
import argparse
import json
import os
import traceback

import config
import contributors
import metrics_activity as A
import metrics_process as P
from util import log


def main():
    names = ["contributors", *A.ALL, *P.ALL]
    ap = argparse.ArgumentParser()
    ap.add_argument("metrics", nargs="*", help="subset to run (default: all)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        print("\n".join(names))
        return
    selected = args.metrics or names
    unknown = set(selected) - set(names)
    if unknown:
        raise SystemExit(f"unknown metric(s): {', '.join(unknown)}. Use --list.")

    gh = None  # all data is read from config.DATA_DIR (our health pipeline); no API client needed
    meta_path = os.path.join(config.DATA_DIR, "github", "meta.json")
    fetched = json.load(open(meta_path)).get("finished_utc", "unknown") if os.path.exists(meta_path) else "unknown"
    log(f"data from {config.DATA_DIR} (GitHub data fetched {fetched})")

    summary = [f"# {config.FULL} community metrics",
               f"Window {config.WINDOW_START:%Y-%m-%d} .. {config.WINDOW_END:%Y-%m-%d} (end exclusive), "
               f"commits by author date at Godot {config.GODOT_SNAPSHOT[:8]}; GitHub data fetched {fetched}", ""]
    people = None

    def run(name, fn):
        log(f"=== {name}")
        try:
            lines = fn()
            summary.append(f"## {name}")
            summary.extend([f"- {l}" for l in lines] + [""])
            for l in lines:
                print(f"{name}: {l}")
        except Exception as e:
            traceback.print_exc()
            summary.extend([f"## {name}", f"- FAILED: {e}", ""])

    need_people = any(n in selected for n in ["contributors", *P.ALL])
    if need_people:
        log("=== building contributor table")
        people = contributors.build(gh)
        if "contributors" in selected:
            run("contributors", lambda: contributors.report(people))

    for n, fn in A.ALL.items():
        if n in selected:
            run(n, lambda fn=fn: fn(gh))
    for n, fn in P.ALL.items():
        if n in selected:
            run(n, lambda fn=fn: fn(gh, people))

    os.makedirs(config.OUT_DIR, exist_ok=True)
    with open(os.path.join(config.OUT_DIR, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary))
    log(f"done. See {config.OUT_DIR}/")


if __name__ == "__main__":
    main()
