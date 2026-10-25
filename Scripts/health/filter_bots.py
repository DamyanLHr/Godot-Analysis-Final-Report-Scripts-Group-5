"""Filtering step 1: bots (and bot-like human accounts) in the window.

Measure 1 - identity (Dey et al. 2020, "name and email"; lecture 5):
  git:    name/email matches a bot pattern ([bot], -bot, bot@, github-actions, dependabot, weblate...)
          A naive substring test for "bot" is reported too, to show its false positives.
  GitHub: author.__typename == "Bot" or a login ending in "[bot]" (needs fetch_github.py data).
Measure 2 - behaviour (Dey et al. 2020 activity features, adapted):
  per identity with >= 5 non-merge commits: share of commits whose subject is one repeated template
  (digits/versions masked), median files changed per commit, and number of distinct hours of day
  active. Templated + wide-reaching commits are what automation produces.
  Commit-level: templated mass commits (e.g. "Sync translations with Weblate") are flagged even when
  the account is human -> "human account carrying automated / many people's work".
Measure 3 (validation, needs a GitHub token): BoDeGHa / RABBIT on the GitHub logins.

Input:  ../data/git/commits_window.csv; optional ../data/github/*.jsonl
Output: ../data/bots/*.csv + summary
"""
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

from people import canonical

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from window import START_ISO, END_ISO  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GIT = os.path.join(HERE, "..", "data", "git")
GH = os.path.join(HERE, "..", "data", "github")
OUT = os.path.join(HERE, "..", "data", "bots")
BOT_PATTERN = re.compile(r"(?:\[bot\]|[-_.]bot\b|\bbot[-_.@]|^bot$|github-actions|dependabot|renovate|weblate|"
                         r"snyk-bot|codecov|noreply@github\.com$)", re.I)
NAIVE = re.compile(r"bot", re.I)
TEMPLATE = re.compile(r"\d+(\.\d+)*")


def template(subject):
    return TEMPLATE.sub("N", str(subject)).strip()


def git_measures(c):
    c = c.copy()
    # One row per person (people.canonical of git_activity.py's person_id); the patterns test the
    # "name <email>" label.
    c["identity"] = c["person_id"].map(canonical)
    nm = c[c["is_merge"] == 0]
    ids = nm.groupby("identity").agg(commits=("hash", "size"), name=("name", "first"), email=("email", "first"),
                                     median_files=("files_changed", "median"))
    label = ids["name"] + " <" + ids["email"].fillna("").str.lower() + ">"
    ids["naive_bot_substring"] = label.str.contains(NAIVE)
    ids["bot_pattern"] = label.str.contains(BOT_PATTERN)

    tpl_share, hours = {}, {}
    for ident, grp in nm.groupby("identity"):
        tpls = Counter(template(s) for s in grp["subject"])
        tpl_share[ident] = tpls.most_common(1)[0][1] / len(grp)
        hours[ident] = pd.to_datetime(grp["author_date"], utc=True).dt.hour.nunique()
    ids["top_template_share"] = pd.Series(tpl_share).round(2)
    ids["distinct_hours"] = pd.Series(hours)
    ids["behaviour_flag"] = (ids["commits"] >= 5) & (ids["top_template_share"] >= 0.8)

    # Commit level: templated mass commits (same subject template >= 3 times in window, >= 20 files)
    nm = nm.assign(tpl=nm["subject"].map(template))
    tpl_counts = nm["tpl"].value_counts()
    mass = nm[(nm["tpl"].map(tpl_counts) >= 3) & (nm["files_changed"] >= 20)]
    return ids.sort_values("commits", ascending=False), mass, c


def github_measures():
    """Collect every GitHub login seen in the window with its __typename / REST type."""
    if not os.path.exists(os.path.join(GH, "prs.jsonl")):
        return None
    lo, hi = START_ISO, END_ISO
    seen = Counter()
    types = {}

    def add(login, typ, when):
        if login and when and lo <= when < hi:
            seen[login] += 1
            types.setdefault(login, typ)

    for name in ("prs", "issues"):
        for line in open(os.path.join(GH, f"{name}.jsonl"), encoding="utf-8"):
            n = json.loads(line)
            a = n.get("author") or {}
            add(a.get("login"), a.get("__typename"), n.get("createdAt"))
            for r in ((n.get("reviews") or {}).get("nodes") or []):
                ra = r.get("author") or {}
                add(ra.get("login"), ra.get("__typename"), r.get("submittedAt"))
    for name in ("issue_comments", "review_comments"):
        path = os.path.join(GH, f"{name}.jsonl")
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                c = json.loads(line)
                add(c.get("user_login"), "Bot" if c.get("user_type") == "Bot" else "User", c.get("created_at"))
    df = pd.DataFrame({"login": list(seen), "events": [seen[l] for l in seen], "type": [types[l] for l in seen]})
    df["typename_bot"] = df["type"].eq("Bot") | df["login"].str.endswith("[bot]")
    df["login_pattern_bot"] = df["login"].str.contains(BOT_PATTERN)
    return df.sort_values("events", ascending=False)


