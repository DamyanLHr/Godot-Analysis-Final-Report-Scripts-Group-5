import csv
from pathlib import Path

path = Path(__file__).resolve().parent / "../out/6_milestone_completion.csv"

with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Recompute each milestone's completion from the item counts (the CSV column is rounded).
pcts = []
for r in rows:
    open_, closed = int(r["open_items"]), int(r["closed_items"])
    if open_ + closed:
        pcts.append(100 * closed / (open_ + closed))

total_open = sum(int(r["open_items"]) for r in rows)
total_closed = sum(int(r["closed_items"]) for r in rows)

print(f"File: {path}")
print(f"Closed milestones: {len(pcts)}")
print(f"Average completion percentage: {sum(pcts) / len(pcts):.2f} %")
print(f"Lowest: {min(pcts):.2f} %   Highest: {max(pcts):.2f} %")
# Optional: weighted by milestone size (all items pooled together)
print(f"Item-weighted completion: {100 * total_closed / (total_open + total_closed):.2f} %")
