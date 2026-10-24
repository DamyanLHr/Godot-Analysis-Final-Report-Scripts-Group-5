# Godot community-health metrics

Collects the 6 activity metrics and 4 process-oriented metrics for `godotengine/godot`
over 16 Sep 2025 – 16 Sep 2026 (end excluded).

The data comes from the health pipeline in this repository (`Scripts/data/`), not from the API:
commits from the Godot clone at 57277407 (author date), GitHub data from `health/fetch_github.py`,
contributor categories from `health/categorise.py`. So the numbers here and in the Project health
section are counted from the same data, and no token is needed to run this.

## Setup

```bash
# from Scripts/, after the health pipeline (see Scripts/README.md)
cd "foreign  - Alexia"
../.venv/Scripts/python run_all.py               # everything
../.venv/Scripts/python run_all.py --list        # metric names
../.venv/Scripts/python run_all.py commits actions former-key   # a subset
../.venv/Scripts/python all_time_key.py          # P4 over people: all-time key contributors no longer key
```

`METRICS_DATA` and `METRICS_OUT` override the data and output folders. The window lives in
`Scripts/window.py`; `config.py` imports it. `github.py` (the old API client) is no longer used.

## Figures (`plots/`)

Alexia's chart and number scripts, read from `out/` after `run_all.py`. Each runs on its own
(`-o` for another file, `--show` for a window); `plot_all.py` runs them all headless.

```bash
../.venv/Scripts/python plots/plot_all.py        # -> out/figures/*.png, printed numbers -> out/plots_output.txt
```

| Script | Reads | Writes |
|---|---|---|
| `commit_per_month.py` | `1_commits_per_month.csv` | `figures/fig_1_commits_per_month.png` |
| `issues_closed.py` | `2c_issue_closed_age.csv` | `figures/fig_2c_issue_closed_age.png` |
| `dubious_reruns.py` | `4_rerun_success_rate.csv` | `figures/fig_4_rerun_flaky_share.png` + overall flaky share |
| `unassigned_projects.py` | `5_project_unassigned.csv` | `figures/fig_5_project_unassigned.png` |
| `Process_oriented_2.py` | `P2_newcomer_commit_share.csv` | `figures/fig_P2_newcomer_commit_share.png` |
| `pull_requests_review_time.py` | `3_pull_requests.csv` | overall median time to first review |
| `milestones_completion_percentage.py` | `6_milestone_completion.csv` | average and item-weighted milestone completion |
| `P4_retired_key_contributors.py` | `P4_former_key_contributors.csv` | % of each milestone's key contributors no longer key (pooled and mean) |

## Outputs (`out/`)

| File | Metric |
|---|---|
| `1_commits_per_month.csv` | Non-merge commits per calendar month |
| `2_issue_same_month_close.csv` | Issues closed in the same calendar month they were opened / issues opened that month × 100 |
| `2b_issue_flow_ratio.csv` | All issues closed / (all opened + all closed) per month, including closures of issues opened before the window; net backlog change and close reasons |
| `2c_issue_closed_age.csv` | Of all issues closed each month: created in the same calendar month vs older (previous month, 2–12 months, over a year) |
| `3_time_to_first_review.csv`, `3_pull_requests.csv` | Median hours to first review, per month and per PR |
| `4_rerun_success_rate.csv` | Failed runs passing on re-run / failed runs re-run × 100 per month (+ conservative variant over all failed first attempts) |
| `4_rerun_by_workflow.csv`, `4_reruns.csv` | Same per workflow, and every re-run run with first and final conclusion |
| `5_project_unassigned.csv` | Open tasks without assignee per project |
| `6_milestone_completion.csv` | Completion % per closed milestone (average in summary) |
| `contributors.csv` | Every author with key / newcomer / established / dormant / left flags |
| `months_active_histogram.csv` | Justifies the 6-month key cut-off |
| `dormancy_thresholds.csv` | Gap percentiles and dormant count per threshold (the 105-day table) |
| `P1_review_time_key_vs_newcomer.csv` | Median first-review time per contributor group |
| `P2_newcomer_commit_share.csv` | Newcomer % of commits per month |
| `P3_assignees.csv`, `P3_assignee_status_summary.csv` | Status of everyone assigned to open issues |
| `P4_former_key_contributors.csv` | Per closed milestone: top-10 % PR authors no longer key |
| `P4_all_time_key_contributors.csv` | `all_time_key.py`: everyone who was top-10 % in any closed milestone, once each, with whether they are key now and their current status |
| `summary.md` | One-line results for everything |

## Definitions as implemented

- **Commits** are dated by **author** date (when the work was written), at Godot commit 57277407; bots left out.
- **Months** for the contributor categories are 12 equal slices of the window (`health/categorise.py`). Reporting tables use calendar months, as the sampling procedure asks.
- **Identity** is one person across all their names and e-mails (`person_id`: .mailmap, then same e-mail or same GitHub noreply login). Their GitHub login comes from Godot's "Merge pull request #N from LOGIN/branch" history (`health/login_map.py`), so PR authors and issue assignees (logins) can be matched to commit authors.
- **Key**: active in ≥ 6 window months. **Newcomer**: first-ever commit inside the window. **Established**: active in ≥ 3 months of the prior year. **Dormant**: established, committed this year, last commit > 105 days (the 99th percentile of gaps between commits) before window end. **Left**: established, no commits this year. All computed by `health/categorise.py`.
- **First review**: earliest submitted review by someone other than the PR author, bots excluded (GitHub's Bot account type, `[bot]` logins). PRs opened by bots are left out. PRs never reviewed are excluded from the median but counted.
- **Actions re-runs**: the unit is one workflow run on one commit; GitHub keeps all its attempts under one run id. Attempt 1 must have failed; the numerator is runs whose final attempt succeeded on the same commit. Re-runs ending cancelled, skipped or timed out are excluded from the re-run denominator. The conservative variant divides by every failed first attempt, since people tend to re-run only what they already suspect is flaky.
- **P3** uses issues opened in the window that were still open at window end, with their *current* assignees.
- **P4** ranks each milestone's contributors by number of merged PRs in it; top 10 % (rounded up) are that milestone's key contributors.
