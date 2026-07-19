"""Seed the demo inbound applicants (with deterministic, baked-in memos).

Four founders apply, giving the demo every outcome:
  • DataForge AI  — inflated deck (12k stars / 50k users) → the Trust layer
    catches the fabrication → DECLINE.
  • NimbusRL      — real multi-source traction, on-thesis → FUND $100K.
  • LedgerLoop    — solid builder, but payments/fintech → DECLINE (off-thesis).
  • SynthMind     — early and thin → DECLINE (founder below bar).

Memos are baked deterministically (trust.py computes the numbers; no LLM), so
the whole story is demo-proof.

Also seeds one outbound-sourced founder — Owen Colegrove (SciPhi, GitHub
emrgnt-cmplxty) — with real repos + his self-declared GitHub email/LinkedIn, to
demonstrate the Verified-contact block and Activate's real send destination.

Usage:
  python seed_demo.py --golden                                   # into vcbrain.db (local)
  python seed_demo.py --golden --db data/vcbrain-seed.sqlite3    # into the committed snapshot
"""

import argparse
from datetime import datetime, timedelta, timezone

from vcbrain import contacts, db, intelligence, ledger, score, trust
from vcbrain import thesis as thesis_mod
from vcbrain.entities import Resolver

U = "https://example.com"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


