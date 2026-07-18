"""Connector contract: fetch heterogeneous public signals, normalize them
into RawSignal, and let a shared ingest() do entity resolution + ledger
appends. Connectors never write to the DB directly."""

import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from .. import ledger
from ..entities import Resolver


@dataclass
class RawSignal:
    kind: str            # person | company
    name: str            # display name of the entity
    handles: dict        # {"hn": "pg", "github": "octocat", "urls": [...]}
    event_type: str      # launch | repo_launch | paper | hackathon_win | accelerator_batch | ...
    event_ts: str        # ISO-8601 UTC
    external_id: str     # unique within the source → dedup key
    payload: dict = field(default_factory=dict)


def ingest(
    conn: sqlite3.Connection, source: str, signals: Iterable[RawSignal]
) -> dict:
    resolver = Resolver(conn)
    new_events = 0
    dupes = 0
    for sig in signals:
        eid = resolver.get_or_create(sig.kind, sig.name, sig.handles)
        event_id = ledger.record(
            conn,
            eid,
            source,
            sig.event_type,
            sig.event_ts,
            f"{source}:{sig.external_id}",
            sig.payload,
        )
        if event_id is None:
            dupes += 1
        else:
            new_events += 1
    return {"source": source, "new_events": new_events, "duplicates_skipped": dupes}
