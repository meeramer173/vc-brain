"""Recent AI papers via the arXiv Atom API (no key; courtesy limit
~1 request / 3 seconds — we make a single request per ingest run).

A recent paper is the "paper worth a phone call" signal from the brief.
v0 credits the first author, where founder-potential signal is strongest.
"""

import time
import xml.etree.ElementTree as ET

import httpx

from .base import RawSignal

API = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}
RETRIES = 3


def fetch_recent_papers(
    category: str = "cs.AI", max_results: int = 100
) -> list[RawSignal]:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for attempt in range(RETRIES):
            resp = client.get(
                API,
                params={
                    "search_query": f"cat:{category}",
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "start": 0,
                    "max_results": max_results,
                },
            )
            if resp.status_code == 503 and attempt < RETRIES - 1:
                # arXiv throttles with 503 + Retry-After; honor it and retry
                time.sleep(int(resp.headers.get("retry-after", 5)))
                continue
            resp.raise_for_status()
            break
        root = ET.fromstring(resp.text)

    signals: list[RawSignal] = []
    for entry in root.findall("atom:entry", NS):
        arxiv_id = entry.find("atom:id", NS).text.rsplit("/", 1)[-1]
        title = " ".join(entry.find("atom:title", NS).text.split())
        published = entry.find("atom:published", NS).text  # already ISO-8601 Z
        authors = [
            a.find("atom:name", NS).text for a in entry.findall("atom:author", NS)
        ]
        if not authors:
            continue
        first = authors[0]
        signals.append(
            RawSignal(
                kind="person",
                name=first,
                handles={"arxiv_name": first.lower()},
                event_type="paper",
                event_ts=published,
                external_id=f"paper:{arxiv_id}",
                payload={
                    "title": title,
                    "category": category,
                    "n_authors": len(authors),
                    "co_authors": authors[1:6],
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                },
            )
        )
    return signals
