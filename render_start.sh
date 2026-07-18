#!/usr/bin/env bash
# Render boot: free tier has no persistent disk, so seed the ledger from the
# committed snapshot on first start. Runtime writes (applications, memos)
# live until the next deploy/restart — fine for the demo.
set -e
if [ ! -f vcbrain.db ] && [ -f data/vcbrain-seed.sqlite3 ]; then
  cp data/vcbrain-seed.sqlite3 vcbrain.db
  echo "ledger seeded from snapshot"
fi
exec uvicorn vcbrain.app:app --host 0.0.0.0 --port "${PORT:-8000}"
