"""Web-signal enrichment via the Tavily search API.

Unlike the discovery connectors (github, hn, yc, arxiv, devpost) which
surface *new* entities, Tavily enriches founders already in the ledger: for
each target it runs a web search and records the independent press / web
coverage it finds as `web_mention` events.

Why this lifts the score honestly:
- Independent web coverage is exactly a *breadth* signal ("distinct
  independent sources vouching for them"). All Tavily events share
  source="tavily", so a founder gains at most +1 source of breadth no
  matter how many articles surface — it cannot be inflated.
- `web_mention` is deliberately NOT a SHIP_TYPE, so press coverage never
  fabricates shipping cadence or momentum (the heavy 60% of the score).

No LLM here. The connector stores raw hits (title, snippet, url, Tavily
relevance) so the ledger stays fact-only and the score stays
deterministic; any synthesis over these events happens later in the
intelligence layer.

Auth: set TAVILY_API_KEY (a Bearer token, tvly-...). Free tier = 1000
credits/month; each `advanced` search costs 2 credits, `basic` 1. One
search runs per target, so a run over N founders costs ~2N credits.
"""

import os
import time
from typing import Iterable
from urllib.parse import urlparse

import httpx

from .. import ledger
from ..entities import normalize_name
from .base import RawSignal

SEARCH_URL = "https://api.tavily.com/search"

# Convenience preset for a LinkedIn/X-focused pass. Public/indexed content
# only — these sites are login-walled, so a broad (undomained) search
# usually surfaces richer signal; use this only when you specifically want
# the social-profile flavor.
SOCIAL_DOMAINS = ["linkedin.com", "x.com", "twitter.com"]


def _api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise SystemExit(
            "TAVILY_API_KEY is not set — export it (see .env.example) "
            "before ingesting the tavily source."
        )
    return key


def _query_for(name: str) -> str:
    """Name-centric query. The quoted name anchors the search on the person;
    role terms bias toward their startup/founder footprint. Deliberately no
    funding/AI keyword soup — that pulled generic listicles that matched the
    topic but not the person, tanking precision."""
    return f'"{name}" (founder OR co-founder OR CEO OR startup)'


def _mentions(name: str, *texts: str | None) -> bool:
    """Deterministic disambiguation guard: keep a result only if the
    founder's name actually appears in it. Kills wrong-person hits that
    Tavily ranks on topical overlap, and lets the connector honestly return
    nothing when a founder has no distinct coverage rather than attaching
    someone else's press."""
    key = normalize_name(name)
    if not key:
        return False
    blob = normalize_name(" ".join(t or "" for t in texts))
    return key in blob


def fetch_web_signals(
    targets: Iterable[dict],
    per_entity: int = 5,
    min_relevance: float = 0.2,
    search_depth: str = "advanced",
    topic: str = "general",
    include_domains: list[str] | None = None,
    pause_s: float = 0.4,
) -> list[RawSignal]:
    """Enrich each target with independent web coverage.

    `targets` is an iterable of {"name": str, "handles": dict} — typically
    the most-active founders in the ledger. One `web_mention` RawSignal is
    emitted per relevant result. The dedup key is (article url, founder),
    so re-runs are idempotent and never double-count the same article.

    A single lookup failing (network / rate limit) is skipped, not fatal —
    one founder must not sink the whole batch.
    """
    key = _api_key()
    headers = {"Authorization": f"Bearer {key}"}
    signals: list[RawSignal] = []

    with httpx.Client(timeout=30) as client:
        for t in targets:
            name = t["name"]
            handles = t.get("handles") or {}
            body = {
                "query": _query_for(name),
                "search_depth": search_depth,
                "topic": topic,
                "max_results": per_entity,
                "include_raw_content": False,
                "include_answer": False,
            }
            if include_domains:
                body["include_domains"] = include_domains

            try:
                resp = client.post(SEARCH_URL, headers=headers, json=body)
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except (httpx.HTTPError, ValueError):
                continue
            finally:
                time.sleep(pause_s)  # be gentle with the free-tier rate limit

            for r in results:
                url = r.get("url")
                relevance = r.get("score") or 0.0
                if not url or relevance < min_relevance:
                    continue
                if not _mentions(name, r.get("title"), r.get("content")):
                    continue  # article doesn't name this founder — skip
                netloc = urlparse(url).netloc.lower()
                domain = netloc[4:] if netloc.startswith("www.") else netloc
                # Prefer the article's real publish date so backtest
                # time-travel (as_of) sees it in the right window; fall
                # back to ingest time when Tavily doesn't supply one.
                event_ts = r.get("published_date") or ledger.utcnow_iso()
                signals.append(
                    RawSignal(
                        kind="person",
                        name=name,
                        # The entity's own handles, straight from the ledger,
                        # so ingest() re-attaches to it. The article URL stays
                        # in payload — never here.
                        handles=dict(handles),
                        event_type="web_mention",
                        event_ts=event_ts,
                        external_id=f"{url}::{name}",
                        payload={
                            "title": r.get("title"),
                            "snippet": (r.get("content") or "")[:500],
                            "url": url,
                            "domain": domain,
                            "relevance": round(float(relevance), 3),
                            "query": body["query"],
                        },
                    )
                )
    return signals


