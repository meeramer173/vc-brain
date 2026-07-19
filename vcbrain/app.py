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

from . import contacts as contacts_mod
from . import db, intelligence, ledger, score
from . import search as search_mod
from . import thesis as thesis_mod
from .entities import Resolver, resolve

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
  border-radius:16px;overflow:visible;margin:1rem 0}
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

/* ─── trust score (deterministic) ─────────────────── */
.trust{font-weight:650;border-radius:99px;padding:.14rem .6rem;font-size:.76rem;
  font-variant-numeric:tabular-nums;white-space:nowrap;border:1px solid transparent;display:inline-block}
.t-hi{background:rgba(61,220,151,.12);color:var(--green);border-color:rgba(61,220,151,.3)}
.t-mid{background:rgba(255,201,77,.12);color:var(--amber);border-color:rgba(255,201,77,.3)}
.t-lo{background:rgba(255,122,138,.12);color:var(--red);border-color:rgba(255,122,138,.3)}
.t-gap{background:rgba(142,163,196,.10);color:var(--muted);border-color:rgba(142,163,196,.22)}
li.claim{margin:.5rem 0;line-height:1.5}
.ctype{font-size:.68rem;color:var(--faint);border:1px solid var(--border2);border-radius:99px;padding:0 .4rem}
details.bd{margin:.25rem 0 .3rem 1.3rem;font-size:.8rem;color:var(--muted)}
details.bd summary{cursor:pointer;color:var(--cyan)}
details.bd code{background:rgba(6,9,19,.55);border:1px solid var(--border);
  padding:.05rem .35rem;border-radius:5px;color:var(--text)}
.trustbar{display:flex;gap:1.6rem;flex-wrap:wrap;align-items:center}
.trustbar .cell{font-size:.76rem;color:var(--faint);line-height:1.3}
.trustbar .cell b{display:block;font-size:1.35rem;color:var(--text);font-variant-numeric:tabular-nums}
.gate-blocked{color:var(--red);font-weight:700}.gate-ok{color:var(--green);font-weight:700}
.trust .tnum{opacity:.6;font-weight:500;margin-left:.4rem;font-size:.72rem}
/* ─── info tooltips, highlights, spinner ──────────── */
.info{position:relative;display:inline-block;width:16px;height:16px;line-height:15px;text-align:center;
  border-radius:50%;font-size:10px;font-style:normal;font-weight:700;background:rgba(109,124,255,.2);
  color:#b9c6ff;cursor:pointer;margin-left:.35rem;vertical-align:middle;text-transform:none;letter-spacing:0;
  border:1px solid rgba(109,124,255,.4)}
.info:hover,.info:focus{background:var(--indigo);color:#fff;outline:none}
.info::after{content:attr(data-tip);position:absolute;left:50%;top:150%;transform:translateX(-50%);
  min-width:180px;max-width:250px;background:#0b1220;border:1px solid var(--border2);color:var(--text);
  padding:.55rem .7rem;border-radius:9px;font-size:.76rem;font-weight:400;line-height:1.45;text-align:left;
  white-space:normal;opacity:0;visibility:hidden;transition:opacity .14s;z-index:80;pointer-events:none;
  box-shadow:0 10px 30px rgba(0,0,0,.5)}
.info:hover::after,.info:focus::after{opacity:1;visibility:visible}
/* claim cards */
li.claim{margin:.7rem 0;padding:.65rem .85rem;border:1px solid var(--border);border-radius:11px;
  background:rgba(6,9,19,.32);list-style:none}
.claim .ctext{font-size:.94rem;line-height:1.45;margin-bottom:.45rem}
.claim .cmeta{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
.claim .cwhy{margin-top:.4rem;font-size:.8rem;color:var(--muted);line-height:1.4}
.claim .cwhy::before{content:'↳ ';color:var(--faint)}
.panel-slim{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}
#finding{display:none;position:fixed;inset:0;z-index:200;background:rgba(6,9,19,.85);
  backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);align-items:center;justify-content:center}
tr.hot td{background:rgba(109,124,255,.06)}
tr.hot td:first-child{box-shadow:inset 3px 0 0 var(--indigo)}
.rankbadge{display:inline-block;min-width:20px;text-align:center;font-weight:750;color:var(--cyan)}
table.ranked th,table.ranked td{border-right:1px solid rgba(28,42,68,.6)}
table.ranked th:last-child,table.ranked td:last-child{border-right:0}
th.lenscol,td.lenscol{background:rgba(57,208,255,.11);
  border-left:1px solid rgba(57,208,255,.3);border-right:1px solid rgba(57,208,255,.3)}
td.lenscol b{color:var(--cyan);font-size:1.08rem}
.spinner{width:36px;height:36px;border-radius:50%;border:3px solid rgba(109,124,255,.22);
  border-top-color:var(--cyan);animation:spin .8s linear infinite;margin:0 auto}
@keyframes spin{to{transform:rotate(360deg)}}
.genwrap{text-align:center;padding:2.6rem 1rem}
.genwrap .elapsed{font-variant-numeric:tabular-nums;color:var(--cyan);font-weight:700}
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
             ("/inbound", "Inbound", "inbound"), ("/thesis", "Thesis", "thesis"),
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
        f"<span>append-only event ledger · <a href='/backtest'>backtested 2.62x lift</a> · "
        f"<a href='/apply'>founder? apply →</a></span>"
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


