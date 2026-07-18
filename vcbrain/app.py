"""The VC Brain — demo surface.

Deliberately thin (UX is 15% of the rubric): server-rendered HTML, no build
step, one signature interaction — every score component links to the exact
ledger events behind it. The "we already knew you" moment happens on inbound
application via the same entity resolution the outbound scanner uses.

Run:  uv run uvicorn vcbrain.app:app --reload
"""

import html
import json
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import db, intelligence, ledger, score
from .entities import Resolver

app = FastAPI(title="The VC Brain")

CSS = """
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:2rem auto;
padding:0 1rem;color:#1a1a2e;background:#fafafa}
h1{font-size:1.5rem} h1 a{color:inherit;text-decoration:none}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{padding:.45rem .6rem;border-bottom:1px solid #eee;text-align:left;font-size:.92rem}
th{background:#f0f0f5} tr:hover td{background:#f6f8ff}
a{color:#2952cc} .pill{border-radius:9px;padding:.1rem .5rem;font-size:.8rem}
.up{background:#d3f9d8}.flat{background:#f0f0f0}.down{background:#ffe3e3}
.banner{background:#153e75;color:#fff;padding:1rem;border-radius:8px;margin:1rem 0;font-size:1.05rem}
.note{color:#777;font-size:.85rem} .num{font-variant-numeric:tabular-nums}
.timer{background:#fff3bf;padding:.6rem 1rem;border-radius:8px;display:inline-block;margin:.5rem 0}
form label{display:block;margin:.6rem 0 .15rem;font-size:.9rem}
input{padding:.4rem;width:320px;border:1px solid #ccc;border-radius:5px}
button{margin-top:1rem;padding:.5rem 1.4rem;background:#153e75;color:#fff;border:0;border-radius:6px;cursor:pointer}
nav a{margin-right:1rem}
"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1><a href='/'>The VC Brain</a></h1>"
        f"<nav><a href='/'>Founders</a> <a href='/apply'>Apply (inbound)</a> "
        f"<a href='/backtest'>Backtest</a></nav>{body}</body></html>"
    )


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


@app.get("/", response_class=HTMLResponse)
def dashboard(n: int = 25, as_of: str | None = None):
    conn = db.connect()
    st = ledger.stats(conn)
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    ranked = score.rank_founders(conn, n=n, as_of=cutoff)
    rows = "".join(
        f"<tr><td class='num'>{i}</td>"
        f"<td><a href='/founder/{eid}'>{esc(name)}</a></td>"
        f"<td class='num'>{b.total}</td>"
        f"<td><span class='pill {'up' if b.trend=='improving' else 'down' if b.trend=='declining' else 'flat'}'>{b.trend}</span></td>"
        f"<td>{esc(', '.join(b.sources))}</td>"
        f"<td class='num'>{b.n_events}</td></tr>"
        for i, (eid, name, b) in enumerate(ranked, 1)
    )
    time_travel = (
        f"<p class='note'>viewing the world as of {esc(as_of)} — "
        f"<a href='/'>back to today</a></p>" if as_of else
        "<p class='note'>time travel: add ?as_of=YYYY-MM-DD to see what the "
        "system knew on any date</p>"
    )
    body = (
        f"<p>{st['events']} signals · {st['entities']} entities · "
        f"{st['merged_away']} identities merged · sources: "
        f"{esc(', '.join(st['events_by_source']))}</p>{time_travel}"
        f"<table><tr><th>#</th><th>founder</th><th>score</th><th>trend</th>"
        f"<th>sources</th><th>events</th></tr>{rows}</table>"
    )
    return page("The VC Brain — ranked founders", body)


@app.get("/founder/{entity_id}", response_class=HTMLResponse)
def founder(entity_id: int, as_of: str | None = None, applied: int = 0):
    conn = db.connect()
    row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return page("Not found", "<p>No such entity.</p>")
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    b = score.founder_score(conn, entity_id, as_of=cutoff)
    events = ledger.events_for(conn, entity_id, as_of=cutoff)

    banner = ""
    apps = [e for e in events if e["event_type"] == "application"]
    if apps:
        app_ev = apps[-1]
        prior = [e for e in events if e["event_ts"] < app_ev["event_ts"]
                 and e["source"] not in ("inbound", "system")]
        if prior and applied:
            n_src = len({e["source"] for e in prior})
            banner = (
                f"<div class='banner'>★ We already knew you — this founder "
                f"existed in Memory with {len(prior)} prior signal{'s' if len(prior) != 1 else ''} from "
                f"{n_src} source{'s' if n_src != 1 else ''} before they applied. "
                f"The Founder Score below was waiting for them.</div>"
            )
        due = ledger.parse_ts(app_ev["event_ts"]) + timedelta(hours=24)
        first_signal = ledger.parse_ts(events[0]["event_ts"])
        applied_at = ledger.parse_ts(app_ev["event_ts"])
        banner += (
            f"<div class='timer'>⏱ first signal → application: "
            f"{(applied_at - first_signal).days}d · $100K decision due "
            f"{due.strftime('%Y-%m-%d %H:%M')}Z</div>"
        )

    comps = "".join(
        f"<tr><td>{comp}</td><td class='num'>{pts} / {score.WEIGHTS[comp]}</td>"
        f"<td>{' '.join(f'<a href=#ev{i}>#{i}</a>' for i in b.evidence[comp][:10])}</td></tr>"
        for comp, pts in b.components.items()
    )
    notes = "".join(f"<p class='note'>! {esc(n)}</p>" for n in b.notes)
    timeline = "".join(
        f"<tr id='ev{e['id']}'><td class='num'>#{e['id']}</td><td>{esc(e['event_ts'][:10])}</td>"
        f"<td>{esc(e['source'])}/{esc(e['event_type'])}</td>"
        f"<td>{esc(e['payload'].get('title') or e['payload'].get('repo') or e['payload'].get('project') or e['payload'].get('one_liner') or '')}"
        + (f" <a href='{esc(e['payload']['url'])}'>↗</a>" if e['payload'].get('url') else "")
        + f"</td><td class='num'>{e['payload'].get('points') or e['payload'].get('stars') or ''}</td></tr>"
        for e in reversed(events)
    )
    body = (
        f"{banner}<h2>{esc(row['canonical_name'])} "
        f"<span class='pill {'up' if b.trend=='improving' else 'down' if b.trend=='declining' else 'flat'}'>{b.trend}</span></h2>"
        f"<p><a href='/memo/{entity_id}'>→ Investment memo &amp; $100K decision</a></p>"
        f"<p class='note'>handles: {esc(row['handles'])}</p>"
        f"<h3>Founder Score: {b.total} <span class='note'>as of {esc(b.as_of[:10])}</span></h3>"
        f"<table><tr><th>component</th><th>points</th><th>evidence (click)</th></tr>{comps}</table>{notes}"
        f"<h3>Timeline ({len(events)} events, newest first)</h3>"
        f"<table><tr><th>id</th><th>when</th><th>signal</th><th>what</th><th>pts</th></tr>{timeline}</table>"
    )
    return page(row["canonical_name"], body)


@app.get("/apply", response_class=HTMLResponse)
def apply_form():
    body = """
    <h2>Founder application</h2>
    <p class='note'>Minimum bar per the brief: company + name. Handles are
    optional — if we've seen you before, we already know.</p>
    <form method='post' action='/apply'>
      <label>Founder name *</label><input name='name' required>
      <label>Company name *</label><input name='company' required>
      <label>One-liner</label><input name='one_liner'>
      <label>HN username</label><input name='hn'>
      <label>GitHub username</label><input name='github'>
      <label>Website</label><input name='url'>
      <button>Apply for $100K</button>
    </form>"""
    return page("Apply", body)


@app.post("/apply")
async def apply_submit(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    company = (form.get("company") or "").strip()
    if not name or not company:
        return RedirectResponse("/apply", status_code=303)
    handles: dict = {}
    if form.get("hn"):
        handles["hn"] = form["hn"].strip()
    if form.get("github"):
        handles["github"] = form["github"].strip()
    if form.get("url"):
        handles["urls"] = [form["url"].strip()]
    if not handles:
        handles = {"applicant_name": name.lower()}

    conn = db.connect()
    eid = Resolver(conn).get_or_create("person", name, handles)
    now = ledger.utcnow_iso()
    ledger.record(
        conn, eid, "inbound", "application", now,
        f"inbound:app:{company.lower()}:{now[:10]}",
        {"company": company, "one_liner": (form.get("one_liner") or "").strip(),
         "founder_name": name},
    )
    return RedirectResponse(f"/founder/{eid}?applied=1", status_code=303)


@app.get("/backtest", response_class=HTMLResponse)
def backtest_view():
    root = Path(__file__).resolve().parent.parent
    report_file = next(
        (p for p in (root / "backtest_report_full.json", root / "backtest_report.json") if p.exists()),
        None,
    )
    if report_file is None:
        return page("Backtest", "<p>No backtest report yet — run vcbrain.backtest.</p>")
    r = json.loads(report_file.read_text())
    top = "".join(
        f"<tr><td>{esc(t['name'])}</td><td class='num'>{t['score_at_t']}</td>"
        f"<td>{'✓ hit' if t['outcome']['hit'] else 'no'}</td>"
        f"<td class='num'>{t['outcome']['best_post_t_points']}</td></tr>"
        for t in r["top_decile"]
    )
    misses = "".join(
        f"<tr><td>{esc(m['name'])}</td><td class='num'>{m['score_at_t']}</td>"
        f"<td class='num'>{m['best_post_t_points']}</td></tr>"
        for m in r["missed_hits_below_median"]
    )
    body = (
        f"<h2>Does the score predict anything? We tested it.</h2>"
        f"<p>Cohort: Show HN founders {esc(r['window'])}, footprints frozen at "
        f"{esc(r['as_of'][:10])} — zero future information. Outcome: {esc(r['hit_definition'])}.</p>"
        f"<table><tr><th>cohort</th><th>base rate</th><th>precision @ top decile</th><th>lift</th>"
        f"<th>mean score (hits)</th><th>mean score (misses)</th></tr>"
        f"<tr class='num'><td>{r['cohort_size']}</td><td>{r['base_rate']:.1%}</td>"
        f"<td>{r['precision_at_top_decile']:.1%}</td><td><b>{r['lift']}x</b></td>"
        f"<td>{r['mean_score_hits']}</td><td>{r['mean_score_misses']}</td></tr></table>"
        f"<h3>Top decile at time T ({len(r['top_decile'])})</h3>"
        f"<table><tr><th>founder</th><th>score @ T</th><th>outcome</th><th>best post-T pts</th></tr>{top}</table>"
        f"<h3>Where we were wrong ({len(r['missed_hits_below_median'])} missed hits below median)</h3>"
        f"<p class='note'>An honest system shows its misses.</p>"
        f"<table><tr><th>founder</th><th>score @ T</th><th>later hit (pts)</th></tr>{misses}</table>"
    )
    return page("Backtest", body)


VERDICT_CLASS = {"supported": "up", "weak": "flat", "contradicted": "down", "gap": "flat"}


def _render_claims(section: str, claims: list, verdicts: dict, start_idx: int) -> tuple[str, int]:
    out = []
    idx = start_idx
    for c in claims:
        cid = f"{section}:{c.get('id', idx)}"
        v = verdicts.get(cid, {})
        verdict = v.get("verdict", "unchecked")
        pill = VERDICT_CLASS.get(verdict, "flat")
        ev = " ".join(f"<a href='#ev{i}'>#{i}</a>" for i in c.get("evidence_ids", []))
        gap = " <b>[GAP — flagged, not guessed]</b>" if c.get("gap") else ""
        out.append(
            f"<li>{esc(c.get('text'))}{gap} "
            f"<span class='pill {pill}' title='{esc(v.get('note', ''))}'>"
            f"{verdict} · trust {v.get('trust', '—')}</span> "
            f"<span class='note'>{ev}</span></li>"
        )
        idx += 1
    return "".join(out), idx


@app.get("/memo/{entity_id}", response_class=HTMLResponse)
def memo_view(entity_id: int, fresh: int = 0):
    conn = db.connect()
    row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return page("Not found", "<p>No such entity.</p>")
    r = intelligence.generate_memo(conn, entity_id, fresh=bool(fresh))

    axes_html = "".join(
        f"<td style='vertical-align:top'><b>{ax.upper()}</b><br>"
        f"<span style='font-size:1.6rem' class='num'>{v.get('score', '—')}/10</span><br>"
        f"{esc(v.get('rating', ''))}<br><span class='note'>confidence {v.get('confidence', '—')}"
        f"{' · insufficient evidence' if v.get('insufficient_evidence') else ''}</span>"
        f"<p class='note'>{esc(v.get('rationale', ''))}</p></td>"
        for ax, v in r["axes"].items()
    )
    verdicts = {v["claim_id"]: v for v in r["validation"].get("verdicts", [])}

    sections_html, idx = "", 0
    memo = r["memo"]
    for sec_name, title in [
        ("company_snapshot", "Company snapshot"),
        ("investment_hypotheses", "Investment hypotheses"),
        ("swot", "SWOT"),
        ("problem_product", "Problem & product"),
        ("traction_kpis", "Traction & KPIs"),
    ]:
        val = memo.get(sec_name)
        if isinstance(val, dict):  # SWOT quadrants
            inner = ""
            for quad, claims in val.items():
                lis, idx = _render_claims(sec_name, claims or [], verdicts, idx)
                inner += f"<p><b>{esc(quad.title())}</b></p><ul>{lis}</ul>"
            sections_html += f"<h3>{title}</h3>{inner}"
        elif isinstance(val, list):
            lis, idx = _render_claims(sec_name, val, verdicts, idx)
            sections_html += f"<h3>{title}</h3><ul>{lis}</ul>"

    d = r["decision"]
    fund = d["decision"].startswith("FUND")
    decision_html = (
        f"<div class='banner' style='background:{'#1b5e20' if fund else '#7a1f1f'}'>"
        f"{'✓' if fund else '✗'} {esc(d['decision'])} — {esc('; '.join(d['reasons']))}"
        f"<br><span style='font-size:.8rem'>deterministic rule: {esc(d['rule'])} · "
        f"LLM writes rationale, never the decision</span></div>"
    )
    body = (
        f"<h2>Investment memo — {esc(r['founder'])}</h2>"
        f"<p class='note'>model {esc(r['model'])} · generated {esc(r['generated_at'])} · "
        f"thesis: {esc(r['thesis']['fund_name'])} · "
        f"<a href='/memo/{entity_id}?fresh=1'>regenerate</a> · "
        f"<a href='/founder/{entity_id}'>evidence timeline</a></p>"
        f"{decision_html}"
        f"<h3>Three axes — scored independently, never averaged</h3>"
        f"<table><tr>{axes_html}</tr></table>"
        f"{sections_html}"
        f"<p class='note'>Every claim carries a per-claim Trust Score from an "
        f"adversarial validator that tried to refute it against the ledger. "
        f"Evidence links jump to the founder timeline.</p>"
    )
    return page(f"Memo — {r['founder']}", body)


@app.get("/api/founders")
def api_founders(n: int = 50, as_of: str | None = None):
    conn = db.connect()
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    ranked = score.rank_founders(conn, n=n, as_of=cutoff)
    return JSONResponse([
        {"id": eid, "name": name, "score": b.total, "trend": b.trend,
         "sources": b.sources, "n_events": b.n_events}
        for eid, name, b in ranked
    ])


@app.get("/api/founder/{entity_id}")
def api_founder(entity_id: int, as_of: str | None = None):
    conn = db.connect()
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    b = score.founder_score(conn, entity_id, as_of=cutoff)
    return JSONResponse({
        "id": entity_id, "score": b.total, "trend": b.trend,
        "components": b.components, "evidence": b.evidence,
        "notes": b.notes, "as_of": b.as_of,
        "events": ledger.events_for(conn, entity_id, as_of=cutoff),
    })
