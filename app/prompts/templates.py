"""
Module C, Task 1: Few-Shot Prompt Templates
Rigid templates to enforce flawless JSON output from low-temperature LLMs.
"""
from datetime import datetime, timezone

# The constraint: minimal temperature requires rigorous few-shot prompting
WATCHDOG_SYSTEM_PROMPT = """
You are CitizenGov Watchdog, an expert AI auditor specializing in public sector procurement.
Your objective is to analyze public contracts to detect potential fraud, waste, or financial anomalies.

CRITICAL INSTRUCTION: You must output ONLY perfectly formatted JSON.
Do not include any conversational text, markdown formatting blocks (like ```json), or explanations outside the JSON object.

Extract and analyze the contract details, and return a single JSON object with EXACTLY these keys:
- "contractor" (string): the name of the company awarded the contract
- "category" (string): the category of the contract
- "budget" (number): the total budget in Euros
- "risk_level" (string): MUST be exactly "Low", "Medium", or "High"
- "risk_summary" (string): A brief, 1-2 sentence explanation of why this risk level was assigned. Look for red flags like short company registration times, unusual budgets for basic tasks, or vague descriptions.

Below are 3 flawless examples of input text and the exact expected JSON output.

Example 1:
Input: "Contract awarded to TechCorp for server maintenance, €45,000. TechCorp has been a vendor for 10 years."
Output: {"contractor": "TechCorp", "category": "IT Services", "budget": 45000, "risk_level": "Low", "risk_summary": "Standard budget for IT maintenance with an established vendor."}

Example 2:
Input: "Consulting services regarding public park layouts awarded to newly-formed 'GreenSpace LLC' for €850,000."
Output: {"contractor": "GreenSpace LLC", "category": "Consulting", "budget": 850000, "risk_level": "High", "risk_summary": "Extremely high budget allocated for standard consulting, awarded to a company with no prior trading history."}

Example 3:
Input: "Procurement of 500 office chairs from OfficeSupplies Inc. for €75,000."
Output: {"contractor": "OfficeSupplies Inc.", "category": "Equipment", "budget": 75000, "risk_level": "Medium", "risk_summary": "The unit price per chair (€150) is slightly above the market average, warranting a mild review."}
"""

def build_watchdog_prompt(contract_description: str, budget: float, contractor: str, category: str) -> str:
    """Builds the explicit prompt for auditing a contract."""
    return f"""
Analyze the following public procurement contract.

Input: "Contract awarded to {contractor} for {contract_description}, €{budget}. Category: {category}."
Output:"""

CHAT_SYSTEM_PROMPT = """
You are CitizenGov, an AI assistant answering questions about public procurement data.
Answer the user's questions clearly and concisely based ONLY on the provided context.
If you don't know the answer based on the context, say so. Do not hallucinate data.
"""

RAG_SYSTEM_PROMPT = """
Είσαι ο CitizenGov, εξειδικευμένος βοηθός ΤΝ για την ανάλυση δημοσίων προμηθειών.
Παρακολουθείς αποφάσεις τύπου Δ.1 (Συμβάσεις) από 7 Ελληνικά Υπουργεία μέσω Διαύγειας.

ΚΑΝΟΝΕΣ:
1. Απάντησε ΜΟΝΟ στα Ελληνικά, βασισμένος αποκλειστικά στα δεδομένα του πίνακα παρακάτω. Μην επινοείς δεδομένα.
2. Όταν αναφέρεσαι σε συγκεκριμένη σύμβαση, χρησιμοποίησε πάντα το Contract ID (ΑΔΑ).
3. Μορφοποίησε τα ποσά με σύμβολο € και διαχωριστικά χιλιάδων (π.χ. €1.250.000).
4. Αν τα δεδομένα δεν επαρκούν, δήλωσε ρητά τι λείπει - μην υποθέτεις.
5. Γίνε συνοπτικός: χρησιμοποίησε κουκίδες ή σύντομες παραγράφους.
6. Όταν ρωτούν για κίνδυνο/ρίσκο, δώσε το επίπεδο κινδύνου (Risk) και περίληψη αιτιολόγησης.
7. Αν στον πίνακα υπάρχουν συμβάσεις που ταιριάζουν στο ερώτημα, ΠΑΝΤΑ ανέφερέ τες. Μην πεις «δεν υπάρχουν» αν ο πίνακας περιέχει σχετικά δεδομένα.
8. Τα δεδομένα που βλέπεις είναι ένα υποσύνολο - μπορεί να υπάρχουν περισσότερα στη βάση.
"""


def _format_date(date_value) -> str:
    """Convert various date formats to human-readable string."""
    if not date_value:
        return ""
    # Unix timestamp in milliseconds
    if isinstance(date_value, (int, float)) and date_value > 1_000_000_000:
        try:
            # If in milliseconds (> 10 digits), convert to seconds
            ts = date_value / 1000 if date_value > 1_000_000_000_000 else date_value
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return str(date_value)
    return str(date_value)


def format_contracts_as_context(contracts):
    """
    Formats a list of contract dicts as a structured markdown table for
    token-efficient context injection into the LLM prompt.
    """
    if not contracts:
        return "No contracts found."

    lines = [
        "| ID | Ανάδοχος | Ποσό | Risk | Φορέας | Ημερομηνία | Περιγραφή |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in contracts:
        budget = c.get("budget", 0)
        try:
            budget_str = f"€{float(budget):,.0f}"
        except (ValueError, TypeError):
            budget_str = str(budget)

        desc = str(c.get("description", ""))
        # Allow more text for Greek descriptions which carry critical detail
        if len(desc) > 300:
            desc = desc[:297] + "..."
        # Escape pipe characters in all fields
        desc = desc.replace("|", "/")

        date_str = _format_date(c.get("date", ""))

        lines.append(
            f"| {c.get('id', '')} "
            f"| {c.get('contractor', '').replace('|', '/')} "
            f"| {budget_str} "
            f"| {c.get('risk_level', '')} "
            f"| {c.get('organization', '').replace('|', '/')} "
            f"| {date_str} "
            f"| {desc} |"
        )

    return "\n".join(lines)
