"""All data loading. Reads the files our health pipeline writes under Scripts/data/ - no API calls,
so the metrics run offline and everyone gets the same numbers. Refresh the data with
health/fetch_github.py (needs a token) and the health scripts; see README.

The function names and return shapes are the ones the API version had, so the metric files did not
need to change. The `gh` argument is kept for that reason and ignored.
"""
import csv
import json
import os

import config
from util import parse, is_bot, log

_memo = {}


def memo(fn):
    def wrap(gh, *args):
        k = (fn.__name__,) + args
        if k not in _memo:
            _memo[k] = fn(gh, *args)
        return _memo[k]
    wrap.__name__ = fn.__name__
    return wrap


def _path(*parts):
    p = os.path.join(config.DATA_DIR, *parts)
    if not os.path.exists(p):
        # an Exception, not SystemExit: run_all then marks only the metrics needing this file as FAILED
        raise FileNotFoundError(f"missing {p} - run the health pipeline first (see README)")
    return p


def _csv(*parts):
    with open(_path(*parts), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _jsonl(name, key):
    """One record per `key`; the fetch pages by update time, so an item updated mid-fetch can appear twice."""
    out = {}
    with open(_path("github", name), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r[key]] = r
    return list(out.values())


# ============================================================== commits (local git, author date)
def _bot_people():
    return {r["identity"] for r in _csv("bots", "git_identities.csv")
            if r["bot_pattern"] == "True" or r["behaviour_flag"] == "True"}


@memo
def commits(gh, since, until):
    """Commits on master at the snapshot with AUTHOR date in [since, until): the window and prior year."""
    bots = _bot_people()
    person = {r["hash"]: r["person_id"] for r in _csv("categories", "commit_person.csv")}  # aliases merged
    rows = _csv("git", "commits_window.csv") + [{**r, "is_merge": "0"} for r in _csv("git", "commits_prior_year.csv")]
    out = []
    for r in rows:
        date = parse(r["author_date"])
        if not (since <= date < until):
            continue
        out.append({
            "sha": r["hash"],
            "person_id": person.get(r["hash"], r["person_id"]),
            "email": (r.get("email") or "").lower(),
            "name": r.get("name"),
            "date": date,
            "merge": r["is_merge"] == "1",
            "bot": r["person_id"] in bots,
        })
    log(f"  {len(out)} commits {since:%Y-%m-%d} .. {until:%Y-%m-%d}")
    return out


def author_key(c):
    """The person a commit belongs to: our person_id (one per person across names and e-mails)."""
    return c["person_id"]


# ============================================================== issues and PRs (data/github)
def _issue(n):
    return {
        "number": n["number"],
        "created": parse(n["createdAt"]),
        "closed": parse(n["closedAt"]) if n["state"] == "CLOSED" else None,
        "state": n["state"],
        "state_reason": n.get("stateReason"),
        "author": (n.get("author") or {}).get("login"),
        "assignees": [a["login"] for a in ((n.get("assignees") or {}).get("nodes") or []) if a],
    }


@memo
def all_issues(gh):
    """Every fetched issue: all issues updated since the window start, so every issue opened OR
    closed in the window, whenever it was created."""
    out = [_issue(n) for n in _jsonl("issues.jsonl", "number")]
    log(f"  {len(out)} issues updated since the window start")
    return out


@memo
def issues(gh):
    """Every issue created in the window (open and closed)."""
    out = [i for i in all_issues(gh) if config.WINDOW_START <= i["created"] < config.WINDOW_END]
    log(f"  {len(out)} issues created in window")
    return out


@memo
def pull_requests(gh):
    """Every PR created in the window, with its first review by someone other than the author.
    Bots are left out on both sides: PRs a bot opened, and reviews a bot submitted."""
    out = []
    for n in _jsonl("prs.jsonl", "number"):
        created = parse(n["createdAt"])
        if not (config.WINDOW_START <= created < config.WINDOW_END):
            continue
        a = n.get("author") or {}
        author = a.get("login")
        if is_bot(author, a.get("__typename")):
            continue
        first = None
        for rv in (n.get("reviews") or {}).get("nodes") or []:
            t = parse(rv.get("submittedAt"))
            ra = rv.get("author") or {}
            reviewer = ra.get("login") or "ghost"
            if t is None or is_bot(reviewer, ra.get("__typename")):
                continue
            if author and reviewer.lower() == author.lower():
                continue  # replies by the PR author in a review thread are not reviews
            if first is None or t < first[0]:
                first = (t, reviewer)
        out.append({
            "number": n["number"],
            "created": created,
            "merged": parse(n.get("mergedAt")),
            "closed": parse(n.get("closedAt")),
            "state": n["state"],
            "draft_now": n.get("isDraft"),
            "author": author,
            "first_review": first[0] if first else None,
            "first_reviewer": first[1] if first else None,
            "hours_to_first_review": (first[0] - created).total_seconds() / 3600 if first else None,
        })
    out.sort(key=lambda p: p["number"])
    log(f"  {len(out)} pull requests created in window (bot-authored left out)")
    return out


# ============================================================== Actions
@memo
def workflow_runs(gh):
    """Every workflow run created in the window, as its LATEST attempt (`attempt` = latest attempt number)."""
    runs = []
    for r in _jsonl("actions_runs.jsonl", "id"):
        created = parse(r["created_at"])
        if not (config.WINDOW_START <= created < config.WINDOW_END):
            continue
        runs.append({**r, "created": created})
    runs.sort(key=lambda r: r["created"])
    log(f"  {len(runs)} workflow runs, {sum(r['attempt'] > 1 for r in runs)} re-run")
    return runs


def first_attempt_conclusion(gh, run):
    """Conclusion of attempt 1 of a run (fetched with the run)."""
    return run["first_attempt_conclusion"]


# ============================================================== Projects v2
@memo
def _projects(gh):
    return _jsonl("projects.jsonl", "id")


def projects(gh):
    found = [{k: p[k] for k in ("id", "number", "title", "closed", "url")} for p in _projects(gh)]
    log(f"  {len(found)} projects")
    return found


def project_items(gh, project_id):
    return next(p["items"] for p in _projects(gh) if p["id"] == project_id)


# ============================================================== Milestones
@memo
def _milestones(gh):
    return sorted(_jsonl("milestones.jsonl", "number"), key=lambda m: m["number"])


def closed_milestones(gh):
    ms = _milestones(gh)
    log(f"  {len(ms)} closed milestones")
    return ms


def milestone_pr_authors(gh, number):
    """Author login of every merged PR in a milestone (one entry per PR; None for bots)."""
    m = next(m for m in _milestones(gh) if m["number"] == number)
    return [None if is_bot(a.get("login"), a.get("__typename")) else a.get("login") for a in m["merged_pr_authors"]]
