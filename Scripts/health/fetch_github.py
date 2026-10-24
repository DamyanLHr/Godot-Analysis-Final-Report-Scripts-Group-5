"""Fetches godotengine/godot activity for the project-health analysis.

Window: ../window.py (end excluded).
Everything *updated* since the window start is downloaded; the analysis scripts then keep only the
events (opening, review, comment, merge) whose own timestamp falls inside the window. This also
captures reviews and comments made in the window on PRs/issues opened before it.

What is fetched (raw, one JSON object per line, under ../data/github/):
  prs.jsonl              GraphQL: PR author (+ __typename User/Bot), authorAssociation, created/merged/
                         closed, mergedBy, and its first 30 reviews (author, state, submittedAt)
  issues.jsonl           GraphQL: issue author (+ __typename), authorAssociation, created/closed,
                         state reason, current assignees
  issue_comments.jsonl   REST /issues/comments?since=  (conversation comments on issues AND PRs)
  review_comments.jsonl  REST /pulls/comments?since=   (inline review comments)
  actions_runs.jsonl     REST /actions/runs created in the window, latest attempt + attempt 1's conclusion
  projects.jsonl         GraphQL: Projects v2 (repository, else organisation) with all items
  milestones.jsonl       REST closed milestones + GraphQL authors of their merged PRs
  meta.json              fetch timestamps per stage, window, request counts -> cite the fetch date

Usage (YOU run this; the token never leaves your shell):
  export GITHUB_TOKEN=...            (bash)   or   $env:GITHUB_TOKEN="..."  (PowerShell)
  ../.venv/Scripts/python fetch_github.py            # resumes from checkpoints if interrupted
Token: public read access, plus project read for projects.jsonl (classic token: read:project;
fine-grained: organisation Projects read-only). Without it that one stage is skipped with a message.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

OWNER, REPO = "godotengine", "godot"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from window import START_ISO as WINDOW_START, END_ISO as WINDOW_END, PRIOR_START_ISO, GODOT_SNAPSHOT  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "github")
GQL = "https://api.github.com/graphql"
REST = f"https://api.github.com/repos/{OWNER}/{REPO}"

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("Set GITHUB_TOKEN in your shell first (see the docstring).")
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"bearer {TOKEN}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "2IRR80-group5-health"})
STATS = {"graphql_requests": 0, "rest_requests": 0}

PR_QUERY = """
query($owner:String!, $repo:String!, $cursor:String) {
  rateLimit { remaining resetAt cost }
  repository(owner:$owner, name:$repo) {
    pullRequests(first:100, after:$cursor, orderBy:{field:UPDATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title state createdAt updatedAt closedAt mergedAt isDraft
        author { login __typename }
        authorAssociation
        mergedBy { login __typename }
        reviews(first:30) {
          totalCount
          nodes { author { login __typename } authorAssociation state submittedAt }
        }
      }
    }
  }
}"""

ISSUE_QUERY = """
query($owner:String!, $repo:String!, $cursor:String) {
  rateLimit { remaining resetAt cost }
  repository(owner:$owner, name:$repo) {
    issues(first:100, after:$cursor, orderBy:{field:UPDATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title state stateReason createdAt updatedAt closedAt
        author { login __typename }
        authorAssociation
        assignees(first:20) { nodes { login } }
        comments { totalCount }
      }
    }
  }
}"""


def wait_until(reset_epoch, why):
    delay = max(5, reset_epoch - time.time() + 5)
    print(f"  [{why}] sleeping {delay:.0f}s", flush=True)
    time.sleep(delay)


def request(method, url, **kw):
    for attempt in range(8):
        r = SESSION.request(method, url, timeout=120, **kw)
        if r.status_code == 200:
            return r
        if r.status_code in (403, 429) and ("rate limit" in r.text.lower() or "retry-after" in r.headers):
            if "retry-after" in r.headers:
                time.sleep(int(r.headers["retry-after"]) + 1)
            else:
                wait_until(int(r.headers.get("x-ratelimit-reset", time.time() + 60)), "rate limit")
            continue
        if r.status_code in (500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        sys.exit(f"HTTP {r.status_code} for {url}: {r.text[:300]}")
    sys.exit(f"Giving up on {url}")


def checkpoint_path(name):
    return os.path.join(OUT, f".{name}.checkpoint")


def fetch_graphql(name, query, connection):
    """Pages through PRs/issues ordered by updatedAt DESC until updatedAt < WINDOW_START."""
    path = os.path.join(OUT, f"{name}.jsonl")
    cursor = open(checkpoint_path(name)).read().strip() if os.path.exists(checkpoint_path(name)) else None
    if cursor == "DONE":
        print(f"[{name}] already complete")
        return
    with open(path, "a", encoding="utf-8") as out:
        while True:
            r = request("POST", GQL, json={"query": query, "variables": {"owner": OWNER, "repo": REPO, "cursor": cursor}})
            STATS["graphql_requests"] += 1
            body = r.json()
            if "errors" in body:
                print(f"  GraphQL errors: {str(body['errors'])[:300]} -- retrying in 30s")
                time.sleep(30)
                continue
            data = body["data"]
            page = data["repository"][connection]
            for node in page["nodes"]:
                out.write(json.dumps(node) + "\n")
            last_updated = page["nodes"][-1]["updatedAt"] if page["nodes"] else WINDOW_START
            rl = data["rateLimit"]
            print(f"[{name}] +{len(page['nodes'])} (last updatedAt {last_updated}, rate left {rl['remaining']})", flush=True)
            cursor = page["pageInfo"]["endCursor"]
            done = not page["pageInfo"]["hasNextPage"] or last_updated < WINDOW_START
            with open(checkpoint_path(name), "w") as cp:
                cp.write("DONE" if done else cursor)
            if done:
                return
            if rl["remaining"] < 50:
                wait_until(datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00")).timestamp(), "graphql budget")


MAX_PAGE = 250   # GitHub refuses pages beyond 300 for these endpoints (HTTP 422, 30,000 items)


def fetch_rest_since(name, endpoint):
    """REST list endpoints with ?since= (ordered by updated ascending), 100 per page.

    GitHub caps pagination at 300 pages, so every MAX_PAGE pages the query restarts at page 1
    with since = the updated_at of the last item received. Items seen twice at the boundary are
    skipped by id. Checkpoint format: "<since> <page>" (or "DONE")."""
    path = os.path.join(OUT, f"{name}.jsonl")
    seen, last_updated = set(), WINDOW_START
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            c = json.loads(line)
            seen.add(c["id"])
            last_updated = max(last_updated, c["updated_at"])
    since, page = WINDOW_START, 1
    if os.path.exists(checkpoint_path(name)):
        cp = open(checkpoint_path(name)).read().split()
        if cp == ["DONE"] or cp == ["-1"]:
            print(f"[{name}] already complete")
            return
        if len(cp) == 2:
            since, page = cp[0], int(cp[1])
        else:   # old single-number checkpoint: resume from the newest item on disk
            since, page = last_updated, 1
    with open(path, "a", encoding="utf-8") as out:
        while True:
            r = request("GET", f"{REST}/{endpoint}", params={"since": since, "sort": "updated",
                                                           "direction": "asc", "per_page": 100, "page": page})
            STATS["rest_requests"] += 1
            items = r.json()
            new = 0
            for c in items:
                last_updated = max(last_updated, c["updated_at"])
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                new += 1
                # Keep only what the analysis needs (bodies are dropped to keep the archive small).
                out.write(json.dumps({
                    "id": c["id"], "created_at": c["created_at"], "updated_at": c["updated_at"],
                    "user_login": (c.get("user") or {}).get("login"), "user_type": (c.get("user") or {}).get("type"),
                    "author_association": c.get("author_association"),
                    "issue_url": c.get("issue_url"), "pull_request_url": c.get("pull_request_url"),
                    "body_len": len(c.get("body") or ""), "body_head": (c.get("body") or "")[:120],
                }) + "\n")
            print(f"[{name}] since {since} page {page}: +{new} new of {len(items)} "
                  f"(rate left {r.headers.get('x-ratelimit-remaining')})", flush=True)
            done = len(items) < 100
            if done:
                state = "DONE"
            elif page >= MAX_PAGE:
                since, page = last_updated, 1          # roll the window forward before the 300-page cap
                state = f"{since} {page}"
            else:
                page += 1
                state = f"{since} {page}"
            with open(checkpoint_path(name), "w") as cp:
                cp.write(state)
            if done:
                return
            if int(r.headers.get("x-ratelimit-remaining", 100)) < 20:
                wait_until(int(r.headers["x-ratelimit-reset"]), "rest budget")


# ------------------------------------------------------------------ stages for Alexia's metrics
# Query strings and range splitting follow her data.py, so her metrics 4-6 and P3/P4 read the same
# things they used to fetch themselves - now from data/github/, one fetch date for the whole section.

def gql(query, variables):
    """One GraphQL call; None (with a message) when the token lacks a scope the query needs."""
    while True:
        r = request("POST", GQL, json={"query": query, "variables": variables})
        STATS["graphql_requests"] += 1
        body = r.json()
        errors = body.get("errors")
        if not errors:
            return body["data"]
        if any(e.get("type") in ("INSUFFICIENT_SCOPES", "FORBIDDEN", "NOT_FOUND") for e in errors):
            print(f"  GraphQL refused: {str(errors)[:300]}")
            return None
        print(f"  GraphQL errors: {str(errors)[:300]} -- retrying in 30s")
        time.sleep(30)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actions():
    """Every workflow run CREATED in the window, as its latest attempt, plus attempt 1's conclusion
    for re-run runs (GitHub keeps all attempts under one run id). The listing caps at 1000 results
    per query, so ranges with more are halved until they fit (her workflow_runs)."""
    name = "actions_runs"
    path = os.path.join(OUT, f"{name}.jsonl")
    done = set(json.load(open(checkpoint_path(name)))) if os.path.exists(checkpoint_path(name)) else set()
    if "DONE" in done:
        print(f"[{name}] already complete")
        return
    start = datetime.fromisoformat(WINDOW_START.replace("Z", "+00:00"))
    end = datetime.fromisoformat(WINDOW_END.replace("Z", "+00:00"))
    stack = [(start, end)]
    with open(path, "a", encoding="utf-8") as out:
        while stack:
            s, e = stack.pop()
            rng = f"{iso(s)}..{iso(e - timedelta(seconds=1))}"
            if rng in done:
                continue
            total = request("GET", f"{REST}/actions/runs", params={"created": rng, "per_page": 1}).json()["total_count"]
            STATS["rest_requests"] += 1
            if total >= 1000 and e - s > timedelta(minutes=10):
                mid = (s + (e - s) / 2).replace(microsecond=0)
                stack.extend([(mid, e), (s, mid)])
                continue
            page, got = 1, 0
            while True:
                runs = request("GET", f"{REST}/actions/runs", params={"created": rng, "per_page": 100, "page": page}).json()["workflow_runs"]
                STATS["rest_requests"] += 1
                for r in runs:
                    first = r.get("conclusion")
                    if (r.get("run_attempt") or 1) > 1:
                        first = request("GET", f"{REST}/actions/runs/{r['id']}/attempts/1").json().get("conclusion")
                        STATS["rest_requests"] += 1
                    out.write(json.dumps({"id": r["id"], "workflow_id": r["workflow_id"], "workflow": r.get("name"),
                                          "head_sha": r["head_sha"], "event": r.get("event"), "branch": r.get("head_branch"),
                                          "attempt": r.get("run_attempt") or 1, "conclusion": r.get("conclusion"),
                                          "first_attempt_conclusion": first, "created_at": r["created_at"],
                                          "url": r.get("html_url")}) + "\n")
                got += len(runs)
                if len(runs) < 100:
                    break
                page += 1
            out.flush()
            done.add(rng)
            json.dump(sorted(done), open(checkpoint_path(name), "w"))
            print(f"[{name}] {rng}: {got} runs (of {total})", flush=True)
    json.dump(["DONE"], open(checkpoint_path(name), "w"))


REPO_PROJECTS_Q = """query($o:String!, $r:String!, $after:String){
  repository(owner:$o, name:$r){
    projectsV2(first:50, after:$after){ pageInfo{ hasNextPage endCursor } nodes{ id number title closed url } }
  }
}"""
ORG_PROJECTS_Q = """query($o:String!, $after:String){
  organization(login:$o){
    projectsV2(first:50, after:$after){ pageInfo{ hasNextPage endCursor } nodes{ id number title closed url } }
  }
}"""
ITEMS_Q = """query($id:ID!, $after:String){
  node(id:$id){ ... on ProjectV2 {
    items(first:100, after:$after){
      pageInfo{ hasNextPage endCursor }
      nodes{
        isArchived
        content{
          __typename
          ... on Issue { number createdAt state repository{ nameWithOwner } assignees(first:1){ totalCount } }
          ... on PullRequest { number createdAt state repository{ nameWithOwner } assignees(first:1){ totalCount } }
          ... on DraftIssue { createdAt assignees(first:1){ totalCount } }
        }
      }
    }
  } }
}"""


def fetch_projects():
    """Projects (v2) of the repository, or of the organisation when the repository has none, with
    every item. Needs a token that may read projects (classic: read:project)."""
    path = os.path.join(OUT, "projects.jsonl")
    if os.path.exists(path):
        print("[projects] already fetched")
        return

    def project_list(scope):
        found, after = [], None
        while True:
            q, v = (REPO_PROJECTS_Q, {"o": OWNER, "r": REPO, "after": after}) if scope == "repository" \
                else (ORG_PROJECTS_Q, {"o": OWNER, "after": after})
            d = gql(q, v)
            conn = ((d or {}).get(scope) or {}).get("projectsV2")
            if not conn:
                return found
            found += [p for p in conn["nodes"] if p]
            if not conn["pageInfo"]["hasNextPage"]:
                return found
            after = conn["pageInfo"]["endCursor"]

    projects = project_list("repository") or project_list("organization")
    if not projects:
        print("[projects] none readable - check the token can read projects (classic: read:project)")
        return
    with open(path + ".tmp", "w", encoding="utf-8") as out:
        for p in projects:
            items, after = [], None
            while True:
                d = gql(ITEMS_Q, {"id": p["id"], "after": after})
                if not d or not d.get("node"):
                    sys.exit(f"[projects] items of #{p['number']} refused - check the token can read projects")
                conn = d["node"]["items"]
                items += [i for i in conn["nodes"] if i]
                if not conn["pageInfo"]["hasNextPage"]:
                    break
                after = conn["pageInfo"]["endCursor"]
            out.write(json.dumps({**p, "items": items}) + "\n")
            print(f"[projects] #{p['number']} {p['title']}: {len(items)} items", flush=True)
    os.replace(path + ".tmp", path)


MS_PRS_Q = """query($o:String!, $r:String!, $n:Int!, $after:String){
  repository(owner:$o, name:$r){
    milestone(number:$n){
      pullRequests(states:MERGED, first:100, after:$after){
        pageInfo{ hasNextPage endCursor }
        nodes{ author{ login __typename } }
      }
    }
  }
}"""


def fetch_milestones():
    """Every closed milestone (open/closed item counts as GitHub reports them now) and the author of
    each merged PR in it (P4)."""
    path = os.path.join(OUT, "milestones.jsonl")
    if os.path.exists(path):
        print("[milestones] already fetched")
        return
    ms, page = [], 1
    while True:
        batch = request("GET", f"{REST}/milestones", params={"state": "closed", "sort": "due_on", "per_page": 100, "page": page}).json()
        STATS["rest_requests"] += 1
        ms += batch
        if len(batch) < 100:
            break
        page += 1
    with open(path + ".tmp", "w", encoding="utf-8") as out:
        for m in ms:
            authors, after = [], None
            while True:
                d = gql(MS_PRS_Q, {"o": OWNER, "r": REPO, "n": m["number"], "after": after})
                if not d or not (d.get("repository") or {}).get("milestone"):
                    sys.exit(f"[milestones] PRs of {m['title']} refused: {d}")
                conn = d["repository"]["milestone"]["pullRequests"]
                authors += [n["author"] for n in conn["nodes"] if n and n.get("author")]
                if not conn["pageInfo"]["hasNextPage"]:
                    break
                after = conn["pageInfo"]["endCursor"]
            out.write(json.dumps({"number": m["number"], "title": m["title"], "closed_at": m["closed_at"],
                                  "open_issues": m["open_issues"], "closed_issues": m["closed_issues"],
                                  "merged_pr_authors": authors}) + "\n")
            print(f"[milestones] {m['title']}: {len(authors)} merged PRs", flush=True)
    os.replace(path + ".tmp", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    meta_path = os.path.join(OUT, "meta.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    # The .jsonl files are appended to (resumable), so a fetch for another window must start empty.
    if meta and (meta.get("window_start"), meta.get("window_end")) != (WINDOW_START, WINDOW_END):
        sys.exit(f"{OUT} holds a fetch for {meta.get('window_start')}..{meta.get('window_end')}; "
                 f"move that folder away (it is the old fetch) and run again for {WINDOW_START}..{WINDOW_END}.")
    meta.setdefault("started_utc", datetime.now(timezone.utc).isoformat())
    meta.update({"repo": f"{OWNER}/{REPO}", "window_start": WINDOW_START, "window_end": WINDOW_END})

    stages = [("prs", lambda: fetch_graphql("prs", PR_QUERY, "pullRequests")),
              ("issues", lambda: fetch_graphql("issues", ISSUE_QUERY, "issues")),
              ("issue_comments", lambda: fetch_rest_since("issue_comments", "issues/comments")),
              ("review_comments", lambda: fetch_rest_since("review_comments", "pulls/comments")),
              ("actions_runs", fetch_actions),
              ("projects", fetch_projects),
              ("milestones", fetch_milestones)]
    meta.setdefault("stages", {})
    for name, run in stages:
        stage = meta["stages"].setdefault(name, {})
        stage.setdefault("started_utc", datetime.now(timezone.utc).isoformat())
        run()
        meta["stages"][name].setdefault("finished_utc", datetime.now(timezone.utc).isoformat())
        json.dump(meta, open(meta_path, "w"), indent=2)

    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    for k, v in STATS.items():
        meta[k] = meta.get(k, 0) + v
    json.dump(meta, open(meta_path, "w"), indent=2)
    print(f"[fetch_github] done -> {OUT}\n{json.dumps(meta, indent=2)}")


if __name__ == "__main__":
    main()
