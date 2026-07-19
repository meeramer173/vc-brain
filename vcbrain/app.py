"""The VC Brain — demo surface.

Server-rendered HTML with zero build step and zero external assets: the whole
UI (styles, animations, interactions) ships from this file, so the live demo
cannot die on a missing CDN. The signature interaction survives every
redesign — every score component links to the exact ledger events behind it,
and the "we already knew you" moment happens on inbound application via the
same entity resolution the outbound scanner uses.

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
*{box-sizing:border-box}
:root{
  --bg:#060913;--card:#0d1526;--card2:#101a30;--border:#1c2a44;--border2:#27395c;
  --text:#e4ebf7;--muted:#8ea3c4;--faint:#5c7095;
  --indigo:#6d7cff;--cyan:#39d0ff;--green:#3ddc97;--red:#ff7a8a;--amber:#ffc94d;
}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,sans-serif;
  margin:0;background:var(--bg);color:var(--text);min-height:100vh;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
/* aurora backdrop */
body::before,body::after{content:'';position:fixed;inset:0;z-index:-2;pointer-events:none}
body::before{background:
  radial-gradient(600px 420px at 12% -8%,rgba(109,124,255,.20),transparent 62%),
  radial-gradient(720px 480px at 88% -12%,rgba(57,208,255,.13),transparent 60%),
  radial-gradient(900px 700px at 50% 118%,rgba(139,92,246,.10),transparent 62%);
  animation:aurora 16s ease-in-out infinite alternate}
body::after{background-image:
  linear-gradient(rgba(142,163,196,.045) 1px,transparent 1px),
  linear-gradient(90deg,rgba(142,163,196,.045) 1px,transparent 1px);
  background-size:44px 44px;
  -webkit-mask-image:radial-gradient(ellipse 90% 60% at 50% 0%,#000 30%,transparent 100%);
  mask-image:radial-gradient(ellipse 90% 60% at 50% 0%,#000 30%,transparent 100%)}
@keyframes aurora{from{transform:translateY(0) scale(1)}to{transform:translateY(26px) scale(1.05)}}

.wrap{max-width:1180px;margin:0 auto;padding:0 1.3rem}
main{padding:1.9rem 0 3rem}

/* ─── nav ─────────────────────────────────────────── */
header.top{position:sticky;top:0;z-index:50;background:rgba(6,9,19,.72);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid rgba(28,42,68,.8)}
.navbar{display:flex;align-items:center;gap:1.1rem;padding:.75rem 0;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:.55rem;text-decoration:none;margin-right:auto}
.brand svg{flex:none}
.brand b{font-size:1.06rem;letter-spacing:-.02em;
  background:linear-gradient(92deg,#fff 20%,var(--cyan) 65%,var(--indigo));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:#fff}
.navlinks{display:flex;gap:.25rem;flex-wrap:wrap}
.navlinks a{color:var(--muted);text-decoration:none;font-size:.9rem;font-weight:500;
  padding:.42rem .85rem;border-radius:99px;border:1px solid transparent;transition:all .22s}
.navlinks a:hover{color:var(--text);background:rgba(109,124,255,.10)}
.navlinks a.active{color:#fff;background:linear-gradient(120deg,rgba(109,124,255,.22),rgba(57,208,255,.14));
  border-color:rgba(109,124,255,.35)}
.live{display:inline-flex;align-items:center;gap:.4rem;font-size:.74rem;color:var(--green);
  letter-spacing:.08em;text-transform:uppercase;font-weight:600}
.live i{width:7px;height:7px;border-radius:50%;background:var(--green);
  box-shadow:0 0 0 0 rgba(61,220,151,.5);animation:pulse 2s infinite}
@keyframes pulse{70%{box-shadow:0 0 0 7px rgba(61,220,151,0)}100%{box-shadow:0 0 0 0 rgba(61,220,151,0)}}

/* ─── hero & typography ───────────────────────────── */
.hero{padding:1.6rem 0 .4rem}
.eyebrow{font-size:.74rem;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan);
  font-weight:700;margin:0 0 .6rem}
h1{font-size:clamp(1.7rem,3.6vw,2.5rem);line-height:1.13;letter-spacing:-.03em;margin:0 0 .55rem;font-weight:750}
h1 .grad{background:linear-gradient(92deg,var(--indigo),var(--cyan));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
h2{font-size:1.32rem;letter-spacing:-.02em;margin:1.6rem 0 .5rem}
h3{font-size:1.02rem;letter-spacing:-.01em;margin:1.5rem 0 .5rem;color:var(--text)}
.sub{color:var(--muted);font-size:1rem;max-width:46rem;margin:.1rem 0 1rem;line-height:1.55}
a{color:var(--cyan);text-decoration:none}
a:hover{text-decoration:underline}
.note{color:var(--faint);font-size:.84rem;line-height:1.5}
.num{font-variant-numeric:tabular-nums}

/* ─── cards ───────────────────────────────────────── */
.card{background:linear-gradient(165deg,var(--card2),var(--card));border:1px solid var(--border);
  border-radius:16px;padding:1.15rem 1.3rem;transition:border-color .25s,transform .25s,box-shadow .25s}
.card:hover{border-color:var(--border2)}
.grid-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.9rem;margin:1.2rem 0}
.stat{position:relative;overflow:hidden}
.stat::after{content:'';position:absolute;inset:0 0 auto;height:2px;
  background:linear-gradient(90deg,var(--indigo),var(--cyan),transparent)}
.stat b{display:block;font-size:1.9rem;letter-spacing:-.03em;font-weight:750;
  background:linear-gradient(120deg,#fff,#b9c6ff);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.stat span{color:var(--muted);font-size:.82rem}
.stat small{display:block;color:var(--faint);font-size:.74rem;margin-top:.25rem}

/* ─── tables ──────────────────────────────────────── */
.tablewrap{background:linear-gradient(165deg,var(--card2),var(--card));border:1px solid var(--border);
  border-radius:16px;overflow-x:auto;margin:1rem 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:.62rem .85rem;border-bottom:1px solid rgba(28,42,68,.65);text-align:left;vertical-align:middle}
th{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);
  font-weight:650;background:rgba(6,9,19,.35);white-space:nowrap}
tr:last-child td{border-bottom:0}
tbody tr,table tr{transition:background .18s}
tr:hover td{background:rgba(109,124,255,.06)}
td a{color:var(--text);font-weight:550}
td a:hover{color:var(--cyan)}
tr[id^=ev]{scroll-margin-top:5.5rem}
tr:target td{background:rgba(255,201,77,.14);box-shadow:inset 3px 0 0 var(--amber)}

/* ─── pills / chips / bars ────────────────────────── */
.pill{border-radius:99px;padding:.14rem .6rem;font-size:.76rem;font-weight:600;
  display:inline-block;border:1px solid transparent;white-space:nowrap}
.up{background:rgba(61,220,151,.12);color:var(--green);border-color:rgba(61,220,151,.3)}
.flat{background:rgba(142,163,196,.10);color:var(--muted);border-color:rgba(142,163,196,.22)}
.down{background:rgba(255,122,138,.10);color:var(--red);border-color:rgba(255,122,138,.3)}
.chip{background:rgba(109,124,255,.12);color:#b9c6ff;border:1px solid rgba(109,124,255,.3);
  border-radius:99px;padding:.14rem .6rem;font-size:.78rem;margin-right:.3rem;display:inline-block}
.sbar{width:74px;height:5px;border-radius:99px;background:rgba(142,163,196,.14);
  display:inline-block;vertical-align:middle;margin-left:.55rem;overflow:hidden}
.sbar i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--indigo),var(--cyan));animation:grow 1s cubic-bezier(.22,1,.36,1)}
@keyframes grow{from{width:0}}

/* ─── banners ─────────────────────────────────────── */
.banner{background:linear-gradient(120deg,rgba(109,124,255,.20),rgba(57,208,255,.10));
  border:1px solid rgba(109,124,255,.4);color:var(--text);padding:1rem 1.2rem;
  border-radius:14px;margin:1rem 0;font-size:1rem;line-height:1.5}
.banner a{color:var(--cyan)}
.banner.gold{background:linear-gradient(120deg,rgba(255,201,77,.14),rgba(255,201,77,.05));
  border-color:rgba(255,201,77,.4)}
.banner.go{background:linear-gradient(120deg,rgba(61,220,151,.16),rgba(61,220,151,.05));
  border-color:rgba(61,220,151,.45)}
.banner.no{background:linear-gradient(120deg,rgba(255,122,138,.14),rgba(255,122,138,.05));
  border-color:rgba(255,122,138,.45)}
.timer{background:rgba(255,201,77,.10);border:1px solid rgba(255,201,77,.35);color:var(--amber);
  padding:.55rem 1rem;border-radius:12px;display:inline-block;margin:.5rem 0;font-size:.9rem}

/* ─── forms & buttons ─────────────────────────────── */
form label{display:block;margin:.85rem 0 .3rem;font-size:.82rem;color:var(--muted);
  font-weight:600;letter-spacing:.02em}
input{padding:.6rem .8rem;width:100%;max-width:420px;border:1px solid var(--border2);
  border-radius:10px;background:rgba(6,9,19,.6);color:var(--text);font-size:.92rem;
  transition:border-color .2s,box-shadow .2s;font-family:inherit}
input:focus{outline:none;border-color:var(--indigo);box-shadow:0 0 0 3px rgba(109,124,255,.18)}
input::placeholder{color:var(--faint)}
button,.btn{margin-top:1rem;padding:.62rem 1.5rem;border:0;border-radius:10px;cursor:pointer;
  font-size:.92rem;font-weight:650;color:#fff;display:inline-block;text-decoration:none;
  background:linear-gradient(120deg,var(--indigo),#4f5fe8 55%,var(--cyan));background-size:150% 100%;
  transition:background-position .3s,transform .2s,box-shadow .2s;font-family:inherit}
button:hover,.btn:hover{background-position:90% 0;transform:translateY(-1px);
  box-shadow:0 8px 22px -8px rgba(109,124,255,.55);text-decoration:none;color:#fff}
.btn.ghost{background:rgba(109,124,255,.10);border:1px solid rgba(109,124,255,.35);color:#b9c6ff}
.btn.ghost:hover{background:rgba(109,124,255,.18);box-shadow:none}
.formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 1.2rem}
.controls{display:flex;gap:.9rem;flex-wrap:wrap;align-items:stretch;margin:1rem 0}
.controls .card{flex:1;min-width:260px;padding:.85rem 1.1rem}
.controls form{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-top:.3rem}
.controls input{width:auto;padding:.4rem .6rem}
.controls button{margin-top:0;padding:.45rem 1rem;font-size:.85rem}

/* ─── founder profile ─────────────────────────────── */
.profile{display:flex;gap:1.6rem;align-items:center;flex-wrap:wrap;padding:1.4rem 1.5rem}
.gauge{width:132px;height:132px;flex:none}
.gauge .g-bg{fill:none;stroke:rgba(142,163,196,.14);stroke-width:9}
.gauge .g-fg{fill:none;stroke:url(#gg);stroke-width:9;stroke-linecap:round;
  transform:rotate(-90deg);transform-origin:center;
  transition:stroke-dashoffset 1.3s cubic-bezier(.22,1,.36,1)}
.gauge text{fill:var(--text);font-weight:750;font-size:30px;letter-spacing:-1px}
.gauge .glabel{fill:var(--faint);font-size:9.5px;font-weight:600;letter-spacing:1.5px}
.profile h2{margin:.1rem 0 .35rem;font-size:1.55rem}
.barrow{display:flex;align-items:center;gap:.7rem}
.barrow .track{flex:1;min-width:120px;max-width:260px;height:7px;border-radius:99px;
  background:rgba(142,163,196,.13);overflow:hidden}
.barrow .track i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--indigo),var(--cyan));animation:grow 1.1s cubic-bezier(.22,1,.36,1)}

/* ─── memo axes / metric cards ────────────────────── */
.axes{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.9rem;margin:1rem 0}
.axis .axname{font-size:.72rem;letter-spacing:.14em;color:var(--cyan);font-weight:700;text-transform:uppercase}
.axis .axscore{font-size:2rem;font-weight:750;letter-spacing:-.03em;margin:.2rem 0}
.axis .axscore small{font-size:.95rem;color:var(--faint);font-weight:500}
.metric b{font-size:1.75rem}
.metric.hi b{background:linear-gradient(92deg,var(--green),var(--cyan));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;font-size:2.3rem}

/* ─── reveal animation ────────────────────────────── */
.reveal{opacity:0;transform:translateY(16px);transition:opacity .6s ease,transform .6s cubic-bezier(.22,1,.36,1)}
.reveal.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
  .reveal{opacity:1;transform:none}}

footer{border-top:1px solid var(--border);padding:1.4rem 0 2.2rem;color:var(--faint);font-size:.82rem}
footer .wrap{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
"""

