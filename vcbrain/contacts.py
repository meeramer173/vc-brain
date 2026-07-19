"""Self-declared contact extraction — accurate by design, never guessed.

We only ever attach contact info a founder has PUBLICLY DECLARED about
themselves. No name matching, no scraping:

- GitHub: the profile `email` field, the `/users/{login}/social_accounts`
  endpoint (the links the user chose to publish), and any LinkedIn/email in
  their bio.
- Hacker News: the `about` field (already in the ledger as a
  `profile_snapshot`), where HN users routinely list email / site / socials.

When nothing is declared we record nothing — abstaining is the correct
answer, exactly like entity resolution does.

Each find is stored as one `contact` event with source="system", so it stays
entirely out of the Founder Score (breadth, cadence, momentum and validation
are all unaffected) and out of the LLM evidence digest. It lives in Memory
like every other fact and is fully auditable: the payload records where each
field came from.
"""

import hashlib
import html
import json
import os
import re
import sqlite3

import httpx

from . import ledger

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9\-_%.]+",
    re.IGNORECASE,
)

GITHUB_API = "https://api.github.com"


def _clean_email(email: str | None) -> str | None:
    """Keep only a real, reachable address. GitHub's privacy relay
    (`*users.noreply.github.com`) and any `noreply` address are not contactable,
    so they are not contact info."""
    if not email:
        return None
    e = email.strip().lower()
    if not EMAIL_RE.fullmatch(e):
        return None
    if "noreply" in e or e.endswith("users.noreply.github.com"):
        return None
    return e


def _norm_linkedin(url: str) -> str:
    """Canonical, clickable LinkedIn URL: force https, drop query + trailing
    slash. Used for both display and dedup."""
    u = url.strip()
    if not u.lower().startswith("http"):
        u = "https://" + u.lstrip("/")
    return u.split("?")[0].rstrip("/")


def extract_from_text(*texts: str | None) -> dict:
    """Pull a declared email + LinkedIn URL out of free text (a bio, an HN
    `about`). HTML-decoded first so `&#x2F;`-style entities resolve."""
    blob = html.unescape(" ".join(t for t in texts if t))
    out: dict = {"email": None, "linkedin": None}
    for m in EMAIL_RE.findall(blob):
        cleaned = _clean_email(m)
        if cleaned:
            out["email"] = cleaned
            break
    li = LINKEDIN_RE.search(blob)
    if li:
        out["linkedin"] = _norm_linkedin(li.group(0))
    return out


def github_contacts(login: str, token: str | None = None) -> dict:
    """Fetch the self-declared contact fields off a GitHub profile.

    Two public calls: the user object (email, blog, twitter, bio) and the
    social_accounts endpoint (explicitly published links). social_accounts is
    the most authoritative source for LinkedIn, so it wins over a bio match.
    Network / rate-limit failures degrade to an empty result — never raise.
    """
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "vcbrain-hackathon"}
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: dict = {"email": None, "linkedin": None, "twitter": None,
                 "blog": None, "source": {}}
    with httpx.Client(timeout=15) as client:
        try:
            r = client.get(f"{GITHUB_API}/users/{login}", headers=headers)
            if r.status_code == 200:
                d = r.json()
                email = _clean_email(d.get("email"))
                if email:
                    out["email"], out["source"]["email"] = email, "github:profile-email"
                if (d.get("blog") or "").strip():
                    out["blog"] = d["blog"].strip()
                if d.get("twitter_username"):
                    out["twitter"] = d["twitter_username"]
                bio = extract_from_text(d.get("bio"))
                if bio["linkedin"]:
                    out["linkedin"], out["source"]["linkedin"] = bio["linkedin"], "github:bio"
                if not out["email"] and bio["email"]:
                    out["email"], out["source"]["email"] = bio["email"], "github:bio"
        except httpx.HTTPError:
            pass
        try:
            r = client.get(f"{GITHUB_API}/users/{login}/social_accounts", headers=headers)
            if r.status_code == 200:
                for acc in r.json():
                    url = (acc.get("url") or "")
                    low = url.lower()
                    if "linkedin.com" in low:
                        out["linkedin"] = _norm_linkedin(url)
                        out["source"]["linkedin"] = "github:social_accounts"
                    elif ("x.com" in low or "twitter.com" in low) and not out["twitter"]:
                        out["twitter"] = url
        except httpx.HTTPError:
            pass
    return out