def _contact_block(contact: dict | None) -> str:
    """Render self-declared contact info as clickable chips, each labeled with
    where it was declared. Empty string when nothing is on record — we never
    show a guessed contact."""
    if not contact:
        return ""
    src = contact.get("sources", {}) or {}
    chips = []
    if contact.get("email"):
        chips.append(
            f"<a class='chip' href='mailto:{esc(contact['email'])}'>✉ {esc(contact['email'])}</a>"
            f"<span class='note' style='margin-left:.25rem'>({esc(src.get('email', 'declared'))})</span>"
        )
    if contact.get("linkedin"):
        head = f" · {esc(contact['headline'])}" if contact.get("headline") else ""
        chips.append(
            f"<a class='chip' target='_blank' rel='noopener' href='{esc(contact['linkedin'])}'>in LinkedIn</a>"
            f"<span class='note' style='margin-left:.25rem'>({esc(src.get('linkedin', 'declared'))}){head}</span>"
        )
    if not chips:
        return ""
    return (
        "<div style='margin:.1rem 0 .8rem'>"
        "<span class='eyebrow' style='margin:0' title='Only info the founder "
        "published themselves on GitHub / HN — never name-matched or scraped'>"
        "Verified contact · self-declared</span><br>"
        + " ".join(chips) + "</div>"
    )


def _trend_pill(trend: str) -> str:
    cls = "up" if trend == "improving" else "down" if trend == "declining" else "flat"
    arrow = "▲" if trend == "improving" else "▼" if trend == "declining" else "▬"
    return f"<span class='pill {cls}'>{arrow} {trend}</span>"


def _score_cell(total: float) -> str:
    pct = max(0, min(100, total))
    return (f"<span class='num'><b>{total}</b></span>"
            f"<span class='sbar'><i style='width:{pct}%'></i></span>")


def _info(text: str) -> str:
    """Small ⓘ icon with a styled, focusable hover popover explaining a score."""
    return f"<span class='info' tabindex='0' data-tip='{esc(text)}'>i</span>"


def _inbound_ids(conn) -> set:
    """Canonical entity ids that have submitted an application (inbound).
    Everyone else in the ledger was sourced by us (outbound)."""
    ids = set()
    for r in conn.execute(
        "SELECT DISTINCT entity_id FROM events WHERE event_type='application'"
    ):
        ids.add(resolve(conn, r["entity_id"]))
    return ids


def _io_tag(is_inbound: bool) -> str:
    if is_inbound:
        return ("<span class='pill up' title='Applied to us (inbound)'>inbound</span>")
    return ("<span class='pill flat' title='We sourced them; they have not applied "
            "(outbound)'>outbound</span>")