PROFILE_DOMAINS = ["linkedin.com", "x.com", "twitter.com"]


def _x_kind(low: str) -> str | None:
    """Classify an x.com/twitter.com URL: 'profile' (bare @handle), 'post'
    (a specific tweet), or None (non-profile page like /home, /search)."""
    for host in ("x.com/", "twitter.com/"):
        i = low.find(host)
        if i == -1:
            continue
        seg = [s for s in low[i + len(host):].split("/") if s]
        if not seg:
            return None
        if "status" in seg:
            return "post"
        if len(seg) == 1 and seg[0] not in {
            "i", "home", "search", "explore", "hashtag", "notifications",
            "messages", "settings",
        }:
            return "profile"
    return None


def find_profiles(name: str, min_relevance: float = 0.3) -> dict:
    """Resolve a founder's public LinkedIn / X presence via Tavily's index
    (no scraping, no login). Name-guarded, so it returns the right person or
    nothing — never a stranger. Prefers the person's OWN profile; falls back
    to a public mention, labeled honestly (profile vs mention/post). Powers
    the "does this founder actually exist" links on the founder page.

    Returns {"linkedin": {"url","type"}|None, "x": {"url","type"}|None}.
    """
    key = _api_key()
    body = {
        "query": f'"{name}"',
        "search_depth": "advanced",
        "topic": "general",
        "max_results": 10,
        "include_raw_content": False,
        "include_answer": False,
        "include_domains": PROFILE_DOMAINS,
    }
    try:
        resp = httpx.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return {"linkedin": None, "x": None}

    # best (relevance, url) per bucket
    li_profile = li_mention = x_profile = x_post = (0.0, None)
    for r in results:
        url = r.get("url") or ""
        low = url.lower()
        rel = float(r.get("score") or 0.0)
        if rel < min_relevance or not _mentions(name, r.get("title"), r.get("content")):
            continue
        if "linkedin.com/in/" in low:  # the person's own profile
            if rel > li_profile[0]:
                li_profile = (rel, url)
        elif "linkedin.com/" in low:  # a post/article naming them
            if rel > li_mention[0]:
                li_mention = (rel, url)
        else:
            kind = _x_kind(low)
            if kind == "profile" and rel > x_profile[0]:
                x_profile = (rel, url)
            elif kind == "post" and rel > x_post[0]:
                x_post = (rel, url)

    def pick(primary, primary_type, fallback, fallback_type):
        if primary[1]:
            return {"url": primary[1], "type": primary_type}
        if fallback[1]:
            return {"url": fallback[1], "type": fallback_type}
        return None

    return {
        "linkedin": pick(li_profile, "profile", li_mention, "mention"),
        "x": pick(x_profile, "profile", x_post, "post"),
    }