JS = """
document.addEventListener('DOMContentLoaded',function(){
  try{
    var io=new IntersectionObserver(function(es){es.forEach(function(e){
      if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:.06});
    document.querySelectorAll('.reveal').forEach(function(el,i){
      el.style.transitionDelay=Math.min(i*70,350)+'ms';io.observe(el);});
  }catch(err){}
  /* fail-safe: nothing may stay hidden if the observer never fires */
  setTimeout(function(){document.querySelectorAll('.reveal:not(.in)')
    .forEach(function(el){el.classList.add('in');});},1400);
  document.querySelectorAll('[data-count]').forEach(function(el){
    var end=parseFloat(el.dataset.count),dec=parseInt(el.dataset.dec||'0',10),
        suf=el.dataset.suffix||'',t0=null,dur=1000;
    function step(t){if(!t0)t0=t;var p=Math.min((t-t0)/dur,1),v=end*(1-Math.pow(1-p,3));
      el.textContent=v.toFixed(dec)+suf;if(p<1)requestAnimationFrame(step);}
    requestAnimationFrame(step);});
  document.querySelectorAll('.g-fg[data-off]').forEach(function(el){
    requestAnimationFrame(function(){requestAnimationFrame(function(){
      el.style.strokeDashoffset=el.dataset.off;});});});
});
"""

