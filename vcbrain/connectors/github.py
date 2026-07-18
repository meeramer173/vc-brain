"""Recently created repos gaining stars, via the GitHub search API.

Works unauthenticated (10 search req/min, 60 core req/hr); export
GITHUB_TOKEN to lift limits to 5000/hr. A young repo accumulating stars is
a shipping-velocity signal on its owner.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

from .base import RawSignal

SEARCH = "https://api.github.com/search/repositories"


def _headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "vcbrain-hackathon",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_new_starred_repos(
    days: int = 14, min_stars: int = 10, per_page: int = 100
) -> list[RawSignal]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            SEARCH,
            headers=_headers(),
            params={
                "q": f"created:>{since} stars:>{min_stars}",
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

    signals: list[RawSignal] = []
    for repo in items:
        owner = repo.get("owner") or {}
        if owner.get("type") != "User":  # orgs are companies; keep v0 person-focused
            continue
        signals.append(
            RawSignal(
                kind="person",
                name=owner["login"],
                handles={
                    "github": owner["login"],
                    "urls": [owner.get("html_url", "")],
                },
                event_type="repo_launch",
                event_ts=repo["created_at"],
                external_id=f"repo:{repo['id']}",
                payload={
                    "repo": repo["full_name"],
                    "description": (repo.get("description") or "")[:300],
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language"),
                    "url": repo.get("html_url"),
                },
            )
        )
    return signals
