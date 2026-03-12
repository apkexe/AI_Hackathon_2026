"""
Module A, Task 1: API Scraper
Fetches public procurement contracts from Diavgeia API or uses local mock data.
"""
import json
import logging
from typing import List, Dict, Any
import requests

from app.config import SAMPLE_CONTRACTS_PATH

logger = logging.getLogger(__name__)

def fetch_contracts(use_mock_data: bool = True) -> List[Dict[str, Any]]:
    """
    Fetches contract data.
    If use_mock_data is true, loads from local JSON.
    Otherwise attempts to fetch from a public API (mocked Diavgeia integration).
    """
    if use_mock_data:
        logger.info(f"Loading mock contracts from {SAMPLE_CONTRACTS_PATH}")
        try:
            with open(SAMPLE_CONTRACTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load mock data: {e}")
            return []
    
    # Real-world API integration (example structure)
    api_url = "https://diavgeia.gov.gr/opendata/search.json?q=decisionType:B.2.1&size=50"
    logger.info(f"Fetching contracts from API: {api_url}")
    
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Transform Diavgeia specific schema to our internal schema
        contracts = []
        for doc in data.get("decisionResultList", []):
            try:
                # This is a simplified transformation for demonstration
                # Real Diavgeia API is much more complex
                contract = {
                    "id": doc.get("ada"),
                    "contractor": doc.get("extraFieldValues", {}).get("sponsorName", "Unknown"),
                    "budget": float(doc.get("extraFieldValues", {}).get("amountWithTaxes", 0)),
                    "date": doc.get("issueDate"),
                    "description": doc.get("subject"),
                    "municipality": doc.get("organizationLabel"),
                    "category": _infer_category(doc.get("subject", ""))
                }
                contracts.append(contract)
            except Exception as e:
                logger.warning(f"Failed to parse document {doc.get('ada')}: {e}")
                
        return contracts
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        logger.info("Falling back to mock data...")
        return fetch_contracts(use_mock_data=True)


def _infer_category(description: str) -> str:
    """Basic rule-based categorization as a fallback."""
    desc = description.lower()
    if any(kw in desc for kw in ["software", "hardware", "server", "web", "it", "computer"]):
        return "IT Services"
    elif any(kw in desc for kw in ["construct", "build", "renovat", "road"]):
        return "Construction"
    elif any(kw in desc for kw in ["consult", "study", "audit", "advis"]):
        return "Consulting"
    return "Miscellaneous"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    contracts = fetch_contracts(use_mock_data=True)
    print(f"Loaded {len(contracts)} contracts.")
    print(json.dumps(contracts[0], indent=2))