LOGO = """<svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
<defs><linearGradient id="lg" x1="0" y1="0" x2="24" y2="24">
<stop stop-color="#6d7cff"/><stop offset="1" stop-color="#39d0ff"/></linearGradient></defs>
<circle cx="6" cy="12" r="2.6" fill="url(#lg)"/><circle cx="17" cy="5.5" r="2.2" fill="url(#lg)"/>
<circle cx="18" cy="18" r="2.9" fill="url(#lg)"/>
<path d="M8 11 15.5 6.4M8.2 13 15.4 17M17.2 8 17.8 15" stroke="url(#lg)" stroke-width="1.4" stroke-linecap="round"/>
</svg>"""

FAVICON = ("%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
           "%3Ccircle cx='6' cy='12' r='2.6' fill='%236d7cff'/%3E"
           "%3Ccircle cx='17' cy='5.5' r='2.2' fill='%2339d0ff'/%3E"
           "%3Ccircle cx='18' cy='18' r='2.9' fill='%236d7cff'/%3E"
           "%3Cpath d='M8 11 15.5 6.4M8.2 13 15.4 17M17.2 8 17.8 15' stroke='%2339d0ff' "
           "stroke-width='1.4' stroke-linecap='round'/%3E%3C/svg%3E")

NAV_ITEMS = [("/", "Founders", "founders"), ("/search", "Search", "search"),
             ("/apply", "Apply", "apply"), ("/thesis", "Thesis", "thesis"),
             ("/backtest", "Backtest", "backtest")]


