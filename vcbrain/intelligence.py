"""Intelligence layer — the only place the LLM is allowed to work.

Design (per our 'LLM at the edges' rule):
- Three axis agents (Founder / Market / Idea-vs-Market) each see ONLY their
  own evidence slice, so disagreement is structural. Never averaged.
- Every memo claim must cite ledger event ids from the evidence it was
  given, or be flagged as an explicit gap ("not disclosed") — never guessed.
- An adversarial validator then tries to REFUTE each claim against the same
  ledger evidence; per-claim Trust Scores come out of that pass.
- The $100K decision itself is a deterministic rule over the axis outputs —
  the LLM writes rationale, it does not decide.
- The finished memo is appended to the ledger as an event: memos live in
  Memory like everything else.
"""

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import db, ledger, score
from . import thesis as thesis_mod
from .thesis import load_thesis

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
EVIDENCE_CAP = 40


def _llm(system: str, user: str, max_tokens: int = 2000) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing from .env")
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_tokens,
    }
    if MODEL.startswith("gpt-5"):
        body["reasoning_effort"] = "low"
    with httpx.Client(timeout=120) as client:
        resp = client.post(API, headers={"Authorization": f"Bearer {key}"}, json=body)
        if resp.status_code == 400 and "reasoning_effort" in body:
            body.pop("reasoning_effort")
            resp = client.post(API, headers={"Authorization": f"Bearer {key}"}, json=body)
        resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


QUERY_SCHEMA = (
    "Translate a VC's free-text founder query into a structured filter over a "
    "founder-signal database. Per founder the database knows: which public "
    "sources vouch for them (github repos, arxiv papers, Show HN launches, "
    "Devpost hackathon wins, YC/accelerator batches), the TEXT of what they "
    "built, programming languages (from github), and a deterministic Founder "
    "Score 0-100 with a trend. It does NOT know location/geography, funding or "
    "VC history, revenue, or team size. Map the query ONLY to the fields below; "
    "put any constraint you cannot map into `unmappable` (verbatim) so the "
    "system can disclose it honestly. Never invent constraints the user did not "
    "ask for. Respond JSON: {sectors: [string]  // topic/sector keywords to "
    "match in what they built, e.g. 'ai infra','developer tools','enterprise'; "
    "technical: bool  // requires code or research evidence; researcher: bool  "
    "// requires a published paper; hackathon_winner: bool; accelerator: bool  "
    "// requires a top-tier accelerator batch e.g. YC; languages: [string]  // "
    "lowercase programming languages; min_founder_score: number|null; trend: "
    "'improving'|null; unmappable: [string]}"
)


def parse_query(q: str) -> dict:
    """LLM edge: free-text founder query -> structured, inspectable filter spec.
    The LLM only extracts intent; all matching/ranking downstream is
    deterministic (see search.py). Raises if no key / the call fails —
    search.py wraps this with a deterministic fallback so the demo never dies."""
    spec = _llm(QUERY_SCHEMA, json.dumps({"query": q}), max_tokens=600)
    spec["raw"] = q
    return spec


def evidence_digest(events: list[dict], types: set[str] | None = None) -> list[dict]:
    """Compact, id-bearing evidence rows. The LLM may only cite these ids."""
    rows = []
    for e in events:
        if e["source"] == "system":
            continue
        if types and e["event_type"] not in types:
            continue
        p = e["payload"]
        rows.append({
            "event_id": e["id"],
            "date": e["event_ts"][:10],
            "source": f"{e['source']}/{e['event_type']}",
            "what": p.get("title") or p.get("repo") or p.get("project")
                    or p.get("one_liner") or p.get("company") or "",
            "signal": {k: p[k] for k in ("points", "stars", "num_comments",
                                         "karma", "prizes", "team_size") if p.get(k)},
        })
    return rows[-EVIDENCE_CAP:]


CITE_RULES = (
    "Rules: every claim object must include evidence_ids citing ONLY event_id "
    "values from the evidence list. If the evidence cannot support a required "
    "statement, output it as a gap claim: {\"text\": \"<topic>: not disclosed / "
    "no evidence available\", \"evidence_ids\": [], \"gap\": true}. Never invent "
    "facts. Confidence is 0.0-1.0 and must reflect evidence strength."
)


