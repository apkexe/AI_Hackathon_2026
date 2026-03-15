"""
Standalone script to fetch real contracts from Diavgeia and run the CitizenGov pipeline.
Replicates what the n8n workflow does, without requiring n8n.

Usage:
    python scripts/fetch_diavgeia.py                    # Direct pipeline with real data
    python scripts/fetch_diavgeia.py --mock              # Use mock data instead
    python scripts/fetch_diavgeia.py --mode api          # POST to FastAPI backend
    python scripts/fetch_diavgeia.py --limit 10          # Limit to 10 contracts
"""
import argparse
import json
import logging
import os
import sys

import requests

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_ingestion.scraper import _infer_category, fetch_contracts
from app.data_ingestion.embeddings import VectorStore
from app.watchdog.rules import evaluate_rules
from app.watchdog.agent import audit_contracts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("fetch_diavgeia")

DIAVGEIA_ADVANCED_URL = "https://diavgeia.gov.gr/opendata/search/advanced.json"
DIAVGEIA_QUERY = (
    'organizationUid:["6013","6114","6247","6","100054486","100054492","100081880"] '
    'AND decisionTypeUid:["\u0392.1.3","\u0392.2.1"]'
)
BACKEND_URL = "http://localhost:8001/api/ingest"


def fetch_from_diavgeia(limit=50):
    """Fetch real contracts from the Diavgeia advanced search API."""
    logger.info(f"Fetching up to {limit} contracts from Diavgeia...")
    params = {"q": DIAVGEIA_QUERY, "size": limit, "sort": "recent"}
    response = requests.get(DIAVGEIA_ADVANCED_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Advanced endpoint returns "decisions", basic returns "decisionResultList"
    decisions = data.get("decisions") or data.get("decisionResultList") or []

    contracts = []
    for decision in decisions:
        extra = decision.get("extraFieldValues") or {}
        budget = extra.get("amountWithTaxes", 0)
        if not budget:
            vat_obj = extra.get("amountWithVAT") or {}
            budget = vat_obj.get("amount", 0) if isinstance(vat_obj, dict) else 0

        contract = {
            "id": decision.get("ada", ""),
            "contractor": (extra.get("sponsorName") or "Unknown").replace("\n", " "),
            "budget": float(budget or 0),
            "date": decision.get("issueDate", ""),
            "description": (decision.get("subject") or "").replace("\n", " "),
            "municipality": (decision.get("organizationLabel") or "Unknown").replace("\n", " "),
            "category": _infer_category(decision.get("subject", ""))
        }
        contracts.append(contract)

    return contracts


def ingest_direct(contracts):
    """Run the full pipeline locally (rules -> AI audit -> ChromaDB)."""
    logger.info("Running rule evaluation...")
    contracts = evaluate_rules(contracts)

    logger.info("Running AI audit on flagged contracts...")
    contracts = audit_contracts(contracts)

    logger.info("Storing in ChromaDB...")
    vs = VectorStore()
    vs.ingest_contracts(contracts)

    logger.info("Direct ingestion complete.")


def ingest_via_api(contracts):
    """POST each contract to the FastAPI backend (same as n8n does)."""
    success = 0
    for c in contracts:
        payload = {
            "ada": c["id"],
            "subject": c["description"],
            "issue_date": c["date"],
            "contractor": c["contractor"],
            "budget": c["budget"],
            "municipality": c["municipality"]
        }
        try:
            resp = requests.post(BACKEND_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                success += 1
            logger.info(f"  {c['id']}: HTTP {resp.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"  {c['id']}: Failed - {e}")

    logger.info(f"API ingestion complete: {success}/{len(contracts)} successful.")


def main():
    parser = argparse.ArgumentParser(description="CitizenGov Diavgeia Fetcher")
    parser.add_argument("--mode", choices=["direct", "api"], default="direct",
                        help="'direct' runs the pipeline locally, 'api' POSTs to the FastAPI backend")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max number of contracts to fetch (default: 50)")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock data instead of calling the Diavgeia API")
    args = parser.parse_args()

    if args.mock:
        logger.info("Using mock data...")
        contracts = fetch_contracts(use_mock_data=True)
    else:
        try:
            contracts = fetch_from_diavgeia(limit=args.limit)
        except Exception as e:
            logger.error(f"Diavgeia API failed: {e}")
            logger.info("Falling back to mock data...")
            contracts = fetch_contracts(use_mock_data=True)

    logger.info(f"Fetched {len(contracts)} contracts.")

    if not contracts:
        logger.error("No contracts to process. Exiting.")
        return

    if args.mode == "direct":
        ingest_direct(contracts)
    else:
        ingest_via_api(contracts)

    logger.info("Done.")


if __name__ == "__main__":
    main()
