"""Central configuration. Everything you might want to tweak lives here."""
import os
import sys
from datetime import timezone

UTC = timezone.utc

OWNER = "godotengine"
REPO = "godot"
FULL = f"{OWNER}/{REPO}"

# Data comes from our health pipeline (Scripts/data/), not the API; see README.
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA_DIR = os.environ.get("METRICS_DATA", os.path.join(SCRIPTS_DIR, "data"))

# Sample window, shared with the health scripts (Scripts/window.py): 16 Sep 2025 (inclusive) to
# 16 Sep 2026 (exclusive) = exactly 12 months. Commits are dated by AUTHOR date.
sys.path.insert(0, SCRIPTS_DIR)
from window import START as WINDOW_START, END as WINDOW_END, PRIOR_START, GODOT_SNAPSHOT  # noqa: E402,F401

# Contributor categories (key, newcomer, established, dormant, left) come from our
# health/categorise.py (data/categories/people.csv), so both report sections count the same people.
MILESTONE_TOP_FRACTION = 0.10 # "key contributors" of a closed milestone = top 10 % by merged PRs

OUT_DIR = os.environ.get("METRICS_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))

# Accounts to treat as bots in addition to GitHub's own Bot accounts and anything ending in "[bot]".
EXTRA_BOTS = {"github-actions", "dependabot", "godot-bot"}
