"""Seed the demo 'catch': a synthetic inbound applicant whose deck inflates the
numbers, so the deterministic Trust Score catches the fabrication live.

Two evidence signals are real and modest (a 41-star repo, a small Show HN); the
applicant *claims* 12,000 stars / 50,000 users / $1.2M ARR. The memo repeats the
claims; trust.py checks each number against the cited event's payload and flips
the fabricated ones to 'contradicted' (trust 0.0), which blocks the $100K gate.

Usage:
  python seed_demo.py                 # create the applicant only (generate memo via the app + your API key)
  python seed_demo.py --golden        # also bake a deterministic memo (no LLM) so the demo is bulletproof
  python seed_demo.py --golden --db data/vcbrain-seed.sqlite3   # bake into the committed snapshot

After --golden, open  /memo/<id>  (the id is printed) and /founder/<id>.
Commit data/vcbrain-seed.sqlite3 if you seeded the snapshot so it survives a redeploy.
"""

import argparse
from datetime import datetime, timedelta, timezone

from vcbrain import db, intelligence, ledger, score
from vcbrain import thesis as thesis_mod
from vcbrain.entities import Resolver

NAME = "Nova Reeves"
COMPANY = "DataForge AI"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_events(conn) -> int:
    """Create the applicant + its (modest, real) evidence + the inflated application."""
    eid = Resolver(conn).get_or_create(
        "person", NAME, {"github": "novareeves", "applicant_name": NAME.lower()}
    )
    ledger.record(
        conn, eid, "github", "repo_launch", _days_ago(45),
        "github:demo:dataforge",
        {"repo": "dataforge", "stars": 41, "url": "https://github.com/novareeves/dataforge"},
    )
    ledger.record(
        conn, eid, "hn", "launch", _days_ago(30),
        "hn:demo:dataforge",
        {"title": "Show HN: DataForge – reliable AI data pipelines", "points": 6,
         "num_comments": 2, "url": "https://news.ycombinator.com/item?id=demo"},
    )
    ledger.record(
        conn, eid, "inbound", "application", ledger.utcnow_iso(),
        f"inbound:app:{COMPANY.lower()}:{_days_ago(0)[:10]}",
        {"company": COMPANY, "founder_name": NAME,
         "one_liner": "AI data pipelines — 12,000 GitHub stars, 50,000 users, $1.2M ARR"},
    )
    return eid


def _memo(gh_id: int, hn_id: int, app_id: int) -> dict:
    return {
        "company_snapshot": [
            {"id": "c1", "text": f"{COMPANY} builds AI data pipelines; its only external "
             "footprint is one public repo and a Show HN launch.",
             "evidence_ids": [gh_id, hn_id], "gap": False},
        ],
        "investment_hypotheses": [
            {"id": "h1", "text": "Ships in public — a working open-source repo plus a "
             "Hacker News launch.", "evidence_ids": [gh_id, hn_id], "gap": False},
            {"id": "h2", "text": "Early Hacker News reception suggests genuine developer "
             "pull.", "evidence_ids": [hn_id], "gap": False},
        ],
        "swot": {
            "strengths": [{"id": "s1", "text": "Demonstrated ability to ship and launch.",
                           "evidence_ids": [gh_id, hn_id], "gap": False}],
            "weaknesses": [{"id": "w1", "text": "Headline traction is unverified against "
                            "independent signals.", "evidence_ids": [gh_id], "gap": False}],
            "opportunities": [{"id": "o1", "text": "AI data-pipeline tooling is an "
                               "expanding developer market.", "evidence_ids": [hn_id],
                               "gap": False}],
            "risks": [{"id": "r1", "text": "Reported metrics appear inflated relative to "
                       "observable evidence.", "evidence_ids": [gh_id], "gap": False}],
        },
        "problem_product": [
            {"id": "p1", "text": "Teams struggle to run reliable AI data pipelines; "
             "DataForge offers a managed one.", "evidence_ids": [hn_id], "gap": False},
        ],
        "traction_kpis": [
            {"id": "t1", "text": "The core repository has 12,000 GitHub stars.",
             "evidence_ids": [gh_id], "gap": False},        # real evidence says 41 → caught
            {"id": "t2", "text": "The product has 50,000 active users.",
             "evidence_ids": [app_id], "gap": False},       # self-report, no hard number → caught
            {"id": "t3", "text": "Revenue / ARR: not disclosed in verifiable evidence.",
             "evidence_ids": [], "gap": True},              # honest gap
        ],
    }