def page(title: str, body: str, active: str = "") -> HTMLResponse:
    links = "".join(
        f"<a href='{href}'{' class=active' if key == active else ''}>{label}</a>"
        for href, label, key in NAV_ITEMS
    )
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<link rel='icon' href=\"data:image/svg+xml,{FAVICON}\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
        f"<header class='top'><div class='wrap navbar'>"
        f"<a class='brand' href='/'>{LOGO}<b>The VC Brain</b></a>"
        f"<nav class='navlinks'>{links}</nav>"
        f"<span class='live'><i></i>live ledger</span>"
        f"</div></header>"
        f"<main><div class='wrap'>{body}</div></main>"
        f"<footer><div class='wrap'><span>LLM at the edges only — everything between is "
        f"deterministic, timestamped, replayable.</span>"
        f"<span>append-only event ledger · <a href='/backtest'>backtested 2.62x lift</a></span>"
        f"</div></footer>"
        f"<script>{JS}</script></body></html>"
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


def _trend_pill(trend: str) -> str:
    cls = "up" if trend == "improving" else "down" if trend == "declining" else "flat"
    arrow = "▲" if trend == "improving" else "▼" if trend == "declining" else "▬"
    return f"<span class='pill {cls}'>{arrow} {trend}</span>"


def _score_cell(total: float) -> str:
    pct = max(0, min(100, total))
    return (f"<span class='num'><b>{total}</b></span>"
            f"<span class='sbar'><i style='width:{pct}%'></i></span>")


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
            f"<td>{_score_cell(b.total)}</td>"
            f"<td>{_fit_cell(f)}</td>"
            f"<td>{_trend_pill(b.trend)}</td>"
            f"<td class='note'>{esc(', '.join(b.sources))}</td>"
            f"<td class='num'>{b.n_events}</td></tr>"
            for i, (eid, name, b, f, blended) in enumerate(ranked, 1)
        )
        header = ("<tr><th>#</th><th>founder</th><th>lens score</th><th>raw score</th>"
                  "<th>thesis fit</th><th>trend</th><th>sources</th><th>events</th></tr>")
        lens_line = (
            f"<div class='card'><b>🔍 Fund lens: {esc(th['fund_name'])}</b>"
            f"<p class='note' style='margin:.35rem 0 0'>Every ranking is filtered &amp; "
            f"scored through the thesis — <a href='/thesis'>edit thesis</a> · "
            f"<a href='/?lens=raw'>view raw scores</a></p></div>"
        )
    else:
        ranked = score.rank_founders(conn, n=n, as_of=cutoff)
        rows = "".join(
            f"<tr><td class='num'>{i}</td>"
            f"<td><a href='/founder/{eid}'>{esc(name)}</a></td>"
            f"<td>{_score_cell(b.total)}</td>"
            f"<td>{_trend_pill(b.trend)}</td>"
            f"<td class='note'>{esc(', '.join(b.sources))}</td>"
            f"<td class='num'>{b.n_events}</td></tr>"
            for i, (eid, name, b) in enumerate(ranked, 1)
        )
        header = ("<tr><th>#</th><th>founder</th><th>score</th><th>trend</th>"
                  "<th>sources</th><th>events</th></tr>")
        lens_line = ("<div class='card'><b>Raw Founder Scores</b>"
                     "<p class='note' style='margin:.35rem 0 0'>No fund lens applied — "
                     "<a href='/'>back to thesis view</a></p></div>")

    if as_of:
        time_travel = (
            f"<div class='card'><b>⏳ Viewing the world as of {esc(as_of)}</b>"
            f"<p class='note' style='margin:.35rem 0 0'>Scores recomputed from only what "
            f"was known then. <a href='/'>Back to today</a></p></div>"
        )
    else:
        time_travel = (
            "<div class='card'><b>⏳ Time travel</b>"
            "<form method='get'>"
            "<span class='note'>see what the system knew on any date</span>"
            "<input type='date' name='as_of'> <button>Go</button>"
            "</form></div>"
        )
    kinds = dict(conn.execute(
        "SELECT kind, COUNT(*) FROM entities WHERE merged_into IS NULL GROUP BY kind"
    ).fetchall())
    n_sources = len(st["events_by_source"])
    merged_note = (f"{st['merged_away']} identities merged on hard evidence"
                   if st["merged_away"] else "deduped via hard-evidence resolution")
    hero = (
        "<div class='hero reveal'>"
        "<p class='eyebrow'>Append-only signal ledger · deterministic scoring</p>"
        "<h1>Founders ranked by what they <span class='grad'>ship</span>,<br>"
        "not who they know.</h1>"
        "<p class='sub'>Live public signals stream into one entity-resolved ledger. "
        "The Founder Score is a pure fold over timestamped events — it trends, "
        "time-travels, and cites the exact evidence behind every point.</p></div>"
        "<div class='grid-stats'>"
        f"<div class='card stat reveal'><b data-count='{st['events']}'>0</b>"
        f"<span>signals in the ledger</span><small>every one timestamped &amp; replayable</small></div>"
        f"<div class='card stat reveal'><b data-count='{kinds.get('person', 0)}'>0</b>"
        f"<span>founders tracked</span><small>{merged_note}</small></div>"
        f"<div class='card stat reveal'><b data-count='{kinds.get('company', 0)}'>0</b>"
        f"<span>companies mapped</span><small>YC directory &amp; launch trails</small></div>"
        f"<div class='card stat reveal'><b data-count='{n_sources}'>0</b>"
        f"<span>live sources</span><small>{esc(', '.join(st['events_by_source']))}</small></div>"
        "</div>"
    )
    body = (
        hero
        + f"<div class='controls reveal'>{lens_line}{time_travel}</div>"
        + f"<div class='tablewrap reveal'><table>{header}{rows}</table></div>"
    )
    return page("The VC Brain — ranked founders", body, active="founders")


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
    return (f"<div class='card reveal' style='margin:1rem 0'>"
            f"<p class='note' style='margin:0 0 .5rem'>How the system read your query "
            f"({how}) — matching &amp; ranking below are 100% deterministic:</p>"
            f"<p style='margin:0'>{inner}</p></div>")


