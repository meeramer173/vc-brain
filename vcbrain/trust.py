"""Trust Score — deterministic, per-claim, auditable.

Design rules (same philosophy as score.py — "LLM at the edges"):
- The LLM supplies only a *verdict* and a *claim_type* (a linguistic judgment).
  The trust NUMBER is computed here, in Python, from evidence — never emitted
  by the model. Same claim + same evidence => same score.
- Every claim's score decomposes into named components (like the Founder
  Score), so a judge can see exactly why a claim is trusted or not.

Components
  citation_validity   fraction of cited event_ids that actually exist  (0..1, gate)
  fact_grounding      do the claim's numbers match the cited evidence? (0/1, HARD gate)
  source_reliability  strength of the strongest cited source           (0.4..1.0)
  corroboration       bonus for multiple independent sources           (1.0..1.3)
  verdict_multiplier  the LLM's adversarial verdict as a factor         (0..1.0)

  trust = citation_validity * fact_grounding * source_reliability
        * corroboration * verdict_multiplier
  then capped: interpretations can never exceed INFERENCE_CAP.

Two things deterministically *override the LLM*:
- a number that doesn't trace to cited evidence forces 'contradicted' (fact_grounding=0)
- gap claims skip the formula and are labelled honest, not scored red
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# How much we trust evidence by its source. Hard, third-party-verifiable
# signals score high; self-reported / community-gameable signals score low.
SOURCE_WEIGHTS = {
    "yc": 0.95,          # accepted into an accelerator — strong external validation
    "github": 0.90,      # public repos/commits (stars are gameable but existence is hard)
    "arxiv": 0.90,       # published paper
    "devpost": 0.70,     # hackathon win
    "hn": 0.60,          # community points — soft, gameable
    "producthunt": 0.60,
    "inbound": 0.40,     # self-reported by the founder — weakest
    "application": 0.40,
    "system": 0.30,
}
DEFAULT_SOURCE_WEIGHT = 0.50

VERDICT_MULTIPLIER = {"supported": 1.0, "weak": 0.6, "contradicted": 0.0}
INFERENCE_CAP = 0.5      # an interpretation is never as trustworthy as a raw fact
FACT_CAP = 1.0

# Structured payload keys that count as hard, checkable evidence numbers.
SIGNAL_KEYS = ("stars", "points", "num_comments", "karma", "prizes",
               "team_size", "followers", "forks", "watchers", "upvotes")

_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


@dataclass
class ClaimTrust:
    claim_id: str
    verdict: str                     # supported | weak | contradicted | gap
    trust: float | None              # None for gap claims
    claim_type: str                  # fact | inference | gap
    note: str
    breakdown: dict = field(default_factory=dict)
    label: str | None = None         # e.g. "honest gap"


def _extract_metric_numbers(text: str) -> list[float]:
    """Pull *metric-sized* numbers out of claim text.

    We deliberately ignore small counts ("5 repos") and bare years, and we
    expand k/m/b and $ suffixes, so "$1M" and "50k users" are checkable.
    """
    nums: list[float] = []
    # suffixed / currency first, e.g. $1.5M, 50k, 2.1m
    for m in re.finditer(r"\$?\s*(\d[\d,]*\.?\d*)\s*([kKmMbB])\b", text):
        val = float(m.group(1).replace(",", "")) * _SUFFIX[m.group(2).lower()]
        nums.append(val)
    # plain currency, e.g. $250,000
    for m in re.finditer(r"\$\s*(\d[\d,]*)\b", text):
        nums.append(float(m.group(1).replace(",", "")))
    # plain integers >= 100 that aren't obviously a year
    for m in re.finditer(r"\b(\d[\d,]{2,})\b", text):
        val = float(m.group(1).replace(",", ""))
        if val >= 100 and not (1900 <= val <= 2100 and "," not in m.group(1)):
            nums.append(val)
    return nums


def _evidence_numbers(events: list[dict]) -> list[float]:
    out: list[float] = []
    for e in events:
        p = e.get("payload", {})
        for k in SIGNAL_KEYS:
            v = p.get(k)
            if isinstance(v, (int, float)):
                out.append(float(v))
    return out


def _matches(claim_num: float, evidence: list[float]) -> bool:
    tol = max(1.0, 0.05 * claim_num)   # 5% tolerance
    return any(abs(claim_num - e) <= tol for e in evidence)


def score_claim(claim: dict, verdict_rec: dict, event_index: dict) -> ClaimTrust:
    cid = claim["claim_id"]
    note = verdict_rec.get("note", "")
    claim_type = verdict_rec.get("claim_type", "fact")
    verdict = verdict_rec.get("verdict", "weak")

    # Gap claims are honest, not wrong — they skip the numeric formula.
    if claim.get("gap") or verdict == "gap":
        return ClaimTrust(cid, "gap", None, "gap", note, label="honest gap")

    cited = [int(i) for i in claim.get("evidence_ids", []) if str(i).isdigit()]
    valid_ids = [i for i in cited if i in event_index]
    valid_events = [event_index[i] for i in valid_ids]

    # 1 · citation validity (unsupported non-gap assertion => 0)
    citation_validity = (len(valid_ids) / len(cited)) if cited else 0.0

    # 2 · fact grounding (HARD gate): every metric number must trace to evidence
    claim_nums = _extract_metric_numbers(claim.get("text", ""))
    ev_nums = _evidence_numbers(valid_events)
    fact_grounding = 1.0
    if claim_nums and not all(_matches(n, ev_nums) for n in claim_nums):
        fact_grounding = 0.0
        verdict = "contradicted"          # Python overrides the LLM here
        if not note:
            note = "number not supported by cited evidence"

    # 3 · source reliability (strongest cited source)
    source_reliability = max(
        (SOURCE_WEIGHTS.get(e.get("source"), DEFAULT_SOURCE_WEIGHT)
         for e in valid_events),
        default=DEFAULT_SOURCE_WEIGHT,
    )

    # 4 · corroboration (independent sources agreeing)
    n_sources = len({e.get("source") for e in valid_events})
    corroboration = min(1.3, 1.0 + 0.15 * max(0, n_sources - 1))

    # 5 · verdict multiplier
    verdict_multiplier = VERDICT_MULTIPLIER.get(verdict, 0.6)

    raw = (citation_validity * fact_grounding * source_reliability
           * corroboration * verdict_multiplier)
    cap = INFERENCE_CAP if claim_type == "inference" else FACT_CAP
    trust = round(min(raw, cap, 1.0), 2)

    breakdown = {
        "citation_validity": round(citation_validity, 2),
        "fact_grounding": fact_grounding,
        "source_reliability": round(source_reliability, 2),
        "corroboration": round(corroboration, 2),
        "verdict_multiplier": verdict_multiplier,
        "cap": cap,
    }
    return ClaimTrust(cid, verdict, trust, claim_type, note, breakdown)


def _summary(scored: list[ClaimTrust]) -> dict:
    graded = [s for s in scored if s.trust is not None]
    contradicted = [s for s in scored if s.verdict == "contradicted"]
    gaps = [s for s in scored if s.verdict == "gap"]
    high = [s for s in graded if s.trust >= 0.7]
    avg = round(sum(s.trust for s in graded) / len(graded), 2) if graded else None
    return {
        "claims_total": len(scored),
        "graded": len(graded),
        "gaps": len(gaps),
        "contradicted": len(contradicted),
        "avg_trust": avg,
        "pct_high_trust": round(100 * len(high) / len(graded)) if graded else None,
        "fund_gate_blocked": len(contradicted) > 0,
    }


def score_all(claims: list[dict], verdicts: list[dict],
              events: list[dict]) -> dict:
    """Attach a deterministic trust score to every claim.

    `verdicts` are the LLM's per-claim {claim_id, verdict, claim_type, note}
    (no trust number). We compute trust here and return the enriched records
    plus a founder-level roll-up used by the decision gate.
    """
    event_index = {e["id"]: e for e in events}
    vmap = {v.get("claim_id"): v for v in verdicts}
    scored = [
        score_claim(c, vmap.get(c["claim_id"], {}), event_index) for c in claims
    ]
    return {
        "verdicts": [
            {"claim_id": s.claim_id, "verdict": s.verdict, "trust": s.trust,
             "claim_type": s.claim_type, "note": s.note,
             "breakdown": s.breakdown, "label": s.label}
            for s in scored
        ],
        "summary": _summary(scored),
    }
