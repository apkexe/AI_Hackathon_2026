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

    def ingest_contracts(self, contracts: List[Dict[str, Any]], batch_size: int = 500):
        """
        Embeds the contract descriptions and stores them with metadata in ChromaDB.
        Deduplicates by ID and upserts in batches to avoid ChromaDB limits.
        """
        if not contracts:
            logger.warning("No contracts to ingest.")
            return

        # Deduplicate by ID (keep the last occurrence)
        seen = {}
        for c in contracts:
            seen[str(c["id"])] = c
        contracts = list(seen.values())

        logger.info(f"Ingesting {len(contracts)} contracts into ChromaDB (batch_size={batch_size})...")

        documents = []
        metadatas = []
        ids = []

        for c in contracts:
            text_to_embed = f"Contractor: {c['contractor']}. Description: {c['description']} Municipality: {c['municipality']}."
            documents.append(text_to_embed)

            metadatas.append({
                "contractor": c.get("contractor", ""),
                "budget": float(c.get("budget", 0)),
                "date": c.get("date", ""),
                "municipality": c.get("municipality", ""),
                "category": c.get("category", ""),
                "risk_level": c.get("risk_level", "Low"),
                "risk_summary": c.get("risk_summary", "")
            })

            ids.append(str(c["id"]))

        # Generate embeddings
        logger.info("Generating embeddings...")
        embeddings = self.encoder.encode(documents, show_progress_bar=True)
        embeddings_list = embeddings.tolist()

        # Upsert in batches
        total = len(ids)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            self.collection.upsert(
                embeddings=embeddings_list[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
                ids=ids[start:end]
            )
            logger.info(f"Upserted batch {start}-{end} of {total}")

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

    def hybrid_search(self, query: str, where_filters: dict = None, n_results: int = 20) -> List[Dict[str, Any]]:
        """
        Performs semantic search with optional ChromaDB metadata filters.
        Falls back to pure semantic search if filters cause an error.
        """
        query_embedding = self.encoder.encode([query]).tolist()

        # Build ChromaDB where clause from filters
        where = None
        if where_filters:
            clauses = []
            for key, value in where_filters.items():
                if key == "municipality":
                    clauses.append({"municipality": {"$contains": value}})
                elif key == "category":
                    clauses.append({"category": value})
                elif key == "risk_level":
                    clauses.append({"risk_level": value})
                elif key == "budget_min":
                    clauses.append({"budget": {"$gte": float(value)}})
                elif key == "budget_max":
                    clauses.append({"budget": {"$lte": float(value)}})

            if len(clauses) == 1:
                where = clauses[0]
            elif len(clauses) > 1:
                where = {"$and": clauses}

        try:
            kwargs = {
                "query_embeddings": query_embedding,
                "n_results": n_results,
            }
            if where:
                kwargs["where"] = where

            results = self.collection.query(**kwargs)
        except Exception as e:
            logger.warning(f"Filtered search failed ({e}), falling back to pure semantic search.")
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=n_results,
            )

        # Handle empty results
        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        contracts = []
        for i in range(len(results["ids"][0])):
            c = results["metadatas"][0][i].copy()
            c["id"] = results["ids"][0][i]
            c["description"] = results["documents"][0][i].split("Description: ")[-1].split(" Municipality:")[0]
            # Store distance for re-ranking
            if results.get("distances") and results["distances"][0]:
                c["_distance"] = results["distances"][0][i]
            contracts.append(c)

        return contracts

    def rerank_results(self, results: List[Dict], query: str, top_k: int = 10) -> List[Dict]:
        """
        Re-ranks search results by combining semantic similarity, budget relevance,
        and risk relevance.
        """
        if not results:
            return []

        query_lower = query.lower()
        mentions_money = any(kw in query_lower for kw in [
            "budget", "cost", "expensive", "spend", "money", "euro", "\u20ac",
            "million", "thousand", "\u03c0\u03c1\u03bf\u03cb\u03c0\u03bf\u03bb\u03bf\u03b3\u03b9\u03c3\u03bc",
        ])
        mentions_risk = any(kw in query_lower for kw in [
            "risk", "fraud", "suspicious", "flagged", "anomal", "danger",
            "\u03ba\u03af\u03bd\u03b4\u03c5\u03bd", "\u03cd\u03c0\u03bf\u03c0\u03c4",
        ])

        scored = []
        for c in results:
            # Base score: inverse of distance (lower distance = higher similarity)
            distance = c.get("_distance", 1.0)
            # ChromaDB L2 distances are >= 0; normalize to a 0-1 similarity
            similarity_score = 1.0 / (1.0 + distance)

            budget_boost = 0.0
            if mentions_money:
                budget = float(c.get("budget", 0))
                # Boost high-budget contracts when query is about money
                if budget >= 500_000:
                    budget_boost = 0.2
                elif budget >= 100_000:
                    budget_boost = 0.1

            risk_boost = 0.0
            if mentions_risk:
                risk = c.get("risk_level", "Low")
                if risk == "High":
                    risk_boost = 0.25
                elif risk == "Medium":
                    risk_boost = 0.1

            total_score = similarity_score + budget_boost + risk_boost
            scored.append((total_score, c))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Remove internal _distance key and return top_k
        top_results = []
        for _, c in scored[:top_k]:
            clean = {k: v for k, v in c.items() if not k.startswith("_")}
            top_results.append(clean)

        return top_results

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
