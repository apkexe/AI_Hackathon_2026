"""
CLI Script to run the full ingestion and auditing pipeline.

Usage:
    python scripts/ingest.py          # Ingest mock data
    python scripts/ingest.py --real   # Ingest real data from Diavgeia API
"""
import argparse
import logging
from typing import List, Dict, Any

from app.data_ingestion.scraper import fetch_contracts
from app.data_ingestion.embeddings import VectorStore
from app.watchdog.rules import evaluate_rules
from app.watchdog.agent import audit_contracts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ingest")

def main():
    parser = argparse.ArgumentParser(description="CitizenGov Ingestion Pipeline")
    parser.add_argument("--real", action="store_true",
                        help="Fetch real data from Diavgeia API instead of mock data")
    args = parser.parse_args()

    use_mock = not args.real

    logger.info("Starting CitizenGov Ingestion Pipeline...")

    # 1. Fetch data
    logger.info(f"Step 1: Fetching contracts ({'real API' if args.real else 'mock data'})...")
    contracts = fetch_contracts(use_mock_data=use_mock)

    if not contracts:
        logger.error("No contracts fetched. Exiting.")
        return

    # 2. Rule evaluation (pre-flagging anomalies)
    logger.info("Step 2: Evaluating watchdog rules...")
    contracts = evaluate_rules(contracts)

    # 3. AI Auditing
    logger.info("Step 3: AI Auditing flagged contracts...")
    contracts = audit_contracts(contracts)

    # 4. Vector Storage
    logger.info("Step 4: Creating embeddings & storing in ChromaDB...")
    vs = VectorStore()
    vs.ingest_contracts(contracts)

    logger.info("Pipeline Complete. Data is ready for the dashboard.")

if __name__ == "__main__":
    main()
