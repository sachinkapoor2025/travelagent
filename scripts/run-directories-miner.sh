#!/usr/bin/env bash
# Run the directories (Google Maps / OSM) lead miner locally or invoke prod Lambda.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/api"

export STORAGE_BACKEND="${STORAGE_BACKEND:-dynamo}"
export AWS_REGION="${AWS_REGION:-ap-south-1}"
export LEADS_TABLE="${LEADS_TABLE:-travel-ai-leads-prod}"
export EVENTS_TABLE="${EVENTS_TABLE:-travel-ai-events-prod}"
export BOOKINGS_TABLE="${BOOKINGS_TABLE:-travel-ai-bookings-prod}"
export SESSIONS_TABLE="${SESSIONS_TABLE:-travel-ai-sessions-prod}"
export CONVERSATIONS_TABLE="${CONVERSATIONS_TABLE:-travel-ai-conversations-prod}"
export PRICE_ALERTS_TABLE="${PRICE_ALERTS_TABLE:-travel-ai-price-alerts-prod}"
export REFERRALS_TABLE="${REFERRALS_TABLE:-travel-ai-referrals-prod}"
export ITINERARIES_TABLE="${ITINERARIES_TABLE:-travel-ai-itineraries-prod}"

MODE="${1:-local}"

if [[ "$MODE" == "lambda" ]]; then
  FN="${WORKER_FUNCTION:-travel-ai-worker-prod}"
  echo "Invoking $FN with job=directories ..."
  aws lambda invoke \
    --region "$AWS_REGION" \
    --function-name "$FN" \
    --payload '{"job":"directories"}' \
    --cli-binary-format raw-in-base64-out \
    /tmp/directories-miner-out.json
  echo "Response:"
  cat /tmp/directories-miner-out.json
  echo
  exit 0
fi

echo "Running directories miner locally (dry-run fetch + optional import) ..."
python3 << 'PY'
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from app.services.miners.directories import mine_directories
from app.services.miners.orchestrator import run_source


async def main():
    raw = await mine_directories()
    print(f"Fetched {len(raw)} leads with phone numbers:")
    for lead in raw[:15]:
        print(f"  - {lead.get('name')} | {lead.get('phone')} | {lead.get('market')} | {lead.get('source_detail')}")

    if os.environ.get("IMPORT", "0") == "1" and raw:
        result = await run_source("directories")
        print("\nImport result:", json.dumps(result, indent=2))
    elif raw:
        print("\nSet IMPORT=1 to write leads to DynamoDB (requires AWS creds + table access).")


asyncio.run(main())
PY
