"""LinkedIn founder discovery via Tavily's search index.

LinkedIn has no public search/discovery API (the brokers that offered one,
e.g. Proxycurl, were sued/shut down), so we can't enumerate profiles the
way the GitHub connector hits the GitHub search API. Instead we run a set
of founder-shaped queries through Tavily restricted to linkedin.com and
keep the real `/in/` profile pages — public, indexed, no scraping, no login.

Positioning: this surfaces *already-visible* people (a who's-who), so it's
a coverage / credibility source, not the cold-start shipping signal that
GitHub/HN give. Each hit becomes one founder entity keyed on the LinkedIn
handle, so it dedups and can later merge with the same person from another
source. The seed event is `profile_listed` — deliberately NOT a SHIP_TYPE,
so a bare profile never fabricates shipping cadence; a freshly discovered
founder honestly starts thin (breadth only) until real signal corroborates.
"""

import re
import time

import httpx

from .. import ledger
from . import tavily
from .base import RawSignal

# Founder-shaped queries across sectors — restricted to linkedin.com. Each
# yields ~1 clean /in/ profile, so ~15 queries -> ~15-20 distinct founders.
DEFAULT_QUERIES = [
    "AI startup founder", "fintech startup co-founder", "SaaS startup CEO founder",
    "biotech startup founder", "developer tools startup founder",
    "climate tech startup founder", "healthtech startup co-founder",
    "cybersecurity startup founder", "robotics startup CEO",
    "edtech startup founder", "data infrastructure startup founder",
    "AI agents startup founder", "machine learning startup co-founder",
    "fintech founder London", "YC startup founder",
]

_SYMBOLS = re.compile(r"[^\w\s.\-'&]", re.UNICODE)  # strip emoji/symbols from names


def _clean_name(title: str) -> str | None:
    """Extract a person name from a LinkedIn page title
    ('Name - Headline | LinkedIn') and reject truncated/placeholder names."""
    name = title.split("|")[0].split(" - ")[0].strip()
    name = _SYMBOLS.sub("", name).strip()
    if len(name.split()) < 2:               # need a real First Last
        return None
    if re.search(r"\b[A-Z]\.?$", name):     # truncated surname ("Ahmed A.")
        return None
    return name


def _handle_from_url(url: str) -> str | None:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else None


def fetch_founders(
    queries: list[str] | None = None,
    limit: int = 15,
    min_relevance: float = 0.3,
    pause_s: float = 0.4,
) -> list[RawSignal]:
    """Discover founders from public LinkedIn `/in/` profiles via Tavily.
    Returns up to `limit` deduped founder RawSignals (one per handle). One
    query failing is skipped, not fatal."""
    key = tavily._api_key()
    headers = {"Authorization": f"Bearer {key}"}
    queries = queries or DEFAULT_QUERIES
    seen: dict[str, RawSignal] = {}  # linkedin handle -> signal (dedup)

    with httpx.Client(timeout=30) as client:
        for q in queries:
            if len(seen) >= limit:
                break
            body = {
                "query": q, "search_depth": "advanced", "topic": "general",
                "max_results": 20, "include_raw_content": False,
                "include_answer": False, "include_domains": ["linkedin.com"],
            }
            try:
                resp = client.post(tavily.SEARCH_URL, headers=headers, json=body)
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except (httpx.HTTPError, ValueError):
                continue
            finally:
                time.sleep(pause_s)

            for r in results:
                url = r.get("url") or ""
                if "linkedin.com/in/" not in url.lower():
                    continue
                if (r.get("score") or 0.0) < min_relevance:
                    continue
                handle = _handle_from_url(url)
                name = _clean_name(r.get("title") or "")
                if not handle or not name or handle in seen:
                    continue
                headline = (r.get("title") or "").split("|")[0].strip()
                seen[handle] = RawSignal(
                    kind="person",
                    name=name,
                    handles={"linkedin": handle, "urls": [url]},
                    event_type="profile_listed",
                    event_ts=ledger.utcnow_iso(),
                    external_id=f"in/{handle}",
                    payload={
                        "title": headline,
                        "url": url,
                        "source_query": q,
                        "relevance": round(float(r.get("score") or 0.0), 3),
                    },
                )
                if len(seen) >= limit:
                    break
    return list(seen.values())