def founder_axis(events: list[dict], breakdown) -> dict:
    ship = evidence_digest(events, {"launch", "repo_launch", "paper",
                                    "hackathon_win", "profile_snapshot"})
    return _llm(
        "You are the Founder axis agent of a VC brain. You see ONLY "
        "founder-behavior evidence (shipping history, wins, profile). Assess "
        "the PERSON: builder velocity, persistence, range. " + CITE_RULES +
        " Respond JSON: {score: 1-10, rating: string, rationale: string (<=80 words), "
        "cited_event_ids: [int], confidence: float, insufficient_evidence: bool}",
        json.dumps({
            "deterministic_founder_score": breakdown.total,
            "score_components": breakdown.components,
            "trend": breakdown.trend,
            "evidence": ship,
        }),
    )


def market_axis(events: list[dict], thesis: dict) -> dict:
    context = evidence_digest(events, {"application", "accelerator_batch", "launch"})
    return _llm(
        "You are the Market axis agent of a VC brain. You see ONLY the "
        "venture/market context (what they're building, for whom), NOT the "
        "founder's history. Rate the market: bullish, neutral, or bear, with "
        "sizing logic in the rationale. Consider fit to the fund thesis. "
        + CITE_RULES +
        " Respond JSON: {score: 1-10, rating: 'bullish'|'neutral'|'bear', "
        "rationale: string (<=80 words), cited_event_ids: [int], "
        "confidence: float, insufficient_evidence: bool}",
        json.dumps({"thesis": thesis, "evidence": context}),
    )


def idea_axis(events: list[dict]) -> dict:
    product = evidence_digest(events, {"launch", "repo_launch", "application"})
    return _llm(
        "You are the Idea-vs-Market axis agent of a VC brain. You see ONLY "
        "product evidence (what was actually shipped and how it was received). "
        "Judge: does the idea survive scrutiny as-is, or is this a bet that "
        "the team can pivot? " + CITE_RULES +
        " Respond JSON: {score: 1-10, rating: 'survives'|'needs_pivot'|'weak', "
        "rationale: string (<=80 words), cited_event_ids: [int], "
        "confidence: float, insufficient_evidence: bool}",
        json.dumps({"evidence": product}),
    )


def draft_memo(name: str, events: list[dict], axes: dict, thesis: dict) -> dict:
    return _llm(
        "You write evidence-locked VC investment memos. Required sections "
        "ONLY (brief-mandated): company_snapshot, investment_hypotheses, swot, "
        "problem_product, traction_kpis. Each section is a list of claim "
        "objects {id: 'c1'.., text, evidence_ids, gap: bool} (company_snapshot "
        "is a single claim list of 1-2 items). Financials, cap table, customer "
        "references are NOT in evidence: include them as explicit gap claims "
        "in traction_kpis. Padding counts against you. " + CITE_RULES +
        " Respond JSON: {company_snapshot: [claim], investment_hypotheses: "
        "[claim], swot: {strengths: [claim], weaknesses: [claim], "
        "opportunities: [claim], risks: [claim]}, problem_product: [claim], "
        "traction_kpis: [claim]}",
        json.dumps({"founder": name, "thesis": thesis, "axes": axes,
                    "evidence": evidence_digest(events)}),
        max_tokens=4000,
    )


def _iter_claims(memo: dict):
    for section, val in memo.items():
        items = (
            [c for lst in val.values() for c in lst] if isinstance(val, dict)
            else val if isinstance(val, list) else []
        )
        for c in items:
            if isinstance(c, dict) and "text" in c:
                yield section, c


def validate(memo: dict, events: list[dict]) -> dict:
    claims = [
        {"claim_id": f"{sec}:{c.get('id', i)}", "text": c["text"],
         "evidence_ids": c.get("evidence_ids", []), "gap": c.get("gap", False)}
        for i, (sec, c) in enumerate(_iter_claims(memo))
    ]
    return _llm(
        "You are an adversarial validator. For each claim, try to REFUTE it "
        "using the evidence list: does the cited evidence actually say what "
        "the claim says? Verdicts: 'supported' (evidence clearly backs it), "
        "'weak' (partially/indirectly backed), 'contradicted' (evidence says "
        "otherwise or ids don't support it), 'gap' (claim correctly flags "
        "missing data). trust is 0.0-1.0. Be skeptical: when uncertain, "
        "choose 'weak' and lower trust. Respond JSON: {verdicts: "
        "[{claim_id, verdict, trust, note (<=25 words)}]}",
        json.dumps({"claims": claims, "evidence": evidence_digest(events)}),
        max_tokens=4000,
    )


