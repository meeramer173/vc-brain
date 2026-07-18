"""Backtest harness — does the Founder Score, computed only from what was
knowable at time T, predict what founders did afterwards?

Method (Area of Research 3 from the brief, made concrete):
  1. Cohort = authors of Show HN posts in a historical window ending at T.
  2. For each author, fetch their FULL pre-T Show HN history (footprint
     frozen at T — no information from the future leaks into the score).
  3. Ingest into a separate backtest ledger; score everyone as_of T.
  4. Outcome = did they ship a post-T Show HN that reached >= hit_points?
  5. Report precision@top-decile vs cohort base rate -> lift, plus the
     failure cases, because an honest backtest reports its misses.

Run:
    uv run python -m vcbrain.backtest --start 2021-05-01 --end 2021-05-31 --limit 120
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import db, score
from .connectors import base as connector_base
from .connectors.base import RawSignal
from .connectors.hackernews import fetch_show_hn

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
SLEEP = 0.15  # stay politely under Algolia's 10k req/hr
BACKTEST_DB = Path(__file__).resolve().parent.parent / "vcbrain-backtest.db"


def _author_show_hn(
    client: httpx.Client, username: str, before: int | None = None, after: int | None = None
) -> list[dict]:
    filters = []
    if before is not None:
        filters.append(f"created_at_i<{before}")
    if after is not None:
        filters.append(f"created_at_i>{after}")
    resp = client.get(
        ALGOLIA,
        params={
            "tags": f"show_hn,author_{username}",
            "numericFilters": ",".join(filters),
            "hitsPerPage": 100,
        },
    )
    resp.raise_for_status()
    time.sleep(SLEEP)
    return resp.json().get("hits", [])


def run_backtest(
    start: str, end: str, limit: int, hit_points: int, fresh: bool = True
) -> dict:
    t_start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    t_end = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    t_iso = t_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    if fresh and BACKTEST_DB.exists():
        BACKTEST_DB.unlink()
    conn = db.connect(BACKTEST_DB)

    # 1. Cohort: Show HN authors in the window (footprint frozen at t_end).
    window_days = (t_end - t_start).days
    cohort_signals = fetch_show_hn(days=window_days, until=t_end)
    authors: list[str] = []
    for s in cohort_signals:
        if s.name not in authors:
            authors.append(s.name)
    authors = authors[:limit]
    cohort_signals = [s for s in cohort_signals if s.name in set(authors)]
    print(f"cohort: {len(authors)} authors, {len(cohort_signals)} launches "
          f"in {start}..{end}")

    # 2. Pre-T history + post-T outcomes per author.
    pre_signals = []
    outcomes: dict[str, dict] = {}
    with httpx.Client(timeout=30) as client:
        for i, author in enumerate(authors):
            pre = _author_show_hn(client, author, before=int(t_start.timestamp()))
            for hit in pre:
                ts = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
                cohort_signals.append(
                    RawSignal(
                        kind="person",
                        name=author,
                        handles={"hn": author},
                        event_type="launch",
                        event_ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        external_id=f"show:{hit['objectID']}",
                        payload={
                            "title": hit.get("title"),
                            "points": hit.get("points") or 0,
                            "num_comments": hit.get("num_comments") or 0,
                        },
                    )
                )
            post = _author_show_hn(client, author, after=int(t_end.timestamp()))
            best = max((h.get("points") or 0 for h in post), default=0)
            outcomes[author] = {
                "post_t_launches": len(post),
                "best_post_t_points": best,
                "hit": best >= hit_points,
            }
            if (i + 1) % 25 == 0:
                print(f"  fetched {i + 1}/{len(authors)} author histories")

    result = connector_base.ingest(conn, "hn", cohort_signals)
    print(f"ledger: {result['new_events']} events ingested")

    # 3. Score everyone as_of T — same code path as production, no leakage.
    ranked = score.rank_founders(conn, n=len(authors), as_of=t_iso)
    ranked = [(eid, name, b) for eid, name, b in ranked if name in outcomes]

    # 4. Evaluate.
    n = len(ranked)
    base_hits = sum(1 for _, name, _ in ranked if outcomes[name]["hit"])
    base_rate = base_hits / n if n else 0.0
    decile = max(1, n // 10)
    top = ranked[:decile]
    top_hits = sum(1 for _, name, _ in top if outcomes[name]["hit"])
    precision = top_hits / decile if decile else 0.0
    lift = (precision / base_rate) if base_rate > 0 else None

    hit_scores = [b.total for _, name, b in ranked if outcomes[name]["hit"]]
    miss_scores = [b.total for _, name, b in ranked if not outcomes[name]["hit"]]

    report = {
        "window": f"{start}..{end}",
        "as_of": t_iso,
        "hit_definition": f"post-T Show HN with >= {hit_points} points",
        "cohort_size": n,
        "base_rate": round(base_rate, 3),
        "top_decile_size": decile,
        "precision_at_top_decile": round(precision, 3),
        "lift": round(lift, 2) if lift else None,
        "mean_score_hits": round(sum(hit_scores) / len(hit_scores), 1) if hit_scores else None,
        "mean_score_misses": round(sum(miss_scores) / len(miss_scores), 1) if miss_scores else None,
        "top_decile": [
            {
                "name": name,
                "score_at_t": b.total,
                "outcome": outcomes[name],
            }
            for _, name, b in top
        ],
        "false_positives": [
            {"name": name, "score_at_t": b.total}
            for _, name, b in top
            if not outcomes[name]["hit"]
        ],
        "missed_hits_below_median": [
            {"name": name, "score_at_t": b.total, "best_post_t_points": outcomes[name]["best_post_t_points"]}
            for _, name, b in ranked[n // 2:]
            if outcomes[name]["hit"]
        ],
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser(prog="vcbrain.backtest")
    p.add_argument("--start", required=True, help="cohort window start YYYY-MM-DD")
    p.add_argument("--end", required=True, help="cohort window end YYYY-MM-DD = time T")
    p.add_argument("--limit", type=int, default=120, help="max authors")
    p.add_argument("--hit-points", type=int, default=100)
    p.add_argument("--out", default="backtest_report.json")
    args = p.parse_args()

    report = run_backtest(args.start, args.end, args.limit, args.hit_points)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("top_decile", "false_positives", "missed_hits_below_median")},
                     indent=2))
    print(f"full report -> {args.out}")


if __name__ == "__main__":
    main()
