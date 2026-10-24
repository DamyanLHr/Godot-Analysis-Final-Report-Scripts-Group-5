"""Run Alexia's figure and number scripts on ../out/ (written by run_all.py).

    python plot_all.py          # figures -> ../out/figures/, printed numbers -> ../out/plots_output.txt

Each script still runs on its own (see its docstring); this only runs them all in one go, headless.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")

# figure scripts save to ../out/figures/fig_<csv name>.png by default
FIGURES = ["commit_per_month.py", "issues_closed.py", "dubious_reruns.py",
           "unassigned_projects.py", "Process_oriented_2.py"]
# number-only scripts, for figures quoted in the text
NUMBERS = ["pull_requests_review_time.py", "milestones_completion_percentage.py",
           "P4_retired_key_contributors.py"]


def main():
    env = {**os.environ, "MPLBACKEND": "Agg"}
    lines, failed = [], []
    for script in FIGURES + NUMBERS:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        print(f"=== {script}\n{r.stdout}{r.stderr}", end="")
        lines += [f"=== {script}", r.stdout.rstrip(), ""]
        if r.returncode:
            failed.append(script)
    with open(os.path.join(OUT, "plots_output.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    if failed:
        raise SystemExit(f"FAILED: {', '.join(failed)}")


if __name__ == "__main__":
    main()
