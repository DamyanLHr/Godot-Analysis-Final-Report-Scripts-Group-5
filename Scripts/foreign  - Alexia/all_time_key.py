"""Share of all-time key contributors who are no longer key contributors.

All-time key contributors = everyone who was in the top 10 % of merged-PR authors of at least one
closed milestone, each person counted once. Current key contributors are read from your existing
CSV (P4_current_key_contributors.csv, or contributors.csv with key_contributor = True).
Result = all-time key contributors not in the current list / all-time key contributors x 100.

The closed milestones' PR authors are read from data/github/milestones.jsonl (health/fetch_github.py),
so no token is needed. Run run_all.py first for contributors.csv.

    cd "foreign  - Alexia"
    ../.venv/Scripts/python all_time_key.py                          # finds the CSV folder automatically
    ../.venv/Scripts/python all_time_key.py "C:\\path\\to\\csv\\folder"  # or point it at the folder with the CSVs
"""
import csv
import math
import sys
from collections import Counter
from pathlib import Path

import config
import data
from util import is_bot, log

HERE = Path(__file__).resolve().parent


def find_csv_folder():
    if len(sys.argv) > 1:
        candidates = [Path(sys.argv[1])]
    else:
        candidates = [Path(config.OUT_DIR), HERE / "godot_metrics_out", HERE / "out",
                      Path.cwd() / "godot_metrics_out", Path.cwd() / "out", HERE]
    names = ("P4_current_key_contributors.csv", "contributors.csv")
    for d in candidates:
        if any((d / n).exists() for n in names):
            return d
    sys.exit("Could not find P4_current_key_contributors.csv or contributors.csv. Looked in:\n  "
             + "\n  ".join(map(str, candidates))
             + '\nRun: py all_time_key.py "<folder with the CSV files>"')


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    folder = find_csv_folder()
    log(f"reading CSVs from {folder}")

    # Current key contributors.
    if (folder / "P4_current_key_contributors.csv").exists():
        current = {r["login"].strip().lower() for r in read(folder / "P4_current_key_contributors.csv") if r["login"]}
        source = "P4_current_key_contributors.csv"
    else:
        current = {r["login"].strip().lower() for r in read(folder / "contributors.csv")
                   if r["login"] and r["key_contributor"] == "True"}
        source = "contributors.csv"

    # Optional status per person (key, dormant, left, ...) for the breakdown.
    status = {}
    if (folder / "contributors.csv").exists():
        status = {r["login"].strip().lower(): r["status"] for r in read(folder / "contributors.csv") if r["login"]}

    gh = None  # data.py reads our health pipeline's files; no API client needed

    # All-time key contributors: union of every closed milestone's top 10 % by merged PRs.
    milestones = data.closed_milestones(gh)
    key_in = {}  # login -> milestones where they were key
    for m in sorted(milestones, key=lambda m: m["closed_at"] or ""):
        log(f"milestone {m['title']}")
        authors = Counter(a.lower() for a in data.milestone_pr_authors(gh, m["number"]) if a and not is_bot(a))
        if not authors:
            continue
        k = max(1, math.ceil(len(authors) * config.MILESTONE_TOP_FRACTION))
        for login, _ in authors.most_common(k):
            key_in.setdefault(login, []).append(m["title"])

    all_time = sorted(key_in, key=lambda l: (-len(key_in[l]), l))
    not_key = [l for l in all_time if l not in current]

    def st(login):
        return status.get(login, "no commits in the last 2 years")

    out = folder / "P4_all_time_key_contributors.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["login", "milestones_as_key", "milestones", "currently_key", "current_status"])
        for l in all_time:
            w.writerow([l, len(key_in[l]), ";".join(key_in[l]), l in current, st(l)])

    print()
    print(f"Closed milestones:                 {len(milestones)}")
    print(f"All-time key contributors:         {len(all_time)}")
    print(f"Current key contributors:          {len(current)}  (from {source})")
    print(f"All-time key still key:            {len(all_time) - len(not_key)}")
    print(f"All-time key NOT key anymore:      {len(not_key)} ({100 * len(not_key) / len(all_time):.1f} %)")
    if status:
        print("\nCurrent status of those no longer key:")
        for s, n in Counter(st(l) for l in not_key).most_common():
            print(f"  {s:<35}{n:>4}  ({100 * n / len(not_key):.1f} %)")
    print(f"\nList written to {out}")


if __name__ == "__main__":
    main()
