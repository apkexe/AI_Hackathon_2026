"""
RAG Query Analyzer – extracts structured filters from natural language queries.
Uses keyword/regex matching only (no LLM calls).
"""
import re
from typing import Dict, Any, Optional


# Ministry mappings: keyword -> canonical name stored in ChromaDB municipality field
_MUNICIPALITY_MAP = {
    # Ministry of National Defence
    "defence": "Εθνικής Άμυνας",
    "defense": "Εθνικής Άμυνας",
    "military": "Εθνικής Άμυνας",
    "άμυνα": "Εθνικής Άμυνας",
    "αμυν": "Εθνικής Άμυνας",
    "στρατ": "Εθνικής Άμυνας",
    # Ministry of Finance
    "finance": "Οικονομικών",
    "economy": "Οικονομικών",
    "οικονομικ": "Οικονομικών",
    # Ministry of Digital Governance
    "digital": "Ψηφιακής Διακυβέρνησης",
    "ψηφιακ": "Ψηφιακής Διακυβέρνησης",
    # Ministry of Citizen Protection
    "citizen protection": "Προστασίας του Πολίτη",
    "police": "Προστασίας του Πολίτη",
    "security": "Προστασίας του Πολίτη",
    "προστασ": "Προστασίας του Πολίτη",
    "αστυνομ": "Προστασίας του Πολίτη",
    # Ministry of Interior
    "interior": "Εσωτερικών",
    "εσωτερικ": "Εσωτερικών",
    # Ministry of Migration and Asylum
    "migration": "Μετανάστευσης",
    "asylum": "Μετανάστευσης",
    "μεταναστ": "Μετανάστευσης",
    "άσυλ": "Μετανάστευσης",
    # Ministry of Education
    "education": "Παιδείας",
    "school": "Παιδείας",
    "παιδεί": "Παιδείας",
    "εκπαίδ": "Παιδείας",
    "σχολ": "Παιδείας",
}

# Risk level keywords
_RISK_HIGH = [r"high risk", r"risky", r"flagged", r"suspicious", r"dangerous", r"fraud"]
_RISK_MEDIUM = [r"medium risk", r"moderate"]
_RISK_LOW = [r"low risk", r"safe", r"clean"]

# Budget patterns
_BUDGET_PATTERNS = [
    # "over 100k", "above €50,000", "more than 1 million"
    (r"(?:over|above|more than|greater than|exceeding|>\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "min"),
    # "under 500k", "below €1,000,000", "less than 2m"
    (r"(?:under|below|less than|up to|<\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "max"),
    # "between 10k and 50k"
    (r"between[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?[^\d]*?and[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "range"),
]


def _parse_amount(value_str: str, suffix: Optional[str]) -> float:
    """Convert a number string with optional k/m suffix to a float."""
    value = float(value_str.replace(",", "").replace(".", "").strip() or "0")
    # If the original string had a decimal point, try to preserve it
    if "." in value_str and not value_str.endswith("."):
        value = float(value_str.replace(",", "").strip())
    if suffix:
        suffix = suffix.lower()
        if suffix in ("k", "thousand"):
            value *= 1_000
        elif suffix in ("m", "million"):
            value *= 1_000_000
    return value


def analyze_query(query: str) -> Dict[str, Any]:
    """
    Analyze a natural language query and extract structured filters.

    Returns {"filters": {...}, "semantic_query": "..."}
    The filters dict only contains keys that were actually detected.
    """
    filters: Dict[str, Any] = {}
    query_lower = query.lower()
    remaining = query

    # --- Municipality detection ---
    for keyword, canonical in _MUNICIPALITY_MAP.items():
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(query):
            filters["municipality"] = canonical
            remaining = pattern.sub("", remaining)
            break

    # --- Risk level detection ---
    for pat in _RISK_HIGH:
        if re.search(pat, query_lower):
            filters["risk_level"] = "High"
            break
    if "risk_level" not in filters:
        for pat in _RISK_MEDIUM:
            if re.search(pat, query_lower):
                filters["risk_level"] = "Medium"
                break
    if "risk_level" not in filters:
        for pat in _RISK_LOW:
            if re.search(pat, query_lower):
                filters["risk_level"] = "Low"
                break

    # --- Budget detection ---
    # Check range first
    range_match = re.search(
        r"between[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?[^\d]*?and[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
        query_lower
    )
    if range_match:
        filters["budget_min"] = _parse_amount(range_match.group(1), range_match.group(2))
        filters["budget_max"] = _parse_amount(range_match.group(3), range_match.group(4))
        remaining = remaining[:range_match.start()] + remaining[range_match.end():]
    else:
        # Check min
        min_match = re.search(
            r"(?:over|above|more than|greater than|exceeding|>\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
            query_lower
        )
        if min_match:
            filters["budget_min"] = _parse_amount(min_match.group(1), min_match.group(2))
            remaining = remaining[:min_match.start()] + remaining[min_match.end():]

        # Check max
        max_match = re.search(
            r"(?:under|below|less than|up to|<\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
            query_lower
        )
        if max_match:
            filters["budget_max"] = _parse_amount(max_match.group(1), max_match.group(2))
            remaining = remaining[:max_match.start()] + remaining[max_match.end():]

    # --- Semantic query: clean up remaining text ---
    semantic_query = re.sub(r"\s+", " ", remaining).strip()
    if not semantic_query:
        semantic_query = query

    return {
        "filters": filters,
        "semantic_query": semantic_query,
    }