@app.get("/search", response_class=HTMLResponse)
def search_view(q: str | None = None, n: int = 25, as_of: str | None = None):
    form = (
        "<div class='hero reveal'>"
        "<p class='eyebrow'>Multi-attribute reasoning</p>"
        "<h1>Ask for a founder in <span class='grad'>plain language</span>.</h1>"
        "<p class='sub'>One compound query, not five filters. The LLM only parses "
        "your words into structured attributes; the search itself is deterministic "
        "evidence-matching over the ledger.</p></div>"
        f"<form method='get' action='/search' class='reveal' "
        f"style='display:flex;gap:.6rem;flex-wrap:wrap;align-items:center'>"
        f"<input name='q' value=\"{esc(q or '')}\" placeholder=\"{esc(EXAMPLE_QUERY)}\" "
        f"style='max-width:640px;flex:1;min-width:260px'>"
        f"<button style='margin-top:0'>Search</button></form>"
        f"<p class='note reveal' style='margin-top:.6rem'>try: "
        f"<a href='/search?q={esc(EXAMPLE_QUERY)}'>{esc(EXAMPLE_QUERY)}</a></p>"
    )
    if not q or not q.strip():
        return page("Search founders", form, active="search")

    conn = db.connect()
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    spec, matches, notes, meta = search_mod.run(conn, q.strip(), n=n, as_of=cutoff)

    disclosure_html = ""
    if notes:
        items = "".join(f"<li>{esc(x)}</li>" for x in notes)
        disclosure_html = (
            "<div class='banner gold reveal'>Honest disclosure — "
            "constraints the current sources can't filter on:<ul style='margin:.4rem 0'>"
            f"{items}</ul></div>"
        )

    if not matches:
        body = (form + _spec_chips(spec) + disclosure_html +
                "<p>No founder in Memory satisfies every constraint. "
                "Loosen the query, or <a href='/'>browse all founders</a>.</p>")
        return page("Search founders", body, active="search")

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
        f"<td>{_score_cell(m.breakdown.total)}</td>"
        f"<td>{_trend_pill(m.breakdown.trend)}</td>"
        f"<td>{_attr_pills(m)}</td>"
        f"<td class='num'>{m.breakdown.n_events}</td></tr>"
        for i, m in enumerate(matches, 1)
    )
    header = ("<tr><th>#</th><th>founder</th><th>match</th><th>score</th><th>trend</th>"
              "<th>constraints (✓ satisfied · ✗ not — hover for evidence)</th><th>events</th></tr>")
    n_perfect = sum(1 for m in matches if m.perfect and m.n_total > 1)
    relax_note = (
        "<p class='note reveal'>No founder matched the requested sector, so this shows "
        "the closest matches on the other constraints instead.</p>"
        if meta.get("relaxed") else ""
    )
    summary = (
        f"<p class='reveal'><b>{len(matches)}</b> "
        + ("closest" if meta.get("relaxed") else "topically-relevant")
        + " founder(s), ranked by constraints satisfied then Founder Score"
        + (f" — <b>{n_perfect}</b> satisfy all {n_constraints}." if n_constraints > 1 else ".")
        + "</p>"
    )
    body = (form + _spec_chips(spec) + disclosure_html + relax_note + summary +
            f"<div class='tablewrap reveal'><table>{header}{rows}</table></div>")
    return page("Search founders", body, active="search")


