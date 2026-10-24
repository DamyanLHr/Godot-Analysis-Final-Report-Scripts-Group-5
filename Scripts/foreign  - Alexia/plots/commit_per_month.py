"""
Line chart of monthly commit counts.

Usage:
    python commit_per_month.py                  # uses DEFAULT_CSV
    python commit_per_month.py data.csv         # use a different CSV
    python commit_per_month.py data.csv -o chart.png

Requires: matplotlib
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

# Path to the CSV, relative to this script's folder (or an absolute path).
# ".csv" is added automatically if the name has no extension.
DEFAULT_CSV = "../out/1_commits_per_month.csv"
DEFAULT_PNG = "../out/figures/fig_1_commits_per_month.png"

SERIES = {
    "commits": {"label": "Commits", "color": "#2563eb", "marker": "o"},
}


def resolve_path(name: str) -> Path:
    """Look next to this script first, then in the current working directory."""
    names = [name] if name.lower().endswith(".csv") else [name, name + ".csv"]
    candidates = []
    for n in names:
        p = Path(n)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates += [Path(__file__).resolve().parent / n, Path.cwd() / n]
    for p in candidates:
        if p.is_file():
            return p
    sys.exit("CSV not found. Looked in:\n  " + "\n  ".join(str(p) for p in candidates))


def load_rows(path: Path) -> list[dict]:
    # utf-8-sig drops the invisible BOM Excel puts before the first header
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        # Excel with Dutch/European settings saves with ';' instead of ','
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(f, dialect=dialect)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        raw_rows = list(reader)

    rows = []
    for r in raw_rows:
        if not r.get("month"):
            continue  # skip blank lines
        row = {"month": datetime.strptime(r["month"].strip(), "%Y-%m")}
        for col in SERIES:
            row[col] = float(r[col])
        rows.append(row)

    rows.sort(key=lambda r: r["month"])
    return rows


def plot(rows: list[dict], out_path: str | None) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    months = [r["month"] for r in rows]

    for col, style in SERIES.items():
        values = [r[col] for r in rows]
        ax.plot(
            months, values,
            color=style["color"],
            marker=style["marker"],
            markersize=6,
            linewidth=2.2,
            label=style["label"],
            markeredgecolor="white",
            markeredgewidth=0.8,
            zorder=3,
        )
        # Label the last point of each line directly
        ax.annotate(
            f"{int(values[-1])}",
            (months[-1], values[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            color=style["color"],
            fontsize=9,
        )

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))

    ax.set_ylim(0, max(r[col] for r in rows for col in SERIES) * 1.12)
    ax.set_ylabel("Count per month")
    ax.set_title("Monthly commit activity", loc="left", fontsize=14, fontweight="bold")

    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.legend(loc="upper right", frameon=False, ncol=2)
    fig.tight_layout()

    if out_path:
        fig.savefig(out_path, dpi=150)
        print(f"Saved chart to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Line chart of monthly commits.")
    parser.add_argument("csv", nargs="?", default=None,
                        help=f"CSV file (default: {DEFAULT_CSV})")
    parser.add_argument("-o", "--output", default=str(Path(__file__).resolve().parent / DEFAULT_PNG),
                        help=f"Image file to save (default: {DEFAULT_PNG})")
    parser.add_argument("--show", action="store_true", help="Show a window instead of saving")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else resolve_path(DEFAULT_CSV)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    plot(load_rows(csv_path), None if args.show else args.output)


if __name__ == "__main__":
    main()