# Each applicant: evidence events, the application one-liner, memo claims, axes.
# claim = (section, id, text, [evidence indices | "app"], gap, verdict, claim_type)
APPLICANTS = [
    {
        "name": "Nova Reeves", "company": "DataForge AI", "github": "novareeves",
        "one_liner": "AI data pipelines — 12,000 GitHub stars, 50,000 users, $1.2M ARR",
        "evidence": [
            ("github", "repo_launch", 45, "dataforge",
             {"repo": "dataforge", "stars": 41, "description": "ai data pipeline toolkit", "url": U}),
            ("hn", "launch", 30, "dataforge",
             {"title": "Show HN: DataForge – reliable AI data pipelines", "points": 6,
              "num_comments": 2, "url": U}),
        ],
        "claims": [
            ("company_snapshot", "c1", "DataForge AI builds AI data pipelines; its only external footprint is one public repo and a Show HN launch.", [0, 1], False, "supported", "fact"),
            ("investment_hypotheses", "h1", "Ships in public — a working open-source repo plus a Hacker News launch.", [0, 1], False, "supported", "fact"),
            ("investment_hypotheses", "h2", "Early Hacker News reception suggests genuine developer pull.", [1], False, "supported", "inference"),
            ("traction_kpis", "t1", "The core repository has 12,000 GitHub stars.", [0], False, "supported", "fact"),
            ("traction_kpis", "t2", "The product has 50,000 active users.", ["app"], False, "supported", "fact"),
            ("traction_kpis", "t3", "Revenue / ARR: not disclosed in verifiable evidence.", [], True, "gap", "gap"),
            ("problem_product", "p1", "Teams struggle to run reliable AI data pipelines; DataForge offers a managed one.", [1], False, "supported", "fact"),
        ],
        "axes": {
            "founder": (6, "Emerging builder", 0.5, "Ships in public, but a thin history: one repo and a launch."),
            "market": (5, "neutral", 0.3, "Crowded AI-tooling space; sizing unclear from evidence."),
            "idea": (6, "survives", 0.4, "Plausible product; execution and traction unproven."),
        },
    },
    {
        "name": "Sofia Almeida", "company": "NimbusRL", "github": "sofia-nimbus",
        "one_liner": "Open-source RL training and serving infrastructure for AI teams",
        "evidence": [
            ("github", "repo_launch", 60, "nimbusrl",
             {"repo": "nimbus-rl", "stars": 2400, "description": "open-source reinforcement-learning infrastructure for ai teams", "url": U}),
            ("github", "repo_launch", 40, "rlserve",
             {"repo": "rl-serve", "stars": 900, "description": "low-latency model serving infrastructure", "url": U}),
            ("arxiv", "paper", 75, "nimbusrl",
             {"title": "Scalable Reinforcement-Learning Serving Infrastructure", "url": U}),
            ("hn", "launch", 30, "nimbusrl",
             {"title": "Show HN: NimbusRL — open-source RL infrastructure for AI teams",
              "points": 180, "num_comments": 40, "url": U}),
        ],
        "claims": [
            ("company_snapshot", "c1", "NimbusRL builds open-source reinforcement-learning training and serving infrastructure for AI teams.", [0, 1, 2, 3], False, "supported", "fact"),
            ("investment_hypotheses", "h1", "Prolific builder — two well-starred open-source repos, a published paper, and a strong Show HN.", [0, 1, 2, 3], False, "supported", "fact"),
            ("investment_hypotheses", "h2", "Squarely on-thesis: AI infrastructure with real, multi-source developer traction.", [1, 3], False, "supported", "inference"),
            ("traction_kpis", "t1", "nimbus-rl has 2,400 GitHub stars.", [0], False, "supported", "fact"),
            ("traction_kpis", "t2", "rl-serve has 900 GitHub stars.", [1], False, "supported", "fact"),
            ("traction_kpis", "t3", "Revenue: not disclosed in verifiable evidence.", [], True, "gap", "gap"),
            ("problem_product", "p1", "AI teams struggle to serve RL models at low latency; NimbusRL provides that infrastructure.", [1, 2], False, "supported", "fact"),
        ],
        "axes": {
            "founder": (8, "Exceptional multi-artifact builder", 0.7, "Two strong repos, a paper, and a well-received launch — consistent shipping across sources."),
            "market": (7, "bullish", 0.55, "AI infrastructure is expanding fast; scalable RL serving is a real, growing need."),
            "idea": (7, "survives", 0.6, "Clear product with genuine early traction; survives scrutiny as-is."),
        },
    },
    {
        "name": "Marcus Kane", "company": "LedgerLoop", "github": "marcuskane",
        "one_liner": "Automated B2B payments reconciliation for finance teams",
        "evidence": [
            ("github", "repo_launch", 50, "ledgerloop",
             {"repo": "ledgerloop", "stars": 600, "description": "automated payments reconciliation for finance teams", "url": U}),
            ("hn", "launch", 25, "ledgerloop",
             {"title": "Show HN: LedgerLoop — automated payments reconciliation", "points": 45,
              "num_comments": 8, "url": U}),
        ],
        "claims": [
            ("company_snapshot", "c1", "LedgerLoop automates B2B payments reconciliation for finance teams.", [0, 1], False, "supported", "fact"),
            ("investment_hypotheses", "h1", "Solid builder with a real product and early Show HN interest.", [0, 1], False, "supported", "fact"),
            ("traction_kpis", "t1", "ledgerloop has 600 GitHub stars.", [0], False, "supported", "fact"),
            ("traction_kpis", "t2", "Revenue: not disclosed in verifiable evidence.", [], True, "gap", "gap"),
            ("problem_product", "p1", "Finance teams waste hours reconciling payments; LedgerLoop automates it.", [1], False, "supported", "fact"),
        ],
        "axes": {
            "founder": (7, "Capable builder", 0.55, "Shipped a real, starred product with early traction."),
            "market": (6, "neutral", 0.4, "Payments reconciliation is a real but competitive niche."),
            "idea": (6, "survives", 0.5, "Clear, useful product — but outside the fund's sectors."),
        },
    },
    {
        "name": "Priya Nair", "company": "SynthMind", "github": "priyanair",
        "one_liner": "AI note-taking that summarizes your meetings",
        "evidence": [
            ("hn", "launch", 20, "synthmind",
             {"title": "Show HN: SynthMind — AI meeting notes", "points": 8, "num_comments": 1, "url": U}),
            ("github", "repo_launch", 18, "synthmind",
             {"repo": "synthmind", "stars": 30, "description": "ai note-taking that summarizes meetings", "url": U}),
        ],
        "claims": [
            ("company_snapshot", "c1", "SynthMind is an AI note-taker that summarizes meetings.", [0, 1], False, "supported", "fact"),
            ("investment_hypotheses", "h1", "Very early: a single small repo and a low-traction Show HN.", [0, 1], False, "weak", "fact"),
            ("traction_kpis", "t1", "synthmind has 30 GitHub stars.", [1], False, "supported", "fact"),
            ("traction_kpis", "t2", "Users / revenue: not disclosed in verifiable evidence.", [], True, "gap", "gap"),
            ("problem_product", "p1", "Meeting notes are tedious; SynthMind summarizes them automatically.", [0], False, "supported", "inference"),
        ],
        "axes": {
            "founder": (5, "Early, thin track record", 0.35, "One small repo and a low-signal launch — not enough to judge yet."),
            "market": (5, "neutral", 0.3, "AI note-taking is crowded; differentiation unclear."),
            "idea": (4, "needs_pivot", 0.3, "Thin evidence; the idea does not yet stand out."),
        },
    },
]


def _eid_by_dedup(conn, key: str):
    r = conn.execute("SELECT id FROM events WHERE dedup_key=?", (key,)).fetchone()
    return r["id"] if r else None


