"""YC company directory via the yc-oss static JSON mirror (no auth,
refreshed daily from YC's own Algolia index).

An accelerator batch is a strong company-level signal; it also validates
founders once entity resolution links them.
"""

import re
from datetime import datetime, timezone

import httpx

from .base import RawSignal

ALL_COMPANIES = "https://yc-oss.github.io/api/companies/all.json"

_SEASON_MONTH = {"winter": "01", "spring": "04", "summer": "06", "fall": "09"}
_SHORT = {"w": "01", "x": "04", "s": "06", "f": "09"}


def batch_to_date(batch: str) -> str | None:
    """'Winter 2024' / 'W24' style batch labels → approximate ISO date."""
    if not batch:
        return None
    m = re.match(r"(winter|spring|summer|fall)\s+(\d{4})", batch.strip(), re.I)
    if m:
        return f"{m.group(2)}-{_SEASON_MONTH[m.group(1).lower()]}-01T00:00:00Z"
    m = re.match(r"([wxsf])(\d{2})$", batch.strip(), re.I)
    if m:
        return f"20{m.group(2)}-{_SHORT[m.group(1).lower()]}-01T00:00:00Z"
    return None


def fetch_companies(since_year: int = 2024) -> list[RawSignal]:
    with httpx.Client(timeout=60) as client:
        resp = client.get(ALL_COMPANIES, follow_redirects=True)
        resp.raise_for_status()
        companies = resp.json()

    signals: list[RawSignal] = []
    for c in companies:
        ts = batch_to_date(c.get("batch", ""))
        if ts is None:
            continue
        if int(ts[:4]) < since_year:
            continue
        website = (c.get("website") or "").strip()
        handles: dict = {"yc_slug": c.get("slug") or str(c.get("id"))}
        if website:
            handles["urls"] = [website]
        signals.append(
            RawSignal(
                kind="company",
                name=c.get("name") or c.get("slug", "unknown"),
                handles=handles,
                event_type="accelerator_batch",
                event_ts=ts,
                external_id=f"company:{c.get('id') or c.get('slug')}",
                payload={
                    "batch": c.get("batch"),
                    "one_liner": c.get("one_liner"),
                    "website": website,
                    "team_size": c.get("team_size"),
                    "status": c.get("status"),
                    "tags": (c.get("tags") or [])[:8],
                    "yc_url": f"https://www.ycombinator.com/companies/{c.get('slug')}",
                },
            )
        )
    return signals
