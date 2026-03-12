"""
Module B, Task 2 & 3: AI Auditing and Output Mapping
The Watchdog Agent connects to OpenRouter, processes flagged contracts, and maps results.
"""
import json
import logging
from typing import List, Dict, Any
import requests

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, DEMO_MODE
from app.prompts.templates import build_watchdog_prompt, WATCHDOG_SYSTEM_PROMPT
# Note: we import parser functions directly to avoid circular dependency
import app.prompts.parser as parser

logger = logging.getLogger(__name__)

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Wrapper to call the LLM API via OpenRouter."""
    if DEMO_MODE:
        logger.info("DEMO MODE: Simulating LLM response.")
        # We simulate a "perfect" response from the LLM
        return """{
  "contractor": "Simulated Contractor",
  "category": "IT Services",
  "budget": 999999,
  "risk_level": "High",
  "risk_summary": "Simulated AI Audit: High budget allocated for a basic website update; awarded to a company registered only 3 days prior."
}"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    
    try:
        response = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {e}")
        if hasattr(response, "text"):
            logger.error(f"Response details: {response.text}")
        raise e

def audit_contracts(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Passes flagged contracts (Medium risk) to the AI Agent for full auditing.
    Updates the contract objects in-place with the final risk assessment.
    """
    for c in contracts:
        # Only audit contracts that the rule engine flagged, to save API costs
        # Or audit all of them if they contain 'high' in description (just for demo purposes)
        if c.get("risk_level") == "Medium" or "High budget allocated" in c.get("description", ""):
            
            user_prompt = build_watchdog_prompt(
                contract_description=c.get("description", ""),
                budget=float(c.get("budget", 0)),
                contractor=c.get("contractor", ""),
                category=c.get("category", "")
            )
            
            logger.info(f"Auditing contract {c.get('id')} via AI...")
            try:
                # Call LLM
                raw_response = call_llm(WATCHDOG_SYSTEM_PROMPT, user_prompt)
                
                # Module C: Fallback parser
                parsed_assessment = parser.parse_llm_response(raw_response, max_retries=3, original_prompt=user_prompt)
                
                if parsed_assessment:
                    # Module B Task 3: Output Mapping
                    c["risk_level"] = parsed_assessment.risk_level
                    c["risk_summary"] = parsed_assessment.risk_summary
                    logger.info(f"AI Audit Complete: Risk Level '{c['risk_level']}' mapped.")
                else:
                    logger.warning(f"AI Audit Failed for contract {c.get('id')} – retaining rule-engine defaults.")
                    
            except Exception as e:
                logger.error(f"Agent failed to audit contract {c.get('id')}: {e}")
                
    return contracts

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_contract = [{
        "id": "test1",
        "contractor": "WebDesigners Ltd.",
        "description": "High budget allocated for a basic website update; awarded to a company registered only 3 days prior.",
        "budget": 150000,
        "category": "IT Services",
        "risk_level": "Medium" # Force audit
    }]
    res = audit_contracts(test_contract)
    print(json.dumps(res, indent=2))