@app.get("/thesis", response_class=HTMLResponse)
def thesis_form(saved: int = 0):
    th = thesis_mod.load_thesis()
    banner = ("<div class='banner go reveal'>✓ Thesis saved — the <a href='/'>dashboard "
              "ranking</a> now reflects it.</div>" if saved else "")
    body = f"""
    {banner}
    <div class='hero reveal'>
    <p class='eyebrow'>Thesis engine</p>
    <h1>The <span class='grad'>fund lens</span> every ranking flows through.</h1>
    <p class='sub'>Sector keywords drive the fit score on the dashboard, risk
    appetite sets the decision-rule bars, disqualifiers gate hard, and check
    size flows into the final decision. Flip the thesis — watch the same pool reorder.</p></div>
    <div class='card reveal' style='padding:1.4rem 1.5rem'>
    <form method='post' action='/thesis'>
      <div class='formgrid'>
      <div><label>Fund name</label><input name='fund_name' value="{esc(th['fund_name'])}"></div>
      <div><label>Risk appetite (high / medium / low — sets decision bars)</label>
      <input name='risk_appetite' value="{esc(th['risk_appetite'])}"></div>
      </div>
      <label>Sectors (comma-separated keywords — matched against founder evidence)</label>
      <input name='sectors' value="{esc(', '.join(th['sectors']))}" style='max-width:100%'>
      <label>Disqualifiers (comma-separated keywords — hard gate)</label>
      <input name='disqualifiers' value="{esc(', '.join(th['disqualifiers']))}" style='max-width:100%'>
      <div class='formgrid'>
      <div><label>Check size (USD)</label><input name='check_size_usd' value="{th['check_size_usd']}"></div>
      <div><label>Stage</label><input name='stage' value="{esc(th['stage'])}"></div>
      <div><label>Geography</label><input name='geography' value="{esc(th['geography'])}"></div>
      <div><label>Ownership target</label><input name='ownership_target' value="{esc(th['ownership_target'])}"></div>
      </div>
      <button>Save thesis</button>
    </form></div>
    <p class='note reveal' style='margin-top:1rem'>Honesty notes: current sources carry no
    reliable location signal, so geography is recorded but not filtered; outbound-sourced
    founders are pre-formal by construction, so stage is trivially satisfied.
    Neither is silently faked.</p>"""
    return page("Thesis Engine", body, active="thesis")


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


