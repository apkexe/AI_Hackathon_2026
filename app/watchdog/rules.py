"""
Module B, Task 1: Rule Definition
Basic rule engine computing averages and flagging anomalous contracts.
"""
import logging
from typing import List, Dict, Any

from app.config import ANOMALY_MULTIPLIER

logger = logging.getLogger(__name__)

def evaluate_rules(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Computes average budgets per category and flags contracts that exceed the 
    average by a given multiplier (e.g. 300%).
    Updates the contract dict in-place with preliminary risk levels.
    """
    if not contracts:
        return []

    # Calculate average budget per category
    category_totals = {}
    category_counts = {}
    
    for c in contracts:
        cat = c.get("category", "Miscellaneous")
        budget = float(c.get("budget", 0))
        
        category_totals[cat] = category_totals.get(cat, 0) + budget
        category_counts[cat] = category_counts.get(cat, 0) + 1
        
    category_averages = {
        cat: total / category_counts[cat] 
        for cat, total in category_totals.items()
    }
    
    logger.info(f"Category averages computed: {category_averages}")

    # Flag contracts
    flagged_count = 0
    for c in contracts:
        cat = c.get("category", "Miscellaneous")
        budget = float(c.get("budget", 0))
        avg = category_averages.get(cat, 0)
        
        # Default baseline
        c["risk_level"] = "Low"
        c["risk_summary"] = "Within standard budget expectations."
        
        # Anomaly rule: Budget is X times higher than average AND budget > 10000
        if avg > 0 and budget > (avg * ANOMALY_MULTIPLIER) and budget > 10000:
            c["risk_level"] = "Medium"  # The LLM will escalate this to High if warranted
            c["risk_summary"] = f"Rule Flag: Budget (€{budget}) is {budget/avg:.1f}x higher than the {cat} average (€{avg:.0f}). Sent to AI Watchdog for review."
            flagged_count += 1
            
    logger.info(f"Rule engine flagged {flagged_count} contracts for AI auditing.")
    return contracts
