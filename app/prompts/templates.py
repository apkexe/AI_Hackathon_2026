"""
Module C, Task 1: Few-Shot Prompt Templates
Rigid templates to enforce flawless JSON output from low-temperature LLMs.
"""

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
You are CitizenGov, an expert AI assistant for analyzing Greek public procurement contracts.

RULES:
1. Answer ONLY based on the contract data provided in the context below. Never invent data.
2. When making a claim about a specific contract, always reference its Contract ID.
3. Format all budget figures with the Euro sign and thousand separators (e.g., €1,250,000).
4. If the provided data does not contain enough information to fully answer the question, explicitly state what is missing.
5. Be concise but thorough: use bullet points or short paragraphs, not lengthy essays.
6. When comparing contracts, use tables if helpful.
7. If asked about risk or fraud, highlight the risk level and summarize the risk reasons.
"""


def format_contracts_as_context(contracts):
    """
    Formats a list of contract dicts as a structured markdown table for
    token-efficient context injection into the LLM prompt.
    """
    if not contracts:
        return "No contracts found."

    lines = [
        "| ID | Contractor | Budget | Risk | Ministry | Description |",
        "|---|---|---|---|---|---|",
    ]
    for c in contracts:
        budget = c.get("budget", 0)
        try:
            budget_str = f"\u20ac{float(budget):,.0f}"
        except (ValueError, TypeError):
            budget_str = str(budget)

        desc = str(c.get("description", ""))
        # Truncate long descriptions for token efficiency
        if len(desc) > 120:
            desc = desc[:117] + "..."
        # Escape pipe characters in all fields
        desc = desc.replace("|", "/")

        lines.append(
            f"| {c.get('id', '')} "
            f"| {c.get('contractor', '').replace('|', '/')} "
            f"| {budget_str} "
            f"| {c.get('risk_level', '')} "
            f"| {c.get('municipality', '').replace('|', '/')} "
            f"| {desc} |"
        )

    return "\n".join(lines)