def _gauge(total: float) -> str:
    """Animated SVG ring for the Founder Score (0–100)."""
    circ = 2 * 3.14159 * 52
    off = circ * (1 - max(0, min(100, total)) / 100)
    return (
        f"<svg class='gauge' viewBox='0 0 120 120'>"
        f"<defs><linearGradient id='gg' x1='0' y1='0' x2='1' y2='1'>"
        f"<stop stop-color='#6d7cff'/><stop offset='1' stop-color='#39d0ff'/></linearGradient></defs>"
        f"<circle class='g-bg' cx='60' cy='60' r='52'/>"
        f"<circle class='g-fg' cx='60' cy='60' r='52' "
        f"style='stroke-dasharray:{circ:.1f};stroke-dashoffset:{circ:.1f}' data-off='{off:.1f}'/>"
        f"<text x='60' y='60' text-anchor='middle' dominant-baseline='central' class='num'>{total}</text>"
        f"<text x='60' y='82' text-anchor='middle' class='glabel'>SCORE</text></svg>"
    )


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
                f"<div class='banner reveal'>★ We already knew you — this founder "
                f"existed in Memory with {len(prior)} prior signal{'s' if len(prior) != 1 else ''} from "
                f"{n_src} source{'s' if n_src != 1 else ''} before they applied. "
                f"The Founder Score below was waiting for them.</div>"
            )
        due = ledger.parse_ts(app_ev["event_ts"]) + timedelta(hours=24)
        first_signal = ledger.parse_ts(events[0]["event_ts"])
        applied_at = ledger.parse_ts(app_ev["event_ts"])
        banner += (
            f"<div class='timer reveal'>⏱ first signal → application: "
            f"{(applied_at - first_signal).days}d · $100K decision due "
            f"{due.strftime('%Y-%m-%d %H:%M')}Z</div>"
        )

    comps = "".join(
        f"<tr><td>{comp.replace('_', ' ')}</td>"
        f"<td class='num' style='white-space:nowrap'>{pts} / {score.WEIGHTS[comp]}</td>"
        f"<td><div class='barrow'><div class='track'>"
        f"<i style='width:{(pts / score.WEIGHTS[comp] * 100):.0f}%'></i></div></div></td>"
        f"<td>{' '.join(f'<a href=\"#ev{i}\">#{i}</a>' for i in b.evidence[comp][:10])}</td></tr>"
        for comp, pts in b.components.items()
    )
    notes = "".join(f"<p class='note'>! {esc(n)}</p>" for n in b.notes)
    timeline = "".join(
        f"<tr id='ev{e['id']}'><td class='num'>#{e['id']}</td><td class='num'>{esc(e['event_ts'][:10])}</td>"
        f"<td><span class='chip'>{esc(e['source'])}/{esc(e['event_type'])}</span></td>"
        f"<td>{esc(e['payload'].get('title') or e['payload'].get('repo') or e['payload'].get('project') or e['payload'].get('one_liner') or '')}"
        + (f" <a href='{esc(e['payload']['url'])}'>↗</a>" if e['payload'].get('url') else "")
        + f"</td><td class='num'>{e['payload'].get('points') or e['payload'].get('stars') or ''}</td></tr>"
        for e in reversed(events)
    )
    profile = (
        f"<div class='card profile reveal'>{_gauge(b.total)}"
        f"<div style='flex:1;min-width:240px'>"
        f"<p class='eyebrow' style='margin:0'>Founder profile · as of {esc(b.as_of[:10])}</p>"
        f"<h2>{esc(row['canonical_name'])} {_trend_pill(b.trend)}</h2>"
        f"<p class='note' style='margin:.2rem 0 .8rem'>{_handles_html(row['handles'])}</p>"
        f"<a class='btn' href='/memo/{entity_id}' style='margin-top:0'>Investment memo &amp; "
        f"$100K decision →</a></div></div>"
    )
    body = (
        f"{banner}{profile}"
        f"<h3 class='reveal'>Score components — every point cites its evidence</h3>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>component</th><th>points</th><th></th><th>evidence (click)</th></tr>{comps}"
        f"</table></div>{notes}"
        f"<h3 class='reveal'>Timeline ({len(events)} events, newest first)</h3>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>id</th><th>when</th><th>signal</th><th>what</th><th>pts</th></tr>{timeline}"
        f"</table></div>"
    )
    return page(row["canonical_name"], body)