COMP_HELP = {
    "shipping_cadence": "How much they shipped in the last 180 days (6+ ships = full marks).",
    "momentum": "Recent shipping, weighted heavily — a 60-day half-life rewards being active now.",
    "breadth": "How many different sources independently vouch for them.",
    "external_validation": "Accumulated stars + points across their work (log-scaled).",
    "consistency": "How many distinct months they were active in the last year.",
}


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
def dashboard(n: int = 25, as_of: str | None = None, lens: str = "on",
              view: str = "thesis"):
    conn = db.connect()
    st = ledger.stats(conn)
    cutoff = f"{as_of}T23:59:59Z" if as_of else None
    th = thesis_mod.load_thesis()
    inbound = _inbound_ids(conn)

    if lens != "raw":
        ranked = thesis_mod.rank_with_lens(conn, th, n=n, as_of=cutoff)
        rows = "".join(
            f"<tr class='{'hot' if i <= 5 else ''}'>"
            f"<td class='num'>{f'<span class=\"rankbadge\">{i}</span>' if i <= 5 else i}</td>"
            f"<td><a href='/founder/{eid}'>{esc(name)}</a> {_io_tag(eid in inbound)}</td>"
            f"<td class='num lenscol'><b>{blended}</b></td>"
            f"<td>{_score_cell(b.total)}</td>"
            f"<td>{_fit_cell(f)}</td>"
            f"<td>{_trend_pill(b.trend)}</td>"
            f"<td class='note'>{esc(', '.join(b.sources))}</td>"
            f"<td class='num'>{b.n_events}</td></tr>"
            for i, (eid, name, b, f, blended) in enumerate(ranked, 1)
        )
        header = (
            "<tr><th>#</th><th>founder</th>"
            f"<th class='lenscol'>lens score{_info('Founder Score adjusted for how well they fit your thesis. The list is ranked by this.')}</th>"
            f"<th>founder score{_info('0-100. How much this person ships, thesis-blind. Deterministic - no AI.')}</th>"
            f"<th>thesis fit{_info('How much their work matches your fund sectors. 1 keyword = 50%, 2+ = 100%.')}</th>"
            f"<th>trend{_info('Did their Founder Score rise or fall over the last 30 days.')}</th>"
            f"<th>sources{_info('Which platforms vouch for them. More sources = better corroborated.')}</th>"
            f"<th>events{_info('How many signals back them = evidence depth, not quality.')}</th></tr>")
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
            f"<td><a href='/founder/{eid}'>{esc(name)}</a> {_io_tag(eid in inbound)}</td>"
            f"<td>{_score_cell(b.total)}</td>"
            f"<td>{_trend_pill(b.trend)}</td>"
            f"<td class='note'>{esc(', '.join(b.sources))}</td>"
            f"<td class='num'>{b.n_events}</td></tr>"
            for i, (eid, name, b) in enumerate(ranked, 1)
        )
        header = (f"<tr><th>#</th><th>founder</th><th>founder score{_info('0-100. How much this person ships. Deterministic - no AI.')}</th>"
                  "<th>trend</th><th>sources</th><th>events</th></tr>")
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
    table_html = f"<div class='tablewrap reveal'><table class='ranked'>{header}{rows}</table></div>"
    th_sectors = ", ".join(th.get("sectors", []))
    risk_word = str(th.get("risk_appetite", "medium")).split()[0]

    # Panel 2 always ranks live; raw view keeps its own simple layout.
    if lens == "raw":
        body = (hero + f"<div class='controls reveal'>{lens_line}{time_travel}</div>"
                + table_html)
        return page("The VC Brain — ranked founders", body, active="founders")

    finding_overlay = (
        "<div id='finding'><div style='text-align:center'><div class='spinner'></div>"
        "<p style='margin-top:1rem;color:var(--text)'>Ranking every founder through your "
        "thesis…</p></div></div>"
        "<script>function showFinding(){document.getElementById('finding')"
        ".style.display='flex';return true;}</script>"
    )

    if view == "thesis":
        # PANEL 1 (maximised) — full editable thesis; PANEL 2 (minimised) —
        # inbound applications + a ready-to-rank teaser.
        disq = ", ".join(th.get("disqualifiers", []))
        wide = "width:100%;max-width:760px"
        panel1 = (
            "<div class='card reveal'><p class='eyebrow'>Step 1 · Your fund thesis</p>"
            "<h2 style='margin:.15rem 0'>What kind of founder are you looking for?</h2>"
            "<p class='note' style='max-width:46rem;margin:.1rem 0 .3rem'>Every founder we've "
            "already sourced is ranked through this lens. Edit anything, then re-rank.</p>"
            "<form method='post' action='/thesis' onsubmit='return showFinding()'>"
            "<input type='hidden' name='next' value='/?view=founders'>"
            f"<label>Fund name</label><input name='fund_name' value=\"{esc(th['fund_name'])}\" style='{wide}'>"
            f"<label>Sectors — comma separated {_info('Keywords matched against what each founder has built. 1 match = 50% fit, 2+ = 100%.')}</label>"
            f"<input name='sectors' value=\"{esc(th_sectors)}\" style='{wide}'>"
            f"<label>Disqualifiers — comma separated, hard gate {_info('Any founder whose work matches these is excluded outright (e.g. crypto/token, consultancy).')}</label>"
            f"<input name='disqualifiers' value=\"{esc(disq)}\" style='{wide}'>"
            f"<label>Ownership target</label>"
            f"<input name='ownership_target' value=\"{esc(th.get('ownership_target', ''))}\" style='{wide}'>"
            "<div class='formgrid'>"
            f"<div><label>Risk appetite {_info('high = back exceptional people even off-thesis; low = stricter bars.')}</label>"
            f"<input name='risk_appetite' value=\"{esc(th.get('risk_appetite', ''))}\"></div>"
            f"<div><label>Check size (USD)</label>"
            f"<input name='check_size_usd' value=\"{esc(th.get('check_size_usd', ''))}\"></div>"
            f"<div><label>Stage</label>"
            f"<input name='stage' value=\"{esc(th.get('stage', ''))}\"></div>"
            f"<div><label>Geography {_info('Recorded but not filtered yet — current sources carry no reliable location signal.')}</label>"
            f"<input name='geography' value=\"{esc(th.get('geography', ''))}\"></div>"
            "</div>"
            "<button class='btn'>🔍 Find founders →</button></form></div>"
        )
        # inbound applications (with matched areas) — shown beside/under the thesis
        apps = conn.execute(
            "SELECT * FROM events WHERE event_type='application' ORDER BY event_ts DESC"
        ).fetchall()
        seen: dict = {}
        for a in apps:
            seen.setdefault(resolve(conn, a["entity_id"]), a)
        in_cards = ""
        for aeid, a in seen.items():
            p = json.loads(a["payload"])
            af = thesis_mod.fit(ledger.events_for(conn, aeid), th)
            anm = conn.execute("SELECT canonical_name FROM entities WHERE id=?",
                               (aeid,)).fetchone()["canonical_name"]
            chips = "".join(f"<span class='chip'>{esc(k)}</span>" for k in af.matched[:4]) \
                or "<span class='pill flat'>off-thesis</span>"
            in_cards += (
                "<div style='padding:.55rem .75rem;border:1px solid var(--border);"
                "border-radius:10px;margin:.5rem 0'>"
                f"<b>{esc(p.get('company', ''))}</b> <span class='note'>· {esc(anm)}</span> {chips}"
                + (f"<br><span class='note'>{esc(p.get('one_liner', ''))}</span>"
                   if p.get('one_liner') else "")
                + f" · <a href='/founder/{aeid}?applied=1'>review →</a></div>"
            )
        inbound_panel = (
            "<div class='card reveal' style='margin-top:1.4rem'><p class='eyebrow'>Inbound applications</p>"
            f"<h3 style='margin:.2rem 0'>{len(seen)} founder application"
            f"{'s' if len(seen) != 1 else ''} waiting</h3>"
            "<p class='note' style='max-width:46rem'>These founders applied to you. Before "
            "you decide, rank them against the whole field you've been quietly tracking.</p>"
            + (in_cards or "<p class='note'>No applications yet — they'll appear here, "
               "already scored.</p>")
            + f"<p class='note' style='margin-top:.6rem'>▾ {kinds.get('person', 0)} founders "
              "indexed and ready — hit <b>Find founders</b> above to rank the field.</p></div>"
        )
        body = hero + panel1 + inbound_panel + finding_overlay
    else:
        # PANEL 1 (minimised) — thesis summary; PANEL 2 (maximised) — the ranking.
        panel1 = (
            "<div class='card reveal panel-slim'>"
            f"<div><b>🔍 {esc(th['fund_name'])}</b> <span class='note'>· sectors: "
            f"{esc(th_sectors) or 'any'} · risk: {esc(risk_word)}</span></div>"
            "<div style='display:flex;gap:.5rem;flex-wrap:wrap'>"
            "<a class='btn ghost' href='/?view=thesis' style='margin:0'>◂ Edit thesis</a>"
            "<a class='btn ghost' href='/?lens=raw' style='margin:0'>view raw scores</a></div></div>"
        )
        body = (hero + panel1
                + f"<div class='controls reveal'>{time_travel}</div>" + table_html
                + finding_overlay)
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
    nxt = (form.get("next") or "").strip()
    dest = nxt if nxt.startswith("/") else "/thesis?saved=1"
    return RedirectResponse(dest, status_code=303)


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


def _confidence_pill(conf: float) -> str:
    """Support confidence — how well-evidenced the score is, distinct from how
    high it is. Kept visually separate from the score so the two never blur."""
    pct = round(conf * 100)
    warn = conf < score.COLD_START_CONF
    color = "#f0b32d" if warn else "#39d0ff"
    return (
        f"<span class='pill flat' style='border-color:{color};color:{color}' "
        f"title='How well-evidenced the score is — not how high it is'>"
        f"confidence {pct}%</span>"
    )


