"""
Newcomer share of commits per month, plotted from the `newcomer_pct` column.

Usage:
    python Process_oriented_2.py                  # uses DEFAULT_CSV
    python Process_oriented_2.py data.csv         # use a different CSV
    python Process_oriented_2.py data.csv -o chart.png

Requires: matplotlib
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

# Path to the CSV, relative to this script's folder (or an absolute path).
# ".csv" is added automatically if the name has no extension.
DEFAULT_CSV = "../out/P2_newcomer_commit_share.csv"
DEFAULT_PNG = "../out/figures/fig_P2_newcomer_commit_share.png"

# Months that are only partially covered by the sample window
PARTIAL_MONTHS = {"2025-09", "2026-09"}

LINE_COLOR = "#2563eb"


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

    rows = [
        {"month": r["month"].strip(), "pct": float(r["newcomer_pct"])}
        for r in raw_rows
        if r.get("month") and r.get("newcomer_pct")
    ]
    rows.sort(key=lambda r: r["month"])
    return rows


def month_label(month: str) -> str:
    label = datetime.strptime(month, "%Y-%m").strftime("%b %y")
    return f"{label}*" if month in PARTIAL_MONTHS else label


def plot(rows: list[dict], out_path: str | None) -> None:
    x = list(range(len(rows)))
    pcts = [r["pct"] for r in rows]

    fig, ax = plt.subplots(figsize=(11, 5.5), layout="constrained")

    ax.plot(x, pcts, color=LINE_COLOR, linewidth=2.4, marker="o",
            markersize=6, markeredgecolor="white", markeredgewidth=0.8, zorder=3)

    for xi, pct in zip(x, pcts):
        ax.annotate(f"{pct:.1f}%", (xi, pct), xytext=(0, 8), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, color="#1f2937")

    ax.set_xticks(x)
    ax.set_xticklabels([month_label(r["month"]) for r in rows])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, max(pcts) * 1.2)
    ax.set_ylabel("Newcomer share of commits (%)")

    fig.suptitle("Share of commits made by newcomers", x=0.01, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title("Newcomer commits / all commits × 100", loc="left",
                 fontsize=10, color="#4b5563")

    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.set_xlabel("* partial month", loc="left", fontsize=9, color="#6b7280")

    if out_path:
        fig.savefig(out_path, dpi=150)
        print(f"Saved chart to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Newcomer share of commits per month.")
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
