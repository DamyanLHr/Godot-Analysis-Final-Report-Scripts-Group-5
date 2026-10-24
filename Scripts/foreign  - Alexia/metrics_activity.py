"""The six activity metrics (commits, issues, PRs, Actions re-runs, Projects, Milestones)."""
from collections import Counter

import config
import data
from util import calendar_months, month_label, in_window, median, pct, rnd, write_csv, log


# ------------------------------------------------------------------ 1. Commits per month
def commits_per_month(gh):
    """Non-merge commits per calendar month by AUTHOR date, bots left out (same commits as the health section)."""
    cs = data.commits(gh, config.WINDOW_START, config.WINDOW_END)
    non_merge = Counter(month_label(c["date"]) for c in cs if not c["merge"] and not c["bot"])
    merges = Counter(month_label(c["date"]) for c in cs if c["merge"])
    rows = [{"month": m, "commits": non_merge[m], "merge_commits_excluded": merges[m]}
            for m, _, _ in calendar_months()]
    write_csv("1_commits_per_month.csv", rows)
    total = sum(r["commits"] for r in rows)
    return [f"Commits (non-merge) in window: {total}, mean {total / 12:.0f} per month"]


# ------------------------------------------------------------------ 2. Issues closed in the month they were opened
def issue_same_month_close(gh):
    """Per calendar month: of the issues opened that month, how many were closed in that same month.
    Closures after the window end do not count (only relevant for the last, partial month)."""
    iss = data.issues(gh)  # every issue created in the window

    def same_month(i):
        return (i["closed"] is not None and i["closed"] < config.WINDOW_END
                and month_label(i["closed"]) == month_label(i["created"]))

    rows = []
    for m, _, _ in calendar_months():
        opened = [i for i in iss if month_label(i["created"]) == m]
        closed = [i for i in opened if same_month(i)]
        rows.append({
            "month": m,
            "opened": len(opened),
            "closed_same_month": len(closed),
            # Issues closed in the same month / Issues opened that month x 100
            "pct_closed_same_month": pct(len(closed), len(opened)),
            "closed_completed": sum(i["state_reason"] == "COMPLETED" for i in closed),
            "closed_not_planned": sum(i["state_reason"] == "NOT_PLANNED" for i in closed),
        })
    write_csv("2_issue_same_month_close.csv", rows)

    o = sum(r["opened"] for r in rows)
    c = sum(r["closed_same_month"] for r in rows)
    return [f"Issues opened in window: {o}, closed in the same month they were opened: {c} ({pct(c, o)} %)"]


# ------------------------------------------------------------------ 2b. Issue flow ratio (all issues)
def issue_flow_ratio(gh):
    """Per calendar month: every issue opened vs every issue closed in that month,
    regardless of when the closed issue was opened (backlog closures included)."""
    every = data.all_issues(gh)
    rows = []
    for m, s, e in calendar_months():
        # Counted from the fetched issues (every issue updated since the window start, so every
        # issue opened or closed in it), matching the search queries this used to send.
        closed_now = [i for i in every if i["closed"] is not None and s <= i["closed"] < e]
        opened = sum(s <= i["created"] < e for i in every)
        closed = len(closed_now)
        completed = sum(i["state_reason"] == "COMPLETED" for i in closed_now)
        not_planned = sum(i["state_reason"] == "NOT_PLANNED" for i in closed_now)
        # closed issues that were opened before the window started (backlog work)
        backlog = sum(i["created"] < config.WINDOW_START for i in closed_now)
        rows.append({
            "month": m,
            "opened": opened,
            "closed": closed,
            "ratio": rnd(closed / (opened + closed), 3) if opened + closed else None,
            "net_backlog_change": opened - closed,  # > 0 means the backlog grew
            "closed_completed": completed,
            "closed_not_planned": not_planned,
            "closed_opened_before_window": backlog,
        })
    write_csv("2b_issue_flow_ratio.csv", rows)

    o = sum(r["opened"] for r in rows)
    c = sum(r["closed"] for r in rows)
    # Cohort view: share of issues opened in the window that were closed by window end.
    iss = data.issues(gh)
    resolved = sum(1 for i in iss if i["closed"] and i["closed"] < config.WINDOW_END)
    return [f"All issues: {o} opened, {c} closed in window -> flow ratio {c / (o + c):.3f} "
            f"(0.5 = backlog stable), net backlog change {o - c:+d}",
            f"Resolution rate of issues opened in window: {pct(resolved, len(iss))} % ({resolved}/{len(iss)})"]


