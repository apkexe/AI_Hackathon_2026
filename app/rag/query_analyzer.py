"""
RAG Query Analyzer – extracts structured filters from natural language queries.
Uses keyword/regex matching only (no LLM calls).
"""
import re
import unicodedata
from typing import Dict, Any, Optional


def _strip_accents(text: str) -> str:
    """Remove Greek accent marks (tonos) for fuzzy matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# Ministry mappings: keyword -> full canonical name as stored in ChromaDB
_ORGANIZATION_MAP = {
    # Ministry of National Defence
    "defence": "Υπουργείο Εθνικής Άμυνας",
    "defense": "Υπουργείο Εθνικής Άμυνας",
    "military": "Υπουργείο Εθνικής Άμυνας",
    "αμυνα": "Υπουργείο Εθνικής Άμυνας",
    "αμυν": "Υπουργείο Εθνικής Άμυνας",
    "στρατ": "Υπουργείο Εθνικής Άμυνας",
    "εθνικης αμυνας": "Υπουργείο Εθνικής Άμυνας",
    # Ministry of Finance
    "finance": "Υπουργείο Οικονομικών",
    "economy": "Υπουργείο Οικονομικών",
    "οικονομικ": "Υπουργείο Οικονομικών",
    # Ministry of Digital Governance
    "digital": "Υπουργείο Ψηφιακής Διακυβέρνησης",
    "ψηφιακ": "Υπουργείο Ψηφιακής Διακυβέρνησης",
    "διακυβερνησ": "Υπουργείο Ψηφιακής Διακυβέρνησης",
    # Ministry of Citizen Protection
    "citizen protection": "Υπουργείο Προστασίας του Πολίτη",
    "police": "Υπουργείο Προστασίας του Πολίτη",
    "προστασ": "Υπουργείο Προστασίας του Πολίτη",
    "αστυνομ": "Υπουργείο Προστασίας του Πολίτη",
    "πολιτη": "Υπουργείο Προστασίας του Πολίτη",
    # Ministry of Interior
    "interior": "Υπουργείο Εσωτερικών",
    "εσωτερικ": "Υπουργείο Εσωτερικών",
    # Ministry of Migration and Asylum
    "migration": "Υπουργείο Μετανάστευσης και Ασύλου",
    "asylum": "Υπουργείο Μετανάστευσης και Ασύλου",
    "μεταναστ": "Υπουργείο Μετανάστευσης και Ασύλου",
    "ασυλ": "Υπουργείο Μετανάστευσης και Ασύλου",
    # Ministry of Education
    "education": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
    "school": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
    "παιδει": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
    "εκπαιδ": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
    "σχολ": "Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού",
}

# Risk level keywords (English + Greek, accent-stripped)
_RISK_HIGH = [
    r"high risk", r"risky", r"flagged", r"suspicious", r"dangerous", r"fraud",
    r"υψηλ[οοη] ρισκ", r"υψηλ[οοη] κινδυν", r"επικινδυν", r"κινδυν",
    r"ρισκ", r"υποπτ", r"απατ", r"παρανομ", r"παρατυπ",
    r"επισημαν", r"ανωμαλ",
]
_RISK_MEDIUM = [r"medium risk", r"moderate", r"μεσαι", r"μετρι"]
_RISK_LOW = [r"low risk", r"safe", r"clean", r"χαμηλ[οοη] ρισκ", r"χαμηλ[οοη] κινδυν", r"ασφαλ"]

# Budget patterns
_BUDGET_PATTERNS = [
    (r"(?:over|above|more than|greater than|exceeding|>\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "min"),
    (r"(?:under|below|less than|up to|<\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "max"),
    (r"between[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?[^\d]*?and[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?", "range"),
]


def _parse_amount(value_str: str, suffix: Optional[str]) -> float:
    """Convert a number string with optional k/m suffix to a float."""
    value = float(value_str.replace(",", "").replace(".", "").strip() or "0")
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
    """
    filters: Dict[str, Any] = {}
    # Strip accents for matching (Greek tonos issues)
    query_normalized = _strip_accents(query.lower())
    remaining = query

    # --- Organization detection (accent-insensitive) ---
    for keyword, canonical in _ORGANIZATION_MAP.items():
        keyword_normalized = _strip_accents(keyword.lower())
        if keyword_normalized in query_normalized:
            filters["organization"] = canonical
            # Remove keyword from remaining text for cleaner semantic query
            pattern = re.compile(re.escape(keyword_normalized), re.IGNORECASE)
            remaining = pattern.sub("", _strip_accents(remaining))
            # Restore original remaining (approximately — just use the query)
            remaining = query
            break

    # --- Risk level detection (accent-insensitive) ---
    for pat in _RISK_HIGH:
        if re.search(pat, query_normalized):
            filters["risk_level"] = "High"
            break
    if "risk_level" not in filters:
        for pat in _RISK_MEDIUM:
            if re.search(pat, query_normalized):
                filters["risk_level"] = "Medium"
                break
    if "risk_level" not in filters:
        for pat in _RISK_LOW:
            if re.search(pat, query_normalized):
                filters["risk_level"] = "Low"
                break

    # --- Budget detection ---
    range_match = re.search(
        r"between[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?[^\d]*?and[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
        query_normalized
    )
    if range_match:
        filters["budget_min"] = _parse_amount(range_match.group(1), range_match.group(2))
        filters["budget_max"] = _parse_amount(range_match.group(3), range_match.group(4))
    else:
        min_match = re.search(
            r"(?:over|above|more than|greater than|exceeding|>\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
            query_normalized
        )
        if min_match:
            filters["budget_min"] = _parse_amount(min_match.group(1), min_match.group(2))

        max_match = re.search(
            r"(?:under|below|less than|up to|<\s*)[^\d]*?([\d,.]+)\s*(k|m|million|thousand)?",
            query_normalized
        )
        if max_match:
            filters["budget_max"] = _parse_amount(max_match.group(1), max_match.group(2))

    # --- Semantic query: use original query (LLM embedding handles it fine) ---
    semantic_query = query

    return {
        "filters": filters,
        "semantic_query": semantic_query,
    }
