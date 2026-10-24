"""The four process-oriented metrics. All take the classified contributor table."""
import math
from collections import Counter, defaultdict

import config
import data
import contributors as C
from util import calendar_months, month_label, median, pct, rnd, is_bot, write_csv, log


# ------------------------------------------------------------------ P1. Review latency: key vs newcomers
def review_key_vs_newcomer(gh, people):
    bl = C.by_login(people)
    groups = defaultdict(lambda: {"prs": 0, "hours": []})
    for pr in data.pull_requests(gh):
        if not pr["author"] or is_bot(pr["author"]):
            continue
        p = bl.get(pr["author"].lower())
        if p is None or not p.active_in_window:
            g = "no commits in window"
        elif p.key_contributor and p.newcomer:
            g = "key AND newcomer (excluded)"
        elif p.key_contributor:
            g = "key"
        elif p.newcomer:
            g = "newcomer"
        else:
            g = "other active"
        groups[g]["prs"] += 1
        if pr["hours_to_first_review"] is not None:
            groups[g]["hours"].append(pr["hours_to_first_review"])

    order = ["key", "newcomer", "other active", "no commits in window", "key AND newcomer (excluded)"]
    rows = [{"group": g, "prs_opened": groups[g]["prs"], "prs_reviewed": len(groups[g]["hours"]),
             "median_hours_to_first_review": rnd(median(groups[g]["hours"]))} for g in order]
    write_csv("P1_review_time_key_vs_newcomer.csv", rows)
    k, n = rows[0]["median_hours_to_first_review"], rows[1]["median_hours_to_first_review"]
    return [f"Median time to first review: key {k} h vs newcomers {n} h"
            + (f" (newcomers wait {n / k:.1f}x as long)" if k and n else "")]


# ------------------------------------------------------------------ P2. Share of commits by newcomers
def newcomer_commit_share(gh, people):
    newcomers = {k for k, p in people.items() if p.newcomer}
    total, newc = Counter(), Counter()
    for c in data.commits(gh, config.WINDOW_START, config.WINDOW_END):
        if c["merge"] or c["bot"]:
            continue
        m = month_label(c["date"])
        total[m] += 1
        newc[m] += data.author_key(c) in newcomers
    rows = [{"month": m, "commits": total[m], "newcomer_commits": newc[m],
             "newcomer_pct": pct(newc[m], total[m])} for m, _, _ in calendar_months()]
    write_csv("P2_newcomer_commit_share.csv", rows)
    t, n = sum(total.values()), sum(newc.values())
    return [f"Newcomer share of commits over the window: {pct(n, t)} % ({n}/{t})"]


# ------------------------------------------------------------------ P3. Dormant / left assignees on open issues
def inactive_assignees(gh, people):
    bl = C.by_login(people)
    # Issues opened in the window and still open at window end. Assignees are the CURRENT ones.
    open_issues = [i for i in data.issues(gh) if i["closed"] is None or i["closed"] >= config.WINDOW_END]
    assigned = [i for i in open_issues if i["assignees"]]
    per_assignee = Counter(a.lower() for i in assigned for a in i["assignees"])

    rows = []
    for login, n in per_assignee.most_common():
        rows.append({"assignee": login, "open_issues_assigned": n, "status": C.status(bl.get(login))})
    write_csv("P3_assignees.csv", rows)

    inactive = {r["assignee"] for r in rows if r["status"] in ("dormant", "left")}
    issues_hit = sum(any(a.lower() in inactive for a in i["assignees"]) for i in assigned)
    by_status = Counter(r["status"] for r in rows)
    summary = [{"status": s, "assignees": c, "pct": pct(c, len(rows))} for s, c in by_status.most_common()]
    write_csv("P3_assignee_status_summary.csv", summary)
    return [f"Open issues (opened in window, open at end): {len(open_issues)}, assigned: {len(assigned)}",
            f"Distinct assignees: {len(rows)}, dormant/left: {len(inactive)} ({pct(len(inactive), len(rows))} %)",
            f"Assigned open issues with a dormant/left assignee: {issues_hit} ({pct(issues_hit, len(assigned))} %)"]


# ------------------------------------------------------------------ P4. Former key contributors no longer frequent
def former_key_contributors(gh, people):
    current_key = {p.login.lower() for p in people.values() if p.key_contributor and p.login}
    active = {p.login.lower() for p in people.values() if p.active_in_window and p.login}

    rows, all_old, all_lapsed = [], set(), set()
    for m in data.closed_milestones(gh):
        log(f"milestone {m['title']}")
        authors = Counter(a.lower() for a in data.milestone_pr_authors(gh, m["number"]) if a and not is_bot(a))
        if not authors:
            continue
        k = max(1, math.ceil(len(authors) * config.MILESTONE_TOP_FRACTION))
        old_key = [a for a, _ in authors.most_common(k)]
        lapsed = [a for a in old_key if a not in current_key]
        still_active = [a for a in lapsed if a in active]
        gone = [a for a in lapsed if a not in active]
        all_old.update(old_key)
        all_lapsed.update(lapsed)
        rows.append({
            "milestone": m["title"], "closed_at": m["closed_at"],
            "contributors": len(authors), "old_key": len(old_key),
            "not_key_anymore": len(lapsed), "pct_not_key_anymore": pct(len(lapsed), len(old_key)),
            "still_committing_not_key": len(still_active), "no_commits_in_window": len(gone),
            "lapsed_logins": lapsed,
        })
    write_csv("P4_former_key_contributors.csv", rows)
    return [f"Former milestone key contributors (union over {len(rows)} milestones): {len(all_old)}, "
            f"no longer key: {len(all_lapsed)} ({pct(len(all_lapsed), len(all_old))} %)"]


ALL = {
    "review-groups": review_key_vs_newcomer,
    "newcomer-commits": newcomer_commit_share,
    "inactive-assignees": inactive_assignees,
    "former-key": former_key_contributors,
}
