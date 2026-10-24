"""
Unassigned share of open tasks per GitHub project:
    open tasks without an assignee / total open tasks x 100

Projects with no open tasks have no defined percentage; they are listed
at the bottom as "no open tasks" instead of being drawn as 0%.

Usage:
    python unassigned_projects.py                  # uses DEFAULT_CSV next to this script
    python unassigned_projects.py data.csv         # use a different CSV
    python unassigned_projects.py data.csv -o chart.png

Requires: matplotlib
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Change this to your CSV's file name. It is looked up in the same folder
# as this script, so it works no matter where PyCharm runs it from.
DEFAULT_CSV = "../out/5_project_unassigned.csv"
DEFAULT_PNG = "../out/figures/fig_5_project_unassigned.png"

UNASSIGNED_COLOR = "#2563eb"   # blue = open tasks WITHOUT an assignee
ASSIGNED_COLOR = "#e5e7eb"     # grey = open tasks WITH an assignee


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"CSV not found: {path}\nSet DEFAULT_CSV at the top of the script, or pass the path as an argument.")

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
        if not r.get("project"):
            continue  # skip blank lines
        open_tasks = int(float(r["open_tasks"]))
        unassigned = int(float(r["open_unassigned"]))
        rows.append({
            "project": r["project"].strip(),
            "closed": r.get("closed_project", "").strip().lower() == "true",
            "open_tasks": open_tasks,
            "unassigned": unassigned,
            # Undefined when the project has no open tasks
            "pct": unassigned / open_tasks * 100 if open_tasks > 0 else None,
        })

    # Projects with data first (highest % on top), then the empty ones
    with_data = sorted((r for r in rows if r["pct"] is not None),
                       key=lambda r: (-r["pct"], -r["open_tasks"]))
    empty = sorted((r for r in rows if r["pct"] is None), key=lambda r: r["project"])
    return with_data + empty


def plot(rows: list[dict], out_path: str | None) -> None:
    y = list(range(len(rows)))
    labels = [f"{r['project']} (closed)" if r["closed"] else r["project"] for r in rows]

    data_y = [yi for yi, r in zip(y, rows) if r["pct"] is not None]
    data_pct = [r["pct"] for r in rows if r["pct"] is not None]

    fig, ax = plt.subplots(figsize=(11, 0.55 * len(rows) + 2), layout="constrained")

    # Full bar = all open tasks (100%). Grey = with assignee, blue = without.
    ax.barh(data_y, [100] * len(data_y), color=ASSIGNED_COLOR, height=0.6, zorder=2)
    ax.barh(data_y, data_pct, color=UNASSIGNED_COLOR, height=0.6, zorder=3)

    for yi, r in zip(y, rows):
        if r["pct"] is None:
            ax.text(1, yi, "no open tasks", va="center", ha="left",
                    fontsize=9, color="#6b7280", style="italic")
        else:
            ax.text(101.5, yi, f"{r['pct']:.1f}%  ({r['unassigned']}/{r['open_tasks']} unassigned)",
                    va="center", ha="left", fontsize=9, color="#1f2937")

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_ylim(len(rows) - 0.4, -0.6)  # inverted: first row on top
    ax.tick_params(axis="y", length=0)

    ax.set_xlim(0, 130)
    ax.set_xticks(range(0, 101, 25))
    ax.set_xticklabels([f"{t}%" for t in range(0, 101, 25)])
    ax.set_xlabel("Share of the project's open tasks", loc="left", fontsize=9, color="#4b5563")

    fig.suptitle("Share of open project tasks without an assignee", x=0.01, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title("Open tasks without an assignee / total open tasks × 100, per project",
                 loc="left", fontsize=10, color="#4b5563", pad=28)

    ax.legend(
        handles=[
            Patch(color=UNASSIGNED_COLOR, label="Open tasks without an assignee"),
            Patch(color=ASSIGNED_COLOR, label="Open tasks with an assignee"),
        ],
        loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9,
    )

    ax.grid(axis="x", color="#f3f4f6", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)

    if out_path:
        fig.savefig(out_path, dpi=150)
        print(f"Saved chart to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Unassigned open tasks per project.")
    parser.add_argument("csv", nargs="?", default=None,
                        help=f"CSV file (default: {DEFAULT_CSV} next to this script)")
    parser.add_argument("-o", "--output", default=str(Path(__file__).resolve().parent / DEFAULT_PNG),
                        help=f"Image file to save (default: {DEFAULT_PNG})")
    parser.add_argument("--show", action="store_true", help="Show a window instead of saving")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else Path(__file__).resolve().parent / DEFAULT_CSV
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    plot(load_rows(csv_path), None if args.show else args.output)


if __name__ == "__main__":
    main()