URLISH = re.compile(r"https?://\S+|#\d+|\b[0-9a-f]{7,40}\b|\d+(\.\d+)*")


def github_comment_behaviour(min_comments=10):
    """Measure 2 on GitHub, adapted from BoDeGHa (Golzadeh et al. 2021): bots repeat a few comment
    patterns. Per login with >= min_comments comments in the window: number of distinct patterns
    (first 120 chars, lower-cased, URLs/PR numbers/hashes/numbers masked), share of the most common
    pattern, share of empty comments. Flag: top-pattern share >= 0.5."""
    lo, hi = START_ISO, END_ISO
    rows = []
    for name in ("issue_comments", "review_comments"):
        p = os.path.join(GH, f"{name}.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                c = json.loads(line)
                if lo <= c["created_at"] < hi and c.get("user_login"):
                    rows.append((c["user_login"], c.get("user_type"),
                                 URLISH.sub("N", (c.get("body_head") or "").strip().lower())))
    df = pd.DataFrame(rows, columns=["login", "type", "pattern"])
    out = []
    for login, g in df.groupby("login"):
        if len(g) < min_comments:
            continue
        vc = g["pattern"].value_counts()
        out.append({"login": login, "type": g["type"].iloc[0], "comments": len(g), "patterns": len(vc),
                    "top_pattern_share": round(vc.iloc[0] / len(g), 2), "top_pattern": vc.index[0][:60],
                    "empty_share": round((g["pattern"] == "").mean(), 2)})
    res = pd.DataFrame(out).sort_values("top_pattern_share", ascending=False)
    res["behaviour_flag"] = res["top_pattern_share"] >= 0.5
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    c = pd.read_csv(os.path.join(GIT, "commits_window.csv"))
    ids, mass, _ = git_measures(c)
    ids.to_csv(os.path.join(OUT, "git_identities.csv"))
    mass.to_csv(os.path.join(OUT, "git_templated_mass_commits.csv"), index=False)

    print(f"[filter_bots] git identities with non-merge commits: {len(ids)}")
    print(f"  naive substring 'bot': {ids['naive_bot_substring'].sum()} -> "
          + "; ".join(ids[ids['naive_bot_substring']].index[:10]))
    print(f"  bot pattern (measure 1): {ids['bot_pattern'].sum()} -> " + "; ".join(ids[ids['bot_pattern']].index))
    print(f"  behaviour flag (measure 2, >=5 commits and >=80% one template): {ids['behaviour_flag'].sum()}")
    print(ids[ids["behaviour_flag"]][["commits", "top_template_share", "median_files", "distinct_hours"]].to_string())
    print(f"  templated mass commits (template >=3x, >=20 files): {len(mass)}")
    print(mass.groupby(["name", "tpl"]).agg(n=("hash", "size"), median_files=("files_changed", "median")).to_string())

    gh = github_measures()
    if gh is None:
        print("[filter_bots] no GitHub data yet (run fetch_github.py) - GitHub measures skipped")
        return
    gh.to_csv(os.path.join(OUT, "github_logins.csv"), index=False)
    print(f"[filter_bots] GitHub logins active in window: {len(gh)}; __typename Bot/[bot]: {gh['typename_bot'].sum()}; "
          f"login pattern: {gh['login_pattern_bot'].sum()}")
    print(gh[gh["typename_bot"] | gh["login_pattern_bot"]].to_string(index=False))

    beh = github_comment_behaviour()
    beh.to_csv(os.path.join(OUT, "github_comment_behaviour.csv"), index=False)
    print(f"[filter_bots] comment behaviour (>=10 comments): {len(beh)} logins; flagged (top pattern >= 50%): "
          f"{int(beh['behaviour_flag'].sum())}")
    print(beh.head(15).to_string(index=False))
    # RABBIT input: every login flagged by any measure + the 30 most active logins (validation sample)
    sample = set(gh.loc[gh["typename_bot"] | gh["login_pattern_bot"], "login"]) | set(beh.loc[beh["behaviour_flag"], "login"])
    sample |= set(gh.sort_values("events", ascending=False)["login"].head(30))
    with open(os.path.join(OUT, "rabbit_input.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(sample)) + "\n")
    print(f"[filter_bots] {len(sample)} logins written to rabbit_input.txt for RABBIT validation")


if __name__ == "__main__":
    main()
