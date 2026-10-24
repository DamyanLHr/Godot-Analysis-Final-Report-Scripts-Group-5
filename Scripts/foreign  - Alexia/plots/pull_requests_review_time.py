import csv
from pathlib import Path
from statistics import median

with open(Path(__file__).resolve().parent / "../out/3_pull_requests.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

hours = [float(r["hours_to_first_review"]) for r in rows if r["hours_to_first_review"]]

print(f"PRs opened:   {len(rows)}")
print(f"PRs reviewed: {len(hours)} ({100 * len(hours) / len(rows):.1f} %)")
print(f"Overall median time to first review: {median(hours):.2f} h ({median(hours) / 24:.2f} days)")
