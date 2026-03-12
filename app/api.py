import logging
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.data_ingestion.embeddings import VectorStore
from app.watchdog.rules import evaluate_rules
from app.watchdog.agent import audit_contracts
from app.data_ingestion.scraper import _infer_category

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CitizenGov Pipeline API")

class DiavgeiaPayload(BaseModel):
    ada: str
    subject: str
    issue_date: str
    contractor: Optional[str] = "Unknown"
    budget: Optional[float] = 0.0
    municipality: Optional[str] = "Unknown"

def process_and_ingest(data: dict):
    logger.info(f"Processing webhook for contract: {data.get('ada')}")
    # Convert payload to our internal project schema
    contract = {
        "id": data.get("ada"),
        "contractor": data.get("contractor"),
        "budget": float(data.get("budget", 0.0) or 0.0),
        "date": data.get("issue_date"),
        "description": data.get("subject", ""),
        "municipality": data.get("municipality"),
        "category": _infer_category(data.get("subject", ""))
    }
    
    contracts = [contract]
    
    try:
        # 1. Run Rule Evaluation
        contracts = evaluate_rules(contracts)
        
        # 2. Run LLM Audit
        contracts = audit_contracts(contracts)
        
        # 3. Embed and Save to ChromaDB
        vs = VectorStore()
        vs.ingest_contracts(contracts)
        logger.info(f"✅ Successfully ingested {contract['id']} into ChromaDB.")
    except Exception as e:
        logger.error(f"❌ Failed to ingest contract {contract['id']}: {e}")

@app.post("/api/ingest")
async def ingest_webhook(payload: DiavgeiaPayload, background_tasks: BackgroundTasks):
    """
    Receives contract data from n8n webhook and processes it in the background.
    """
    background_tasks.add_task(process_and_ingest, payload.model_dump())
    return {"status": "success", "message": f"Contract {payload.ada} queued for processing"}