# ------------------------------------------------------------------ 2c. Age of closed issues
def _add_months(dt, n):
    y, m = divmod(dt.year * 12 + dt.month - 1 + n, 12)
    return dt.replace(year=y, month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def issue_closed_age(gh):
    """Per calendar month: of ALL issues closed that month, how many were created in that same
    calendar month vs earlier. Issues opened before the window are included."""
    every = data.all_issues(gh)
    rows = []
    for m, s, e in calendar_months():
        month_start = _add_months(s, 0)  # first day of the calendar month, even for the partial first month
        prev_start = _add_months(month_start, -1)
        year_start = _add_months(month_start, -12)

        created = [i["created"] for i in every if i["closed"] is not None and s <= i["closed"] < e]
        total = len(created)
        same = sum(c >= month_start for c in created)
        prev = sum(prev_start <= c < month_start for c in created)
        within_year = sum(year_start <= c < prev_start for c in created)
        over_year = sum(c < year_start for c in created)
        older = total - same

        if same + prev + within_year + over_year != total:
            log(f"WARNING {m}: age buckets sum to {same + prev + within_year + over_year}, total is {total}")
        rows.append({
            "month": m,
            "closed": total,
            "created_same_month": same,
            "created_older": older,
            "pct_same_month": pct(same, total),
            "pct_older": pct(older, total),
            # breakdown of the older issues
            "older_previous_month": prev,
            "older_2_to_12_months": within_year,
            "older_over_1_year": over_year,
        })
    write_csv("2c_issue_closed_age.csv", rows)

    t = sum(r["closed"] for r in rows)
    s = sum(r["created_same_month"] for r in rows)
    y = sum(r["older_over_1_year"] for r in rows)
    return [f"Issues closed in window: {t}; created in the same month: {s} ({pct(s, t)} %), "
            f"older: {t - s} ({pct(t - s, t)} %), of which over a year old: {y} ({pct(y, t)} % of all closures)"]


# ------------------------------------------------------------------ 3. Time to first review
def time_to_first_review(gh):
    prs = data.pull_requests(gh)
    write_csv("3_pull_requests.csv", [{**p, "hours_to_first_review": rnd(p["hours_to_first_review"])} for p in prs])
    rows = []
    for m, _, _ in calendar_months():
        mp = [p for p in prs if month_label(p["created"]) == m]
        hrs = [p["hours_to_first_review"] for p in mp if p["hours_to_first_review"] is not None]
        rows.append({"month": m, "prs_opened": len(mp), "prs_reviewed": len(hrs),
                     "median_hours_to_first_review": rnd(median(hrs))})
    write_csv("3_time_to_first_review.csv", rows)
    hrs = [p["hours_to_first_review"] for p in prs if p["hours_to_first_review"] is not None]
    return [f"PRs opened in window: {len(prs)}, reviewed: {len(hrs)} ({pct(len(hrs), len(prs))} %)",
            f"Median time to first review: {median(hrs):.1f} h ({median(hrs) / 24:.1f} days)" if hrs else
            "Median time to first review: n/a"]


# ------------------------------------------------------------------ 4. Re-run success rate of workflows
COUNTED = ("success", "failure")  # cancelled, skipped and timed_out attempts are excluded


def _rerun_stats(runs):
    first_failed = [r for r in runs if r["first"] == "failure"]
    rerun = [r for r in first_failed if r["attempt"] > 1 and r["conclusion"] in COUNTED]
    passed = [r for r in rerun if r["conclusion"] == "success"]
    return {
        "runs": len(runs),
        "first_attempt_failed": len(first_failed),
        "failed_and_rerun": len(rerun),
        "passed_on_rerun": len(passed),
        # Failed runs passing on re-run / Failed runs re-run x 100
        "rerun_success_pct": pct(len(passed), len(rerun), 2),
        # Conservative variant: Failed runs passing on re-run / All failed first attempts x 100
        "flaky_share_of_failures_pct": pct(len(passed), len(first_failed), 2),
    }


def rerun_success_rate(gh):
    runs = data.workflow_runs(gh)
    reruns = [r for r in runs if r["attempt"] > 1]
    log(f"checking attempt 1 of {len(reruns)} re-run workflow runs")
    for i, r in enumerate(runs, 1):
        r["first"] = data.first_attempt_conclusion(gh, r)
    rows = [{"month": m, **_rerun_stats([r for r in runs if month_label(r["created"]) == m])}
            for m, _, _ in calendar_months()]
    write_csv("4_rerun_success_rate.csv", rows)

    by_wf = {}
    for r in runs:
        by_wf.setdefault(r["workflow"] or str(r["workflow_id"]), []).append(r)
    wf_rows = [{"workflow": w, **_rerun_stats(rs)} for w, rs in by_wf.items()]
    wf_rows.sort(key=lambda r: -r["passed_on_rerun"])
    write_csv("4_rerun_by_workflow.csv", wf_rows)

    write_csv("4_reruns.csv", [{
        "run_id": r["id"], "workflow": r["workflow"], "head_sha": r["head_sha"], "event": r["event"],
        "branch": r["branch"], "created": r["created"].isoformat(), "attempts": r["attempt"],
        "first_attempt": r["first"], "final_attempt": r["conclusion"], "url": r["url"],
    } for r in reruns])

    t = _rerun_stats(runs)
    return [f"Workflow runs: {t['runs']}, first attempt failed: {t['first_attempt_failed']}, "
            f"re-run after failing: {t['failed_and_rerun']}, passed on re-run: {t['passed_on_rerun']}",
            f"Re-run success rate: {t['rerun_success_pct']} % "
            f"(flaky share of all failed first attempts: {t['flaky_share_of_failures_pct']} %)"]


# ------------------------------------------------------------------ 5. Unassigned open tasks per project
def unassigned_project_tasks(gh):
    rows = []
    for p in data.projects(gh):
        log(f"project #{p['number']} {p['title']}")
        total = unassigned = 0
        for item in data.project_items(gh, p["id"]):
            c = item.get("content")
            if item.get("isArchived") or not c:
                continue
            repo = (c.get("repository") or {}).get("nameWithOwner")
            if repo and repo.lower() != config.FULL.lower():
                continue  # org projects can hold items from other repos
            created = c.get("createdAt")
            if not created or not in_window(data.parse(created)):
                continue
            is_open = c["__typename"] == "DraftIssue" or c.get("state") == "OPEN"
            if not is_open:
                continue
            total += 1
            unassigned += c["assignees"]["totalCount"] == 0
        rows.append({"project": p["title"], "number": p["number"], "closed_project": p["closed"],
                     "url": p["url"], "open_tasks": total, "open_unassigned": unassigned,
                     "pct_unassigned": pct(unassigned, total)})
    write_csv("5_project_unassigned.csv", rows)
    t = sum(r["open_tasks"] for r in rows)
    u = sum(r["open_unassigned"] for r in rows)
    with_tasks = [r for r in rows if r["open_tasks"]]
    return [f"Projects: {len(rows)} ({len(with_tasks)} with open window tasks); "
            f"unassigned open tasks overall {pct(u, t)} % ({u}/{t})"]


# ------------------------------------------------------------------ 6. Milestone completion
def milestone_completion(gh):
    rows = []
    for m in data.closed_milestones(gh):
        total = m["open_issues"] + m["closed_issues"]
        rows.append({"milestone": m["title"], "number": m["number"], "closed_at": m["closed_at"],
                     "open_items": m["open_issues"], "closed_items": m["closed_issues"],
                     "completion_pct": pct(m["closed_issues"], total)})
    write_csv("6_milestone_completion.csv", rows)
    vals = [r["completion_pct"] for r in rows if r["completion_pct"] is not None]
    avg = sum(vals) / len(vals) if vals else None
    return [f"Closed milestones: {len(rows)}, average completion {avg:.1f} %" if avg is not None
            else "Closed milestones: none"]


ALL = {
    "commits": commits_per_month,
    "issues": issue_same_month_close,
    "issues-flow": issue_flow_ratio,
    "issues-closed-age": issue_closed_age,
    "reviews": time_to_first_review,
    "actions": rerun_success_rate,
    "projects": unassigned_project_tasks,
    "milestones": milestone_completion,
}
