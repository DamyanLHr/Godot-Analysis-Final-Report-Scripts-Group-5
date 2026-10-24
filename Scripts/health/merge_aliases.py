"""Filtering step 2: detect multiple git identities (aliases) that belong to the same person.

Two independent measures on the raw (name, email) identities that authored commits in the window:
  Measure 1  Godot's own .mailmap (maintained by the project; applied by git as %aN/%aE), then the
             same mailmapped e-mail or the same noreply login = one person (git_activity.person_id),
             then the same GitHub PR login with the same name (login_map.py, people.canonical).
             This is the measure the contributor categories use.
  Measure 2  gambit (Gote & Zingg 2021, pip gambit-disambig 1.0.5): rule-based name/email
             disambiguation, plus GitHub noreply-ID matching ("12345+login@users.noreply.github.com"
             links to the login used as a name elsewhere).
Both are run on the RAW identities, so they can be compared: what each finds that the other misses
goes to hand validation.

Input:  ../data/git/commits_window.csv  (git_activity.py)
Output: ../data/git/aliases_mailmap.csv, aliases_gambit.csv, alias_disagreements.csv + summary
Usage:  python merge_aliases.py
"""
import os
import re

import sys

import gambit
import pandas as pd

from people import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "git")
NOREPLY = re.compile(r"^(?:\d+\+)?(?P<login>[^@]+)@users\.noreply\.github\.com$", re.I)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c = pd.read_csv(os.path.join(DATA, "commits_window.csv"))
    c = c.assign(raw_email=c["raw_email"].fillna(""), email=c["email"].fillna(""))
    c = c[c["is_merge"] == 0]   # authorship = non-merge commits (merges record who pressed merge)
    raw = c.groupby(["raw_name", "raw_email"]).agg(commits=("hash", "size"),
                                                   mailmap_name=("name", "first"),
                                                   mailmap_email=("email", "first"),
                                                   person_id=("person_id", "first")).reset_index()
    raw["raw_email_l"] = raw["raw_email"].str.lower()

    # Measure 1: .mailmap groups, plus same e-mail / same noreply login (git_activity.py's person_id),
    # plus same GitHub PR login and same name (login_map.py) - what the contributor categories use
    raw["mailmap_id"] = raw["person_id"].map(canonical)
    mm_groups = raw.groupby("mailmap_id").filter(lambda g: len(g) > 1)
    mm_groups.sort_values(["mailmap_id", "commits"], ascending=[True, False]).to_csv(
        os.path.join(DATA, "aliases_mailmap.csv"), index=False)

    # Measure 2: gambit on the raw identities, then union with noreply-login matches
    g = gambit.disambiguate_aliases(raw.rename(columns={"raw_name": "alias_name", "raw_email_l": "alias_email"})
                                    [["alias_name", "alias_email"]].copy())
    raw["gambit_id"] = g["author_id"].values
    login = raw["raw_email_l"].str.extract(NOREPLY)["login"].str.lower()
    by_login = {l: gid for l, gid in zip(login, raw["gambit_id"]) if isinstance(l, str)}
    # A raw name equal to a noreply login (e.g. name "bruvzg") joins that login's gambit group.
    raw["gambit_id"] = [by_login.get(str(n).lower(), gid) for n, gid in zip(raw["raw_name"], raw["gambit_id"])]
    gb_groups = raw.groupby("gambit_id").filter(lambda x: len(x) > 1)
    gb_groups.sort_values(["gambit_id", "commits"], ascending=[True, False]).to_csv(
        os.path.join(DATA, "aliases_gambit.csv"), index=False)

    # Disagreements: pairs one measure merges and the other does not
    def pairs(df, key):
        out = set()
        for _, grp in df.groupby(key):
            ids = sorted(grp["raw_name"] + " <" + grp["raw_email_l"] + ">")
            out |= {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]}
        return out
    p_mm, p_gb = pairs(raw, "mailmap_id"), pairs(raw, "gambit_id")
    dis = [{"identity_a": a, "identity_b": b, "found_by": "mailmap only"} for a, b in sorted(p_mm - p_gb)]
    dis += [{"identity_a": a, "identity_b": b, "found_by": "gambit only"} for a, b in sorted(p_gb - p_mm)]
    pd.DataFrame(dis).to_csv(os.path.join(DATA, "alias_disagreements.csv"), index=False)

    print(f"[merge_aliases] raw (name,email) identities with non-merge commits in window: {len(raw)}")
    print(f"  measure 1 .mailmap + same e-mail + same PR login and name : {raw['mailmap_id'].nunique()} people "
          f"({len(mm_groups)} raw identities in {mm_groups['mailmap_id'].nunique()} multi-identity groups)")
    print(f"  measure 2 gambit   : {raw['gambit_id'].nunique()} people "
          f"({len(gb_groups)} raw identities in {gb_groups['gambit_id'].nunique()} multi-identity groups)")
    print(f"  pairs merged by both: {len(p_mm & p_gb)}; mailmap only: {len(p_mm - p_gb)}; gambit only: {len(p_gb - p_mm)}")
    print("  largest .mailmap groups:")
    for mid, grp in sorted(mm_groups.groupby("mailmap_id"), key=lambda kv: -len(kv[1]))[:5]:
        print(f"    {mid}: " + "; ".join(f"{n} <{e}>" for n, e in zip(grp['raw_name'], grp['raw_email'])))


if __name__ == "__main__":
    main()
