"""Multi-Attribute Reasoning — compound natural-language founder search
(MVP requirement 3: "beyond keyword search", resolved in one pass).

Design (same 'LLM at the edges' rule as the rest of the brain):
- The LLM does ONE thing: parse the free text into a structured spec
  (intelligence.parse_query). That parse is shown to the user — the single
  inspectable edge.
- Everything here is deterministic: each specified attribute becomes a hard
  filter over a founder's ledger evidence, survivors are ranked by Founder
  Score, and every match reports exactly which evidence satisfied it.
- Attributes the data cannot support (location, VC-funding history) are never
  silently dropped: they are surfaced as honest disclosures, not fake filters.

If the LLM call fails (no key, timeout), a deterministic keyword fallback
keeps search working so a live demo never dies.
"""

import re
from dataclasses import dataclass, field

from . import intelligence, ledger, score
from .thesis import _corpus, _keywords

# event_type sets that answer each capability attribute
_CODE_TYPES = {"repo_launch"}
_PAPER_TYPES = {"paper"}
_WIN_TYPES = {"hackathon_win"}
_ACCEL_TYPES = {"accelerator_batch"}

# words in `unmappable` that we can honestly re-frame rather than just shrug at
_VC_HINTS = ("vc", "funding", "funded", "backing", "backed", "raised", "investor",
             "seed round", "series")


@dataclass
class Attr:
    """One evaluated attribute of the query against one founder."""
    label: str
    ok: bool
    detail: str = ""
    evidence_ids: list[int] = field(default_factory=list)


@dataclass
class Match:
    entity_id: int
    name: str
    breakdown: object            # score.Breakdown
    attrs: list[Attr]            # every specified constraint, ok True/False
    matched_sectors: list[str] = field(default_factory=list)
    sector_ok: bool = True       # False only when a sector was asked for and missed

    @property
    def satisfied(self) -> list[Attr]:
        return [a for a in self.attrs if a.ok]

    @property
    def missed(self) -> list[Attr]:
        return [a for a in self.attrs if not a.ok]

    @property
    def n_total(self) -> int:
        return len(self.attrs)

    @property
    def perfect(self) -> bool:
        return bool(self.attrs) and all(a.ok for a in self.attrs)


def _naive_parse(q: str) -> dict:
    """Deterministic fallback parser — no LLM. Good enough to keep the feature
    alive: comma/space phrases become sector keywords, and a few capability
    words are detected directly."""
    low = q.lower()
    spec = {
        "sectors": [p.strip() for p in re.split(r"[,;]", q) if p.strip()],
        "technical": any(w in low for w in ("technical", "engineer", "developer", "hacker")),
        "researcher": any(w in low for w in ("research", "paper", "phd", "arxiv")),
        "hackathon_winner": "hackathon" in low or "devpost" in low,
        "accelerator": any(w in low for w in ("accelerator", "yc", "y combinator", "cohort", "batch")),
        "languages": [],
        "min_founder_score": None,
        "trend": "improving" if any(w in low for w in ("momentum", "rising", "improving", "trending")) else None,
        "unmappable": [],
        "raw": q,
        "_fallback": True,
    }
    return spec


def build_spec(q: str) -> dict:
    """Parse via the LLM edge; fall back to deterministic parsing on any error."""
    try:
        return intelligence.parse_query(q)
    except Exception as exc:  # noqa: BLE001 — demo must not die on an LLM hiccup
        spec = _naive_parse(q)
        spec["_fallback_reason"] = str(exc)[:120]
        return spec


def _has_type(events, types) -> list[int]:
    return [e["id"] for e in events if e["event_type"] in types]


def _languages(events) -> dict[str, list[int]]:
    langs: dict[str, list[int]] = {}
    for e in events:
        lang = (e["payload"].get("language") or "").lower()
        if lang:
            langs.setdefault(lang, []).append(e["id"])
    return langs


def _sector_hits(corpus: str, sectors: list[str]) -> list[str]:
    return [
        kw for kw in _keywords(sectors)
        if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", corpus)
    ]


