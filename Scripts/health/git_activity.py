"""Extracts commit activity from the local Godot clone for the health analysis.

Window: ../window.py, by AUTHOR date (git's --since/--until filter on the COMMITTER date, so the
window is applied here on the author date instead: the moment the work was done, not when it was
rebased or merged).

Identity: every commit gets a person_id, the key one person keeps across names and e-mails:
  the GitHub login for noreply addresses ("12345+login@users.noreply.github.com" and
  "login@users.noreply.github.com" are the same person), else the mailmapped e-mail (Godot's own
  .mailmap, lower-cased), else "name:<mailmapped name>" when the e-mail is empty.
The display name is NOT part of the key: keying on name + e-mail split people who renamed
themselves (9 in the window) and made their old commits invisible to the newcomer check.

Output (../data/git/):
  commits_window.csv   one row per commit in the window: hash, author date, raw name/email (%an/%ae),
                       mailmapped name/email (%aN/%aE), person_id, committer, is_merge,
                       files changed, subject, co-author trailers
  first_commit.csv     all-time first authored commit per person_id (for newcomer detection)
  commits_prior_year.csv  non-merge commits authored in the prior year (for dormancy detection)

Usage:  python git_activity.py [GODOT_DIR]
"""
import csv
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from window import START as SINCE, END as UNTIL, PRIOR_START as PRIOR_SINCE  # noqa: E402

SEP, REC = "\x1f", "\x1e"
NOREPLY = re.compile(r"^(?:\d+\+)?(?P<login>[^@]+)@users\.noreply\.github\.com$", re.I)


def person_id(name, email):
    """MUST MATCH for every alias of one person: see the module docstring."""
    email = (email or "").strip().lower()
    m = NOREPLY.match(email)
    if m:
        return m.group("login").lower()
    return email if email else f"name:{name}"


def git(godot, *args):
    return subprocess.run(["git", "-C", godot, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    godot = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "godot"))
    out = os.path.join(here, "..", "data", "git")
    os.makedirs(out, exist_ok=True)
    head = git(godot, "rev-parse", "HEAD").strip()

    # Only the master history at HEAD: --all would add the stable branches, whose cherry-picks
    # duplicate master commits by the same authors.
    # Pass 1 (all history, no stats, fast): all-time first commit per person.
    # The same pass keeps the PRIOR year's non-merge commits, needed to detect dormant contributors.
    first, prior = {}, []
    for rec in git(godot, "log", "HEAD", f"--format={REC}%H{SEP}%aN{SEP}%aE{SEP}%aI{SEP}%P").split(REC)[1:]:
        h, aN, aE, adate, parents = rec.strip("\n").split(SEP)
        aN = unicodedata.normalize("NFC", aN)
        when, pid = datetime.fromisoformat(adate), person_id(aN, aE)
        if pid not in first or when < first[pid][0]:
            first[pid] = (when, aN, aE)
        if PRIOR_SINCE <= when.astimezone(timezone.utc) < SINCE and len(parents.split()) == 1:
            prior.append({"hash": h, "author_date": when.astimezone(timezone.utc).isoformat(), "name": aN,
                          "email": aE, "person_id": pid})

    # Pass 2 (with --shortstat): commits COMMITTED since the window start. Every commit AUTHORED in
    # the window is committed on or after its author date, so this is a superset; filter on author date.
    fmt = SEP.join(["%H", "%aI", "%an", "%ae", "%aN", "%aE", "%cN", "%P", "%s",
                    "%(trailers:key=Co-authored-by,valueonly,separator=;)"])
    log = git(godot, "log", "HEAD", f"--since={SINCE.isoformat()}", f"--format={REC}{fmt}", "--shortstat")
    rows = []
    for block in log.split(REC)[1:]:
        lines = block.strip("\n").split("\n")
        h, adate, an, ae, aN, aE, cN, parents, subject, coauth = lines[0].split(SEP)
        # Godot's .mailmap stores some names in decomposed Unicode (NFD), e.g. "Pāvels", so the same
        # visible name can be two different strings. Mailmapped names and committers are normalised
        # to NFC; raw names are kept as-is because the difference is itself an alias finding.
        aN, cN = unicodedata.normalize("NFC", aN), unicodedata.normalize("NFC", cN)
        stat = next((l for l in lines[1:] if "changed" in l), "")
        files = int(stat.strip().split(" ")[0]) if stat else 0
        when = datetime.fromisoformat(adate)
        if SINCE <= when.astimezone(timezone.utc) < UNTIL:
            rows.append({"hash": h, "author_date": when.astimezone(timezone.utc).isoformat(),
                         "raw_name": an, "raw_email": ae, "name": aN, "email": aE, "person_id": person_id(aN, aE),
                         "committer": cN, "is_merge": int(len(parents.split()) > 1), "files_changed": files,
                         "subject": subject, "co_authors": coauth})

    with open(os.path.join(out, "commits_window.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, "commits_prior_year.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["hash", "author_date", "name", "email", "person_id"])
        w.writeheader()
        w.writerows(prior)
    with open(os.path.join(out, "first_commit.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["person_id", "name", "email", "first_commit_utc"])
        for pid, (d, n, e) in sorted(first.items(), key=lambda kv: kv[1][0]):
            w.writerow([pid, n, e, d.astimezone(timezone.utc).isoformat()])
    merges = sum(r["is_merge"] for r in rows)
    print(f"[git_activity] HEAD {head}; window {SINCE.isoformat()}..{UNTIL.isoformat()} (author date, end excluded)")
    print(f"[git_activity] {len(rows)} commits in window ({merges} merges, {len(rows) - merges} non-merge); "
          f"{len(first)} all-time people -> {out}")


if __name__ == "__main__":
    main()