def _latest_hn_about(conn: sqlite3.Connection, entity_id: int) -> str | None:
    about = None
    for e in ledger.events_for(conn, entity_id):
        if e["event_type"] == "profile_snapshot" and e["payload"].get("about"):
            about = e["payload"]["about"]  # events are oldest-first → keep the newest
    return about


def discover(conn: sqlite3.Connection, entity_id: int) -> dict | None:
    """Merge declared contact info from every source this founder is known on.
    Returns None when nothing is declared (the honest, common case)."""
    row = conn.execute("SELECT handles FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return None
    handles = json.loads(row["handles"])
    found: dict = {"email": None, "linkedin": None, "twitter": None,
                   "blog": None, "sources": {}}

    gh_login = handles.get("github")
    if gh_login:
        g = github_contacts(gh_login)
        for field in ("email", "linkedin", "twitter", "blog"):
            if g.get(field) and not found[field]:
                found[field] = g[field]
                if field in g["source"]:
                    found["sources"][field] = g["source"][field]

    about = _latest_hn_about(conn, entity_id)
    if about:
        ex = extract_from_text(about)
        if ex["email"] and not found["email"]:
            found["email"], found["sources"]["email"] = ex["email"], "hn:about"
        if ex["linkedin"] and not found["linkedin"]:
            found["linkedin"], found["sources"]["linkedin"] = ex["linkedin"], "hn:about"

    if not (found["email"] or found["linkedin"]):
        return None
    return found


def record_contact(conn: sqlite3.Connection, entity_id: int, contact: dict) -> int | None:
    """Append a `contact` event. Content-addressed dedup: the same declared
    contact never duplicates, but a changed one records a fresh event, and
    `latest_contact` always returns the newest."""
    sig = json.dumps({k: contact.get(k) for k in ("email", "linkedin")}, sort_keys=True)
    digest = hashlib.md5(sig.encode()).hexdigest()[:12]
    payload = {**contact, "discovered_at": ledger.utcnow_iso()}
    return ledger.record(
        conn, entity_id, "system", "contact", ledger.utcnow_iso(),
        f"system:contact:{entity_id}:{digest}", payload,
    )


def latest_contact(conn: sqlite3.Connection, entity_id: int) -> dict | None:
    contacts = [e for e in ledger.events_for(conn, entity_id)
                if e["event_type"] == "contact"]
    return contacts[-1]["payload"] if contacts else None


def enrich_entity(
    conn: sqlite3.Connection, entity_id: int, with_headline: bool = False
) -> dict | None:
    """Discover + persist contact info for one founder. When `with_headline`
    and a declared LinkedIn URL exist, attach the public search snippet
    (Option A — URL-anchored, no scraping) as `headline`."""
    contact = discover(conn, entity_id)
    if contact is None:
        return None
    if with_headline and contact.get("linkedin"):
        row = conn.execute(
            "SELECT canonical_name FROM entities WHERE id=?", (entity_id,)
        ).fetchone()
        try:
            from .connectors import tavily
            head = tavily.linkedin_headline(row["canonical_name"], contact["linkedin"])
            if head:
                contact["headline"] = head
        except Exception:
            pass  # headline is a bonus; never let it sink the enrichment
    record_contact(conn, entity_id, contact)
    return contact


def enrich_all(
    conn: sqlite3.Connection, limit: int = 50, with_headline: bool = False
) -> dict:
    """Enrich the most-active founders first. Returns a summary; founders with
    nothing declared are counted as `abstained`, not failures."""
    rows = conn.execute(
        """
        SELECT e.id FROM entities e LEFT JOIN events ev ON ev.entity_id = e.id
        WHERE e.kind = 'person' AND e.merged_into IS NULL
        GROUP BY e.id ORDER BY COUNT(ev.id) DESC, e.id ASC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    found, abstained = [], 0
    for r in rows:
        c = enrich_entity(conn, r["id"], with_headline=with_headline)
        if c is None:
            abstained += 1
        else:
            found.append({"entity": r["id"], "email": c.get("email"),
                          "linkedin": c.get("linkedin")})
    return {"scanned": len(rows), "with_contact": len(found),
            "abstained": abstained, "found": found}
