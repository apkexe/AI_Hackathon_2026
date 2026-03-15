import logging
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List

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
    contract = {
        "id": data.get("ada"),
        "contractor": data.get("contractor") or "Unknown",
        "budget": float(data.get("budget") or 0.0),
        "date": data.get("issue_date"),
        "description": data.get("subject", ""),
        "municipality": data.get("municipality") or "Unknown",
        "category": _infer_category(data.get("subject", ""))
    }

    contracts = [contract]

    try:
        contracts = evaluate_rules(contracts)
        contracts = audit_contracts(contracts)
        vs = VectorStore()
        vs.ingest_contracts(contracts)
        logger.info(f"Successfully ingested {contract['id']} into ChromaDB.")
    except Exception as e:
        logger.error(f"Failed to ingest contract {contract['id']}: {e}")

@app.get("/api/health")
async def health():
    """Healthcheck endpoint for n8n and monitoring."""
    return {"status": "ok"}

@app.get("/api/contracts")
async def list_contracts():
    """List all contracts currently stored in ChromaDB."""
    try:
        vs = VectorStore()
        contracts = vs.search_contracts("", n_results=100)
        return {"contracts": contracts, "count": len(contracts)}
    except Exception as e:
        logger.error(f"Failed to list contracts: {e}")
        return {"contracts": [], "count": 0, "error": str(e)}

@app.post("/api/ingest")
async def ingest_webhook(payload: DiavgeiaPayload, background_tasks: BackgroundTasks):
    """
    Receives contract data from n8n webhook and processes it in the background.
    """
    background_tasks.add_task(process_and_ingest, payload.model_dump())
    return {"status": "success", "message": f"Contract {payload.ada} queued for processing"}

@app.post("/api/ingest/batch")
async def ingest_batch(payloads: List[DiavgeiaPayload], background_tasks: BackgroundTasks):
    """
    Receives multiple contracts at once and processes them in the background.
    """
    for p in payloads:
        background_tasks.add_task(process_and_ingest, p.model_dump())
    return {"status": "success", "message": f"{len(payloads)} contracts queued for processing"}