def _footprint_action(entity_id: int, label: str, primary: bool) -> str:
    """The public-footprint (LinkedIn / X) enrichment button + result slot.
    Rendered in exactly one place per page so the #profiles id stays unique."""
    cls = "btn" if primary else "btn ghost"
    return (
        f"<a class='{cls}' style='margin-top:0;cursor:pointer' "
        f"onclick='findProfiles(this)' data-entity='{entity_id}'>{label}</a> "
        f"<span id='profiles' class='note' style='margin-left:.4rem'></span>"
    )


def _coldstart_panel(b, footprint_html: str) -> str:
    """Explicit pre-track-record reasoning path — the brief's central rubric
    note. We do NOT silently rank thin founders to the bottom; we say so and
    show the method."""
    reasons = "".join(f"<li>{esc(r)}</li>" for r in b.cold_start_reasons)
    return (
        "<div class='card reveal' style='border-color:#6b4e12;"
        "background:linear-gradient(180deg,rgba(240,179,45,.06),transparent)'>"
        "<p class='eyebrow' style='color:#f0b32d;margin:0'>Cold-start founder · "
        "pre-track-record</p>"
        "<h3 style='margin:.25rem 0 .4rem'>Scored, but deliberately held at low "
        "confidence</h3>"
        "<p class='note' style='max-width:46rem'>This founder has too little "
        "independent history to treat the Founder Score as a track record. "
        "Ranking them to the bottom would just rebuild the network-gated system "
        "this tool exists to replace — so instead of hiding the uncertainty, we "
        "switch to an explicit method:</p>"
        f"<ul class='note' style='max-width:46rem'>{reasons}</ul>"
        "<p class='note' style='max-width:46rem'><b>Method:</b> (1) the score "
        "stays provisional and low-confidence — never shown as a track record; "
        "(2) we lean on what a track-record-only system misses — the application "
        "one-liner and any early prototype signal; (3) we enrich from the "
        "founder's public footprint to find corroboration off the usual VC "
        "radar. A first-time founder with no funding or GitHub still leaves a "
        "footprint.</p>"
        f"{footprint_html}"
        "</div>"
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
    contact = contacts_mod.latest_contact(conn, entity_id)

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
        f"<tr><td>{comp.replace('_', ' ')}{_info(COMP_HELP.get(comp, ''))}</td>"
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
        for e in reversed(events) if e["event_type"] != "contact"
    )
    # The public-footprint enrichment lives in exactly one place: the cold-start
    # panel when thin (primary action), the profile card otherwise (secondary).
    cold_panel = ""
    footprint_here = ""
    if b.cold_start:
        cold_panel = _coldstart_panel(
            b, _footprint_action(entity_id, "Enrich from public footprint →", primary=True)
        )
    else:
        footprint_here = (
            f"<div style='margin:0 0 .8rem'>"
            f"{_footprint_action(entity_id, 'Find LinkedIn / X profile', primary=False)}</div>"
        )

    cold_flag = (
        "<span class='pill flat' style='border-color:#f0b32d;color:#f0b32d' "
        "title='Too little independent evidence to treat as a track record'>cold-start</span>"
        if b.cold_start else ""
    )
    # Outbound founders (never applied) can be Activated: draft cold outreach.
    activate_btn = "" if apps else (
        f"<a class='btn ghost' href='/activate/{entity_id}' style='margin-top:0'>"
        f"Activate — draft outreach →</a>"
    )
    profile = (
        f"<div class='card profile reveal'>{_gauge(b.total)}"
        f"<div style='flex:1;min-width:240px'>"
        f"<p class='eyebrow' style='margin:0'>Founder profile · as of {esc(b.as_of[:10])}</p>"
        f"<h2>{esc(row['canonical_name'])} {_trend_pill(b.trend)} "
        f"{_confidence_pill(b.confidence)} {cold_flag}</h2>"
        f"<p class='note' style='margin:.2rem 0 .8rem'>{_handles_html(row['handles'])}</p>"
        f"{_contact_block(contact)}"
        f"{footprint_here}"
        f"<a class='btn' href='/memo/{entity_id}' style='margin-top:0'>Investment memo &amp; "
        f"$100K decision →</a> {activate_btn}</div></div>"
    )
    body = (
        f"<p><a class='btn ghost' href='/?view=founders' style='margin-top:0'>← All founders</a></p>"
        f"{banner}{profile}{cold_panel}"
        f"<h3 class='reveal'>How the Founder Score ({b.total}) was calculated{_info('Deterministic: same events in, same score out. No AI.')}</h3>"
        f"<p class='note reveal' style='max-width:44rem'>The Founder Score is a 0-100 tally of "
        f"how much this person ships — five weighted components that add up to 100. Every point "
        f"cites the exact ledger events behind it (hover each component's ⓘ for what it measures).</p>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>component</th><th>points</th><th></th><th>evidence (click)</th></tr>{comps}"
        f"</table></div>{notes}"
        f"<h3 class='reveal'>Timeline ({len(events)} events, newest first)</h3>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>id</th><th>when</th><th>signal</th><th>what</th><th>pts</th></tr>{timeline}"
        f"</table></div>"
    )
    body += (
        "<script>function findProfiles(el){"
        "var id=el.getAttribute('data-entity');"
        "var out=document.getElementById('profiles');"
        "el.textContent='Searching the web...';el.style.pointerEvents='none';"
        "fetch('/api/founder/'+id+'/profiles').then(function(r){return r.json();}).then(function(d){"
        "el.style.display='none';"
        "if(d.error){out.innerHTML=\"<span class='chip'>web lookup unavailable</span>\";return;}"
        "var c=[];"
        "if(d.linkedin)c.push(\"<a class='chip' target='_blank' rel='noopener' href='\"+d.linkedin.url+\"'>LinkedIn \"+d.linkedin.type+\"</a>\");"
        "if(d.x)c.push(\"<a class='chip' target='_blank' rel='noopener' href='\"+d.x.url+\"'>X \"+d.x.type+\"</a>\");"
        "out.innerHTML=c.length?c.join(' '):\"<span class='chip'>no public profile found</span>\";"
        "}).catch(function(){el.style.display='none';out.innerHTML=\"<span class='chip'>lookup failed</span>\";});}"
        "</script>"
    )
    return page(row["canonical_name"], body)


