# The VC Brain

Hack-Nation 6th Global AI Hackathon · Challenge 2 (Maschmeyer Group).

An AI-first VC operating system: **Sourcing → Screening → Diligence → Decision**,
built on an append-only signal ledger with a persistent, backtested Founder Score
and per-claim evidence tracing.

## Design rule

Every team has the same LLM. The LLM works only at the edges (extraction,
judgment); everything between is **deterministic, timestamped, and replayable**:

- Every fact = an **event** in an append-only ledger (source-tagged, deduped).
- The **Founder Score is a fold over events** → trends and time-travel (`--as-of`)
  come for free, and every number traces to the event ids that produced it.
- Entity resolution merges the same human across sources on hard evidence only —
  merges are themselves ledger events (auditable identity).

## Quickstart

```bash
uv sync
cp .env.example .env          # fill in keys as needed (spine runs without any)
uv run python -m vcbrain.cli init
uv run python -m vcbrain.cli ingest hn --days 7
uv run python -m vcbrain.cli ingest yc --since-year 2024
uv run python -m vcbrain.cli ingest github --days 14 --min-stars 10
uv run python -m vcbrain.cli ingest arxiv --category cs.AI --max 100
uv run python -m vcbrain.cli top --n 15
uv run python -m vcbrain.cli show --entity <id>
```

## Layout

```
vcbrain/
  db.py           SQLite schema (entities + events)
  ledger.py       append-only event store, as-of replay, merge clusters
  entities.py     deterministic cross-source entity resolution
  score.py        Founder Score v0 — auditable fold, per-component evidence
  cli.py          ingest / stats / top / show
  connectors/     hn, yc, github, arxiv (devpost + producthunt TODO)
```

## Team split (suggested)

- **A — data spine & sourcing** (this scaffold): more connectors (Devpost,
  Product Hunt), momentum scanner tuning, entity-resolution edge cases.
- **B — intelligence**: thesis engine, 3-axis agents (disjoint evidence slices,
  never averaged), adversarial validator, memo with per-claim Trust Score.
  Needs `ANTHROPIC_API_KEY`.
- **C — backtest**: freeze 2019–21 Show HN/Devpost cohorts at time T with
  `--as-of`, evaluate vs known 2026 outcomes, report lift + failure cases.
- **D — experience**: FastAPI + dashboard; inbound application endpoint
  ("we already knew you" merge), memo click-through to evidence, decision timer.

## Rubric anchors (from the challenge brief)

- Data Architecture & Intelligence 30% — sourcing depth + explicit cold-start method
- Investment Utility & Execution 30% — end-to-end to a $100K decision + funnel timer
- Intelligent Analysis & Trust 25% — per-claim Trust Score, honest gaps
- UX 15% — thin dashboard, one signature interaction (claim → evidence)
