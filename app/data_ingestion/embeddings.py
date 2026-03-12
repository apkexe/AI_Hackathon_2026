"""
Module A, Task 2: Chunking & Embedding
Uses sentence-transformers to embed contract descriptions and stores metadata in ChromaDB.
"""
import logging
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from app.config import CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        logger.info(f"Connecting to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
        try:
            self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        except Exception as e:
            logger.warning(f"Failed to connect to ChromaDB HTTP Client: {e}. Falling back to Ephemeral client for local testing.")
            self.client = chromadb.EphemeralClient()

        self.collection = self.client.get_or_create_collection(name=CHROMA_COLLECTION)
        
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        self.encoder = SentenceTransformer(EMBEDDING_MODEL)

    def ingest_contracts(self, contracts: List[Dict[str, Any]]):
        """
        Embeds the contract descriptions and stores them with metadata in ChromaDB.
        """
        if not contracts:
            logger.warning("No contracts to ingest.")
            return

        logger.info(f"Ingesting {len(contracts)} contracts into ChromaDB...")
        
        documents = []
        metadatas = []
        ids = []

        for c in contracts:
            # We construct a rich text representation to embed
            text_to_embed = f"Contractor: {c['contractor']}. Description: {c['description']} Municipality: {c['municipality']}."
            documents.append(text_to_embed)
            
            # The metadata must be simple types (str, int, float, bool)
            metadatas.append({
                "contractor": c.get("contractor", ""),
                "budget": float(c.get("budget", 0)),
                "date": c.get("date", ""),
                "municipality": c.get("municipality", ""),
                "category": c.get("category", "")
            })
            
            ids.append(str(c["id"]))

        # Generate embeddings in batches
        logger.info("Generating embeddings...")
        embeddings = self.encoder.encode(documents, show_progress_bar=False)
        
        # Upsert to ChromaDB
        self.collection.upsert(
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info("Ingestion complete.")

    def search_contracts(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Performs semantic search to find relevant contracts.
        """
        query_embedding = self.encoder.encode([query]).tolist()
        
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results
        )
        
        # Reconstruct exactly as original dicts for easy use
        contracts = []
        for i in range(len(results['ids'][0])):
            c = results['metadatas'][0][i].copy()
            c['id'] = results['ids'][0][i]
            c['description'] = results['documents'][0][i].split("Description: ")[-1].split(" Municipality:")[0]
            contracts.append(c)
            
        return contracts

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.data_ingestion.scraper import fetch_contracts
    
    contracts = fetch_contracts(use_mock_data=True)
    vs = VectorStore()
    vs.ingest_contracts(contracts)
    
    print("\n--- Testing Search ---")
    res = vs.search_contracts("computer repairs", n_results=2)
    for r in res:
        print(f"[{r['id']}] {r['contractor']} - €{r['budget']} - {r['description'][:50]}...")
