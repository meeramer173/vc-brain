"""Devpost hackathon winners via the HuggingFace dataset mirror
(alvanlii/devpost-hackathon-projects, ~262k projects, no auth).

Devpost itself bot-walls scrapers (202 challenge / 403), so live galleries
would need a real browser — this mirror gives us the historical winner
corpus instead. A hackathon win is exactly the brief's cold-start signal
("a hackathon win, a paper worth a phone call").

Honesty note: the dataset carries no event dates. We stamp a conservative
sentinel date and flag `date_unknown` in the payload, so wins contribute to
breadth/validation but never fake recency in momentum.
"""

import ast
import time

import httpx

from .base import RawSignal

ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "alvanlii/devpost-hackathon-projects"
PAGE = 100
PAGE_SLEEP = 1.0   # anonymous HF datasets-server rate limit is tight
RETRIES = 3
SENTINEL_TS = "2023-01-01T00:00:00Z"  # dataset snapshot era; predates any live data


def _parse_list(raw: str) -> list[str]:
    try:
        val = ast.literal_eval(raw)
        return [str(v).strip() for v in val if str(v).strip()] if isinstance(val, list) else []
    except (ValueError, SyntaxError):
        return []


def fetch_winners(max_rows: int = 10000, offset: int = 0) -> list[RawSignal]:
    """Scan `max_rows` of the dataset, keep projects that won a prize,
    emit one hackathon_win signal per team member."""
    signals: list[RawSignal] = []
    with httpx.Client(timeout=60) as client:
        for off in range(offset, offset + max_rows, PAGE):
            resp = None
            for attempt in range(RETRIES):
                resp = client.get(
                    ROWS_API,
                    params={
                        "dataset": DATASET,
                        "config": "default",
                        "split": "train",
                        "offset": off,
                        "length": PAGE,
                    },
                )
                if resp.status_code == 429 and attempt < RETRIES - 1:
                    time.sleep(int(resp.headers.get("retry-after", 10)))
                    continue
                break
            if resp.status_code == 429:
                # persistent throttle: keep what we have, resume later via --offset
                print(f"devpost: rate-limited at offset {off}; "
                      f"resume with --offset {off}")
                break
            resp.raise_for_status()
            time.sleep(PAGE_SLEEP)
            rows = resp.json().get("rows", [])
            if not rows:
                break
            for r in rows:
                row = r["row"]
                prizes = _parse_list(row.get("prize") or "[]")
                if not prizes:
                    continue
                members = _parse_list(row.get("team_members") or "[]")
                slug = (row.get("project_link") or "").rstrip("/").rsplit("/", 1)[-1]
                if not slug:
                    continue
                for i, member in enumerate(members):
                    signals.append(
                        RawSignal(
                            kind="person",
                            name=member,
                            # display name, lowercased; spaces prevent false
                            # cross-platform username merges by construction
                            handles={"devpost_name": member.lower()},
                            event_type="hackathon_win",
                            event_ts=SENTINEL_TS,
                            external_id=f"win:{slug}:{i}",
                            payload={
                                "project": row.get("title"),
                                "prizes": prizes[:5],
                                "tags": _parse_list(row.get("tags") or "[]")[:8],
                                "url": row.get("project_link"),
                                "team_size": len(members),
                                "date_unknown": True,
                            },
                        )
                    )
    return signals
