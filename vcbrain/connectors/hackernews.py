"""Show HN launches via the Algolia HN API (no auth, 10k req/hr per IP).

A Show HN post is a launch signal: someone shipped something publicly.
Author profiles can be enriched via the official Firebase API.
"""

from datetime import datetime, timedelta, timezone

import httpx

from .base import RawSignal

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
FIREBASE_USER = "https://hacker-news.firebaseio.com/v0/user/{username}.json"
MAX_PAGES = 10


def fetch_show_hn(days: int = 7, until: datetime | None = None) -> list[RawSignal]:
    """Show HN posts from the trailing `days` window ending at `until`
    (default: now). Passing a historical `until` is how the backtest
    freezes a founder's footprint at time T."""
    until = until or datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    signals: list[RawSignal] = []
    with httpx.Client(timeout=30) as client:
        for page in range(MAX_PAGES):
            resp = client.get(
                ALGOLIA,
                params={
                    "tags": "show_hn",
                    "numericFilters": (
                        f"created_at_i>{int(since.timestamp())},"
                        f"created_at_i<{int(until.timestamp())}"
                    ),
                    "hitsPerPage": 100,
                    "page": page,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            for hit in data.get("hits", []):
                author = hit.get("author")
                if not author:
                    continue
                ts = datetime.fromtimestamp(
                    hit["created_at_i"], tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                signals.append(
                    RawSignal(
                        kind="person",
                        name=author,
                        handles={"hn": author},
                        event_type="launch",
                        event_ts=ts,
                        external_id=f"show:{hit['objectID']}",
                        payload={
                            "title": hit.get("title"),
                            "url": hit.get("url"),
                            "points": hit.get("points") or 0,
                            "num_comments": hit.get("num_comments") or 0,
                            "hn_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                        },
                    )
                )
            if page >= data.get("nbPages", 1) - 1:
                break
    return signals


def fetch_user_profile(username: str) -> RawSignal | None:
    """Karma + account age snapshot for one author (official API, no auth)."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(FIREBASE_USER.format(username=username))
        if resp.status_code != 200 or resp.json() is None:
            return None
        u = resp.json()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return RawSignal(
        kind="person",
        name=username,
        handles={"hn": username},
        event_type="profile_snapshot",
        event_ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        external_id=f"user:{username}:{today}",  # at most one snapshot per day
        payload={
            "karma": u.get("karma", 0),
            "account_created": datetime.fromtimestamp(
                u.get("created", 0), tz=timezone.utc
            ).strftime("%Y-%m-%d"),
            "about": (u.get("about") or "")[:500],
        },
    )