@app.get("/apply", response_class=HTMLResponse)
def apply_form():
    body = """
    <div class='hero reveal'>
    <p class='eyebrow'>Inbound</p>
    <h1>Apply for a <span class='grad'>$100K</span> check.</h1>
    <p class='sub'>Minimum bar per the brief: company + name. Handles are
    optional — if we've seen you before, we already know.</p></div>
    <div class='card reveal' style='max-width:560px;padding:1.4rem 1.5rem'>
    <form method='post' action='/apply'>
      <label>Founder name *</label><input name='name' required>
      <label>Company name *</label><input name='company' required>
      <label>One-liner</label><input name='one_liner'>
      <div class='formgrid'>
      <div><label>HN username</label><input name='hn'></div>
      <div><label>GitHub username</label><input name='github'></div>
      </div>
      <label>Website</label><input name='url'>
      <button>Apply for $100K</button>
    </form></div>"""
    return page("Apply", body, active="apply")


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
        return page("Backtest", "<p>No backtest report yet — run vcbrain.backtest.</p>",
                    active="backtest")
    r = json.loads(report_file.read_text())
    top = "".join(
        f"<tr><td>{esc(t['name'])}</td><td class='num'>{t['score_at_t']}</td>"
        f"<td>{'<span class=\"pill up\">✓ hit</span>' if t['outcome']['hit'] else '<span class=\"pill flat\">no</span>'}</td>"
        f"<td class='num'>{t['outcome']['best_post_t_points']}</td></tr>"
        for t in r["top_decile"]
    )
    misses = "".join(
        f"<tr><td>{esc(m['name'])}</td><td class='num'>{m['score_at_t']}</td>"
        f"<td class='num'>{m['best_post_t_points']}</td></tr>"
        for m in r["missed_hits_below_median"]
    )
    metrics = (
        "<div class='grid-stats'>"
        f"<div class='card stat metric hi reveal'><b data-count='{r['lift']}' data-dec='2' data-suffix='x'>0</b>"
        f"<span>lift over base rate</span><small>top decile vs cohort</small></div>"
        f"<div class='card stat metric reveal'><b data-count='{r['precision_at_top_decile'] * 100:.1f}' data-dec='1' data-suffix='%'>0</b>"
        f"<span>precision @ top decile</span><small>vs {r['base_rate']:.1%} base rate</small></div>"
        f"<div class='card stat metric reveal'><b data-count='{r['cohort_size']}'>0</b>"
        f"<span>founders in cohort</span><small>{esc(r['window'])}</small></div>"
        f"<div class='card stat metric reveal'><b class='num'>{r['mean_score_hits']} <small style='color:var(--faint);font-size:1rem'>vs</small> {r['mean_score_misses']}</b>"
        f"<span>mean score — hits vs misses</span><small>at freeze time, zero future info</small></div>"
        "</div>"
    )
    body = (
        f"<div class='hero reveal'>"
        f"<p class='eyebrow'>Backtest — footprints frozen at {esc(r['as_of'][:10])}</p>"
        f"<h1>Does the score predict anything? <span class='grad'>We tested it.</span></h1>"
        f"<p class='sub'>Cohort: Show HN founders {esc(r['window'])}, footprints frozen "
        f"with zero future information. Outcome: {esc(r['hit_definition'])}.</p></div>"
        f"{metrics}"
        f"<h3 class='reveal'>Top decile at time T ({len(r['top_decile'])})</h3>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>founder</th><th>score @ T</th><th>outcome</th><th>best post-T pts</th></tr>{top}"
        f"</table></div>"
        f"<h3 class='reveal'>Where we were wrong ({len(r['missed_hits_below_median'])} missed hits below median)</h3>"
        f"<p class='note reveal'>An honest system shows its misses.</p>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>founder</th><th>score @ T</th><th>later hit (pts)</th></tr>{misses}"
        f"</table></div>"
    )
    return page("Backtest", body, active="backtest")


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
        f"<div class='card axis reveal'><span class='axname'>{esc(ax)}</span>"
        f"<div class='axscore num'>{v.get('score', '—')}<small>/10</small></div>"
        f"<div class='barrow' style='margin:.2rem 0 .5rem'><div class='track'>"
        f"<i style='width:{(v.get('score') or 0) * 10}%'></i></div></div>"
        f"<b style='font-size:.9rem'>{esc(v.get('rating', ''))}</b><br>"
        f"<span class='note'>confidence {v.get('confidence', '—')}"
        f"{' · insufficient evidence' if v.get('insufficient_evidence') else ''}</span>"
        f"<p class='note' style='margin:.5rem 0 0'>{esc(v.get('rationale', ''))}</p></div>"
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
            sections_html += (f"<div class='card reveal' style='margin:1rem 0'>"
                              f"<h3 style='margin-top:0'>{title}</h3>{inner}</div>")
        elif isinstance(val, list):
            lis, idx = _render_claims(sec_name, val, verdicts, idx, entity_id)
            sections_html += (f"<div class='card reveal' style='margin:1rem 0'>"
                              f"<h3 style='margin-top:0'>{title}</h3><ul>{lis}</ul></div>")

    d = r["decision"]
    fund = d["decision"].startswith("FUND")
    tf = d.get("thesis_fit")
    fit_line = ""
    if tf:
        fit_desc = (f"disqualified: {', '.join(tf['disqualified'])}" if tf["disqualified"]
                    else f"fit {tf['fit']:.0%}" + (f" (matched: {', '.join(tf['matched'][:5])})" if tf["matched"] else " — off-thesis"))
        fit_line = f"<br><span class='note'>thesis lens: {esc(fit_desc)}</span>"
    decision_html = (
        f"<div class='banner {'go' if fund else 'no'} reveal' style='font-size:1.1rem'>"
        f"<b>{'✓' if fund else '✗'} {esc(d['decision'])}</b> — {esc('; '.join(d['reasons']))}"
        f"<br><span class='note'>deterministic rule: {esc(d['rule'])} · "
        f"LLM writes rationale, never the decision</span>{fit_line}</div>"
    )
    body = (
        f"<div class='hero reveal' style='padding-bottom:0'>"
        f"<p class='eyebrow'>Evidence-locked memo</p>"
        f"<h1>Investment memo — <span class='grad'>{esc(r['founder'])}</span></h1>"
        f"<p class='note'>model {esc(r['model'])} · generated {esc(r['generated_at'])} · "
        f"thesis: {esc(r['thesis']['fund_name'])} · "
        f"<a href='/memo/{entity_id}?fresh=1'>regenerate</a> · "
        f"<a href='/founder/{entity_id}'>evidence timeline</a></p></div>"
        f"{decision_html}"
        f"<h3 class='reveal'>Three axes — scored independently, never averaged</h3>"
        f"<div class='axes'>{axes_html}</div>"
        f"{sections_html}"
        f"<p class='note reveal'>Every claim carries a per-claim Trust Score from an "
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
