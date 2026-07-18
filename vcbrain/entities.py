"""Deterministic entity resolution — one human across all sources.

Auto-merge happens only on hard evidence:
  1. identical (source, handle) — same account seen again
  2. identical URL in the handles' url list
  3. identical username (len >= 4) on different platforms

Name-only similarity NEVER auto-merges (too many false positives); it can
be surfaced as a suggestion later. Every merge is recorded in the ledger as
a `merge` event with its basis, so identity decisions are auditable.
"""

import json
import re
import sqlite3

from . import ledger

MIN_XPLATFORM_HANDLE_LEN = 4


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", name.lower())).strip()


def _load_handles(row) -> dict:
    return json.loads(row["handles"])


def resolve(conn: sqlite3.Connection, entity_id: int) -> int:
    """Follow merge pointers to the surviving entity."""
    seen = set()
    while True:
        if entity_id in seen:  # defensive: cycles should be impossible
            return entity_id
        seen.add(entity_id)
        row = conn.execute(
            "SELECT merged_into FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None or row["merged_into"] is None:
            return entity_id
        entity_id = row["merged_into"]


def merge(conn: sqlite3.Connection, winner_id: int, loser_id: int, basis: str) -> None:
    winner_id, loser_id = resolve(conn, winner_id), resolve(conn, loser_id)
    if winner_id == loser_id:
        return
    w = conn.execute("SELECT * FROM entities WHERE id = ?", (winner_id,)).fetchone()
    l = conn.execute("SELECT * FROM entities WHERE id = ?", (loser_id,)).fetchone()
    wh, lh = _load_handles(w), _load_handles(l)
    urls = sorted(set(wh.get("urls", [])) | set(lh.get("urls", [])))
    merged_handles = {**lh, **wh}  # winner's handles take precedence on conflict
    if urls:
        merged_handles["urls"] = urls
    conn.execute(
        "UPDATE entities SET handles = ? WHERE id = ?",
        (json.dumps(merged_handles), winner_id),
    )
    conn.execute(
        "UPDATE entities SET merged_into = ? WHERE id = ?", (winner_id, loser_id)
    )
    conn.commit()
    ledger.record(
        conn,
        winner_id,
        "system",
        "merge",
        ledger.utcnow_iso(),
        f"system:merge:{loser_id}->{winner_id}",
        {"absorbed_entity": loser_id, "absorbed_name": l["canonical_name"], "basis": basis},
    )


class Resolver:
    """In-memory index over entity handles, kept in sync as we ingest.

    Hackathon-scale (thousands of entities) — a full load per ingest run is
    cheap and keeps the logic transparent.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.by_source_handle: dict[tuple[str, str], int] = {}
        self.by_username: dict[str, set[int]] = {}
        self.by_url: dict[str, int] = {}
        for row in conn.execute("SELECT * FROM entities WHERE merged_into IS NULL"):
            self._index(row["id"], _load_handles(row))

    def _index(self, eid: int, handles: dict) -> None:
        for source, handle in handles.items():
            if source == "urls":
                for u in handle:
                    self.by_url[u.lower().rstrip("/")] = eid
                continue
            h = str(handle).lower()
            self.by_source_handle[(source, h)] = eid
            if len(h) >= MIN_XPLATFORM_HANDLE_LEN:
                self.by_username.setdefault(h, set()).add(eid)

    def get_or_create(self, kind: str, name: str, handles: dict) -> int:
        """Find the entity these handles belong to, merging when hard
        evidence links previously separate entities; create if unseen."""
        urls = [u.lower().rstrip("/") for u in handles.get("urls", [])]
        plain = {k: str(v).lower() for k, v in handles.items() if k != "urls"}

        matches: dict[int, str] = {}
        for source, h in plain.items():
            if (source, h) in self.by_source_handle:
                matches[self.by_source_handle[(source, h)]] = f"same_account:{source}"
        for u in urls:
            if u in self.by_url:
                matches.setdefault(self.by_url[u], "same_url")
        for h in plain.values():
            if len(h) >= MIN_XPLATFORM_HANDLE_LEN:
                for eid in self.by_username.get(h, set()):
                    matches.setdefault(eid, "same_username_cross_platform")

        matches = {resolve(self.conn, e): b for e, b in matches.items()}

        if not matches:
            cur = self.conn.execute(
                "INSERT INTO entities (kind, canonical_name, handles) VALUES (?, ?, ?)",
                (kind, name, json.dumps(handles)),
            )
            self.conn.commit()
            eid = cur.lastrowid
            self._index(eid, handles)
            return eid

        # Deterministic winner: lowest id (oldest profile) survives.
        ordered = sorted(matches)
        winner = ordered[0]
        for loser in ordered[1:]:
            merge(self.conn, winner, loser, matches[loser])

        # Enrich winner with any handles it didn't have yet.
        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (winner,)
        ).fetchone()
        existing = _load_handles(row)
        new_handles = {**{k: v for k, v in handles.items() if k != "urls"}}
        changed = False
        for k, v in new_handles.items():
            if k not in existing:
                existing[k] = v
                changed = True
        merged_urls = sorted(set(existing.get("urls", [])) | set(handles.get("urls", [])))
        if merged_urls and merged_urls != existing.get("urls", []):
            existing["urls"] = merged_urls
            changed = True
        if changed:
            self.conn.execute(
                "UPDATE entities SET handles = ? WHERE id = ?",
                (json.dumps(existing), winner),
            )
            self.conn.commit()
        self._index(winner, existing)
        return winner
