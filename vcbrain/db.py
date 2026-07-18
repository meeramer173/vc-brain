"""SQLite backing store for the signal ledger.

Append-only by convention: nothing in this codebase updates or deletes
events. Entities gain handles via merges, but every merge is itself
recorded as an event, so history stays fully replayable.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "vcbrain.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'person',          -- person | company
    canonical_name TEXT NOT NULL,
    handles TEXT NOT NULL DEFAULT '{}',           -- JSON {source: handle, "urls": [...]}
    merged_into INTEGER REFERENCES entities(id),  -- set when absorbed by another entity
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    source TEXT NOT NULL,        -- hn | yc | github | arxiv | devpost | producthunt | inbound | system
    event_type TEXT NOT NULL,    -- launch | repo_launch | paper | hackathon_win | accelerator_batch | application | merge | ...
    event_ts TEXT NOT NULL,      -- ISO-8601 UTC: when the signal happened out in the world
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    dedup_key TEXT NOT NULL UNIQUE,  -- "<source>:<external id>" — re-ingestion is idempotent
    payload TEXT NOT NULL            -- JSON, raw enough to re-derive anything later
);

CREATE INDEX IF NOT EXISTS idx_events_entity_ts ON events(entity_id, event_ts);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_entities_merged ON entities(merged_into);
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
