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
            text_to_embed = f"Contractor: {c.get('contractor', '')}. Description: {c.get('description', '')} Organization: {c.get('organization', '')}."
            documents.append(text_to_embed)

            metadatas.append({
                "contractor": c.get("contractor", ""),
                "budget": float(c.get("budget", 0)),
                "date": c.get("date", ""),
                "organization": c.get("organization", ""),
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

    def _build_where(self, filters: dict) -> dict:
        """Build a ChromaDB where clause from filter dict.
        ChromaDB supports: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin for metadata.
        No $contains — use $eq for exact string match.
        """
        clauses = []
        for key, value in filters.items():
            if key == "organization":
                # Full canonical name (e.g. "Υπουργείο Ψηφιακής Διακυβέρνησης")
                clauses.append({"organization": {"$eq": value}})
            elif key == "category":
                clauses.append({"category": {"$eq": value}})
            elif key == "risk_level":
                clauses.append({"risk_level": {"$eq": value}})
            elif key == "budget_min":
                clauses.append({"budget": {"$gte": float(value)}})
            elif key == "budget_max":
                clauses.append({"budget": {"$lte": float(value)}})

        if len(clauses) == 0:
            return None
        elif len(clauses) == 1:
            return clauses[0]
        else:
            return {"$and": clauses}

    def _query_chromadb(self, query_embedding, where, n_results):
        """Run a ChromaDB query, return results or None on failure."""
        kwargs = {"query_embeddings": query_embedding, "n_results": n_results}
        if where:
            kwargs["where"] = where
        try:
            results = self.collection.query(**kwargs)
            if results and results.get("ids") and results["ids"][0]:
                return results
        except Exception as e:
            logger.warning(f"ChromaDB query failed with where={where}: {e}")
        return None

    def _parse_results(self, results) -> List[Dict[str, Any]]:
        """Parse ChromaDB results into contract dicts."""
        contracts = []
        for i in range(len(results["ids"][0])):
            c = results["metadatas"][0][i].copy()
            c["id"] = results["ids"][0][i]
            doc = results["documents"][0][i] if results.get("documents") and results["documents"][0] else ""
            c["description"] = doc.split("Description: ")[-1].split(" Organization:")[0] if doc else ""
            if results.get("distances") and results["distances"][0]:
                c["_distance"] = results["distances"][0][i]
            contracts.append(c)
        return contracts

    def search_contracts(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Performs semantic search to find relevant contracts."""
        query_embedding = self.encoder.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_embedding, n_results=n_results)
        if not results or not results.get("ids") or not results["ids"][0]:
            return []
        return self._parse_results(results)

    def hybrid_search(self, query: str, where_filters: dict = None, n_results: int = 50) -> List[Dict[str, Any]]:
        """
        Performs semantic search with optional ChromaDB metadata filters.
        Uses progressive fallback: tries all filters first, then loosens progressively.
        """
        query_embedding = self.encoder.encode([query]).tolist()

        if not where_filters:
            # No filters — pure semantic search
            results = self._query_chromadb(query_embedding, None, n_results)
            if results:
                logger.info(f"Pure semantic search returned {len(results['ids'][0])} results.")
                return self._parse_results(results)
            return []

        # Strategy 1: Try all filters combined
        where = self._build_where(where_filters)
        logger.info(f"Hybrid search with filters: {where_filters} → where={where}")
        results = self._query_chromadb(query_embedding, where, n_results)
        if results:
            count = len(results["ids"][0])
            logger.info(f"All filters matched: {count} results.")
            return self._parse_results(results)

        # Strategy 2: Try each filter individually and merge results
        logger.info("All filters returned 0 results. Trying individual filters...")
        all_contracts = {}
        for key in where_filters:
            single_where = self._build_where({key: where_filters[key]})
            results = self._query_chromadb(query_embedding, single_where, n_results)
            if results:
                for c in self._parse_results(results):
                    all_contracts[c["id"]] = c
                logger.info(f"  Filter '{key}={where_filters[key]}' returned {len(results['ids'][0])} results.")
            else:
                logger.info(f"  Filter '{key}={where_filters[key]}' returned 0 results.")

        if all_contracts:
            logger.info(f"Individual filters produced {len(all_contracts)} unique results.")
            return list(all_contracts.values())

        # Strategy 3: Pure semantic fallback
        logger.warning("All filters failed. Falling back to pure semantic search.")
        results = self._query_chromadb(query_embedding, None, n_results)
        if results:
            return self._parse_results(results)
        return []

    def rerank_results(self, results: List[Dict], query: str, top_k: int = 15) -> List[Dict]:
        """
        Re-ranks search results by combining semantic similarity, budget relevance,
        and risk relevance.
        """
        if not results:
            return []

        import unicodedata
        def _strip(t):
            return ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
        query_lower = _strip(query.lower())
        mentions_money = any(kw in query_lower for kw in [
            "budget", "cost", "expensive", "spend", "money", "euro", "€",
            "million", "thousand", "προϋπολογισμ", "δαπάν", "κόστ", "ακριβ",
            "ποσό", "ποσα", "εκατομμύρ", "χιλιάδ",
        ])
        mentions_risk = any(kw in query_lower for kw in [
            "risk", "fraud", "suspicious", "flagged", "anomal", "danger",
            "κίνδυν", "ρίσκ", "ύποπτ", "υποπτ", "επικίνδυν", "απάτ", "παράνομ",
            "παρατυπ", "επισημαν", "προβλημ", "ανωμαλ", "υψηλ",
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
                if budget >= 500_000:
                    budget_boost = 0.2
                elif budget >= 100_000:
                    budget_boost = 0.1

            risk_boost = 0.0
            if mentions_risk:
                risk = c.get("risk_level", "Low")
                if risk == "High":
                    risk_boost = 0.3
                elif risk == "Medium":
                    risk_boost = 0.15

            total_score = similarity_score + budget_boost + risk_boost
            scored.append((total_score, c))

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
