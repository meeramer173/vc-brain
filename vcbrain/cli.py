"""vcbrain CLI — ingest sources, inspect the ledger, rank founders.

Examples:
    python -m vcbrain.cli init
    python -m vcbrain.cli ingest hn --days 7
    python -m vcbrain.cli ingest yc --since-year 2024
    python -m vcbrain.cli ingest github --days 14 --min-stars 10
    python -m vcbrain.cli ingest arxiv --category cs.AI --max 100
    python -m vcbrain.cli ingest tavily --limit 30            # enrich top founders
    python -m vcbrain.cli ingest tavily --limit 30 --domains linkedin.com,x.com
    python -m vcbrain.cli stats
    python -m vcbrain.cli top --n 15 [--as-of 2026-06-01]
    python -m vcbrain.cli show --entity 42
"""

import argparse
import json

from . import db, ledger, score
from .connectors import base
from .connectors import arxiv as arxiv_conn
from .connectors import devpost as devpost_conn
from .connectors import github as github_conn
from .connectors import hackernews as hn_conn
from .connectors import tavily as tavily_conn
from .connectors import ycombinator as yc_conn


def cmd_ingest(args) -> None:
    conn = db.connect()
    if args.source == "hn":
        signals = hn_conn.fetch_show_hn(days=args.days)
        result = base.ingest(conn, "hn", signals)
    elif args.source == "yc":
        signals = yc_conn.fetch_companies(since_year=args.since_year)
        result = base.ingest(conn, "yc", signals)
    elif args.source == "github":
        signals = github_conn.fetch_new_starred_repos(
            days=args.days, min_stars=args.min_stars
        )
        result = base.ingest(conn, "github", signals)
    elif args.source == "arxiv":
        signals = arxiv_conn.fetch_recent_papers(
            category=args.category, max_results=args.max
        )
        result = base.ingest(conn, "arxiv", signals)
    elif args.source == "devpost":
        signals = devpost_conn.fetch_winners(
            max_rows=args.max_rows, offset=args.offset
        )
        result = base.ingest(conn, "devpost", signals)
    elif args.source == "tavily":
        # Enrichment source: pull existing founders (most-active first) and
        # search the web for independent coverage of each. Handles come
        # straight from the ledger so ingest() re-attaches to the same
        # entity instead of minting a new one.
        rows = conn.execute(
            """
            SELECT e.id, e.canonical_name, e.handles, COUNT(ev.id) AS c
            FROM entities e LEFT JOIN events ev ON ev.entity_id = e.id
            WHERE e.kind = 'person' AND e.merged_into IS NULL
            GROUP BY e.id
            ORDER BY c DESC, e.id ASC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        targets = [
            {"name": r["canonical_name"], "handles": json.loads(r["handles"])}
            for r in rows
        ]
        domains = (
            [d.strip() for d in args.domains.split(",") if d.strip()]
            if args.domains
            else None
        )
        signals = tavily_conn.fetch_web_signals(
            targets,
            per_entity=args.per_entity,
            min_relevance=args.min_relevance,
            include_domains=domains,
        )
        result = base.ingest(conn, "tavily", signals)
    else:
        raise SystemExit(f"unknown source: {args.source}")
    print(json.dumps(result, indent=2))


def cmd_stats(_args) -> None:
    conn = db.connect()
    print(json.dumps(ledger.stats(conn), indent=2))


def cmd_top(args) -> None:
    conn = db.connect()
    as_of = f"{args.as_of}T23:59:59Z" if args.as_of else None
    ranked = score.rank_founders(conn, n=args.n, as_of=as_of)
    print(f"{'#':>3} {'id':>5}  {'score':>5}  {'trend':<10} {'src':<3}  name")
    for i, (eid, name, b) in enumerate(ranked, 1):
        print(
            f"{i:>3} {eid:>5}  {b.total:>5.1f}  {b.trend:<10}"
            f" {len(b.sources):<3}  {name}"
        )


def cmd_show(args) -> None:
    conn = db.connect()
    row = conn.execute(
        "SELECT * FROM entities WHERE id = ?", (args.entity,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"no entity {args.entity}")
    b = score.founder_score(conn, args.entity, as_of=args.as_of)
    print(f"entity {row['id']} [{row['kind']}] {row['canonical_name']}")
    print(f"handles: {row['handles']}")
    print(f"\nFounder Score {b.total} ({b.trend}) as of {b.as_of}")
    for comp, pts in b.components.items():
        ev = b.evidence[comp]
        print(f"  {comp:<20} {pts:>5.1f} / {score.WEIGHTS[comp]:<3}  evidence: events {ev[:8]}")
    for note in b.notes:
        print(f"  ! {note}")
    print("\ntimeline:")
    for e in ledger.events_for(conn, args.entity):
        title = (
            e["payload"].get("title")
            or e["payload"].get("repo")
            or e["payload"].get("one_liner")
            or e["event_type"]
        )
        print(f"  {e['event_ts']}  [{e['source']}/{e['event_type']}] #{e['id']} {title}")


def main() -> None:
    p = argparse.ArgumentParser(prog="vcbrain")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the database")

    pi = sub.add_parser("ingest", help="pull a source into the ledger")
    pi.add_argument(
        "source", choices=["hn", "yc", "github", "arxiv", "devpost", "tavily"]
    )
    pi.add_argument("--days", type=int, default=7)
    pi.add_argument("--since-year", type=int, default=2024)
    pi.add_argument("--min-stars", type=int, default=10)
    pi.add_argument("--category", default="cs.AI")
    pi.add_argument("--max", type=int, default=100)
    pi.add_argument("--max-rows", type=int, default=10000)
    pi.add_argument("--offset", type=int, default=0)
    # tavily enrichment: --limit founders searched (~2 credits each),
    # --per-entity results kept per founder, --domains to focus (e.g. social)
    pi.add_argument("--limit", type=int, default=50)
    pi.add_argument("--per-entity", type=int, default=5)
    pi.add_argument("--min-relevance", type=float, default=0.2)
    pi.add_argument("--domains", default=None)
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("stats", help="ledger stats")
    ps.set_defaults(func=cmd_stats)

    pt = sub.add_parser("top", help="rank founders by score")
    pt.add_argument("--n", type=int, default=10)
    pt.add_argument("--as-of", default=None, help="YYYY-MM-DD time-travel cutoff")
    pt.set_defaults(func=cmd_top)

    pw = sub.add_parser("show", help="entity timeline + score breakdown")
    pw.add_argument("--entity", type=int, required=True)
    pw.add_argument("--as-of", default=None)
    pw.set_defaults(func=cmd_show)

    args = p.parse_args()
    if args.cmd == "init":
        db.connect()
        print(f"db ready at {db.DEFAULT_DB}")
        return
    args.func(args)


if __name__ == "__main__":
    main()