@app.get("/inbound", response_class=HTMLResponse)
def inbound_queue():
    """VC-side, read-only: the applications received, each already scored."""
    conn = db.connect()
    apps = conn.execute(
        "SELECT * FROM events WHERE event_type='application' ORDER BY event_ts DESC"
    ).fetchall()
    seen: dict = {}
    for a in apps:  # one card per founder (most recent application)
        eid = resolve(conn, a["entity_id"])
        seen.setdefault(eid, a)

    if not seen:
        empty = ("<div class='hero reveal'><p class='eyebrow'>Inbound queue</p>"
                 "<h1>No applications yet.</h1><p class='sub'>When a founder applies via "
                 "the <a href='/apply'>founder portal</a>, they appear here — already "
                 "scored against the field.</p></div>")
        return page("Inbound", empty, active="inbound")

    cards = ""
    for eid, a in seen.items():
        p = json.loads(a["payload"])
        nm = conn.execute("SELECT canonical_name FROM entities WHERE id=?",
                          (eid,)).fetchone()["canonical_name"]
        b = score.founder_score(conn, eid)
        events = ledger.events_for(conn, eid)
        prior = [e for e in events if e["event_ts"] < a["event_ts"]
                 and e["source"] not in ("inbound", "system")]
        n_src = len({e["source"] for e in prior})
        due = ledger.parse_ts(a["event_ts"]) + timedelta(hours=24)
        knew = (f"<span class='pill up'>★ we already knew you — {len(prior)} prior "
                f"signal{'s' if len(prior) != 1 else ''} from {n_src} "
                f"source{'s' if n_src != 1 else ''}</span>" if prior else
                "<span class='pill flat'>new to us — no prior footprint</span>")
        cards += (
            f"<div class='card reveal' style='margin:.8rem 0'>"
            f"<div style='display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap'>"
            f"<div><b style='font-size:1.06rem'>{esc(p.get('company', ''))}</b> "
            f"<span class='note'>· {esc(nm)}</span> {_io_tag(True)}<br>"
            f"<span class='note'>{esc(p.get('one_liner', ''))}</span></div>"
            f"<div class='num' style='font-size:1.6rem;font-weight:750;text-align:right'>"
            f"{b.total}<div class='note' style='font-size:.72rem'>founder score</div></div></div>"
            f"<div style='margin-top:.7rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center'>"
            f"{knew}<span class='pill flat'>⏱ decision due {due.strftime('%Y-%m-%d %H:%M')}Z</span>"
            f"<a class='btn ghost' href='/founder/{eid}?applied=1' style='margin:0'>Review profile →</a>"
            f"<a class='btn' href='/memo/{eid}' style='margin:0'>Memo &amp; decision →</a></div></div>"
        )
    hero = ("<div class='hero reveal'><p class='eyebrow'>Inbound queue</p>"
            f"<h1>{len(seen)} founder application{'s' if len(seen) != 1 else ''} "
            f"<span class='grad'>received</span></h1>"
            "<p class='sub'>Submitted through the founder portal — each already scored "
            "against the whole field. Where we'd sourced them before they applied, their "
            "history was already waiting.</p></div>")
    return page("Inbound", hero + cards, active="inbound")


@app.get("/apply", response_class=HTMLResponse)
def apply_form():
    body = """
    <div class='hero reveal'>
    <p class='eyebrow'>Founder portal · standalone</p>
    <h1>Apply for a <span class='grad'>$100K</span> check.</h1>
    <p class='sub'>Minimum bar: company + name. Handles are optional — if we've seen
    you before, we already know. Investors never see this form; your application shows
    up in their Inbound queue, already scored.</p></div>
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
    return page("Founder portal — apply", body)


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


# Outbound Activation — draft evidence-grounded outreach, cached per entity so a
# re-view spends no extra tokens. Redraft with ?fresh=1.
_OUTREACH_CACHE: dict = {}


def _outreach_signal_rows(events: list[dict], cited: list) -> str:
    """Deterministic 'why we reached out' — the actual cited signals, not the
    LLM's prose, so the reader sees the evidence the outreach rests on."""
    cited_set = {int(i) for i in cited if str(i).isdigit()}
    picked = [e for e in events if e["id"] in cited_set]
    if not picked:
        picked = [e for e in events if e["source"] != "system"][:5]
    rows = ""
    for e in picked[:6]:
        p = e["payload"]
        what = (p.get("title") or p.get("repo") or p.get("project")
                or p.get("one_liner") or e["event_type"])
        pts = p.get("stars") or p.get("points") or ""
        rows += (
            f"<tr><td class='num'>#{e['id']}</td>"
            f"<td><span class='chip'>{esc(e['source'])}/{esc(e['event_type'])}</span></td>"
            f"<td>{esc(str(what))}</td><td class='num'>{esc(str(pts))}</td></tr>"
        )
    return rows


