"""Small helpers: dates, months, percentiles, CSV output, logging."""
import csv
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import config

UTC = timezone.utc
_t0 = time.time()


def log(msg):
    print(f"[{time.time() - _t0:7.1f}s] {msg}", file=sys.stderr, flush=True)


def iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def search_range(start, end):
    """Inclusive range string for GitHub search syntax from a [start, end) interval."""
    return f"{iso(start)}..{iso(end - timedelta(seconds=1))}"


def in_window(dt, start=None, end=None):
    start = start or config.WINDOW_START
    end = end or config.WINDOW_END
    return dt is not None and start <= dt < end


def month_label(dt):
    return dt.astimezone(UTC).strftime("%Y-%m")


def calendar_months(start=None, end=None):
    """[(label, start, end)] for every calendar month touching [start, end), clipped to it."""
    start = start or config.WINDOW_START
    end = end or config.WINDOW_END
    out = []
    cur = datetime(start.year, start.month, 1, tzinfo=UTC)
    while cur < end:
        nxt = datetime(cur.year + cur.month // 12, cur.month % 12 + 1, 1, tzinfo=UTC)
        out.append((cur.strftime("%Y-%m"), max(cur, start), min(nxt, end)))
        cur = nxt
    return out


def relative_month(dt, start):
    """Index of the 'window month' dt falls into, where month 0 starts at `start` (16th to 15th)."""
    m = (dt.year - start.year) * 12 + dt.month - start.month
    if (dt.day, dt.hour, dt.minute, dt.second) < (start.day, start.hour, start.minute, start.second):
        m -= 1
    return m


def percentile(values, p):
    """Linear-interpolation percentile (same as numpy's default)."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return v[f] + (v[c] - v[f]) * (k - f)


def median(values):
    return percentile(values, 50)


def rnd(x, n=2):
    return None if x is None else round(x, n)


def pct(num, den, n=1):
    return None if not den else round(100 * num / den, n)


def is_bot(login, typename=None):
    """GitHub's own account type first: Copilot's reviewer is a Bot account without "[bot]" in its login."""
    if typename == "Bot":
        return True
    if not login:
        return False
    l = login.lower()
    return l.endswith("[bot]") or l in config.EXTRA_BOTS


def write_csv(name, rows, fields=None):
    os.makedirs(config.OUT_DIR, exist_ok=True)
    path = os.path.join(config.OUT_DIR, name)
    rows = list(rows)
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(v) if isinstance(v, (list, set, tuple)) else v) for k, v in r.items()})
    log(f"wrote {path} ({len(rows)} rows)")
    return path