def bake(conn, spec: dict) -> tuple[int, dict]:
    r = Resolver(conn)
    eid = r.get_or_create("person", spec["name"],
                          {"github": spec["github"], "applicant_name": spec["name"].lower()})
    ev_ids = []
    for (src, typ, days, suffix, payload) in spec["evidence"]:
        key = f"{src}:demo:{suffix}"
        ev_ids.append(ledger.record(conn, eid, src, typ, _days_ago(days), key, payload)
                      or _eid_by_dedup(conn, key))
    app_key = f"inbound:app:{spec['company'].lower()}:{_days_ago(0)[:10]}"
    app_id = ledger.record(conn, eid, "inbound", "application", ledger.utcnow_iso(), app_key,
                           {"company": spec["company"], "founder_name": spec["name"],
                            "one_liner": spec["one_liner"]}) or _eid_by_dedup(conn, app_key)

    memo: dict = {}
    authored: dict = {}
    for (section, cid, text, idxs, gap, verdict, ctype) in spec["claims"]:
        eids = [app_id if x == "app" else ev_ids[x] for x in idxs]
        memo.setdefault(section, []).append(
            {"id": cid, "text": text, "evidence_ids": eids, "gap": gap})
        authored[f"{section}:{cid}"] = (verdict, ctype)

    events = ledger.events_for(conn, eid)
    claims = [
        {"claim_id": f"{sec}:{c.get('id', i)}", "text": c["text"],
         "evidence_ids": c.get("evidence_ids", []), "gap": c.get("gap", False)}
        for i, (sec, c) in enumerate(intelligence._iter_claims(memo))
    ]
    verdicts = [{"claim_id": cid, "verdict": v, "claim_type": ct, "note": ""}
                for cid, (v, ct) in authored.items()]
    validation = trust.score_all(claims, verdicts, events)

    axes = {}
    for ax, (sc, rating, conf, rationale) in spec["axes"].items():
        axes[ax] = {"score": sc, "rating": rating, "confidence": conf,
                    "rationale": rationale, "cited_event_ids": ev_ids[:3],
                    "insufficient_evidence": sc < 6}

    breakdown = score.founder_score(conn, eid)
    thesis = thesis_mod.load_thesis()
    fit = thesis_mod.fit(events, thesis)
    decision = intelligence.decide(breakdown, axes, validation, thesis, fit)

    now = ledger.utcnow_iso()
    result = {"entity_id": eid, "founder": spec["name"], "thesis": thesis, "axes": axes,
              "memo": memo, "validation": validation, "decision": decision,
              "model": "golden-demo (deterministic trust, no LLM)", "generated_at": now}
    ledger.record(conn, eid, "system", "memo", now, f"system:memo:{eid}:{now}", result)
    return eid, decision


# Outbound-sourced founders: we found them from public signals; they have NOT
# applied. Owen is the worked example for the self-declared-contact + Activate
# feature. Values are the REAL ones from the GitHub API (repo stars/dates, and
# the email/LinkedIn he publicly declares in his bio + social_accounts),
# hardcoded so the seed stays deterministic and offline — no live fetch needed.
OUTBOUND_FOUNDERS = [
    {
        "name": "Owen Colegrove",
        "github": "emrgnt-cmplxty",
        "urls": ["https://github.com/emrgnt-cmplxty"],
        # (repo, stars, language, event_ts, description, url) — real values;
        # event_ts is each repo's real creation date.
        "repos": [
            ("emrgnt-cmplxty/automata", 680, "Python", "2023-06-20T00:00:00Z",
             "Automata: A self-coding agent", "https://github.com/emrgnt-cmplxty/automata"),
            ("emrgnt-cmplxty/zero-shot-replication", 74, "Python", "2023-08-24T00:00:00Z",
             "", "https://github.com/emrgnt-cmplxty/zero-shot-replication"),
            ("emrgnt-cmplxty/SmolTrainer", 21, "Python", "2023-08-31T00:00:00Z",
             "", "https://github.com/emrgnt-cmplxty/SmolTrainer"),
        ],
        # Self-declared on GitHub: email in the profile bio, LinkedIn in social_accounts.
        "contact": {
            "email": "owen@sciphi.ai",
            "linkedin": "https://www.linkedin.com/in/owencolegrove",
            "twitter": "ocolegro", "blog": None,
            "sources": {"email": "github:bio", "linkedin": "github:social_accounts"},
        },
    },
]


def seed_outbound(conn, spec: dict) -> int:
    """Seed an outbound-sourced founder: real repo shipping signals + the
    contact info they self-declared on GitHub. Idempotent — stable repo dedup
    keys, and record_contact is content-addressed. No memo/application (they
    haven't applied); the founder page + Activate read this directly."""
    eid = Resolver(conn).get_or_create(
        "person", spec["name"], {"github": spec["github"], "urls": spec["urls"]})
    for (repo, stars, lang, ts, desc, url) in spec["repos"]:
        ledger.record(
            conn, eid, "github", "repo_launch", ts, f"github:demo-outbound:{repo}",
            {"repo": repo, "stars": stars, "language": lang, "description": desc, "url": url},
        )
    contacts.record_contact(conn, eid, dict(spec["contact"]))
    return eid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true", help="bake deterministic memos (no LLM)")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args()
    conn = db.connect(args.db)
    for spec in APPLICANTS:
        if args.golden:
            eid, decision = bake(conn, spec)
            print(f"  {spec['company']:<14} → #{eid}  {decision['decision']}")
        else:
            eid = Resolver(conn).get_or_create(
                "person", spec["name"],
                {"github": spec["github"], "applicant_name": spec["name"].lower()})
            print(f"  seeded {spec['company']} → #{eid}")
    for spec in OUTBOUND_FOUNDERS:
        eid = seed_outbound(conn, spec)
        print(f"  outbound {spec['name']:<16} → #{eid}  (self-declared contact)")
    print(f"done ({args.db})")


if __name__ == "__main__":
    main()
