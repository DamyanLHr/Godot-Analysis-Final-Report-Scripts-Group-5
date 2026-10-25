# Godot quality and health measurements: 2IRR80 Capstone, Group 5

Scripts behind the *Project quality* metrics (M1–M8) and the *Project health* filtering and
contributor categories in our final report. Every number in the report can be re-created with the
commands below.

| What | Value |
|---|---|
| Repository | `godotengine/godot` |
| Code snapshot | `57277407e77e61b161f35dbd7aeb510f7a9e26a6` (master, 18 Sep 2026) |
| Activity window | `2025-09-16T00:00:00Z` to `2026-09-16T00:00:00Z`, end excluded (365 days), in `window.py`; **author** date for git |
| Platform used | Windows 11, Git Bash, Python 3.13.0 |

## Tools and versions

| Tool | Version | Used for |
|---|---|---|
| SciTools Understand | 8.0, build 1264 (`und version`) | M1 cross-check, M3, M8 comment ratio, graphs |
| lizard | 1.24.1 (pip) | M1 cyclomatic complexity (primary) |
| clang-tidy | 22.1.3 (bundled with Visual Studio 18) | M2 cognitive complexity of selected functions |
| SCons | 4.11.1 (pip), with MSVC 14.5 / Windows SDK 10.0.26100.0 | only to generate `compile_commands.json` and `*.gen.h` for clang-tidy |
| Simian | 2.5.10 (`Tools/simian.jar`), Java 21 | M5 duplication |
| Godot `doc/tools/doc_status.py` | in the repository at the snapshot | M8 API documentation coverage |
| git | 2.x | M7 churn and all git-based health data |
| gambit-disambig | 1.0.5 (pip) | alias detection, measure 2 |
| rabbit-ng | 3.0.0 (pip, separate venv) | bot detection, validation |
| pandas / matplotlib / numpy | see `requirements.txt` | analysis and plots |

## Setup

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
git clone https://github.com/godotengine/godot.git ../godot && git -C ../godot checkout 57277407e77e61b161f35dbd7aeb510f7a9e26a6
```

Paths: Windows tools cannot parse MSYS `/c/...` paths that contain an apostrophe. The scripts
convert every path with `cygpath -m`, so run them from Git Bash.

## Project quality (`quality/`)

```bash
bash quality/und_build.sh                       # Understand DB + metrics CSV (approx. 35 min)
"C:/Program Files/SciTools/bin/pc-win64/upython.exe" quality/und_export.py \
     quality/understand/godot-57277407.und ../godot quality/out/und_57277407     # per-entity CSVs with file
UP="C:/Program Files/SciTools/bin/pc-win64/upython.exe"                          # report figures,
for f in $("$UP" quality/und_graphs.py --list); do                              # one process each
  "$UP" quality/und_graphs.py quality/understand/godot-57277407.und quality/out/figures "$f"; done
.venv/Scripts/python quality/compose_m3.py                                       # M4 figure, 3 graphs side by side
bash quality/lizard_run.sh                      # M1 primary: lizard CCN per function
bash quality/simian_run.sh                      # M5: per module, thresholds 6 and 10
.venv/Scripts/python quality/layer_violations.py   # M4
.venv/Scripts/python quality/test_reach.py         # M6
.venv/Scripts/python quality/hotspots.py           # M7 (needs und_export output)
.venv/Scripts/python quality/summarise_quality.py  # M1/M3/M8 tables + lizard vs Understand check
(cd ../godot && python doc/tools/doc_status.py -p doc/classes modules/*/doc_classes platform/*/doc_classes)   # M8

# Cognitive complexity (clang-tidy) runs on a git-archive COPY, because it generates build files:
mkdir -p work/src-57277407 && git -C ../godot archive 57277407 | tar -x -C work/src-57277407
bash quality/cognitive_run.sh work/src-57277407 "$PWD/quality/out/cognitive_before.csv" editor/editor_log.cpp editor/editor_node.cpp
IGNORE_MACROS=true bash quality/cognitive_run.sh ...       # variant without macro increments
```

The `.und` database can be opened in the Understand GUI (*File → Open → Project*) to browse the
same numbers: Metrics Browser, Metrics Treemap, dependency graphs, UML class diagrams and
control-flow graphs.

## Project health (`health/`)

Everything except the fetch runs offline from `data/`, so anyone can rebuild the numbers without a token.

```bash
# Only to refresh the GitHub data (token needed). The .jsonl files are appended to, so a new
# fetch starts from an empty data/github/ (fetch_github.py refuses a folder from another window).
export GITHUB_TOKEN=...                         # public read + project read (classic token: read:project)
.venv/Scripts/python health/fetch_github.py     # PRs, reviews, issues (+assignees), comments, Actions runs,
                                                # Projects, Milestones (resumable)
# Offline, in this order:
.venv/Scripts/python health/git_activity.py     # commits in window, prior year, all-time first commits, person_id
.venv/Scripts/python health/login_map.py        # person -> GitHub login from the PR merge history; same-login aliases
.venv/Scripts/python health/merge_aliases.py    # aliases: measure 1 (.mailmap + same e-mail + same login/name) vs gambit
.venv/Scripts/python health/filter_bots.py      # bot measures 1 and 2 (git + GitHub)
.venv/Scripts/python health/categorise.py       # H1 + key / newcomer / dormant / left -> data/categories/people.csv
(cd "foreign  - Alexia" && ../.venv/Scripts/python run_all.py)   # Alexia's activity + process metrics -> her out/
.venv/Scripts/python "foreign  - Alexia/plots/plot_all.py"       # her report figures -> her out/figures/
.venv/Scripts/python health/check_consistency.py                 # fails if her CSVs and ours disagree
export GITHUB_API_KEY=$GITHUB_TOKEN             # RABBIT reads this name
.venv-bots/Scripts/rabbit-ng --input-file data/bots/rabbit_input.txt --format csv > data/bots/rabbit_output.csv
```

The GitHub comment endpoints refuse pages beyond 300 (30,000 items). `fetch_github.py` therefore
restarts every 250 pages with `since=` set to the last item's timestamp, and skips duplicates by id.

One person = one `person_id` (`health/git_activity.py`): the login for GitHub noreply addresses, else
the mailmapped e-mail. `login_map.py` then merges two ids whose merged PRs ran under the same GitHub
login and who use the same name (`person_alias.csv`, applied by `health/people.py`); different names
behind one login are listed in `login_conflicts.csv` and left apart. Contributor categories are
computed once, in `categorise.py`; Alexia's scripts read them from `data/categories/` rather than
classifying people themselves.

## Not in the repository

`.venv*/`, `quality/understand/*.und` (rebuildable, large) and `work/` (archive copies with build
output) are excluded via `.gitignore`.
