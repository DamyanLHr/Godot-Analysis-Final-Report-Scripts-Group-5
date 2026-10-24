"""Fails (exit 1) when Alexia's CSVs and our health data disagree on the things both report.

Run after categorise.py, login_map.py and her run_all.py. Checks:
  1. her 1_commits_per_month.csv total = our non-merge, non-bot commits in the window
  2. her contributors.csv = our people.csv: same people, every flag equal
  3. P1: PRs over all groups = PRs with a known author in 3_pull_requests.csv
  4. every CSV her original (API) version wrote exists, with its original header
Also prints how many PR authors and issue assignees could be matched to a person (login map coverage).

Usage:  python check_consistency.py [ALEXIA_OUT_DIR]
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
HEADERS = {   # as her API version wrote them; her chart code reads these columns
    "1_commits_per_month.csv": "month,commits,merge_commits_excluded",
    "2_issue_same_month_close.csv": "month,opened,closed_same_month,pct_closed_same_month,closed_completed,closed_not_planned",
    "2b_issue_flow_ratio.csv": "month,opened,closed,ratio,net_backlog_change,closed_completed,closed_not_planned,closed_opened_before_window",
    "2c_issue_closed_age.csv": "month,closed,created_same_month,created_older,pct_same_month,pct_older,older_previous_month,older_2_to_12_months,older_over_1_year",
    "3_pull_requests.csv": "number,created,merged,closed,state,draft_now,author,first_review,first_reviewer,hours_to_first_review",
    "3_time_to_first_review.csv": "month,prs_opened,prs_reviewed,median_hours_to_first_review",
    "4_rerun_success_rate.csv": "month,runs,first_attempt_failed,failed_and_rerun,passed_on_rerun,rerun_success_pct,flaky_share_of_failures_pct",
    "4_rerun_by_workflow.csv": "workflow,runs,first_attempt_failed,failed_and_rerun,passed_on_rerun,rerun_success_pct,flaky_share_of_failures_pct",
    "4_reruns.csv": "run_id,workflow,head_sha,event,branch,created,attempts,first_attempt,final_attempt,url",
    "5_project_unassigned.csv": "project,number,closed_project,url,open_tasks,open_unassigned,pct_unassigned",
    "6_milestone_completion.csv": "milestone,number,closed_at,open_items,closed_items,completion_pct",
    "contributors.csv": "key,login,name,window_commits,window_months_active,prior_commits,prior_months_active,last_window_commit,silence_days,key_contributor,newcomer,established,dormant,left,status",
    "months_active_histogram.csv": "months_active,authors_exactly,authors_at_least,pct_at_least",
    "dormancy_thresholds.csv": "definition,threshold_days,dormant",
    "P1_review_time_key_vs_newcomer.csv": "group,prs_opened,prs_reviewed,median_hours_to_first_review",
    "P2_newcomer_commit_share.csv": "month,commits,newcomer_commits,newcomer_pct",
    "P3_assignees.csv": "assignee,open_issues_assigned,status",
    "P3_assignee_status_summary.csv": "status,assignees,pct",
    "P4_former_key_contributors.csv": "milestone,closed_at,contributors,old_key,not_key_anymore,pct_not_key_anymore,still_committing_not_key,no_commits_in_window,lapsed_logins",
}


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "foreign  - Alexia", "out")
    failures = []

    def check(ok, what):
        print(f"  {'ok  ' if ok else 'FAIL'} {what}")
        if not ok:
            failures.append(what)

    print("[check] CSV files and headers")
    for name, header in HEADERS.items():
        path = os.path.join(out, name)
        if not os.path.exists(path):
            check(False, f"{name} missing")
            continue
        with open(path, encoding="utf-8") as f:
            check(f.readline().strip() == header, f"{name} header")

    people = {r["person_id"]: r for r in rows(os.path.join(DATA, "categories", "people.csv"))}
    print("[check] numbers both sections report")
    if os.path.exists(os.path.join(out, "1_commits_per_month.csv")):
        hers = sum(int(r["commits"]) for r in rows(os.path.join(out, "1_commits_per_month.csv")))
        ours = sum(int(p["window_commits"]) for p in people.values())
        check(hers == ours, f"commits in window: hers {hers}, ours {ours}")
    if os.path.exists(os.path.join(out, "contributors.csv")):
        theirs = {r["key"]: r for r in rows(os.path.join(out, "contributors.csv"))}
        check(set(theirs) == set(people), f"people: hers {len(theirs)}, ours {len(people)}")
        flags = [("key_contributor", "key"), ("newcomer", "newcomer"), ("established", "established"),
                 ("dormant", "dormant"), ("left", "left"), ("window_commits", "window_commits")]
        bad = [(k, a) for k in theirs.keys() & people.keys() for a, b in flags if theirs[k][a] != people[k][b]]
        check(not bad, f"flags per person ({len(bad)} differ{': ' + str(bad[:5]) if bad else ''})")
    p1, prs = os.path.join(out, "P1_review_time_key_vs_newcomer.csv"), os.path.join(out, "3_pull_requests.csv")
    if os.path.exists(p1) and os.path.exists(prs):
        # P1 skips PRs whose author account was deleted ("ghost"): no login, so no group.
        groups, n_prs = sum(int(r["prs_opened"]) for r in rows(p1)), sum(bool(r["author"]) for r in rows(prs))
        check(groups == n_prs, f"P1 groups cover every PR with a known author: {groups} of {n_prs}")

    print("[check] login map coverage")
    logins = {r["login"].lower() for r in rows(os.path.join(DATA, "categories", "person_login.csv"))}
    if os.path.exists(prs):
        authors = {r["author"].lower() for r in rows(prs) if r["author"]}
        print(f"  PR authors linked to a git person: {len(authors & logins)} of {len(authors)} "
              "(the rest have no merged commit since the prior year started)")
    p3 = os.path.join(out, "P3_assignees.csv")
    if os.path.exists(p3):
        a = rows(p3)
        print(f"  issue assignees linked to a git person: {sum(r['assignee'] in logins for r in a)} of {len(a)}")

    print(f"[check] {'FAILED: ' + '; '.join(failures) if failures else 'all checks passed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