def decide(breakdown, axes: dict, validation: dict, thesis: dict, fit) -> dict:
    """Deterministic decision rule — the LLM never makes this call.
    The thesis parameterizes the bars: risk appetite sets thresholds,
    disqualifiers and sector fit gate the outcome, check size sets the amount."""
    bars = thesis_mod.decision_bars(thesis)
    contradicted = [v for v in validation.get("verdicts", [])
                    if v.get("verdict") == "contradicted"]
    f, m, i = axes["founder"], axes["market"], axes["idea"]
    reasons = []
    if fit.disqualified:
        reasons.append(f"matches thesis disqualifier(s): {', '.join(fit.disqualified)}")
    if f.get("score", 0) < bars["founder_bar"]:
        reasons.append(f"founder axis {f.get('score')}/10 below bar ({bars['founder_bar']})")
    if m.get("rating") == "bear":
        reasons.append("market axis is bear")
    if i.get("score", 0) < bars["idea_bar"] and f.get("score", 0) < 8:
        reasons.append("idea weak and founder not strong enough to pivot-bet")
    if fit.fit == 0:
        off_ok = bars["off_thesis_ok_if_founder"]
        if off_ok is not None and f.get("score", 0) >= off_ok:
            pass  # high risk appetite: exceptional founder overrides sector fit
        else:
            reasons.append("outside thesis sectors (fit 0)")
    if contradicted:
        reasons.append(f"{len(contradicted)} contradicted claim(s) unresolved")
    fund = not reasons
    if fund:
        reasons.append("all bars cleared through the fund lens, no contradicted claims")
    check = thesis.get("check_size_usd", 100000)
    return {
        "decision": f"FUND ${check:,.0f}" if fund else "PASS",
        "rule": (f"risk_appetite={bars['appetite']}: fund iff no disqualifier AND "
                 f"founder>={bars['founder_bar']} AND market!=bear AND "
                 f"(idea>={bars['idea_bar']} OR founder>=8) AND on-thesis "
                 f"AND zero contradicted claims"),
        "reasons": reasons,
        "thesis_fit": {"fit": fit.fit, "matched": fit.matched,
                       "disqualified": fit.disqualified},
        "deterministic_founder_score": breakdown.total,
    }


def generate_memo(conn, entity_id: int, fresh: bool = False) -> dict:
    existing = [e for e in ledger.events_for(conn, entity_id)
                if e["event_type"] == "memo"]
    if existing and not fresh:
        return existing[-1]["payload"]

    row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    events = ledger.events_for(conn, entity_id)
    breakdown = score.founder_score(conn, entity_id)
    thesis = load_thesis()
    fit = thesis_mod.fit(events, thesis)

    axes = {
        "founder": founder_axis(events, breakdown),
        "market": market_axis(events, thesis),
        "idea": idea_axis(events),
    }
    memo = draft_memo(row["canonical_name"], events, axes, thesis)
    validation = validate(memo, events)
    decision = decide(breakdown, axes, validation, thesis, fit)

    result = {
        "entity_id": entity_id,
        "founder": row["canonical_name"],
        "thesis": thesis,
        "axes": axes,
        "memo": memo,
        "validation": validation,
        "decision": decision,
        "model": MODEL,
        "generated_at": ledger.utcnow_iso(),
    }
    ledger.record(
        conn, entity_id, "system", "memo", result["generated_at"],
        f"system:memo:{entity_id}:{result['generated_at']}", result,
    )
    return result


def main() -> None:
    p = argparse.ArgumentParser(prog="vcbrain.intelligence")
    p.add_argument("--entity", type=int, required=True)
    p.add_argument("--fresh", action="store_true")
    args = p.parse_args()
    conn = db.connect()
    print(json.dumps(generate_memo(conn, args.entity, fresh=args.fresh), indent=2))


if __name__ == "__main__":
    main()
