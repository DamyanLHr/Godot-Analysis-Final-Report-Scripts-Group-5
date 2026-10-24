"""H1 current contributors + H3 involvement categories (key/frequent, newcomer, dormant).

Window ../window.py (end excluded, 365 days), split into 12 equal slices ("months").
Activity types per person (lecture 5: commits, PRs, issues + reviews/comments as involvement):
  git     non-merge commits authored (one person = people.canonical(person_id); bots removed)  [always]
  GitHub  PRs opened, reviews submitted, issues opened, comments (conversation+inline)  [if fetched]
Merges are NOT counted as authorship: a merge commit records who pressed "merge" (gatekeeping),
which is reported separately (H1 "merged by").

Thresholds are derived from the data and printed with their justification:
  key/frequent  active in >= K slices; K = where about 10% of people remain (top decile of
                regularity) - printed with the histogram. Git: fixed at KEY_MIN_SLICES = 6 (10.1 %);
                GitHub: the smallest K where the share drops below 10%
  newcomer      first-ever commit (all-time git history, any of the person's names/e-mails) inside the window
  established   active in >= 3 slices of the prior year
  dormant       established, but no commit in the last G days of the window, where
                G = DORMANCY_PERCENTILE of the gaps between consecutive commits of regular contributors
  left          established, no commit at all in the window

This script is the ONE place contributors are categorised: Alexia's metrics read the exports below
instead of classifying people themselves, so both report sections count the same people.

Usage:  python categorise.py
Output: ../data/categories/*.csv and plots in plots/
  people.csv                 every person active in the window or the prior year, with all flags
  commit_person.csv          commit hash -> person_id (window and prior year)
  months_active_histogram.csv, dormancy_thresholds.csv   the tables behind the thresholds
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import window  # noqa: E402
from people import canonical  # noqa: E402

GIT = os.path.join(HERE, "..", "data", "git")
GH = os.path.join(HERE, "..", "data", "github")
BOTS = os.path.join(HERE, "..", "data", "bots")
OUT = os.path.join(HERE, "..", "data", "categories")
PLOTS = os.path.join(HERE, "plots")
START = pd.Timestamp(window.START)
END = pd.Timestamp(window.END)
PRIOR_START = pd.Timestamp(window.PRIOR_START)
SLICE = (END - START) / 12
ESTABLISHED_MIN_SLICES = 3
# Key (git): fixed at 6 months, where about 10 % of authors remain (10.1 % at our snapshot). The
# "< 10 %" rule alone sits on a knife edge here (it gives 7 by 0.1 point) and is still printed.
KEY_MIN_SLICES = 6
DORMANCY_PERCENTILE = 0.99   # the report's choice: the conservative end of the sensitivity table


def slice_of(ts, start=START):
    return ((ts - start) / SLICE).astype(int).clip(0, 11)


def bot_people():
    gi = os.path.join(BOTS, "git_identities.csv")
    if not os.path.exists(gi):
        return set()
    b = pd.read_csv(gi)
    return set(b.loc[b["bot_pattern"] | b["behaviour_flag"], "identity"])


def git_events():
    c = pd.read_csv(os.path.join(GIT, "commits_window.csv"))
    c["ts"] = pd.to_datetime(c["author_date"], utc=True)
    c["person_id"] = c["person_id"].map(canonical)
    c["person"] = c["person_id"]
    bots = bot_people()
    merges = c[c["is_merge"] == 1]
    authored = c[(c["is_merge"] == 0) & (~c["person"].isin(bots))]
    return authored.assign(type="commit")[["person", "ts", "type"]], merges, bots, c


def github_events():
    if not os.path.exists(os.path.join(GH, "prs.jsonl")):
        return None
    ev = []
    for line in open(os.path.join(GH, "prs.jsonl"), encoding="utf-8"):
        n = json.loads(line)
        a = n.get("author") or {}
        ev.append((a.get("login"), a.get("__typename"), n["createdAt"], "pr", n.get("authorAssociation")))
        for r in (n.get("reviews") or {}).get("nodes") or []:
            ra = r.get("author") or {}
            ev.append((ra.get("login"), ra.get("__typename"), r.get("submittedAt"), "review", r.get("authorAssociation")))
    for line in open(os.path.join(GH, "issues.jsonl"), encoding="utf-8"):
        n = json.loads(line)
        a = n.get("author") or {}
        ev.append((a.get("login"), a.get("__typename"), n["createdAt"], "issue", n.get("authorAssociation")))
    for name in ("issue_comments", "review_comments"):
        p = os.path.join(GH, f"{name}.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                c = json.loads(line)
                ev.append((c.get("user_login"), "Bot" if c.get("user_type") == "Bot" else "User",
                           c.get("created_at"), "comment", c.get("author_association")))
    df = pd.DataFrame(ev, columns=["person", "typename", "when", "type", "association"]).dropna(subset=["person", "when"])
    df = df[(df["when"] >= window.START_ISO) & (df["when"] < window.END_ISO)]
    is_bot = df["typename"].eq("Bot") | df["person"].str.endswith("[bot]")
    df["ts"] = pd.to_datetime(df["when"], utc=True)
    return df[~is_bot], df[is_bot]


def concentration(counts):
    s = counts.sort_values(ascending=False)
    cum = s.cumsum() / s.sum()
    return {"people": len(s), "events": int(s.sum()), "top10_share_pct": round(100 * s.head(10).sum() / s.sum(), 1),
            "bus_factor_50pct": int((cum < 0.5).sum() + 1), "people_for_80pct": int((cum < 0.8).sum() + 1)}


def categorise(ev, label, first_seen, prior_people, fixed_K=None):
    ev = ev.assign(slice=slice_of(ev["ts"]))
    per = ev.groupby("person").agg(events=("ts", "size"), slices_active=("slice", "nunique"),
                                   first_in_window=("ts", "min"), last_in_window=("ts", "max"))
    hist = per["slices_active"].value_counts().sort_index()
    share_ge = {k: (per["slices_active"] >= k).mean() for k in range(1, 13)}
    derived_K = next(k for k in range(1, 13) if share_ge[k] < 0.10)
    K = fixed_K or derived_K

    # Gaps between consecutive activities of regular contributors (>= 3 active slices)
    regular = per.index[per["slices_active"] >= 3]
    gaps = (ev[ev["person"].isin(regular)].sort_values("ts").groupby("person")["ts"].diff().dt.days.dropna())
    G = int(np.ceil(gaps.quantile(DORMANCY_PERCENTILE))) if len(gaps) else 90

    per["key"] = per["slices_active"] >= K
    per["newcomer"] = per.index.map(lambda p: p in first_seen and first_seen[p] >= START)
    cutoff = END - pd.Timedelta(days=G)
    per["silent_last_G_days"] = per["last_in_window"] < cutoff
    dormant_in_window = per.index[per["silent_last_G_days"] & per.index.isin(prior_people)]
    left = sorted(set(prior_people) - set(per.index))   # active the year before, nothing in window

    print(f"\n=== {label}: {len(per)} active people, {len(ev)} events ===")
    print("slices active -> people:", hist.to_dict())
    print(f"key/frequent threshold K = {K} slices (share of people active in >= K slices: {share_ge[K]:.1%}; "
          f"in >= {K - 1}: {share_ge[K - 1]:.1%})")
    if K != derived_K:
        print(f"  (fixed; the < 10 % rule alone would give K = {derived_K}: {share_ge[derived_K]:.1%})")
    print(f"dormancy gap G = {G} days (p{int(DORMANCY_PERCENTILE * 100)} of {len(gaps)} gaps between consecutive "
          f"activities of {len(regular)} regular contributors)")
    print(f"key: {per['key'].sum()}  newcomers: {per['newcomer'].sum()}  "
          f"dormant (prior-year established, silent last {G}d of window): {len(dormant_in_window)}  "
          f"left (prior-year established, nothing in window): {len(left)}")
    # Dormancy is threshold-sensitive (lecture 5: "dormancy is tricky"), so show the alternatives.
    print("dormancy sensitivity (gap percentile -> days -> established people silent that long at window end):")
    sens = []
    for q in (0.75, 0.90, 0.95, 0.99):
        g = int(np.ceil(gaps.quantile(q))) if len(gaps) else 0
        n = int((per["last_in_window"] < END - pd.Timedelta(days=g))[per.index.isin(prior_people)].sum())
        sens.append({"definition": f"P{int(q * 100)} of gaps", "threshold_days": g, "dormant": n})
        print(f"   p{int(q * 100)}: {g:>4} days -> {n}")
    return per, hist, K, G, dormant_in_window, left, sens


def export_people(per, K, G, dormant, left, prior, first_seen, names, sens, hist):
    """people.csv + the two threshold tables, in the shape Alexia's contributors.report writes them."""
    prior_per = prior.groupby("person").agg(prior_commits=("hash", "size"), prior_months_active=("slice", "nunique"))
    everyone = sorted(set(per.index) | set(prior_per.index))
    p = pd.DataFrame(index=pd.Index(everyone, name="person_id"))
    p["name"] = [names.get(x, x) for x in everyone]
    p["window_commits"] = per["events"].reindex(everyone).fillna(0).astype(int)
    p["window_months_active"] = per["slices_active"].reindex(everyone).fillna(0).astype(int)
    p["prior_commits"] = prior_per["prior_commits"].reindex(everyone).fillna(0).astype(int)
    p["prior_months_active"] = prior_per["prior_months_active"].reindex(everyone).fillna(0).astype(int)
    last = per["last_in_window"].reindex(everyone)
    p["last_window_commit"] = last.dt.date
    p["silence_days"] = ((END - last).dt.total_seconds() / 86400).round(1)
    p["key"] = p["window_months_active"] >= K
    p["newcomer"] = [bool(x in per.index and per.at[x, "newcomer"]) for x in everyone]
    p["established"] = p["prior_months_active"] >= ESTABLISHED_MIN_SLICES
    p["dormant"] = p.index.isin(dormant)
    p["left"] = p.index.isin(left)
    p["first_commit_utc"] = [first_seen.get(x) for x in everyone]
    p.sort_values(["window_commits", "prior_commits"], ascending=False).to_csv(os.path.join(OUT, "people.csv"))

    n = len(per)
    rows = []
    for k in range(1, 13):
        at_least = int((per["slices_active"] >= k).sum())
        rows.append({"months_active": k, "authors_exactly": int(hist.get(k, 0)), "authors_at_least": at_least,
                     "pct_at_least": round(100 * at_least / n, 1)})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "months_active_histogram.csv"), index=False)
    pd.DataFrame(sens + [{"definition": "configured", "threshold_days": G, "dormant": len(dormant)}]).to_csv(
        os.path.join(OUT, "dormancy_thresholds.csv"), index=False)
    print(f"[categorise] people.csv: {len(p)} people ({n} active in window, {int(p['key'].sum())} key, "
          f"{int(p['newcomer'].sum())} newcomers, {int(p['established'].sum())} established, "
          f"{int(p['dormant'].sum())} dormant, {int(p['left'].sum())} left)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PLOTS, exist_ok=True)

    commits, merges, bots, all_window = git_events()
    fc = pd.read_csv(os.path.join(GIT, "first_commit.csv"))
    fc["first"] = pd.to_datetime(fc["first_commit_utc"], utc=True)
    # A merged alias's first commit counts for the person: the earliest over all their ids.
    first_seen = fc.assign(person=fc["person_id"].map(canonical)).groupby("person")["first"].min().to_dict()
    prior = pd.read_csv(os.path.join(GIT, "commits_prior_year.csv"))
    prior["person_id"] = prior["person_id"].map(canonical)
    prior["person"] = prior["person_id"]
    prior = prior[~prior["person"].isin(bots)]
    # Only people who were ESTABLISHED the year before can "go dormant"; a one-off contributor who
    # never came back is a one-time contributor, not a dormant one. Established = active in >= 3 of
    # the 12 slices of the prior year (same slice length as the window).
    prior["slice"] = slice_of(pd.to_datetime(prior["author_date"], utc=True), PRIOR_START)
    prior_slices = prior.groupby("person")["slice"].nunique()
    prior_people = set(prior_slices.index[prior_slices >= ESTABLISHED_MIN_SLICES])
    print(f"prior year ({window.PRIOR_START:%Y-%m-%d}..{window.START:%Y-%m-%d}, end excluded): "
          f"{len(prior_slices)} commit authors, {len(prior_people)} established (>= {ESTABLISHED_MIN_SLICES} slices)")

    # Display name = the name a person used most (window first, then the prior year).
    named = pd.concat([all_window[["person_id", "name"]], prior[["person_id", "name"]]])
    names = named.groupby("person_id")["name"].agg(lambda s: s.value_counts().index[0]).to_dict()

    print("=== H1 git (non-merge commits, one person per person_id, bots removed:", sorted(bots), ") ===")
    print(concentration(commits.groupby("person").size()))
    print("merge commits by merger (committer of merge commits):")
    print(merges["committer"].value_counts().head(5).to_string())

    per, hist, K, G, dormant, left, sens = categorise(commits, "git commit authors", first_seen, prior_people, KEY_MIN_SLICES)
    per.assign(name=[names.get(x, x) for x in per.index]).to_csv(os.path.join(OUT, "git_people.csv"))
    pd.Series(sorted(left), name="person").to_csv(os.path.join(OUT, "git_left.csv"), index=False)
    export_people(per, K, G, dormant, left, prior, first_seen, names, sens, hist)
    pd.concat([all_window[["hash", "person_id"]], prior[["hash", "person_id"]]]).to_csv(
        os.path.join(OUT, "commit_person.csv"), index=False)
    print("key contributors (git):")
    print(per[per["key"]].assign(name=[names.get(x, x) for x in per.index[per["key"]]])
          .sort_values("events", ascending=False).head(25)[["name", "events", "slices_active"]].to_string())

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(hist.index, hist.values, color=["#4a86e8" if k >= K else "#b0b0b0" for k in hist.index])
    ax.axvline(K - 0.5, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel(f"active months (12 equal slices of {window.START:%Y-%m-%d}..{window.END:%Y-%m-%d}, end excluded)")
    ax.set_ylabel("commit authors")
    ax.set_yscale("log")
    ax.set_title(f"Months active per commit author (key threshold K={K})")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "git_months_active.png"), dpi=150)

    gh = github_events()
    if gh is None:
        print("\n[categorise] no GitHub data yet - run fetch_github.py; GitHub activity types skipped")
        return
    human, botev = gh
    print("\n=== H1 GitHub (bots removed) ===")
    print("bot events removed:", botev.groupby("person").size().sort_values(ascending=False).head(10).to_dict())
    for t in ["pr", "review", "issue", "comment"]:
        s = human[human["type"] == t].groupby("person").size()
        print(f"{t:<8}", concentration(s))
    # Newcomer and dormancy are measured on git only: our GitHub pull has no history before the window,
    # and GitHub computes authorAssociation at QUERY time (no FIRST_TIME_* values remain for last
    # year's PRs). What association does show: "NONE" today = the author still has no merged commit.
    per_gh, hist_gh, K2, _, _, _, _ = categorise(human[["person", "ts", "type"]], "GitHub participants (all types)", {}, set())
    print("(GitHub newcomer/dormant counts above are not meaningful - see comment; use the git ones)")
    prs = human[human["type"] == "pr"]
    assoc = prs.groupby("association")["person"].agg(prs="size", authors="nunique")
    print("PR authors by authorAssociation at query time (NONE = still no merged contribution):")
    print(assoc.sort_values("prs", ascending=False).to_string())
    merged = pd.DataFrame([(n.get("authorAssociation"), bool(n.get("mergedAt")))
                           for n in map(json.loads, open(os.path.join(GH, "prs.jsonl"), encoding="utf-8"))
                           if window.START_ISO <= n["createdAt"] < window.END_ISO
                           and (n.get("author") or {}).get("__typename") != "Bot"], columns=["association", "merged"])
    print("PRs opened in window, share merged by now, per authorAssociation:")
    print((merged.groupby("association")["merged"].mean() * 100).round(1).to_string())
    types =human.pivot_table(index="person", columns="type", values="ts", aggfunc="size", fill_value=0)
    per_gh.join(types).to_csv(os.path.join(OUT, "github_people.csv"))


if __name__ == "__main__":
    main()