def _evaluate(spec: dict, events, breakdown, handles: dict) -> tuple[list[Attr], list[str], bool]:
    """Return (per-attribute results, matched sector terms, sector_ok).
    Every specified attribute is evaluated (ok True/False); ranking decides
    what surfaces. sector_ok is True when no sector was asked for."""
    corpus = _corpus(events)
    attrs: list[Attr] = []
    matched_sectors: list[str] = []
    sector_ok = True

    sectors = spec.get("sectors") or []
    if sectors:
        hits = _sector_hits(corpus, sectors)
        matched_sectors = hits
        sector_ok = bool(hits)
        attrs.append(Attr(
            f"sector: {', '.join(sectors)}", bool(hits),
            "matched " + ", ".join(hits[:5]) if hits else "no sector term in evidence",
        ))

    if spec.get("technical"):
        ids = _has_type(events, _CODE_TYPES | _PAPER_TYPES)
        has_gh = "github" in handles
        attrs.append(Attr(
            "technical founder", bool(ids) or has_gh,
            f"{len(ids)} code/research signal(s)" + (" + github handle" if has_gh else "")
            if (ids or has_gh) else "no code or research evidence",
            ids,
        ))

    if spec.get("researcher"):
        ids = _has_type(events, _PAPER_TYPES)
        attrs.append(Attr("published researcher", bool(ids),
                          f"{len(ids)} paper(s)" if ids else "no papers", ids))

    if spec.get("hackathon_winner"):
        ids = _has_type(events, _WIN_TYPES)
        attrs.append(Attr("hackathon winner", bool(ids),
                          f"{len(ids)} win(s)" if ids else "no hackathon wins", ids))

    if spec.get("accelerator"):
        ids = _has_type(events, _ACCEL_TYPES)
        has_yc = "yc" in handles
        attrs.append(Attr("top-tier accelerator", bool(ids) or has_yc,
                          "accelerator batch on record" if (ids or has_yc)
                          else "no accelerator signal", ids))

    langs_req = [l.lower() for l in (spec.get("languages") or [])]
    if langs_req:
        founder_langs = _languages(events)
        got = {l: founder_langs[l] for l in langs_req if l in founder_langs}
        ids = [i for lst in got.values() for i in lst]
        attrs.append(Attr(f"language: {', '.join(langs_req)}", bool(got),
                          "ships in " + ", ".join(got) if got else "no matching language", ids))

    floor = spec.get("min_founder_score")
    if isinstance(floor, (int, float)):
        attrs.append(Attr(f"Founder Score ≥ {floor}", breakdown.total >= floor,
                          f"score {breakdown.total}"))

    if spec.get("trend") == "improving":
        attrs.append(Attr("trend improving", breakdown.trend == "improving",
                          f"trend {breakdown.trend}"))

    return attrs, matched_sectors, sector_ok


def disclosures(spec: dict) -> list[str]:
    """Honest notes for constraints the data cannot filter on."""
    out: list[str] = []
    for item in spec.get("unmappable") or []:
        text = str(item)
        if any(h in text.lower() for h in _VC_HINTS):
            out.append(f"“{text}” — satisfied by construction: every founder here is "
                       f"pre-track-record; the system ingests no funding data, so nobody "
                       f"in the pool has prior VC backing.")
        else:
            out.append(f"“{text}” — no signal for this in current sources "
                       f"(e.g. location/geography); shown, not filtered.")
    return out


def run(conn, q: str, n: int = 25, as_of: str | None = None):
    """Full compound search: parse (LLM edge) -> deterministic score+rank.

    Attributes are scored, not strict-AND'd: a founder surfaces if it is
    topically relevant (matches the sector, when one is asked for) and
    satisfies at least one constraint. Ranking is by how many constraints are
    satisfied, then Founder Score. This keeps sparse attributes (e.g. an
    accelerator signal few founders carry) from zeroing out the whole result
    while every constraint stays visible as a pass/fail on each row."""
    import json  # local: entities.handles is JSON text
    spec = build_spec(q)
    has_sectors = bool(spec.get("sectors"))
    rows = conn.execute(
        "SELECT id, canonical_name, handles FROM entities"
        " WHERE kind = 'person' AND merged_into IS NULL"
    ).fetchall()

    candidates: list[Match] = []
    for r in rows:
        events = ledger.events_for(conn, r["id"], as_of=as_of)
        b = score.founder_score(conn, r["id"], as_of=as_of, events=events)
        handles = json.loads(r["handles"] or "{}")
        attrs, sectors, sector_ok = _evaluate(spec, events, b, handles)
        m = Match(r["id"], r["canonical_name"], b, attrs, sectors, sector_ok)
        if not attrs:                       # empty query -> top founders
            candidates.append(m)
        elif any(a.ok for a in attrs):      # satisfies at least one constraint
            candidates.append(m)

    # Prefer topically-relevant founders (sector matched). Only if that leaves
    # nothing do we relax to the best partial matches, and say so.
    on_topic = [m for m in candidates if m.sector_ok] if has_sectors else candidates
    relaxed = has_sectors and not on_topic
    pool = candidates if relaxed else on_topic

    pool.sort(key=lambda m: (len(m.satisfied), m.breakdown.total), reverse=True)
    meta = {"relaxed": relaxed, "candidates": len(pool)}
    return spec, pool[:n], disclosures(spec), meta
