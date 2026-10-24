"""Contributor classification: key, newcomer, established, dormant, left.

The categories are NOT computed here any more: they are read from our health pipeline
(Scripts/data/categories/, written by health/categorise.py), so the Project health section and these
metrics count the same people. Definitions as categorise.py applies them:
  key         active (>= 1 non-merge commit) in >= K of the 12 window months; K from the data (6)
  newcomer    first-ever commit to the repository (under any of the person's names/e-mails) inside the window
  established active in >= 3 months of the year before the window
  dormant     established, committed in the window, but silent for longer than the 99th percentile of
              gaps between commits (105 days at our snapshot) at window end
  left        established, no commits at all in the window

"Months" are 12 equal slices of the window. Commits are dated by author date.
Identity = one person across all their names and e-mails (person_id); GitHub logins are linked
from Godot's "Merge pull request #N from LOGIN/branch" history (health/login_map.py), so PR
authors and issue assignees (logins) can be matched to commit authors.
"""
import csv
import os
import shutil

import config
from util import write_csv, log, pct


class Contributor:
    def __init__(self, key, login, name, email):
        self.key, self.login, self.name, self.email = key, login, name, email
        self.window_commits = self.prior_commits = 0
        self.window_months_active = self.prior_months_active = 0
        self.last_window_commit = None
        self.newcomer = False
        self.key_contributor = self.established = self.dormant = self.left = False
        self.silence_days = None

    @property
    def active_in_window(self):
        return self.window_commits > 0


def _rows(name):
    path = os.path.join(config.DATA_DIR, "categories", name)
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} - run health/categorise.py and health/login_map.py first")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(gh):
    logins = {r["person_id"]: r["login"] for r in _rows("person_login.csv")}
    people = {}
    for r in _rows("people.csv"):
        p = Contributor(r["person_id"], logins.get(r["person_id"]), r["name"], None)
        p.window_commits, p.prior_commits = int(r["window_commits"]), int(r["prior_commits"])
        p.window_months_active, p.prior_months_active = int(r["window_months_active"]), int(r["prior_months_active"])
        p.last_window_commit = r["last_window_commit"] or None
        p.silence_days = float(r["silence_days"]) if r["silence_days"] else None
        p.key_contributor, p.newcomer = r["key"] == "True", r["newcomer"] == "True"
        p.established, p.dormant, p.left = r["established"] == "True", r["dormant"] == "True", r["left"] == "True"
        people[p.key] = p
    log(f"loaded {len(people)} people from data/categories ({sum(p.login is not None for p in people.values())} with a GitHub login)")
    return people


def by_login(people):
    return {p.login.lower(): p for p in people.values() if p.login}


def status(p):
    """Single label, most specific first."""
    if p is None:
        return "no commits (prior year or window)"
    if p.left:
        return "left"
    if p.dormant:
        return "dormant"
    if p.key_contributor and p.newcomer:
        return "key+newcomer"
    if p.key_contributor:
        return "key"
    if p.newcomer:
        return "newcomer"
    if p.active_in_window:
        return "other active"
    return "inactive (not established)"


def report(people):
    authors = [p for p in people.values() if p.active_in_window]
    n = len(authors)

    # Months-active distribution and the dormancy threshold table: computed by categorise.py.
    os.makedirs(config.OUT_DIR, exist_ok=True)
    for name in ("months_active_histogram.csv", "dormancy_thresholds.csv"):
        shutil.copyfile(os.path.join(config.DATA_DIR, "categories", name), os.path.join(config.OUT_DIR, name))
        log(f"wrote {os.path.join(config.OUT_DIR, name)} (from data/categories)")
    table = _rows("dormancy_thresholds.csv")

    rows = []
    for p in sorted(people.values(), key=lambda p: (-p.window_commits, p.key)):
        rows.append({
            "key": p.key, "login": p.login, "name": p.name,
            "window_commits": p.window_commits, "window_months_active": p.window_months_active,
            "prior_commits": p.prior_commits, "prior_months_active": p.prior_months_active,
            "last_window_commit": p.last_window_commit,
            "silence_days": p.silence_days,
            "key_contributor": p.key_contributor, "newcomer": p.newcomer,
            "established": p.established, "dormant": p.dormant, "left": p.left,
            "status": status(p),
        })
    write_csv("contributors.csv", rows)

    key = sum(p.key_contributor for p in authors)
    newc = sum(p.newcomer for p in authors)
    established = [p for p in people.values() if p.established]
    configured = next(r for r in table if r["definition"] == "configured")
    return [
        f"Window authors: {n}",
        f"Key contributors: {key} ({pct(key, n)} %)",
        f"Newcomers: {newc} ({pct(newc, n)} %)",
        f"Established (prior year >= 3 months): {len(established)}",
        f"Dormant (> {configured['threshold_days']} d silent): {sum(p.dormant for p in people.values())}",
        f"Left (no commits in window): {sum(p.left for p in people.values())}",
        f"Silence gap percentiles (days): " + ", ".join(f"{r['definition']}={r['threshold_days']}" for r in table[:-1]),
    ]
