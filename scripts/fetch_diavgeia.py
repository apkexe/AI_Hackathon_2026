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
import time

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
    'organizationUid:["6","15","100054486","100054489","100054492","100056663","100081880"] '
    'AND decisionTypeUid:["\u0392.1.3","\u0392.2.1"]'
)
BACKEND_URL = "http://localhost:8001/api/ingest"

# Mapping of Diavgeia organization IDs to human-readable names
ORG_ID_TO_LABEL = {
    "6": "Υπουργείο Εθνικής Άμυνας",
    "15": "Υπουργείο Οικονομικών",
    "100054486": "Υπουργείο Ψηφιακής Διακυβέρνησης",
    "100054489": "Υπουργείο Προστασίας του Πολίτη",
    "100054492": "Υπουργείο Εσωτερικών",
    "100056663": "Υπουργείο Μετανάστευσης και Ασύλου",
    "100081880": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
}


def _parse_decisions(decisions):
    """Parse a list of Diavgeia decision objects into contract dicts."""
    contracts = []
    for decision in decisions:
        extra = decision.get("extraFieldValues") or {}
        budget = extra.get("amountWithTaxes", 0)
        if not budget:
            vat_obj = extra.get("amountWithVAT") or {}
            budget = vat_obj.get("amount", 0) if isinstance(vat_obj, dict) else 0

        # Resolve organization label from ID mapping
        org_id = str(decision.get("organizationId", ""))
        municipality = ORG_ID_TO_LABEL.get(org_id, decision.get("organizationLabel") or "Unknown")

        contract = {
            "id": decision.get("ada", ""),
            "contractor": (extra.get("sponsorName") or "Unknown").replace("\n", " "),
            "budget": float(budget or 0),
            "date": decision.get("issueDate", ""),
            "description": (decision.get("subject") or "").replace("\n", " "),
            "municipality": municipality,
            "category": _infer_category(decision.get("subject", ""))
        }
        contracts.append(contract)
    return contracts


def _fetch_for_org(org_uid, org_label, per_org_limit):
    """Fetch contracts for a single organization with pagination."""
    query = (
        f'organizationUid:"{org_uid}" '
        'AND decisionTypeUid:["\u0392.1.3","\u0392.2.1"]'
    )
    contracts = []
    page = 0
    page_size = 50

    while len(contracts) < per_org_limit:
        params = {"q": query, "size": page_size, "page": page, "sort": "recent"}
        try:
            response = requests.get(DIAVGEIA_ADVANCED_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"  [{org_label}] API failed on page {page}: {e}")
            break

        decisions = data.get("decisions") or data.get("decisionResultList") or []
        if not decisions:
            break

        contracts.extend(_parse_decisions(decisions))

        info = data.get("info", {})
        total_available = info.get("total")
        logger.info(
            f"  [{org_label}] page {page}: {len(contracts)}/{per_org_limit}"
            + (f" (available: {total_available})" if total_available else "")
        )

        if total_available is not None and (page + 1) * page_size >= total_available:
            break

        page += 1
        time.sleep(0.3)

    return contracts[:per_org_limit]


def fetch_from_diavgeia(limit=50):
    """Fetch contracts from Diavgeia, balanced equally across all monitored ministries."""
    per_org = limit // len(ORG_ID_TO_LABEL)
    logger.info(f"Fetching {per_org} contracts from each of {len(ORG_ID_TO_LABEL)} ministries ({limit} total)...")

    all_contracts = []
    for org_uid, org_label in ORG_ID_TO_LABEL.items():
        logger.info(f"Fetching from {org_label} (UID: {org_uid})...")
        org_contracts = _fetch_for_org(org_uid, org_label, per_org)
        logger.info(f"  Got {len(org_contracts)} from {org_label}")
        all_contracts.extend(org_contracts)

    logger.info(f"Total fetched: {len(all_contracts)} contracts across {len(ORG_ID_TO_LABEL)} ministries.")
    return all_contracts


CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audited_contracts_cache.json")


def ingest_direct(contracts):
    """Run the full pipeline locally (rules -> AI audit -> ChromaDB)."""
    total = len(contracts)

    logger.info(f"Running rule evaluation on all {total} contracts...")
    contracts = evaluate_rules(contracts)

    # Count flagged contracts (Medium or High risk after rules)
    flagged = [c for c in contracts if c.get("risk_level") in ("Medium", "High")]
    logger.info(f"Rule evaluation complete: {len(flagged)}/{total} contracts flagged for AI audit.")

    logger.info("Running AI audit on flagged contracts...")
    contracts = audit_contracts(contracts)

    # Cache audited contracts so we can skip fetch+audit on re-run
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(contracts, f, ensure_ascii=False, indent=2)
    logger.info(f"Cached {len(contracts)} audited contracts to {CACHE_PATH}")

    logger.info("Storing in ChromaDB...")
    vs = VectorStore()
    vs.ingest_contracts(contracts)

    logger.info(f"Direct ingestion complete. Total: {total}, Flagged: {len(flagged)}.")


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
    parser.add_argument("--from-cache", action="store_true",
                        help="Skip fetch+audit, load previously cached contracts and store in ChromaDB")
    args = parser.parse_args()

    if args.from_cache:
        if not os.path.exists(CACHE_PATH):
            logger.error(f"No cache file found at {CACHE_PATH}. Run without --from-cache first.")
            return
        logger.info(f"Loading cached contracts from {CACHE_PATH}...")
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            contracts = json.load(f)
        logger.info(f"Loaded {len(contracts)} contracts from cache.")
        logger.info("Storing in ChromaDB...")
        vs = VectorStore()
        vs.ingest_contracts(contracts)
        logger.info("Done (from cache).")
        return

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
