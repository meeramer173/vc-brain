"""Founder Score v0 — a deterministic, auditable fold over ledger events.

Design rules:
- No LLM anywhere in the score. Same events in, same number out.
- Every component lists the event ids that produced it (traceability).
- `as_of` recomputes the score from only what was known at that moment —
  the same code path powers trends today and the backtest harness.

Components (weights sum to 100):
  shipping_cadence     how much they ship in the trailing 180 days
  momentum             recency-weighted shipping (half-life 60 days)
  breadth              distinct independent sources vouching for them
  external_validation  accumulated points/stars (log-scaled)
  consistency          active months out of the last 12
"""

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import ledger

WEIGHTS = {
    "shipping_cadence": 30,
    "momentum": 30,
    "breadth": 15,
    "external_validation": 15,
    "consistency": 10,
}

SHIP_TYPES = {"launch", "repo_launch", "paper", "hackathon_win"}
TREND_WINDOW_DAYS = 30
TREND_EPSILON = 2.0  # score points; smaller moves count as "stable"

# Cold-start: a founder whose score rests on too little independent evidence to
# be treated as a track record. The brief's central rubric note — a system that
# can't reason about pre-track-record founders "has just rebuilt the
# network-gated system the challenge exists to replace." We compute a *support
# confidence* (how well-evidenced the score is, NOT how high it is) and flag the
# thin ones explicitly so the UI can switch to the cold-start reasoning path
# instead of silently ranking them to the bottom.
COLD_START_CONF = 0.4


@dataclass
class Breakdown:
    total: float
    components: dict[str, float]           # component -> 0..weight contribution
    evidence: dict[str, list[int]]         # component -> contributing event ids
    n_events: int
    sources: list[str]
    as_of: str
    trend: str = "stable"                  # improving | stable | declining
    notes: list[str] = field(default_factory=list)
    confidence: float = 1.0                # 0..1 — how well-evidenced the score is
    cold_start: bool = False               # thin, pre-track-record profile
    cold_start_reasons: list[str] = field(default_factory=list)


def _score_at(events: list[dict], as_of: datetime) -> tuple[dict, dict]:
    ship = [e for e in events if e["event_type"] in SHIP_TYPES]

    recent = [
        e for e in ship
        if ledger.parse_ts(e["event_ts"]) >= as_of - timedelta(days=180)
    ]
    cadence_norm = min(1.0, len(recent) / 6)

    momentum = sum(
        0.5 ** ((as_of - ledger.parse_ts(e["event_ts"])).days / 60) for e in ship
    )
    momentum_norm = min(1.0, momentum / 4)

    sources = {e["source"] for e in events if e["source"] != "system"}
    breadth_norm = min(1.0, len(sources) / 4)

    validation = sum(
        (e["payload"].get("points", 0) or 0) + (e["payload"].get("stars", 0) or 0)
        for e in events
    )
    validation_norm = min(1.0, math.log10(1 + validation) / 3)  # 1000 pts -> 1.0

    active_months = {
        ledger.parse_ts(e["event_ts"]).strftime("%Y-%m")
        for e in ship
        if ledger.parse_ts(e["event_ts"]) >= as_of - timedelta(days=365)
    }
    consistency_norm = min(1.0, len(active_months) / 6)

    norms = {
        "shipping_cadence": cadence_norm,
        "momentum": momentum_norm,
        "breadth": breadth_norm,
        "external_validation": validation_norm,
        "consistency": consistency_norm,
    }
    evidence = {
        "shipping_cadence": [e["id"] for e in recent],
        "momentum": [e["id"] for e in ship],
        "breadth": [e["id"] for e in events if e["source"] != "system"][:20],
        "external_validation": [
            e["id"] for e in events
            if (e["payload"].get("points") or e["payload"].get("stars"))
        ],
        "consistency": [e["id"] for e in ship],
    }
    return norms, evidence


