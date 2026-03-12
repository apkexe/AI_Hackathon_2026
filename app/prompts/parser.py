"""
Module C, Task 2: Fallback Parser
Uses Pydantic to ensure LLM JSON outputs are perfectly structured. Triggers automatic retries on failure.
"""
import json
import logging
from typing import Optional, Literal
from pydantic import BaseModel, Field, ValidationError


logger = logging.getLogger(__name__)

class RiskAssessment(BaseModel):
    contractor: str = Field(..., description="The name of the company awarded the contract")
    category: str = Field(..., description="The category of the contract")
    budget: float = Field(..., description="The total budget in Euros")
    risk_level: Literal["Low", "Medium", "High"] = Field(..., description="The assessed risk level")
    risk_summary: str = Field(..., description="A brief, 1-2 sentence explanation of the risk level")

def parse_llm_response(response_text: str, max_retries: int = 3, original_prompt: str = "") -> Optional[RiskAssessment]:
    """
    Attempts to parse exactly one JSON object from the LLM response.
    If it fails Pydantic validation, it asks the LLM to fix it.
    """
    current_attempt = 1
    current_text = response_text

    while current_attempt <= max_retries:
        try:
            # Try to strip out any markdown block formatting that low-temp models sometimes add anyway
            clean_text = current_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()
            
            # Find the first { and last }
            start = clean_text.find('{')
            end = clean_text.rfind('}')
            if start != -1 and end != -1:
                clean_text = clean_text[start:end+1]

            # Parse to dict
            data = json.loads(clean_text)
            
            # Validate with Pydantic
            validated_data = RiskAssessment(**data)
            return validated_data
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Attempt {current_attempt} failed to parse LLM output. Error: {e}")
            
            if current_attempt == max_retries:
                logger.error(f"Failed to parse LLM response after {max_retries} attempts.")
                return None
            
            # Module C Constraint: Fallback logic explicitly telling the LLM what went wrong
            retry_prompt = f"""
{original_prompt}

Your previous response failed validation. 
Error details: {str(e)}

You MUST output ONLY a valid JSON object. Fix the errors and try again.
"""
            # We must import inside the function to avoid circular imports.
            # But we passed the `call_llm` function into this module. Wait, let's just make sure we handle that loop properly.
            logger.info("Retrying LLM call with error feedback...")
            current_text = _fallback_call(retry_prompt)
            current_attempt += 1

    return None

def _fallback_call(prompt: str) -> str:
    """Helper to do the LLM call for a retry"""
    from app.watchdog.agent import call_llm
    from app.prompts.templates import WATCHDOG_SYSTEM_PROMPT
    return call_llm(system_prompt=WATCHDOG_SYSTEM_PROMPT, user_prompt=prompt)