@app.get("/activate/{entity_id}", response_class=HTMLResponse)
def activate_view(entity_id: int, fresh: int = 0):
    conn = db.connect()
    row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return page("Not found", "<p>No such entity.</p>")
    name = row["canonical_name"]
    events = ledger.events_for(conn, entity_id)
    applied = any(e["event_type"] == "application" for e in events)

    if fresh:
        _OUTREACH_CACHE.pop(entity_id, None)
    o = _OUTREACH_CACHE.get(entity_id)
    if o is None:
        try:
            o = intelligence.draft_outreach(name, events, thesis_mod.load_thesis())
        except Exception:
            back = f"<a class='btn ghost' href='/founder/{entity_id}' style='margin-top:0'>← back</a>"
            return page(
                "Outreach unavailable",
                f"<p>{back}</p><div class='card reveal'><p class='note'>Outreach drafting "
                f"needs the LLM (OPENAI_API_KEY) and it's unavailable right now. Everything "
                f"else on this founder still works.</p></div>",
            )
        _OUTREACH_CACHE[entity_id] = o

    from urllib.parse import quote

    email = o.get("email", {}) or {}
    signal_rows = _outreach_signal_rows(events, o.get("cited_event_ids", []))

    # Real destinations, from the founder's SELF-DECLARED contact info only —
    # the draft is no longer a message into the void. Absent → say so honestly.
    contact = contacts_mod.latest_contact(conn, entity_id) or {}
    csrc = contact.get("sources", {}) or {}
    to_addr, li_url = contact.get("email"), contact.get("linkedin")
    if to_addr:
        mailto = ("mailto:" + to_addr + "?subject=" + quote(email.get("subject", ""))
                  + "&body=" + quote(email.get("body", "")))
        email_action = (
            f"<a class='btn' target='_blank' href='{esc(mailto)}' style='margin-top:.4rem'>"
            f"Send to {esc(to_addr)} →</a>"
            f"<span class='note' style='margin-left:.4rem'>self-declared · {esc(csrc.get('email', 'profile'))}</span>"
        )
    else:
        email_action = (
            "<p class='note' style='margin:.3rem 0 0'>No self-declared email on file — "
            "copy the draft, or try the web lookup on the founder page.</p>"
        )
    if li_url:
        li_action = (
            f"<a class='btn ghost' target='_blank' rel='noopener' href='{esc(li_url)}' style='margin-top:.4rem'>"
            f"Open LinkedIn profile →</a>"
            f"<span class='note' style='margin-left:.4rem'>self-declared · {esc(csrc.get('linkedin', 'profile'))}</span>"
        )
    else:
        li_action = (
            "<p class='note' style='margin:.3rem 0 0'>No declared LinkedIn URL — "
            "the founder page can attempt a name-guarded web lookup.</p>"
        )

    channels = (
        f"<div class='card reveal' style='margin:.8rem 0'>"
        f"<p class='eyebrow' style='margin:0'>Email</p>"
        f"<p style='margin:.35rem 0'><b>Subject:</b> {esc(email.get('subject', ''))}</p>"
        f"<p class='note' style='white-space:pre-wrap;margin:.2rem 0'>{esc(email.get('body', ''))}</p>"
        f"{email_action}</div>"
        f"<div class='card reveal' style='margin:.8rem 0'>"
        f"<p class='eyebrow' style='margin:0'>LinkedIn</p>"
        f"<p class='note' style='white-space:pre-wrap;margin:.2rem 0'>{esc(o.get('linkedin', ''))}</p>"
        f"{li_action}</div>"
        f"<div class='card reveal' style='margin:.8rem 0'>"
        f"<p class='eyebrow' style='margin:0'>X / Twitter DM</p>"
        f"<p class='note' style='white-space:pre-wrap;margin:.2rem 0'>{esc(o.get('x', ''))}</p></div>"
    )
    converge = "" if applied else (
        f"<form method='post' action='/activate/{entity_id}' style='margin-top:1rem'>"
        f"<button class='btn'>Simulate: founder replies &amp; applies →</button>"
        f"<span class='note' style='margin-left:.5rem'>records an application so this "
        f"outbound founder converges into the same screening funnel as inbound</span></form>"
    )
    applied_note = (
        "<div class='banner go reveal'>✓ Already converged — this founder is in the "
        "screening funnel.</div>" if applied else ""
    )
    body = (
        f"<p><a class='btn ghost' href='/founder/{entity_id}' style='margin-top:0'>← Back to founder</a> "
        f"<a class='btn ghost' href='/activate/{entity_id}?fresh=1' style='margin-top:0'>↻ Redraft</a></p>"
        f"<div class='hero reveal' style='padding-bottom:0'>"
        f"<p class='eyebrow'>Outbound · Activate</p>"
        f"<h1>Reach out to <span class='grad'>{esc(name)}</span></h1>"
        f"<p class='sub'>We sourced this founder from public signals before they applied. "
        f"Activation is cold outreach to trigger a real application — not a cold investment.</p></div>"
        f"{applied_note}"
        f"<div class='banner reveal'><b>Why reach out:</b> {esc(o.get('reason', ''))}</div>"
        f"<h3 class='reveal'>Signals that surfaced them{_info('The evidence the outreach is grounded in — cited, not invented.')}</h3>"
        f"<div class='tablewrap reveal'><table>"
        f"<tr><th>id</th><th>signal</th><th>what</th><th>pts</th></tr>{signal_rows}</table></div>"
        f"<h3 class='reveal'>Draft outreach</h3>"
        f"<p class='note reveal' style='max-width:44rem'>Drafted by the LLM, grounded only in "
        f"the signals above — no invented traction or facts. Cold outreach invites an "
        f"application; it never promises the check.</p>"
        f"{channels}{converge}"
    )
    return page(f"Activate — {name}", body)