def founder_score(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of: str | None = None,
    events: list[dict] | None = None,
) -> Breakdown:
    """`events`, when provided, must already respect the as_of cutoff —
    used by callers that fetch once and score + thesis-fit in one pass."""
    as_of = as_of or ledger.utcnow_iso()
    as_of_dt = ledger.parse_ts(as_of)

    if events is None:
        events = ledger.events_for(conn, entity_id, as_of=as_of)
    norms, evidence = _score_at(events, as_of_dt)
    components = {k: round(norms[k] * WEIGHTS[k], 1) for k in WEIGHTS}
    total = round(sum(components.values()), 1)

    # Trend: same fold, 30 days earlier. Time travel is free with a ledger.
    prev_cutoff = (as_of_dt - timedelta(days=TREND_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    prev_events = [e for e in events if e["event_ts"] <= prev_cutoff]
    prev_norms, _ = _score_at(prev_events, as_of_dt - timedelta(days=TREND_WINDOW_DAYS))
    prev_total = sum(prev_norms[k] * WEIGHTS[k] for k in WEIGHTS)

    if total - prev_total > TREND_EPSILON:
        trend = "improving"
    elif prev_total - total > TREND_EPSILON:
        trend = "declining"
    else:
        trend = "stable"

    notes = []
    if len(events) < 3:
        notes.append("low-evidence profile: score is weakly supported")

    # Support confidence: how much *independent* evidence backs this number,
    # separate from the number itself. Breadth of sources dominates (one
    # gameable source is weak corroboration), then how much they've shipped,
    # then external validation. This is the "how sure are we" that the memo
    # keeps distinct from "how good are they".
    real_sources = sorted({e["source"] for e in events if e["source"] != "system"})
    n_ship = sum(1 for e in events if e["event_type"] in SHIP_TYPES)
    ship_support = min(1.0, n_ship / 4)
    confidence = round(
        0.5 * norms["breadth"] + 0.3 * ship_support + 0.2 * norms["external_validation"],
        2,
    )

    cold_start_reasons: list[str] = []
    if len(real_sources) <= 1:
        cold_start_reasons.append(
            f"only {len(real_sources)} independent source"
            f"{'s' if len(real_sources) != 1 else ''} — no cross-source corroboration yet"
        )
    if n_ship <= 1:
        cold_start_reasons.append("little to no shipping history on record")
    if norms["external_validation"] < 0.2:
        cold_start_reasons.append("minimal external validation (stars / points)")
    cold_start = confidence < COLD_START_CONF
    if cold_start and not cold_start_reasons:
        cold_start_reasons.append("thin overall footprint")

    return Breakdown(
        total=total,
        components=components,
        evidence=evidence,
        n_events=len(events),
        sources=real_sources,
        as_of=as_of,
        trend=trend,
        notes=notes,
        confidence=confidence,
        cold_start=cold_start,
        cold_start_reasons=cold_start_reasons,
    )


def slice_trend(
    events: list[dict],
    types: set[str],
    as_of: str | None = None,
    window_days: int = 90,
) -> str:
    """Deterministic trend for one axis's evidence slice: is activity of these
    event types accelerating or fading? Compares the trailing window against the
    window before it. Same philosophy as the Founder Score trend — a fold over
    the ledger, not an LLM guess — so each axis can show its own honest
    direction. No recent activity either side => 'stable'."""
    ref = ledger.parse_ts(as_of) if as_of else datetime.now(timezone.utc)

    def count(lo: datetime, hi: datetime) -> int:
        return sum(
            1 for e in events
            if e["event_type"] in types
            and lo <= ledger.parse_ts(e["event_ts"]) < hi
        )

    recent = count(ref - timedelta(days=window_days), ref + timedelta(days=1))
    prior = count(ref - timedelta(days=2 * window_days), ref - timedelta(days=window_days))
    if recent > prior:
        return "improving"
    if recent < prior:
        return "declining"
    return "stable"


def rank_founders(
    conn: sqlite3.Connection, n: int = 10, as_of: str | None = None
) -> list[tuple[int, str, Breakdown]]:
    rows = conn.execute(
        "SELECT id, canonical_name FROM entities"
        " WHERE kind = 'person' AND merged_into IS NULL"
    ).fetchall()
    scored = [
        (r["id"], r["canonical_name"], founder_score(conn, r["id"], as_of=as_of))
        for r in rows
    ]
    scored.sort(key=lambda t: t[2].total, reverse=True)
    return scored[:n]
