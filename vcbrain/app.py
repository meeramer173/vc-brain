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
from . import search as search_mod
from . import thesis as thesis_mod
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
tr[id^=ev]{scroll-margin-top:1rem} tr:target td{background:#fff3bf;transition:background .3s}
.chip{background:#eef;border-radius:9px;padding:.1rem .5rem;font-size:.82rem;margin-right:.3rem}
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
        f"<nav><a href='/'>Founders</a> <a href='/search'>Search</a> "
        f"<a href='/apply'>Apply (inbound)</a> "
        f"<a href='/thesis'>Thesis</a> <a href='/backtest'>Backtest</a></nav>{body}</body></html>"
    )


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


_HANDLE_LABELS = {"github": "GitHub", "hn": "Hacker News", "arxiv_name": "arXiv",
                  "devpost_name": "Devpost", "yc_slug": "YC", "applicant_name": "applied"}


def _handles_html(handles_json: str) -> str:
    """Render the stored handles JSON as readable chips + links, not raw JSON."""
    try:
        h = json.loads(handles_json)
    except (ValueError, TypeError):
        return ""
    parts = []
    for k, v in h.items():
        if k == "urls":
            for u in v:
                parts.append(f"<a href='{esc(u)}'>{esc(u.split('//')[-1])}</a>")
        else:
            parts.append(f"<span class='chip'>{esc(_HANDLE_LABELS.get(k, k))}: {esc(v)}</span>")
    return " ".join(parts)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _fit_cell(f) -> str:
    if f.disqualified:
        return (f"<span class='pill down'>disqualified</span> "
                f"<span class='note'>{esc(', '.join(f.disqualified))}</span>")
    if f.fit == 0:
        return "<span class='pill flat'>off-thesis</span>"
    chips = esc(", ".join(f.matched[:4]))
    return f"<span class='pill up'>{f.fit:.0%}</span> <span class='note'>{chips}</span>"


@app.get("/", response_class=HTMLResponse)
def dashboard(n: int = 25, as_of: str | None = None, lens: str = "on"):
    conn = db.connect()
    st = ledger.stats(conn)
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    th = thesis_mod.load_thesis()

    if lens != "raw":
        ranked = thesis_mod.rank_with_lens(conn, th, n=n, as_of=cutoff)
        rows = "".join(
            f"<tr><td class='num'>{i}</td>"
            f"<td><a href='/founder/{eid}'>{esc(name)}</a></td>"
            f"<td class='num'><b>{blended}</b></td>"
            f"<td class='num'>{b.total}</td>"
            f"<td>{_fit_cell(f)}</td>"
            f"<td><span class='pill {'up' if b.trend=='improving' else 'down' if b.trend=='declining' else 'flat'}'>{b.trend}</span></td>"
            f"<td>{esc(', '.join(b.sources))}</td>"
            f"<td class='num'>{b.n_events}</td></tr>"
            for i, (eid, name, b, f, blended) in enumerate(ranked, 1)
        )
        header = ("<tr><th>#</th><th>founder</th><th>lens score</th><th>raw</th>"
                  "<th>thesis fit</th><th>trend</th><th>sources</th><th>events</th></tr>")
        lens_line = (
            f"<p>🔍 fund lens: <b>{esc(th['fund_name'])}</b> — every ranking is "
            f"filtered &amp; scored through it (<a href='/thesis'>edit thesis</a> · "
            f"<a href='/?lens=raw'>view raw scores</a>)</p>"
        )
    else:
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
        header = ("<tr><th>#</th><th>founder</th><th>score</th><th>trend</th>"
                  "<th>sources</th><th>events</th></tr>")
        lens_line = ("<p>viewing raw Founder Scores (no fund lens) — "
                     "<a href='/'>back to thesis view</a></p>")

    time_travel = (
        f"<p class='note'>viewing the world as of {esc(as_of)} — "
        f"<a href='/'>back to today</a></p>" if as_of else
        "<p class='note'>time travel: add ?as_of=YYYY-MM-DD to see what the "
        "system knew on any date</p>"
    )
    body = (
        f"<p>{st['events']} signals · {st['entities']} entities · "
        f"{st['merged_away']} identities merged · sources: "
        f"{esc(', '.join(st['events_by_source']))}</p>{lens_line}{time_travel}"
        f"<table>{header}{rows}</table>"
    )
    return page("The VC Brain — ranked founders", body)


EXAMPLE_QUERY = ("technical founder, AI infra, enterprise traction, "
                 "no prior VC backing, top-tier accelerator")


def _spec_chips(spec: dict) -> str:
    """Render the parsed query so the LLM edge is fully inspectable."""
    chips = []
    if spec.get("sectors"):
        chips.append(f"sectors: {esc(', '.join(spec['sectors']))}")
    for flag, label in [("technical", "technical"), ("researcher", "researcher"),
                        ("hackathon_winner", "hackathon winner"),
                        ("accelerator", "top-tier accelerator")]:
        if spec.get(flag):
            chips.append(label)
    if spec.get("languages"):
        chips.append(f"language: {esc(', '.join(spec['languages']))}")
    if isinstance(spec.get("min_founder_score"), (int, float)):
        chips.append(f"score ≥ {spec['min_founder_score']}")
    if spec.get("trend") == "improving":
        chips.append("trend improving")
    inner = " ".join(f"<span class='pill up'>{c}</span>" for c in chips) or \
        "<span class='note'>no structured constraints — showing top founders</span>"
    how = ("deterministic keyword fallback (LLM unavailable)" if spec.get("_fallback")
           else f"parsed by {esc(intelligence.MODEL)} into structured attributes")
    return (f"<p class='note'>How the system read your query "
            f"({how}) — matching &amp; ranking below are 100% deterministic:</p>"
            f"<p>{inner}</p>")


@app.get("/search", response_class=HTMLResponse)
def search_view(q: str | None = None, n: int = 25, as_of: str | None = None):
    form = (
        "<h2>Multi-attribute founder search</h2>"
        "<p class='note'>Ask in plain language — one compound query, not five "
        "filters. The LLM only parses your words into structured attributes; "
        "the search itself is deterministic evidence-matching over the ledger.</p>"
        f"<form method='get' action='/search'>"
        f"<input name='q' value=\"{esc(q or '')}\" placeholder=\"{esc(EXAMPLE_QUERY)}\" "
        f"style='width:640px'><button>Search</button></form>"
        f"<p class='note'>try: <a href='/search?q={esc(EXAMPLE_QUERY)}'>{esc(EXAMPLE_QUERY)}</a></p>"
    )
    if not q or not q.strip():
        return page("Search founders", form)

    conn = db.connect()
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    spec, matches, notes, meta = search_mod.run(conn, q.strip(), n=n, as_of=cutoff)

    disclosure_html = ""
    if notes:
        items = "".join(f"<li>{esc(x)}</li>" for x in notes)
        disclosure_html = (
            "<div class='banner' style='background:#5c4d1a'>Honest disclosure — "
            "constraints the current sources can't filter on:<ul style='margin:.4rem 0'>"
            f"{items}</ul></div>"
        )

    if not matches:
        body = (form + _spec_chips(spec) + disclosure_html +
                "<p>No founder in Memory satisfies every constraint. "
                "Loosen the query, or <a href='/'>browse all founders</a>.</p>")
        return page("Search founders", body)

    def _attr_pills(m) -> str:
        if not m.attrs:
            return "<span class='note'>top founder (no constraints given)</span>"
        return " ".join(
            f"<span class='pill {'up' if a.ok else 'down'}' title='{esc(a.detail)}'>"
            f"{'✓' if a.ok else '✗'} {esc(a.label)}</span>"
            for a in m.attrs
        )

    n_constraints = len(matches[0].attrs) if matches else 0
    rows = "".join(
        f"<tr><td class='num'>{i}</td>"
        f"<td><a href='/founder/{m.entity_id}'>{esc(m.name)}</a>"
        + (" <span class='pill up' title='matches every constraint'>★ all</span>" if m.perfect and m.n_total > 1 else "")
        + "</td>"
        f"<td class='num'>{len(m.satisfied)}/{m.n_total}</td>"
        f"<td class='num'><b>{m.breakdown.total}</b></td>"
        f"<td><span class='pill {'up' if m.breakdown.trend=='improving' else 'down' if m.breakdown.trend=='declining' else 'flat'}'>{m.breakdown.trend}</span></td>"
        f"<td>{_attr_pills(m)}</td>"
        f"<td class='num'>{m.breakdown.n_events}</td></tr>"
        for i, m in enumerate(matches, 1)
    )
    header = ("<tr><th>#</th><th>founder</th><th>match</th><th>score</th><th>trend</th>"
              "<th>constraints (✓ satisfied · ✗ not — hover for evidence)</th><th>events</th></tr>")
    n_perfect = sum(1 for m in matches if m.perfect and m.n_total > 1)
    relax_note = (
        "<p class='note'>No founder matched the requested sector, so this shows "
        "the closest matches on the other constraints instead.</p>"
        if meta.get("relaxed") else ""
    )
    summary = (
        f"<p><b>{len(matches)}</b> "
        + ("closest" if meta.get("relaxed") else "topically-relevant")
        + " founder(s), ranked by constraints satisfied then Founder Score"
        + (f" — <b>{n_perfect}</b> satisfy all {n_constraints}." if n_constraints > 1 else ".")
        + "</p>"
    )
    body = (form + _spec_chips(spec) + disclosure_html + relax_note + summary +
            f"<table>{header}{rows}</table>")
    return page("Search founders", body)


@app.get("/thesis", response_class=HTMLResponse)
def thesis_form(saved: int = 0):
    th = thesis_mod.load_thesis()
    banner = ("<div class='banner'>Thesis saved — the <a style='color:#fff' "
              "href='/'>dashboard ranking</a> now reflects it.</div>" if saved else "")
    body = f"""
    {banner}
    <h2>Thesis Engine — the fund lens</h2>
    <p class='note'>Every recommendation is filtered and scored through this
    configuration: sector keywords drive the fit score on the dashboard, risk
    appetite sets the decision-rule bars, disqualifiers gate hard, and check
    size flows into the final decision.</p>
    <form method='post' action='/thesis'>
      <label>Fund name</label><input name='fund_name' value="{esc(th['fund_name'])}">
      <label>Sectors (comma-separated keywords — these are matched against founder evidence)</label>
      <input name='sectors' value="{esc(', '.join(th['sectors']))}" style='width:640px'>
      <label>Disqualifiers (comma-separated keywords — hard gate)</label>
      <input name='disqualifiers' value="{esc(', '.join(th['disqualifiers']))}" style='width:640px'>
      <label>Risk appetite (high / medium / low — sets decision bars)</label>
      <input name='risk_appetite' value="{esc(th['risk_appetite'])}">
      <label>Check size (USD)</label><input name='check_size_usd' value="{th['check_size_usd']}">
      <label>Stage</label><input name='stage' value="{esc(th['stage'])}">
      <label>Geography</label><input name='geography' value="{esc(th['geography'])}">
      <label>Ownership target</label><input name='ownership_target' value="{esc(th['ownership_target'])}">
      <button>Save thesis</button>
    </form>
    <p class='note'>Honesty notes: current sources carry no reliable location
    signal, so geography is recorded but not filtered; outbound-sourced
    founders are pre-formal by construction, so stage is trivially satisfied.
    Neither is silently faked.</p>"""
    return page("Thesis Engine", body)


@app.post("/thesis")
async def thesis_save(request: Request):
    form = await request.form()
    th = thesis_mod.load_thesis()
    for key in ("fund_name", "risk_appetite", "stage", "geography", "ownership_target"):
        if form.get(key):
            th[key] = form[key].strip()
    for key in ("sectors", "disqualifiers"):
        if form.get(key) is not None:
            th[key] = [s.strip() for s in form[key].split(",") if s.strip()]
    try:
        th["check_size_usd"] = int(str(form.get("check_size_usd", th["check_size_usd"])).replace(",", "").replace("$", ""))
    except ValueError:
        pass
    thesis_mod.save_thesis(th)
    return RedirectResponse("/thesis?saved=1", status_code=303)


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
        f"<td>{' '.join(f'<a href=\"#ev{i}\">#{i}</a>' for i in b.evidence[comp][:10])}</td></tr>"
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
        f"<p class='note'>{_handles_html(row['handles'])}</p>"
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


def _render_claims(section: str, claims: list, verdicts: dict, start_idx: int,
                   entity_id: int) -> tuple[str, int]:
    out = []
    idx = start_idx
    for c in claims:
        cid = f"{section}:{c.get('id', idx)}"
        v = verdicts.get(cid, {})
        verdict = v.get("verdict", "unchecked")
        pill = VERDICT_CLASS.get(verdict, "flat")
        # Evidence anchors live on the founder timeline, not this page — link there.
        ev = " ".join(f"<a href='/founder/{entity_id}#ev{i}'>#{i}</a>"
                      for i in c.get("evidence_ids", []))
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
                lis, idx = _render_claims(sec_name, claims or [], verdicts, idx, entity_id)
                inner += f"<p><b>{esc(quad.title())}</b></p><ul>{lis}</ul>"
            sections_html += f"<h3>{title}</h3>{inner}"
        elif isinstance(val, list):
            lis, idx = _render_claims(sec_name, val, verdicts, idx, entity_id)
            sections_html += f"<h3>{title}</h3><ul>{lis}</ul>"

    d = r["decision"]
    fund = d["decision"].startswith("FUND")
    tf = d.get("thesis_fit")
    fit_line = ""
    if tf:
        fit_desc = (f"disqualified: {', '.join(tf['disqualified'])}" if tf["disqualified"]
                    else f"fit {tf['fit']:.0%}" + (f" (matched: {', '.join(tf['matched'][:5])})" if tf["matched"] else " — off-thesis"))
        fit_line = f"<br><span style='font-size:.8rem'>thesis lens: {esc(fit_desc)}</span>"
    decision_html = (
        f"<div class='banner' style='background:{'#1b5e20' if fund else '#7a1f1f'}'>"
        f"{'✓' if fund else '✗'} {esc(d['decision'])} — {esc('; '.join(d['reasons']))}"
        f"<br><span style='font-size:.8rem'>deterministic rule: {esc(d['rule'])} · "
        f"LLM writes rationale, never the decision</span>{fit_line}</div>"
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
