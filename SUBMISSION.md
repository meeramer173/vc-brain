# Submission — The VC Brain (Challenge 02, Maschmeyer Group)

Draft for the 6-part structured form. Word counts follow the winning-submission
pattern from the 5th event (~440 words total). Edit freely.

## Problem & Challenge (~70 words)

Venture capital funds networks, not merit. Founders stay invisible until they
know the right person; diligence takes weeks; by the time a fund sees them,
equally strong founders have given up. Worst served are pre-track-record
founders: every commercial sourcing platform (Harmonic, Specter, Tracxn) keys
off digital exhaust — incorporations, job changes, funding history — so a
first-time builder with no network is structurally unseeable. The cold-start
founder is the industry's blind spot.

## Target Audience (~40 words)

Early-stage funds and solo GPs who want reach without an analyst team — and,
on the other side of the table, pre-track-record founders who deserve to be
found for what they ship, not who they know.

## Solution & Core Features (~105 words)

The VC Brain is an append-only signal ledger with reasoning on top. Five live
public sources (GitHub, Hacker News, arXiv, the YC directory, Devpost) stream
into deterministic entity resolution — one human across all platforms. The persistent Founder Score is a fold over timestamped
events: it trends, time-travels (--as-of), never resets, and every component
cites the exact events behind it. Inbound applications merge with profiles the
outbound scanner already built — "we already knew you." An investor-editable
Thesis Engine (sectors, risk appetite, check size, disqualifiers) filters and
re-ranks everything through the fund lens — flip the thesis, watch the same
pool reorder. Screening runs three axis agents (Founder / Market / Idea) on
disjoint evidence slices, never averaged. An adversarial validator assigns per-claim Trust Scores. A
deterministic rule — not the LLM — makes the $100K call inside 24 hours.

## Unique Selling Proposition (~60 words)

Every team has the same LLM; we made it work only at the edges. Everything
between is deterministic, timestamped, replayable — and tested: we froze 400
founders' footprints at June 2021 and measured 2.62x lift over base rate on
5-year outcomes, publishing our misses alongside. Gaps are flagged, never
filled. Honesty is the product.

## Implementation & Technology (~80 words)

Python 3.13 / FastAPI / SQLite event ledger (append-only; merges and memos are
themselves events), uv-managed, deployed on Render with a seeded snapshot.
Five live connectors with rate-limit-aware clients; entity resolution merges
only on hard evidence and records every merge as an auditable event. GPT-5-mini
powers the three axis agents, memo drafting, and the adversarial validator —
each receiving only its evidence slice. The decision rule, Founder Score, and
backtest are pure deterministic code.

## Results & Impact (~80 words)

Backtest (n=400, footprints frozen 2021, outcomes through 2026): base rate
10.5% → top-decile precision 27.5% = 2.62x lift; eventual hits scored 41.5 vs
27.8 at freeze time. 29 false positives and 8 missed hits are published in the
report — an honest system shows its misses. Live deployment sources real
founders continuously, produces evidence-locked memos with per-claim trust,
and instruments signal→decision time against the 24-hour promise. This is
equitable capital allocation as working infrastructure, not a slide.

## jury_scope (underused field — tell judges where to look)

Judge us on the data and reasoning layers (55% of the rubric): /backtest for
the measured 2.62x lift with published failure cases, /founder/{id} for
evidence-cited scoring, /memo/{id} for per-claim Trust Scores and explicit
gap flags, and the "we already knew you" inbound-outbound merge on /apply.

## Submission checklist

- [ ] Flip repo public: `gh repo edit meeramer173/vc-brain --visibility public --accept-visibility-change-consequences`
- [ ] Live demo URL: https://vc-brain.onrender.com (warm it up before judging)
- [ ] Demo video: apply → banner → evidence click → /backtest → memo trust pills → decision
- [ ] Paste the 6 sections above into the form
- [ ] GitHub repo link in the form
