"""Thesis Engine — the fund-specific lens (MVP requirement 1).

The investor sets sectors, stage, geography, check size, ownership target,
and risk appetite. Everything downstream runs through this lens:
- the dashboard re-ranks founders by a deterministic thesis-fit blend,
- the fit is keyword evidence over ledger events (matched terms shown, so
  the lens is as auditable as everything else),
- risk appetite parameterizes the deterministic decision rule's bars,
- check size flows into the final decision text.

Honesty notes (also shown in the UI): our current sources carry no reliable
geography signal, so geography is displayed but not filtered; every
outbound-sourced founder is pre-formal by construction, so stage is
satisfied trivially. Neither is silently faked.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THESIS_FILE = ROOT / "thesis.json"

DEFAULT_THESIS = {
    "fund_name": "Maschmeyer Group — demo thesis",
    "sectors": ["AI", "LLM", "agents", "developer tools", "infrastructure"],
    "stage": "pre-seed / first check",
    "geography": "global, remote-friendly",
    "check_size_usd": 100000,
    "ownership_target": "SAFE, uncapped-friendly at this size",
    "risk_appetite": "high",
    "disqualifiers": ["crypto", "token", "casino", "gambling"],
}

_STOPWORDS = {"and", "for", "the", "applied", "tools", "with", "app", "apps"}


def load_thesis() -> dict:
    if THESIS_FILE.exists():
        return {**DEFAULT_THESIS, **json.loads(THESIS_FILE.read_text())}
    THESIS_FILE.write_text(json.dumps(DEFAULT_THESIS, indent=2))
    return dict(DEFAULT_THESIS)


def save_thesis(thesis: dict) -> None:
    THESIS_FILE.write_text(json.dumps(thesis, indent=2))


def _keywords(entries: list[str]) -> list[str]:
    """Sector/disqualifier strings -> matchable lowercase keywords.
    Multi-word entries contribute the full phrase plus useful single words."""
    out: list[str] = []
    for entry in entries:
        phrase = entry.strip().lower()
        if not phrase:
            continue
        out.append(phrase)
        for word in re.findall(r"[a-z0-9+#-]{2,}", phrase):
            if word not in _STOPWORDS and word not in out:
                out.append(word)
    return out


@dataclass
class Fit:
    fit: float                      # 0..1 strength of sector match
    matched: list[str] = field(default_factory=list)
    disqualified: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _corpus(events: list[dict]) -> str:
    parts: list[str] = []
    for e in events:
        p = e["payload"]
        for k in ("title", "description", "one_liner", "repo", "project",
                  "company", "language"):
            if p.get(k):
                parts.append(str(p[k]))
        parts.extend(str(t) for t in (p.get("tags") or []))
        parts.extend(str(t) for t in (p.get("prizes") or []))
    return " ".join(parts).lower()


def fit(events: list[dict], thesis: dict) -> Fit:
    """Deterministic keyword-evidence fit of a founder's ledger against the
    thesis. v0 is transparent by design: the matched terms ARE the score."""
    corpus = _corpus(events)

    def hits(entries):
        return [kw for kw in _keywords(entries)
                if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", corpus)]

    matched = hits(thesis.get("sectors", []))
    disqualified = hits(thesis.get("disqualifiers", []))
    strength = min(1.0, len(matched) / 2)  # 1 term = 0.5, 2+ terms = 1.0
    return Fit(
        fit=strength,
        matched=matched[:8],
        disqualified=disqualified[:8],
        notes=[
            "geography: no location signal in current sources — shown, not filtered",
            "stage: outbound-sourced founders are pre-formal by construction",
        ],
    )


def blended_score(total: float, f: Fit) -> float:
    """Dashboard ranking value: thesis-fit blend of the Founder Score.
    Off-thesis founders keep 45% weight (visible, not hidden); disqualified
    founders are penalized hard but still listed with the reason."""
    value = total * (0.45 + 0.55 * f.fit)
    if f.disqualified:
        value *= 0.2
    return round(value, 1)


def decision_bars(thesis: dict) -> dict:
    """Risk appetite parameterizes the deterministic decision rule."""
    appetite = str(thesis.get("risk_appetite", "medium")).lower().split()[0]
    bars = {
        "high":   {"founder_bar": 6, "idea_bar": 4, "off_thesis_ok_if_founder": 8},
        "medium": {"founder_bar": 6, "idea_bar": 5, "off_thesis_ok_if_founder": None},
        "low":    {"founder_bar": 7, "idea_bar": 6, "off_thesis_ok_if_founder": None},
    }
    return {"appetite": appetite, **bars.get(appetite, bars["medium"])}


def rank_with_lens(conn, thesis: dict, n: int = 25, as_of: str | None = None):
    """Single-pass ranking of all persons through the fund lens.
    Returns [(entity_id, name, score_breakdown, Fit, blended)] sorted by blend."""
    from . import ledger, score  # local import to avoid cycles

    rows = conn.execute(
        "SELECT id, canonical_name FROM entities"
        " WHERE kind = 'person' AND merged_into IS NULL"
    ).fetchall()
    out = []
    for r in rows:
        events = ledger.events_for(conn, r["id"], as_of=as_of)
        b = score.founder_score(conn, r["id"], as_of=as_of, events=events)
        f = fit(events, thesis)
        out.append((r["id"], r["canonical_name"], b, f, blended_score(b.total, f)))
    out.sort(key=lambda t: t[4], reverse=True)
    return out[:n]
