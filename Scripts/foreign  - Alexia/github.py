"""Thin GitHub REST + GraphQL client with on-disk caching and rate-limit handling.

Every response is cached under CACHE_DIR keyed by request, so an interrupted run resumes
where it stopped and re-runs are instant. Delete the cache folder (or set NO_CACHE=1)
to refetch.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

import config
from util import log

API = "https://api.github.com"


class GitHub:
    def __init__(self):
        if not config.TOKEN:
            raise SystemExit(
                "Set GITHUB_TOKEN (or GH_TOKEN). GraphQL needs auth and the unauthenticated "
                "REST limit (60/h) is far too low for Godot."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "godot-community-metrics",
            "Authorization": f"Bearer {config.TOKEN}",
        })
        self.cache_dir = Path(config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = not os.environ.get("NO_CACHE")
        self.calls = 0

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _key(*parts):
        return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

    def _cached(self, key, fetch):
        path = self.cache_dir / f"{key}.json"
        if self.use_cache and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        value = fetch()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value), encoding="utf-8")
        tmp.replace(path)
        return value

    # ------------------------------------------------------------------ transport
    @staticmethod
    def _sleep(seconds, why):
        seconds = max(1, int(seconds))
        log(f"sleeping {seconds}s ({why})")
        time.sleep(seconds)

    def _send(self, method, url, **kw):
        for attempt in range(10):
            try:
                r = self.session.request(method, url, timeout=120, **kw)
            except requests.RequestException as e:
                self._sleep(min(2 ** attempt, 120), f"network error: {e}")
                continue
            self.calls += 1

            if r.status_code in (403, 429):
                retry_after = r.headers.get("Retry-After")
                remaining = r.headers.get("X-RateLimit-Remaining")
                if retry_after:
                    self._sleep(int(retry_after) + 1, "secondary rate limit")
                    continue
                if remaining == "0":
                    reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                    self._sleep(reset - time.time() + 2, "primary rate limit exhausted")
                    continue
                if "rate limit" in r.text.lower():
                    self._sleep(60 * (attempt + 1), "secondary rate limit")
                    continue
            if r.status_code in (500, 502, 503, 504):
                self._sleep(min(2 ** attempt * 2, 120), f"HTTP {r.status_code}")
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"{method} {url} -> HTTP {r.status_code}: {r.text[:500]}")

            remaining = r.headers.get("X-RateLimit-Remaining")
            if remaining is not None and int(remaining) < 10:
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                self._sleep(reset - time.time() + 2, "rate limit nearly exhausted")
            return r
        raise RuntimeError(f"giving up on {method} {url}")

    # ------------------------------------------------------------------ REST
    def get(self, path, params=None):
        url = path if path.startswith("http") else API + path
        key = self._key("GET", url, params)
        return self._cached(key, lambda: self._send("GET", url, params=params).json())

    def paginate(self, path, params=None, items_key=None):
        """Yield items across all pages, following Link: rel=next."""
        url = API + path
        params = dict(params or {})
        params.setdefault("per_page", 100)
        while url:
            key = self._key("PAGE", url, params)

            def fetch(url=url, params=params):
                r = self._send("GET", url, params=params)
                return {"data": r.json(), "next": r.links.get("next", {}).get("url")}

            page = self._cached(key, fetch)
            data = page["data"]
            yield from (data[items_key] if items_key else data)
            url, params = page["next"], None  # the next URL already carries the query string

    # ------------------------------------------------------------------ GraphQL
    def graphql(self, query, variables=None):
        variables = variables or {}
        key = self._key("GQL", query, variables)

        def fetch():
            for attempt in range(6):
                r = self._send("POST", API + "/graphql", json={"query": query, "variables": variables})
                body = r.json()
                errors = body.get("errors")
                if errors:
                    if any(e.get("type") == "RATE_LIMITED" for e in errors):
                        self._sleep(60 * (attempt + 1), "GraphQL rate limit")
                        continue
                    if body.get("data") is None:
                        raise RuntimeError(f"GraphQL error: {errors}")
                    log(f"GraphQL partial errors (continuing): {errors[:2]}")
                return body["data"]
            raise RuntimeError("GraphQL: giving up after rate-limit retries")

        return self._cached(key, fetch)

    def rate_limit(self):
        return self._send("GET", API + "/rate_limit").json()["resources"]
