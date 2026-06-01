#!/usr/bin/env sh
# Start the Sales Lead Research web UI. On first run (no customer database
# yet), seed the bundled demo dataset so the UI shows real account matches.
set -e

DB="${SALES_DB_PATH:-/app/data/customers.sqlite}"

if [ ! -f "$DB" ]; then
  echo "No customer database at $DB."
  echo "Seeding the bundled demo dataset (FedEx / DHL / Apple / Microsoft / 3M families)..."
  mkdir -p "$(dirname "$DB")"
  python scripts/init_dummy_db.py
fi

echo "Sales Lead Research API -> http://localhost:${APP_PORT:-8000}"
exec uvicorn sales_lead_research.api:app --host 0.0.0.0 --port "${APP_PORT:-8000}"
