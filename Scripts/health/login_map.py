"""Links each git person (git_activity.person_id) to a GitHub login, offline, and finds the
same-person aliases that only the GitHub login shows.

GitHub data (PR authors, reviewers, issue assignees) names people by login; git names them by
e-mail. Every PR merge on Godot's master reads "Merge pull request #N from LOGIN/branch" (9664 of
9665 merges since Sep 2024; the other is a "Re-Merge" of the same form), so:
  1. for each merge M, the PR's commits are those reachable from M's second parent and not
     already on master (walked here in pure Python over the parent graph, oldest merge first);
  2. each of those commits votes "its author = the PR author", the login taken from prs.jsonl
     when the PR is there, else from the merge subject (the fork owner);
  3. a person whose person_id IS a login (noreply address) keeps that login outright;
  4. every other person gets the login with most votes. Maintainers push fix-up commits into
     other people's PRs, so a person's minority votes are noise, not a second account.
A login won by two people stays with the one with most commits voting for it. The other is
  - the SAME person when the names match (letters only, case-insensitive; or their name is the
    login): one person with an e-mail .mailmap doesn't know -> person_alias.csv, which the
    later scripts apply through people.canonical();
  - otherwise reported in login_conflicts.csv and left alone: mostly someone whose commit landed in
    another person's PR (a salvaged or co-written PR).

Why not GitHub's own commit -> account link: it only links e-mails registered to an account,
and needs the API. The merge history links every merged author, including unlinked e-mails.

Input:  the Godot clone, ../data/git/commits_window.csv + commits_prior_year.csv (git_activity.py),
        ../data/github/prs.jsonl
Output: ../data/categories/person_login.csv   (person_id, login, votes, person_votes, source)
        ../data/categories/person_alias.csv   (person_id, canonical, login, name)
        ../data/categories/login_conflicts.csv
Usage:  python login_map.py [GODOT_DIR]      (run after git_activity.py, before merge_aliases.py)
"""
import csv
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from window import PRIOR_START  # noqa: E402

GIT = os.path.join(HERE, "..", "data", "git")
CAT = os.path.join(HERE, "..", "data", "categories")
GH = os.path.join(HERE, "..", "data", "github")
MERGE = re.compile(r"^(?:Re-)?Merge pull request #(?P<pr>\d+) from (?P<login>[^/\s]+)/")
BOT_NAME = re.compile(r"\[bot\]|[-_.]bot\b|^bot$|dependabot|github-actions", re.I)   # filter_bots.py's identity measure, names only


