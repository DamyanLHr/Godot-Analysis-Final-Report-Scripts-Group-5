"""
Stacked bar chart: created_same_month + created_older = monthly total.

Usage:
    python issues_closed.py                  # uses DEFAULT_CSV next to this script
    python issues_closed.py data.csv         # use a different CSV
    python issues_closed.py data.csv -o chart.png

The CSV needs the columns `created_same_month` and `created_older`,
one row per month, in chronological order (Sep 2025 -> Sep 2026).

Requires: matplotlib
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

# Change this to your CSV's file name. It is looked up in the same folder
# as this script, so it works no matter where the IDE runs it from.
DEFAULT_CSV = "../out/2c_issue_closed_age.csv"
DEFAULT_PNG = "../out/figures/fig_2c_issue_closed_age.png"

MONTHS = ["Sep 25*", "Oct 25", "Nov 25", "Dec 25", "Jan 26", "Feb 26", "Mar 26",
          "Apr 26", "May 26", "Jun 26", "Jul 26", "Aug 26", "Sep 26*"]

SAME_COLOR = "#2563eb"
OLDER_COLOR = "#93c5fd"


def load_rows(path: Path) -> tuple[list[float], list[float]]:
    if not path.exists():
        sys.exit(f"CSV not found: {path}\nSet DEFAULT_CSV at the top of the script, or pass the path as an argument.")

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Filter rows jointly so the two lists stay aligned with each other
    # and with MONTHS. Filtering each column separately can silently
    # shift one series by a month if a single cell is empty.
    rows = [r for r in rows if r["created_same_month"] and r["created_older"]]

    same = [float(r["created_same_month"]) for r in rows]
    older = [float(r["created_older"]) for r in rows]
    return same, older

def ratio_label(same: float, older: float) -> str:
    """Share of the month's total that was created in the same month."""
    total = same + older
    return "{total}"

def plot(same: list[float], older: list[float], out_path: str | None) -> None:
    if len(same) != len(MONTHS):
        sys.exit(f"Got {len(same)} data rows but {len(MONTHS)} month labels; fix the CSV or MONTHS.")

    totals = [s + o for s, o in zip(same, older)]
    x = range(len(MONTHS))

    fig, ax = plt.subplots(figsize=(11, 5.5))

    ax.bar(x, same, color=SAME_COLOR, label="Created same month", width=0.7, zorder=3)
    ax.bar(x, older, bottom=same, color=OLDER_COLOR, label="Created earlier", width=0.7, zorder=3)

    # Total on top of each bar
    for xi, total in zip(x, totals):
        ax.annotate(
            f"{total:g}",
            (xi, total),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#374151",
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(MONTHS)
    ax.set_ylim(0, max(totals) * 1.12)
    ax.set_ylabel("Count per month")
    ax.set_title("Monthly closed issues, split by when the issue was created", loc="left",
                 fontsize=14, fontweight="bold")

    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="x", length=0)

    ax.legend(loc="upper right", frameon=False, ncol=2)
    fig.text(0.01, 0.01, "* partial month", fontsize=9, color="#6b7280")
    fig.tight_layout(rect=(0, 0.03, 1, 1))

    if out_path:
        fig.savefig(out_path, dpi=150)
        print(f"Saved chart to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Stacked bar chart of same-month vs older items.")
    parser.add_argument("csv", nargs="?", default=None,
                        help=f"CSV with created_same_month and created_older columns (default: {DEFAULT_CSV})")
    parser.add_argument("-o", "--output", default=str(Path(__file__).resolve().parent / DEFAULT_PNG),
                        help=f"Image file to save (default: {DEFAULT_PNG})")
    parser.add_argument("--show", action="store_true", help="Show a window instead of saving")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else Path(__file__).resolve().parent / DEFAULT_CSV
    same, older = load_rows(csv_path)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    plot(same, older, None if args.show else args.output)


if __name__ == "__main__":
    main()
