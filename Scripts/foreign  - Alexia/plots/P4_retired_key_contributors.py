"""
Metric 1: Percentage of former key contributors who are not key anymore.

For each closed milestone, the old key contributors are the top 10% of that
milestone's contributors. Subtracting the current key contributors from that
list leaves the old key contributors who no longer contribute frequently or
at all. This script computes that percentage per milestone and overall.

Usage: python P4_retired_key_contributors.py [path/to/P4_former_key_contributors.csv]
"""

import csv
import sys
from pathlib import Path

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "../out/P4_former_key_contributors.csv"


def version_key(milestone: str):
    """Sort milestones numerically (2.0, 2.1, 3.0, ... 4.7)."""
    return tuple(int(part) for part in milestone.split("."))


rows = []
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        old_key = int(row["old_key"])
        not_key = int(row["not_key_anymore"])
        rows.append({
            "milestone": row["milestone"],
            "closed_at": row["closed_at"][:10],
            "old_key": old_key,
            "not_key": not_key,
            "pct": 100 * not_key / old_key if old_key else 0.0,
        })

rows.sort(key=lambda r: version_key(r["milestone"]))

# Per-milestone percentages
print(f"{'Milestone':<10}{'Closed':<12}{'Old key':>8}{'Not key anymore':>17}{'%':>8}")
for r in rows:
    print(f"{r['milestone']:<10}{r['closed_at']:<12}{r['old_key']:>8}{r['not_key']:>17}{r['pct']:>7.1f}%")

# Overall percentages
total_old = sum(r["old_key"] for r in rows)
total_not = sum(r["not_key"] for r in rows)
pooled = 100 * total_not / total_old
mean = sum(r["pct"] for r in rows) / len(rows)

print()
print(f"Milestones analysed:            {len(rows)}")
print(f"Total old key contributors:     {total_old}")
print(f"Total no longer key:            {total_not}")
print(f"Overall (pooled) percentage:    {pooled:.1f}%")
print(f"Mean of per-milestone values:   {mean:.1f}%")

