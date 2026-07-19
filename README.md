# 🧠 The VC Brain

**An AI-first VC operating system that finds exceptional founders before anyone else — and can defend every call it makes.**

Hack-Nation 6th Global AI Hackathon · Challenge 2 · **Maschmeyer Group** — *"Deploying $100K checks in 24 hours."*
Built by team **tokenlimit**.

**▶ Live demo → https://vc-brain-production-a828.up.railway.app** &nbsp;·&nbsp; Backtested **2.62× lift** over base rate (n = 400)

---

## Why this exists

Today capital flows through networks, not merit. Founders stay invisible until they know the right person — their story scattered across GitHub repos, half-built sites, and posts nobody's reading. The VC Brain surfaces founders from their **public footprints**, scores them the moment they ship, and takes an opportunity end-to-end from first signal to a **$100K FUND / PASS decision** — with a Founder Score that follows the *person* across companies and a per-claim Trust Score on every memo.

## The one design rule

> Every team has the same LLM. So the LLM only works at the **edges** (extraction, judgment). Everything between is **deterministic, timestamped, and replayable.**

- Every fact is an **event** in an append-only ledger (source-tagged, deduped, never deleted).
- The **Founder Score is a fold over those events** → trends and time-travel (`--as-of`) come for free, and every point traces to the exact event ids behind it.
- **Entity resolution** merges the same human across sources on hard evidence only — and each merge is itself a ledger event (auditable identity).

Same events in → same number out. A judge can inspect a *system*, not a prompt.

## ▶ Try it in 60 seconds (no setup)