# The LLM's job only: verdict + claim_type. The trust NUMBER is computed by trust.py.
# t1/t2 are authored as 'supported' on purpose — the model is fooled; Python overrides.
VERDICTS = {
    "company_snapshot:c1": ("supported", "fact"),
    "investment_hypotheses:h1": ("supported", "fact"),
    "investment_hypotheses:h2": ("supported", "inference"),
    "swot:s1": ("supported", "fact"),
    "swot:w1": ("weak", "inference"),
    "swot:o1": ("supported", "inference"),
    "swot:r1": ("weak", "inference"),
    "problem_product:p1": ("supported", "fact"),
    "traction_kpis:t1": ("supported", "fact"),
    "traction_kpis:t2": ("supported", "fact"),
    "traction_kpis:t3": ("gap", "gap"),
}


def bake_golden(conn, eid: int) -> None:
    from vcbrain import trust
    events = ledger.events_for(conn, eid)
    by = lambda src, typ: next(e["id"] for e in events
                               if e["source"] == src and e["event_type"] == typ)
    memo = _memo(by("github", "repo_launch"), by("hn", "launch"),
                 by("inbound", "application"))

    claims = [
        {"claim_id": f"{sec}:{c.get('id', i)}", "text": c["text"],
         "evidence_ids": c.get("evidence_ids", []), "gap": c.get("gap", False)}
        for i, (sec, c) in enumerate(intelligence._iter_claims(memo))
    ]
    verdicts = [{"claim_id": cid, "verdict": v, "claim_type": ct, "note": ""}
                for cid, (v, ct) in VERDICTS.items()]
    validation = trust.score_all(claims, verdicts, events)

    axes = {
        "founder": {"score": 6, "rating": "Emerging builder", "confidence": 0.5,
                    "rationale": "Ships in public, but a thin history: one repo and a launch.",
                    "cited_event_ids": [by("github", "repo_launch"), by("hn", "launch")],
                    "insufficient_evidence": False},
        "market": {"score": 5, "rating": "neutral", "confidence": 0.3,
                   "rationale": "Crowded AI-tooling space; sizing unclear from evidence.",
                   "cited_event_ids": [by("hn", "launch")], "insufficient_evidence": True},
        "idea": {"score": 6, "rating": "survives", "confidence": 0.4,
                 "rationale": "Plausible product; execution and traction unproven.",
                 "cited_event_ids": [by("github", "repo_launch")],
                 "insufficient_evidence": False},
    }

    breakdown = score.founder_score(conn, eid)
    thesis = thesis_mod.load_thesis()
    fit = thesis_mod.fit(events, thesis)
    decision = intelligence.decide(breakdown, axes, validation, thesis, fit)

    now = ledger.utcnow_iso()
    result = {
        "entity_id": eid, "founder": NAME, "thesis": thesis, "axes": axes,
        "memo": memo, "validation": validation, "decision": decision,
        "model": "golden-demo (deterministic trust, no LLM)", "generated_at": now,
    }
    ledger.record(conn, eid, "system", "memo", now,
                  f"system:memo:{eid}:{now}", result)
    s = validation["summary"]
    print(f"  baked golden memo · decision={decision['decision']} · "
          f"contradicted={s['contradicted']} · avg_trust={s['avg_trust']} · "
          f"gate_blocked={s['fund_gate_blocked']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true",
                    help="also bake a deterministic memo (no LLM) with the catch")
    ap.add_argument("--db", default=str(db.DEFAULT_DB),
                    help="DB path (use data/vcbrain-seed.sqlite3 to bake into the snapshot)")
    args = ap.parse_args()

    conn = db.connect(args.db)
    eid = seed_events(conn)
    print(f"seeded applicant '{NAME}' ({COMPANY}) → entity #{eid} in {args.db}")
    if args.golden:
        bake_golden(conn, eid)
    print(f"open  /memo/{eid}  and  /founder/{eid}")


if __name__ == "__main__":
    main()
