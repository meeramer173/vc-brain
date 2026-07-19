"""Curated (synthetic) profile loader — kept fully separate from scraped data.

Reads data/curated_profiles.json and maps each record onto its founder entity
by handle (same entity resolution the scrapers use), then appends events tagged
`source="curated"` so they are:
  - distinguishable from scraped data forever (every event knows its source),
  - weighted as self-reported (Medium trust) by trust.py,
  - folded into the Founder Score's experience / technical_depth components.

By policy this only enriches FICTIONAL demo personas — never real scraped
founders — so nothing about a real person is ever fabricated. A `sim_reply`
record (an obviously-simulated founder response) powers the offer demo and, not
being a scoring event type, never affects the score.
"""

import hashlib
import json
from pathlib import Path

from . import ledger
from .entities import Resolver

PATH = Path(__file__).resolve().parent.parent / "data" / "curated_profiles.json"


def _ts_for(ev: dict) -> str:
    """Career events carry a year → date them then (so tenure/span is honest);
    otherwise stamp now."""
    y = ev.get("year")
    return f"{int(y)}-06-01T00:00:00Z" if y else ledger.utcnow_iso()


def _digest(obj: dict) -> str:
    return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:10]


def load_curated(conn, path: Path | str = PATH) -> dict:
    """Attach curated experience / tech-depth / sim_reply events to the personas
    named in the JSON. Personas must already exist (seeded) with a github handle;
    unknown handles are skipped. Idempotent via content-addressed dedup keys."""
    data = json.loads(Path(path).read_text())
    resolver = Resolver(conn)
    added, skipped = 0, 0
    for handle, rec in data.items():
        if handle.startswith("_"):          # metadata keys like "_note"
            continue
        eid = resolver.by_source_handle.get(("github", handle.lower()))
        if eid is None:
            skipped += 1
            continue
        for ev in list(rec.get("experience", [])) + list(rec.get("tech_depth", [])):
            etype = ev.get("type")
            if not etype:
                continue
            if ledger.record(conn, eid, "curated", etype, _ts_for(ev),
                             f"curated:{handle}:{etype}:{_digest(ev)}", ev):
                added += 1
        reply = rec.get("sim_reply")
        if reply:
            ledger.record(conn, eid, "curated", "sim_reply", ledger.utcnow_iso(),
                          f"curated:reply:{handle}:{_digest(reply)}", reply)
    return {"added": added, "skipped_unknown": skipped}


def sim_reply(conn, entity_id: int) -> dict | None:
    """The latest simulated founder response, if one was curated for this
    entity (used by the offer demo)."""
    replies = [e for e in ledger.events_for(conn, entity_id)
               if e["event_type"] == "sim_reply"]
    return replies[-1]["payload"] if replies else None