Open the [live demo](https://vc-brain-production-a828.up.railway.app) and:

1. **"We already knew you."** On `/apply`, apply as a founder we've already sourced → your application **merges into a profile the system already built**, score history waiting.
2. **Upload a pitch deck.** On `/apply`, attach a `.pptx`. We read the slides, extract the claims, and **cross-check them against what we independently sourced** — an inflated "12,000 GitHub stars" against a real 41 gets flagged *contradicted*, not trusted. (Sample decks in [`data/sample_decks/`](data/sample_decks).)
3. **Click any memo claim → its exact evidence lights up** (`/memo/{id}`). No number exists without a receipt; missing data says *"not disclosed"* instead of being invented.
4. **Read `/backtest`** — a measured **2.62× lift** over the base success rate, *including the founders we scored low who later succeeded*. An honest system shows its misses.

## What makes it different

- **Backtested, not vibes.** Froze 400 real founders' footprints at June 2021, predicted, checked real 2026 outcomes: 10.5% base rate → 27.5% top-decile = **2.62× lift**. False positives and missed hits are published in the report.
- **Trust, per claim.** An adversarial validator *tries to refute* every memo claim against the evidence; each claim gets a Trust Score, and gaps are flagged — never filled in.
- **Cold-start aware.** An explicit method + confidence score for founders with *no* track record — exactly the people a fund wants to find first — instead of pretending the data is there.
- **Honest data provenance.** Contacts are **self-declared only** (no scraping); pitch-deck numbers are self-reported until corroborated; curated/synthetic data is tagged `source="curated"` forever and weighted as lower trust.
- **The $100K call is a deterministic rule**, parameterised by a configurable fund thesis. The LLM writes the rationale; it never makes the decision.

## Architecture

Four layers. Sourcing feeds Memory, Memory feeds Intelligence, Intelligence produces a Decision, and a PASS loops back into Memory — every screening sharpens the next.

```
 SOURCING            MEMORY                 INTELLIGENCE            DECISION
 ─────────           ──────                 ────────────            ────────
 Outbound scan  ┐                       ┌ Thesis Engine ┐
  GitHub · HN   │   Entity resolution   │ (fund config  │
  arXiv · YC    ├─▶ (one human, many ───┤  → filters)   ├──▶ Evidence memo ──▶ $100K
  Devpost       │   sources)            │ 3 axis agents │    per-claim Trust    FUND / PASS
  LinkedIn      │        │              │  Founder      │    (gaps flagged)     + 24h timer
               │        ▼              │  Market       │         ▲                  │
 Inbound apply ┘  Append-only ledger   │  Idea         │    Adversarial            │
  deck + name      → Founder Score      │  (never       │    validator             │
                   → Backtest           └  averaged)  ──┘    (refutes claims)       │
                        ▲                                                           │
                        └──────────────── PASS ≠ forget: signals keep flowing ──────┘
```

## Feature tour (mapped to the challenge brief)

| Brief item | What we built | Where |
|---|---|---|
| Thesis Engine (1) | Investor-editable sectors / stage / check size / risk → compiled to filters + weights | `/thesis` |
| Smart data collection (2) | 7 connectors + cross-source entity resolution + append-only ledger | `vcbrain/connectors/` |
| Multi-attribute reasoning (3) | Natural-language founder search, LLM parses → deterministic matcher | `/search` |
| Inbound apply + **deck ingestion** (4) | `.pptx` upload → extracted claims → cross-checked vs the ledger | `/apply` |
| Outbound identify + **Activate** (5) | Sourced founders + evidence-grounded cold-outreach drafts with a real send destination | `/activate/{id}` |
| 3-axis screening, never averaged (6) | Founder / Market / Idea agents, each on its own evidence slice, with per-axis trend | `/memo/{id}` |
| Evidence memo + Trust Score (7) | Only the brief-required sections; every claim carries a trust verdict | `/memo/{id}` |
| Founder Score | Deterministic 0–100 fold, persists across companies, backtested | `/founder/{id}` |
| Agentic traceability (stretch) | Claim → exact ledger event, everywhere | across the app |

The **Founder Score** is a deterministic fold over weighted, evidence-cited components: shipping cadence (20), momentum (20), consistency (10), breadth of sources (10), external validation (10), experience (15), technical depth (15) — each citing the exact events behind it.

## Quickstart (local)

```bash
uv sync
cp .env.example .env          # add OPENAI_API_KEY for memos; the data spine runs without any keys

uv run python -m vcbrain.cli init
uv run python -m vcbrain.cli ingest hn --days 7
uv run python -m vcbrain.cli ingest github --days 14 --min-stars 20
uv run python -m vcbrain.cli ingest arxiv --category cs.AI --max 100
uv run python -m vcbrain.cli top --n 15
uv run python -m vcbrain.cli show --entity <id>

uv run uvicorn vcbrain.app:app --reload      # → http://localhost:8000
```

Prefer the pre-seeded snapshot? `cp data/vcbrain-seed.sqlite3 vcbrain.db` before running the app.

## Repo layout

```
vcbrain/
  db.py            SQLite schema (entities + events)
  ledger.py        append-only event store, as-of replay, merge clusters
  entities.py      deterministic cross-source entity resolution
  score.py         Founder Score — auditable fold, per-component evidence + confidence + cold-start
  thesis.py        configurable fund thesis → filters, weights, decision bars
  intelligence.py  the ONLY place the LLM runs: 3 axis agents, validator, memo, outreach, deck extract
  trust.py         deterministic per-claim Trust Score from the validator's verdicts
  backtest.py      freeze-at-T evaluation → measured lift over base rate
  contacts.py      self-declared email / LinkedIn from GitHub + HN (no scraping; abstains)
  deck.py          .pptx pitch-deck ingestion + deterministic deck-claim vs ledger check
  curated.py       optional synthetic-persona enrichment, tagged + lower-trust
  search.py        natural-language founder search
  cli.py           ingest / stats / top / show / enrich-contacts
  app.py           FastAPI demo surface (server-rendered, zero external assets)
  connectors/      github · hackernews · arxiv · ycombinator · devpost · linkedin · tavily
```

## Data & ethics

All sourced founders are **real people found through public footprints** (GitHub, Hacker News, arXiv, YC, Devpost, and public LinkedIn via search — never scraping or login). The demo *applicants* (DataForge, NimbusRL, …) are **synthetic**, and curated enrichment is tagged `source="curated"` and weighted as lower trust so it can never masquerade as independently-verified evidence. Secrets live only in a local `.env` (git-ignored) and the deployment's environment — never in the repo.

## Team — tokenlimit

- **Meera Mer** — [@meeramer173](https://github.com/meeramer173)
- **Muhammad Talal Anwar**
- **Hamza Manzoor** — [@HamzaManzoor66](https://github.com/HamzaManzoor66)
- **Harshil Mistry** — [@harshil79](https://github.com/harshil79)
