"""The analysis window, in one place for every script (ours and Alexia's).

16 Sep 2025 00:00 UTC (included) to 16 Sep 2026 00:00 UTC (EXCLUDED): exactly 365 days, 12 months.
Commits are placed by AUTHOR date (when the work was written); GitHub events by their own timestamp.
The prior year (for "established" contributors) is the 365 days before START.

Every script tests  START <= t < END.  Never <= END: the window used to run to 16 Sep 23:59:59,
which made it 366 days and put one extra day into every count.
"""
from datetime import datetime, timezone

START = datetime(2025, 9, 16, tzinfo=timezone.utc)
END = datetime(2026, 9, 16, tzinfo=timezone.utc)
PRIOR_START = datetime(2024, 9, 16, tzinfo=timezone.utc)

# The same instants as GitHub-style strings, for comparing against API timestamps ("...Z").
START_ISO, END_ISO, PRIOR_START_ISO = (d.strftime("%Y-%m-%dT%H:%M:%SZ") for d in (START, END, PRIOR_START))

GODOT_SNAPSHOT = "57277407e77e61b161f35dbd7aeb510f7a9e26a6"