@app.post("/activate/{entity_id}")
async def activate_apply(entity_id: int):
    """Converge: an activated outbound founder enters the SAME inbound funnel."""
    conn = db.connect()
    row = conn.execute(
        "SELECT canonical_name FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    if row is None:
        return RedirectResponse("/", status_code=303)
    now = ledger.utcnow_iso()
    ledger.record(
        conn, entity_id, "inbound", "application", now,
        f"inbound:activated:{entity_id}",   # stable key => double-click is idempotent
        {"company": row["canonical_name"], "founder_name": row["canonical_name"],
         "one_liner": "Applied after outbound activation outreach",
         "activated_via": "outbound"},
    )
    return RedirectResponse(f"/founder/{entity_id}?applied=1", status_code=303)


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


def _trust_badge(v: dict) -> str:
    """Trust shown as a Low / Medium / High category (the number is secondary)."""
    if not v:
        return "<span class='trust t-gap'>unchecked</span>"
    if v.get("verdict") == "gap" or v.get("trust") is None:
        return "<span class='trust t-gap'>✔ honest gap</span>"
    t = v["trust"]
    if v.get("verdict") == "contradicted":
        cls, label = "t-lo", "⚠ Contradicted"
    elif t >= 0.7:
        cls, label = "t-hi", "High trust"
    elif t >= 0.4:
        cls, label = "t-mid", "Medium trust"
    else:
        cls, label = "t-lo", "Low trust"
    return f"<span class='trust {cls}'>{label}<span class='tnum'>{t:.2f}</span></span>"


def _trust_reason(v: dict) -> str:
    """Plain-language explanation of *why* a claim scored the trust it did —
    what pushed it up or down. Replaces the raw component formula."""
    if not v:
        return ""
    if v.get("verdict") == "gap" or v.get("trust") is None:
        return "Honestly flagged as missing — not guessed, not counted against the founder."
    bd = v.get("breakdown") or {}
    if not bd:
        return esc(v.get("note", ""))
    factors = []
    if bd.get("fact_grounding") == 0:
        factors.append("a number in this claim isn’t backed by the cited evidence")
    if bd.get("citation_validity", 1) < 1:
        factors.append("some cited evidence couldn’t be found")
    if v.get("claim_type") == "inference" and bd.get("cap") == 0.5:
        factors.append("it’s an interpretation, not a hard fact (capped at 0.50)")
    sr = bd.get("source_reliability", 1)
    if sr <= 0.45:
        factors.append("it rests on a self-reported source")
    elif sr >= 0.85 and bd.get("fact_grounding") == 1:
        factors.append("it’s backed by a hard, verifiable source")
    if bd.get("corroboration", 1) > 1:
        factors.append("it’s corroborated by more than one source")
    head = {"contradicted": "Contradicted", "weak": "Weak evidence",
            "supported": "Verified"}.get(v.get("verdict"), "")
    tail = "; ".join(factors) if factors else esc(v.get("note", ""))
    return f"<b>{head}.</b> {tail}".strip() if head else tail


def _trust_summary_html(summary: dict) -> str:
    if not summary:
        return ""
    avg = summary.get("avg_trust")
    pct = summary.get("pct_high_trust")
    blocked = summary.get("fund_gate_blocked")
    gate = ("<span class='gate-blocked'>⛔ funding gate BLOCKED</span>"
            if blocked else "<span class='gate-ok'>✓ no contradictions</span>")
    if avg is None:
        avg_cell = "<b>—</b>"
    else:
        cat = "High" if avg >= 0.7 else "Medium" if avg >= 0.4 else "Low"
        avg_cell = (f"<b>{cat}</b><span class='note' style='font-size:.72rem'>"
                    f"avg {avg:.2f}</span>")
    return (
        "<div class='card' style='margin:1rem 0'><div class='trustbar'>"
        f"<div class='cell'>overall trust{avg_cell}</div>"
        f"<div class='cell'>high-trust claims<b>{pct if pct is not None else '—'}%</b></div>"
        f"<div class='cell'>contradicted<b>{summary.get('contradicted', 0)}</b></div>"
        f"<div class='cell'>honest gaps<b>{summary.get('gaps', 0)}</b></div>"
        f"<div class='cell'>{gate}</div>"
        "</div></div>"
    )


def _render_claims(section: str, claims: list, verdicts: dict, start_idx: int,
                   entity_id: int) -> tuple[str, int]:
    out = []
    idx = start_idx
    for c in claims:
        cid = f"{section}:{c.get('id', idx)}"
        v = verdicts.get(cid, {})
        ctype = v.get("claim_type")
        ctype_html = (f"<span class='ctype'>{esc(ctype)}</span>"
                      if ctype and ctype != "gap" else "")
        # Evidence anchors live on the founder timeline, not this page — link there.
        ev = " ".join(f"<a href='/founder/{entity_id}#ev{i}'>#{i}</a>"
                      for i in c.get("evidence_ids", []))
        gap = " <b>[missing — flagged, not guessed]</b>" if c.get("gap") else ""
        why = _trust_reason(v)
        why_html = f"<div class='cwhy'>{why}</div>" if why else ""
        out.append(
            f"<li class='claim'>"
            f"<div class='ctext'>{esc(c.get('text'))}{gap}</div>"
            f"<div class='cmeta'>{_trust_badge(v)} {ctype_html} "
            f"<span class='note'>evidence {ev if ev else '—'}</span></div>"
            f"{why_html}</li>"
        )
        idx += 1
    return "".join(out), idx


def _memo_cached(conn, entity_id: int) -> bool:
    return any(e["event_type"] == "memo"
               for e in ledger.events_for(conn, entity_id))


def _memo_loading_page(entity_id: int, name: str, fresh: bool):
    """Instant page shown while the backend generates the memo (spinner + timer).
    Client-side JS kicks off generation, shows elapsed time, then swaps in the memo."""
    q = "?fresh=1" if fresh else ""
    body = (
        f"<p><a class='btn ghost' href='/founder/{entity_id}' style='margin-top:0'>← Back to founder</a></p>"
        f"<div class='card genwrap'>"
        f"<div class='spinner'></div>"
        f"<h2 style='margin:1rem 0 .3rem'>Generating investment memo…</h2>"
        f"<p class='note' style='max-width:34rem;margin:0 auto'>Running three axis agents, "
        f"drafting an evidence-locked memo, and adversarially validating every claim against "
        f"the ledger. Usually ~10–30 seconds.</p>"
        f"<p style='margin-top:1rem'>elapsed <span class='elapsed' id='el'>0.0s</span></p></div>"
        f"<script>"
        f"var t0=Date.now(),el=document.getElementById('el');"
        f"var iv=setInterval(function(){{el.textContent=((Date.now()-t0)/1000).toFixed(1)+'s';}},100);"
        f"fetch('/memo/{entity_id}/generate{q}').then(function(r){{return r.json();}})"
        f".then(function(){{clearInterval(iv);location.replace('/memo/{entity_id}');}})"
        f".catch(function(){{clearInterval(iv);el.textContent='error — please retry';}});"
        f"</script>"
    )
    return page(f"Generating memo — {name}", body)


@app.get("/memo/{entity_id}/generate")
def memo_generate(entity_id: int, fresh: int = 0):
    """Blocking generation endpoint the loading page calls via fetch()."""
    conn = db.connect()
    intelligence.generate_memo(conn, entity_id, fresh=bool(fresh))
    return JSONResponse({"ok": True})


@app.get("/memo/{entity_id}", response_class=HTMLResponse)
def memo_view(entity_id: int, fresh: int = 0):
    conn = db.connect()
    row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return page("Not found", "<p>No such entity.</p>")
    # If the memo must be built (or a regenerate was asked), show the loading
    # page instead of blocking; it triggers generation and swaps itself out.
    if fresh or not _memo_cached(conn, entity_id):
        return _memo_loading_page(entity_id, row["canonical_name"], bool(fresh))
    r = intelligence.generate_memo(conn, entity_id, fresh=False)

    axes_html = "".join(
        f"<div class='card axis reveal'><span class='axname'>{esc(ax)}</span> "
        f"{_trend_pill(v.get('trend', 'stable'))}"
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
    trust_summary_html = _trust_summary_html(r["validation"].get("summary"))

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
    verdict_txt = d["decision"] if fund else "DECLINE — do not fund"
    decision_html = (
        f"<div class='banner {'go' if fund else 'no'} reveal'>"
        f"<div style='font-size:1.35rem;font-weight:750'>{'✅' if fund else '🚫'} {esc(verdict_txt)}</div>"
        f"<div style='margin-top:.35rem'><b>Why:</b> {esc('; '.join(d['reasons']))}</div>"
        f"<span class='note'>deterministic rule: {esc(d['rule'])} · "
        f"LLM writes rationale, never the decision</span>{fit_line}</div>"
    )
    body = (
        f"<div style='display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.4rem'>"
        f"<a class='btn ghost' href='/founder/{entity_id}' style='margin-top:0'>← Back to founder</a>"
        f"<a class='btn ghost' href='/memo/{entity_id}?fresh=1' style='margin-top:0'>↻ Regenerate memo</a></div>"
        f"<div class='hero reveal' style='padding-bottom:0'>"
        f"<p class='eyebrow'>Evidence-locked memo</p>"
        f"<h1>Investment memo — <span class='grad'>{esc(r['founder'])}</span></h1>"
        f"<p class='note'>model {esc(r['model'])} · generated {esc(r['generated_at'])} · "
        f"thesis: {esc(r['thesis']['fund_name'])} · "
        f"<a href='/founder/{entity_id}'>evidence timeline</a></p></div>"
        f"<p class='eyebrow reveal' style='margin-bottom:.4rem'>The $100K decision</p>"
        f"{decision_html}"
        f"<h3 class='reveal'>Evidence health{_info('How much of this memo is backed by verified evidence vs unverified or contradicted claims.')}</h3>"
        f"{trust_summary_html}"
        f"<h3 class='reveal'>Multi-axis screening{_info('Three independent report cards from the AI. Never averaged — the decision gate reads each separately.')}</h3>"
        f"<p class='note reveal' style='margin-top:-.3rem;max-width:44rem'>Three report cards "
        f"(Founder · Market · Idea), each 0–10, scored on its own slice of evidence so they "
        f"can genuinely disagree. <b>Score</b> = how good; <b>confidence</b> = how sure the AI is.</p>"
        f"<div class='axes'>{axes_html}</div>"
        f"<h3 class='reveal'>Evidence-locked memo{_info('Every claim cites its source events; each carries a deterministic Trust Score.')}</h3>"
        f"<p class='note reveal' style='margin-top:-.3rem;max-width:44rem'>Each claim shows a "
        f"colour-coded Trust Score — green = verified, amber = weak/inference, red = contradicted, "
        f"grey = honestly flagged gap.</p>"
        f"{sections_html}"
        f"<p class='note reveal'>Trust is <b>deterministic</b>: the LLM only gives a "
        f"verdict; the score = citation validity × fact-grounding × source "
        f"reliability × corroboration × verdict. Numbers in a claim are checked "
        f"against the cited event's payload, so a fabricated figure is caught in "
        f"code, not by the model. Each claim shows in plain words why it scored what it did.</p>"
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


# Resolved public-profile links, cached per entity for the session so a
# re-click (or a re-view) is instant and spends no extra Tavily credits.
_PROFILE_CACHE: dict = {}


@app.get("/api/founder/{entity_id}/profiles")
def api_founder_profiles(entity_id: int):
    """Live LinkedIn / X profile lookup for a founder (dynamic, not seeded).
    Name-guarded via the Tavily connector; returns {linkedin, x} or an
    `error` field the UI degrades on. Never 500s the page."""
    import os

    from .connectors import tavily

    if not os.environ.get("TAVILY_API_KEY"):
        return JSONResponse({"error": "not configured"})
    if entity_id in _PROFILE_CACHE:
        return JSONResponse(_PROFILE_CACHE[entity_id])
    conn = db.connect()
    row = conn.execute(
        "SELECT canonical_name FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    if row is None:
        return JSONResponse({"error": "no such entity"}, status_code=404)
    try:
        res = tavily.find_profiles(row["canonical_name"])
    except Exception:
        return JSONResponse({"error": "lookup failed"})
    res["name"] = row["canonical_name"]
    _PROFILE_CACHE[entity_id] = res
    return JSONResponse(res)
