"""Weekly dataset refresh.

Ingests fresh signals *on top of* the committed snapshot (so the ledger grows,
it is never rebuilt from scratch and never loses history), then writes a clean,
WAL-folded single-file snapshot back to data/vcbrain-seed.sqlite3.

Runs locally or from CI (.github/workflows/weekly-refresh.yml). The append-only
ledger dedups on a UNIQUE key, so re-seeing last week's items is a no-op — that
is why the free sources use an 8-day lookback (a full week + a day of overlap
cushion) with zero risk of duplicates.

Env knobs:
  LOOKBACK_DAYS    lookback window for hn/github (default 8)
  REFRESH_SOURCES  comma list of free sources to run (default hn,github,arxiv)
  RUN_LINKEDIN     "1" to also run LinkedIn discovery (spends Tavily credits)
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "vcbrain-seed.sqlite3"
DB = ROOT / "vcbrain.db"


def _run(*args: str) -> None:
    print("+ python -m vcbrain.cli", *args, flush=True)
    # non-fatal: one flaky source must not abandon the whole refresh
    subprocess.run([sys.executable, "-m", "vcbrain.cli", *args], cwd=ROOT)


def _reset_db() -> None:
    """Start from the committed snapshot so we grow it, not rebuild it."""
    for ext in ("", "-wal", "-shm"):
        p = Path(str(DB) + ext)
        if p.exists():
            p.unlink()
    if SEED.exists():
        shutil.copyfile(SEED, DB)


def _snapshot() -> None:
    """Fold the WAL in and write a clean, compact single-file snapshot back
    to the committed seed path. VACUUM INTO refuses to overwrite, so the old
    snapshot is removed first (its data is already inside DB)."""
    con = sqlite3.connect(DB)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if SEED.exists():
        SEED.unlink()
    con.execute("VACUUM INTO ?", (SEED.as_posix(),))
    con.close()


def _event_count(path: Path) -> int:
    if not path.exists():
        return 0
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        con.close()


def main() -> None:
    before = _event_count(SEED)
    _reset_db()
    _run("init")

    days = os.environ.get("LOOKBACK_DAYS", "8")
    sources = [
        s.strip()
        for s in os.environ.get("REFRESH_SOURCES", "hn,github,arxiv").split(",")
        if s.strip()
    ]
    for s in sources:
        if s == "hn":
            _run("ingest", "hn", "--days", days)
        elif s == "github":
            _run("ingest", "github", "--days", days)
        elif s == "arxiv":
            _run("ingest", "arxiv", "--max", "60")
        else:
            print(f"! unknown free source '{s}', skipping", flush=True)

    if os.environ.get("RUN_LINKEDIN") == "1":
        _run("ingest", "linkedin", "--limit", "15")

    _snapshot()
    con = sqlite3.connect(SEED)
    n_ev = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    n_ppl = con.execute(
        "SELECT COUNT(*) FROM entities WHERE kind='person' AND merged_into IS NULL"
    ).fetchone()[0]
    con.close()
    new_events = max(0, n_ev - before)
    print(f"seed refreshed -> {SEED}")
    print(f"  events: {n_ev} (+{new_events} new)  founders: {n_ppl}")

    # Tell CI whether anything genuinely changed. VACUUM rewrites the binary
    # every run, so the git diff is meaningless — gate commit/deploy on this.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"new_events={new_events}\n")
            fh.write(f"total_events={n_ev}\n")
            fh.write(f"founders={n_ppl}\n")


if __name__ == "__main__":
    main()
