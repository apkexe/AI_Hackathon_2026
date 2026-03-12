"""
CLI Script to run the full ingestion and auditing pipeline.
"""
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
    logger.info("Starting CitizenGov Ingestion Pipeline...")
    
    # 1. Fetch data
    logger.info("Step 1: Fetching contracts...")
    contracts = fetch_contracts(use_mock_data=True)
    
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
