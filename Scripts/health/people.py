"""Canonical person ids: git_activity.py's person_id, with the same-person aliases login_map.py found.

git_activity.py can only merge what the commits themselves show (.mailmap, same e-mail, same
noreply login). login_map.py runs next and finds more: two person_ids whose merged PRs ran under
one GitHub login AND who use the same name are one person with an e-mail .mailmap doesn't know.
Every script after login_map.py goes through canonical() so they all count the same people.
"""
import csv
import os

ALIAS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "categories", "person_alias.csv")
_aliases = None


def aliases():
    """{person_id: canonical person_id}; empty before login_map.py has run."""
    global _aliases
    if _aliases is None:
        _aliases = {}
        if os.path.exists(ALIAS_CSV):
            with open(ALIAS_CSV, encoding="utf-8") as f:
                _aliases = {r["person_id"]: r["canonical"] for r in csv.DictReader(f)}
    return _aliases


def canonical(person_id):
    return aliases().get(person_id, person_id)
