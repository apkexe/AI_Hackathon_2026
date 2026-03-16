"""
Repair script: re-fetches contract metadata from Diavgeia to fix organization
and category fields, then merges with existing AI audit results from cache.
Does NOT re-run the expensive LLM audits.

Usage:
    python scripts/repair_cache.py
    python scripts/repair_cache.py --reingest   # Also re-ingest into ChromaDB
"""
import argparse
import json
import logging
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_ingestion.scraper import _infer_category

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("repair_cache")

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audited_contracts_cache.json")

DIAVGEIA_ADVANCED_URL = "https://diavgeia.gov.gr/opendata/search/advanced.json"
DIAVGEIA_QUERY = (
    'organizationUid:["6","15","100054486","100054489","100054492","100056663","100081880"] '
    'AND decisionTypeUid:["\u0392.1.3","\u0392.2.1"]'
)

ORG_ID_TO_LABEL = {
    "6": "Υπουργείο Εθνικής Άμυνας",
    "15": "Υπουργείο Οικονομικών",
    "100054486": "Υπουργείο Ψηφιακής Διακυβέρνησης",
    "100054489": "Υπουργείο Προστασίας του Πολίτη",
    "100054492": "Υπουργείο Εσωτερικών",
    "100056663": "Υπουργείο Μετανάστευσης και Ασύλου",
    "100081880": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
}


def fetch_ada_to_org_mapping(limit=10000):
    """Re-fetch from Diavgeia to build ADA -> organizationId mapping."""
    logger.info(f"Re-fetching up to {limit} decisions to get organization IDs...")
    ada_to_org = {}
    page = 0

    while len(ada_to_org) < limit:
        params = {"q": DIAVGEIA_QUERY, "size": 50, "page": page, "sort": "recent"}
        try:
            response = requests.get(DIAVGEIA_ADVANCED_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"API request failed on page {page}: {e}")
            break

        decisions = data.get("decisions") or []
        if not decisions:
            break

        for d in decisions:
            ada = d.get("ada", "")
            org_id = str(d.get("organizationId", ""))
            if ada:
                ada_to_org[ada] = org_id

        info = data.get("info", {})
        total = info.get("total")
        logger.info(f"Page {page}: mapped {len(ada_to_org)} ADAs" +
                     (f" (API total: {total})" if total else ""))

        if total and (page + 1) * 50 >= total:
            break
        page += 1
        time.sleep(0.3)

    return ada_to_org


def main():
    parser = argparse.ArgumentParser(description="Repair cached contracts")
    parser.add_argument("--reingest", action="store_true",
                        help="Also re-ingest into ChromaDB after repair")
    args = parser.parse_args()

    if not os.path.exists(CACHE_PATH):
        logger.error(f"No cache at {CACHE_PATH}. Nothing to repair.")
        return

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        contracts = json.load(f)
    logger.info(f"Loaded {len(contracts)} contracts from cache.")

    # Step 1: Re-fetch org mapping from Diavgeia
    ada_to_org = fetch_ada_to_org_mapping(limit=len(contracts))
    logger.info(f"Built mapping for {len(ada_to_org)} ADAs.")

    # Step 2: Fix organization and re-categorize
    fixed_muni = 0
    fixed_cat = 0
    for c in contracts:
        ada = c.get("id", "")
        org_id = ada_to_org.get(ada, "")
        if org_id and org_id in ORG_ID_TO_LABEL:
            old_muni = c.get("organization", "Unknown")
            c["organization"] = ORG_ID_TO_LABEL[org_id]
            if old_muni != c["organization"]:
                fixed_muni += 1

        old_cat = c.get("category", "")
        new_cat = _infer_category(c.get("description", ""))
        if old_cat != new_cat:
            c["category"] = new_cat
            fixed_cat += 1

    logger.info(f"Fixed {fixed_muni} municipalities, {fixed_cat} categories.")

    # Step 3: Save repaired cache
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(contracts, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved repaired cache to {CACHE_PATH}")

    # Step 4: Optionally re-ingest
    if args.reingest:
        from app.data_ingestion.embeddings import VectorStore
        logger.info("Re-ingesting into ChromaDB...")
        vs = VectorStore()
        vs.ingest_contracts(contracts)
        logger.info("Re-ingestion complete.")

    # Print summary
    from collections import Counter
    risks = Counter(c.get("risk_level", "Low") for c in contracts)
    munis = Counter(c.get("organization", "Unknown") for c in contracts)
    cats = Counter(c.get("category", "?") for c in contracts)
    logger.info(f"Risk distribution: {dict(risks)}")
    logger.info(f"Municipality distribution: {dict(munis)}")
    logger.info(f"Category distribution: {dict(cats)}")


if __name__ == "__main__":
    main()
