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
    
    # Real Diavgeia advanced search – same query as the n8n workflow
    api_url = "https://diavgeia.gov.gr/opendata/search/advanced.json"
    query = (
        'organizationUid:["6","15","100054486","100054489","100054492","100056663","100081880"] '
        'AND decisionTypeUid:["\u0392.1.3","\u0392.2.1"]'
    )
    logger.info(f"Fetching contracts from Diavgeia advanced search API...")

    try:
        response = requests.get(api_url, params={"q": query, "size": 50, "sort": "recent"}, timeout=30)
        response.raise_for_status()
        data = response.json()

        # The advanced endpoint returns "decisions", basic returns "decisionResultList"
        decisions = data.get("decisions") or data.get("decisionResultList") or []

        contracts = []
        for doc in decisions:
            try:
                extra = doc.get("extraFieldValues") or {}
                budget = extra.get("amountWithTaxes", 0)
                if not budget:
                    vat_obj = extra.get("amountWithVAT") or {}
                    budget = vat_obj.get("amount", 0) if isinstance(vat_obj, dict) else 0

                contract = {
                    "id": doc.get("ada", ""),
                    "contractor": (extra.get("sponsorName") or "Unknown").replace("\n", " "),
                    "budget": float(budget or 0),
                    "date": doc.get("issueDate", ""),
                    "description": (doc.get("subject") or "").replace("\n", " "),
                    "municipality": (doc.get("organizationLabel") or "Unknown").replace("\n", " "),
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
    """Rule-based categorization supporting both English and Greek keywords."""
    desc = description.lower()
    if any(kw in desc for kw in [
        "software", "hardware", "server", "web", "it", "computer",
        "πληροφορικ", "λογισμικ", "ψηφιακ", "ηλεκτρονικ", "διαδικτ",
        "υπολογιστ", "τεχνολογ", "πλατφόρμ", "μηχανογρ"
    ]):
        return "IT Services"
    elif any(kw in desc for kw in [
        "construct", "build", "renovat", "road",
        "κατασκευ", "οικοδομ", "ανακαίνισ", "οδοποι",
        "γέφυρα", "κτίριο", "κτηρι", "ασφαλτ", "δρόμο"
    ]):
        return "Construction"
    elif any(kw in desc for kw in [
        "consult", "study", "audit", "advis",
        "σύμβουλ", "μελέτ", "υπηρεσί", "παροχή υπηρεσ",
        "νομικ", "λογιστικ", "δαπάν", "πίστωσ", "δέσμευσ",
        "έγκρισ", "διάθεσ"
    ]):
        return "Consulting"
    elif any(kw in desc for kw in [
        "supply", "purchase", "procure", "equipment",
        "προμήθ", "εξοπλισμ", "αγορ", "προϊόν",
        "ανταλλακτικ", "υλικ", "τρόφιμ", "καύσιμ", "φάρμακ"
    ]):
        return "Supplies"
    elif any(kw in desc for kw in [
        "maintenance", "clean", "waste", "repair",
        "συντήρ", "καθαρ", "απορριμμ", "επισκευ",
        "αποκατάστασ", "φωτισμ"
    ]):
        return "Maintenance"
    elif any(kw in desc for kw in [
        "event", "festival", "ceremony", "conference",
        "εκδήλωσ", "φεστιβάλ", "συνέδρι", "γιορτ", "αγών",
        "αθλητ", "σχολικ", "παιδεί", "εκπαίδ"
    ]):
        return "Education & Events"
    elif any(kw in desc for kw in [
        "ανάληψη", "υποχρέωσ", "αποφασ", "κράτησ",
        "ανακλητικ", "πολυετ", "βεβαίωσ"
    ]):
        return "Budget Commitments"
    return "Public Expenditure"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    contracts = fetch_contracts(use_mock_data=True)
    print(f"Loaded {len(contracts)} contracts.")
    print(json.dumps(contracts[0], indent=2))
