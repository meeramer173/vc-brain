"""Append-only signal ledger.

Every fact the system knows is an event: (entity, source, type, timestamp,
payload). Scores are folds over events with an `as_of` cutoff, which gives
trend lines and time-travel for free and makes every number auditable down
to the events that produced it.
"""

import json
import sqlite3
from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def record(
    conn: sqlite3.Connection,
    entity_id: int,
    source: str,
    event_type: str,
    event_ts: str,
    dedup_key: str,
    payload: dict,
) -> int | None:
    """Append one event. Returns event id, or None if dedup_key already seen."""
    try:
        cur = conn.execute(
            "INSERT INTO events (entity_id, source, event_type, event_ts, dedup_key, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, source, event_type, event_ts, dedup_key, json.dumps(payload)),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # already ingested — idempotent by design


def cluster_ids(conn: sqlite3.Connection, entity_id: int) -> list[int]:
    """The entity plus every entity that was merged into it (transitively)."""
    rows = conn.execute(
        """
        WITH RECURSIVE cluster(id) AS (
            SELECT ?
            UNION
            SELECT e.id FROM entities e JOIN cluster c ON e.merged_into = c.id
        )
        SELECT id FROM cluster
        """,
        (entity_id,),
    ).fetchall()
    return [r["id"] for r in rows]


def events_for(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """All events for an entity's merge cluster, oldest first.

    `as_of` is the time-travel knob: pass an ISO timestamp and you see
    exactly what the system knew at that moment (used by trends and the
    backtest harness).
    """
    ids = cluster_ids(conn, entity_id)
    q = f"SELECT * FROM events WHERE entity_id IN ({','.join('?' * len(ids))})"
    params: list = list(ids)
    if as_of:
        q += " AND event_ts <= ?"
        params.append(as_of)
    if source:
        q += " AND source = ?"
        params.append(source)
    q += " ORDER BY event_ts ASC"
    rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def stats(conn: sqlite3.Connection) -> dict:
    n_entities = conn.execute(
        "SELECT COUNT(*) c FROM entities WHERE merged_into IS NULL"
    ).fetchone()["c"]
    n_merged = conn.execute(
        "SELECT COUNT(*) c FROM entities WHERE merged_into IS NOT NULL"
    ).fetchone()["c"]
    n_events = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    by_source = {
        r["source"]: r["c"]
        for r in conn.execute(
            "SELECT source, COUNT(*) c FROM events GROUP BY source ORDER BY c DESC"
        )
    }
    return {
        "entities": n_entities,
        "merged_away": n_merged,
        "events": n_events,
        "events_by_source": by_source,
    }