def git(godot, *args):
    return subprocess.run(["git", "-C", godot, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def letters(s):
    """'Mattia Zirpoli' == 'mattia.zirpoli'; accents folded."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def write(name, rows, fields):
    with open(os.path.join(CAT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(CAT, exist_ok=True)
    godot = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "godot"))
    commit_person, names, window_commits = {}, defaultdict(Counter), Counter()
    for fname, in_window in (("commits_window.csv", True), ("commits_prior_year.csv", False)):
        for r in csv.DictReader(open(os.path.join(GIT, fname), encoding="utf-8")):
            if r.get("is_merge", "0") == "1":
                continue
            commit_person[r["hash"]] = r["person_id"]
            names[r["person_id"]][r["name"]] += 1
            window_commits[r["person_id"]] += in_window
    name = {pid: c.most_common(1)[0][0] for pid, c in names.items()}
    pr_author = {}
    for line in open(os.path.join(GH, "prs.jsonl"), encoding="utf-8"):
        n = json.loads(line)
        a = n.get("author") or {}
        if a.get("login") and a.get("__typename") != "Bot":
            pr_author[n["number"]] = a["login"]

    # Parent graph of everything committed since the prior year started (a commit authored then
    # is committed no earlier, so this covers every commit above).
    since = PRIOR_START.isoformat()
    parents, merges = {}, []
    for line in git(godot, "log", "HEAD", f"--since={since}", "--format=%H\x1f%P\x1f%s").splitlines():
        h, p, s = line.split("\x1f", 2)
        parents[h] = p.split()
        m = MERGE.match(s)
        if m and len(parents[h]) == 2:
            merges.append((h, int(m.group("pr")), m.group("login")))
    mainline = set(git(godot, "rev-list", "--first-parent", "HEAD", f"--since={since}").split())
    merges.reverse()   # oldest first, so each commit is credited to the merge that brought it in

    seen, votes = set(mainline), defaultdict(Counter)
    via_subject = 0
    for m, pr, subject_login in merges:
        login = pr_author.get(pr)
        if login is None:
            login, via_subject = subject_login, via_subject + 1
        stack = [parents[m][1]]
        while stack:
            c = stack.pop()
            if c in seen or c not in parents:
                continue
            seen.add(c)
            stack.extend(parents[c])
            if c in commit_person and len(parents[c]) == 1:
                votes[commit_person[c]][login.lower()] += 1

    people = set(commit_person.values())
    best = {}
    for pid in people:
        if BOT_NAME.search(name[pid]) or BOT_NAME.search(pid):
            continue   # a bot's commit inside a human's PR (e.g. snyk-bot) must not take that human's login
        if "@" not in pid and not pid.startswith("name:"):
            best[pid] = (pid, votes[pid][pid] or 1, sum(votes[pid].values()) or 1, "noreply")
        elif votes[pid]:
            login, n = votes[pid].most_common(1)[0]
            best[pid] = (login, n, sum(votes[pid].values()), "pr-merges")

    # One login, one person: keep it with whoever has the most commits voting for it (a noreply
    # address outranks votes: it IS that account). Shares would favour a one-commit person at 1/1.
    owner, dropped = {}, []
    for pid, (login, n, total, src) in sorted(best.items(), key=lambda kv: (kv[1][3] != "noreply", -kv[1][1])):
        if login in owner:
            dropped.append((pid, login, owner[login]))
            continue
        owner[login] = pid

    alias, conflicts = [], []
    for pid, login, other in dropped:
        same = letters(name[pid]) in (letters(name[other]), letters(login))
        row = {"person_id": pid, "name": name[pid], "login": login, "votes": best[pid][1], "kept_by": other,
               "kept_by_name": name[other], "both_active_in_window": window_commits[pid] > 0 and window_commits[other] > 0}
        if same:
            alias.append({"person_id": pid, "canonical": other, "login": login, "name": name[pid]})
        else:
            conflicts.append(row)
    rows = [{"person_id": pid, "login": login, "votes": best[pid][1] + sum(best[a["person_id"]][1] for a in alias if a["canonical"] == pid),
             "person_votes": best[pid][2], "source": best[pid][3]}
            for login, pid in sorted(owner.items(), key=lambda kv: kv[1])]
    write("person_login.csv", rows, ["person_id", "login", "votes", "person_votes", "source"])
    write("person_alias.csv", alias, ["person_id", "canonical", "login", "name"])
    write("login_conflicts.csv", conflicts, ["person_id", "name", "login", "votes", "kept_by", "kept_by_name", "both_active_in_window"])

    print(f"[login_map] {len(merges)} PR merges since {PRIOR_START:%Y-%m-%d} "
          f"({len(merges) - via_subject} PR authors from prs.jsonl, {via_subject} from the merge subject)")
    print(f"[login_map] {len(rows)} of {len(people) - len(alias)} people linked to a login "
          f"({sum(r['source'] == 'noreply' for r in rows)} by noreply address); "
          f"{len(people) - len(best)} never in a merged PR or bots")
    print(f"[login_map] same person, same login and name: {len(alias)} aliases merged "
          f"({sum(window_commits[a['person_id']] > 0 and window_commits[a['canonical']] > 0 for a in alias)} with both "
          f"active in the window) -> person_alias.csv")
    print(f"[login_map] different names behind one login, left apart: {len(conflicts)} -> login_conflicts.csv")
    for c in conflicts:
        print(f"    {c['name']} ({c['person_id']}) in PRs of {c['kept_by_name']} ({c['login']})")


if __name__ == "__main__":
    main()
