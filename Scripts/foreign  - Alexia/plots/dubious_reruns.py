"""
Flaky-failure share: failed runs passing on re-run / all failed first attempts x 100.

Plots the metric per month and prints the overall figure for all months combined.

Usage:
    python dubious_reruns.py                  # uses DEFAULT_CSV
    python dubious_reruns.py data.csv         # use a different CSV
    python dubious_reruns.py data.csv -o chart.png

Requires: matplotlib
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

# Path to the CSV, relative to this script's folder (or an absolute path)
DEFAULT_CSV = "../out/4_rerun_success_rate.csv"
DEFAULT_PNG = "../out/figures/fig_4_rerun_flaky_share.png"

# Months that are only partially covered by the sample window
PARTIAL_MONTHS = {"2025-09", "2026-09"}

LINE_COLOR = "#2563eb"


def resolve_path(name: str) -> Path:
    """Look next to this script first, then in the current working directory."""
    candidates = [Path(name)] if Path(name).is_absolute() else [
        Path(__file__).resolve().parent / name,
        Path.cwd() / name,
    ]
    for p in candidates:
        if p.exists():
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
        failed = int(float(r["first_attempt_failed"]))
        passed = int(float(r["passed_on_rerun"]))
        rows.append({
            "month": r["month"].strip(),
            "failed": failed,
            "passed": passed,
            # Recompute the metric from the raw counts rather than trusting the column
            "pct": passed / failed * 100 if failed > 0 else 0.0,
        })

    rows.sort(key=lambda r: r["month"])
    return rows


def overall(rows: list[dict]) -> tuple[int, int, float]:
    """Sum all months first, then divide (not an average of the monthly %)."""
    passed = sum(r["passed"] for r in rows)
    failed = sum(r["failed"] for r in rows)
    return passed, failed, passed / failed * 100


def month_label(month: str) -> str:
    label = datetime.strptime(month, "%Y-%m").strftime("%b %y")
    return f"{label}*" if month in PARTIAL_MONTHS else label


def plot(rows: list[dict], out_path: str | None) -> None:
    passed, failed, total_pct = overall(rows)
    x = list(range(len(rows)))
    pcts = [r["pct"] for r in rows]

    fig, ax = plt.subplots(figsize=(11, 5.5), layout="constrained")

    # Overall reference line
    ax.axhline(total_pct, color="#9ca3af", linestyle="--", linewidth=1, zorder=1)
    ax.annotate(f"All months: {total_pct:.2f}%", (len(rows) - 0.6, total_pct),
                xytext=(0, -4), textcoords="offset points",
                ha="right", va="top", fontsize=9, color="#6b7280")

    ax.plot(x, pcts, color=LINE_COLOR, linewidth=2.4, marker="o",
            markersize=6, markeredgecolor="white", markeredgewidth=0.8, zorder=3)

    for xi, pct in zip(x, pcts):
        ax.annotate(f"{pct:.1f}%", (xi, pct), xytext=(0, 8), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, color="#1f2937")

    ax.set_xticks(x)
    ax.set_xticklabels([month_label(r["month"]) for r in rows])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, max(pcts) * 1.25)
    ax.set_ylabel("Flaky share of failures (%)")

    fig.suptitle("Share of failed CI runs that pass on re-run", x=0.01, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title("Failed runs passing on re-run / all failed first attempts × 100",
                 loc="left", fontsize=10, color="#4b5563")

    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.set_xlabel(
        f"Overall, all months: {passed} passed on re-run / {failed} failed first attempts "
        f"= {total_pct:.2f}%        * partial month",
        loc="left", fontsize=9, color="#4b5563",
    )

    if out_path:
        fig.savefig(out_path, dpi=150)
        print(f"Saved chart to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Flaky-failure share chart.")
    parser.add_argument("csv", nargs="?", default=None,
                        help=f"CSV file (default: {DEFAULT_CSV})")
    parser.add_argument("-o", "--output", default=str(Path(__file__).resolve().parent / DEFAULT_PNG),
                        help=f"Image file to save (default: {DEFAULT_PNG})")
    parser.add_argument("--show", action="store_true", help="Show a window instead of saving")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else resolve_path(DEFAULT_CSV)
    rows = load_rows(csv_path)

    passed, failed, total_pct = overall(rows)
    print(f"Months:                     {len(rows)}")
    print(f"Failed first attempts:      {failed}")
    print(f"Passed on re-run:           {passed}")
    print(f"Overall flaky share:        {passed} / {failed} x 100 = {total_pct:.2f}%")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    plot(rows, None if args.show else args.output)


if __name__ == "__main__":
    main()
