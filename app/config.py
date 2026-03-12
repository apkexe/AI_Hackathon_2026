"""
CitizenGov – Centralized Configuration
Reads from environment variables with sensible defaults for demo mode.
"""

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_CONTRACTS_PATH = DATA_DIR / "sample_contracts.json"

# ── LLM / OpenRouter ────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "mistralai/mistral-7b-instruct")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# ── Embeddings ───────────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── ChromaDB ─────────────────────────────────────────────────────────────
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "procurement_contracts")

# ── Watchdog rules ───────────────────────────────────────────────────────
ANOMALY_MULTIPLIER = float(os.getenv("ANOMALY_MULTIPLIER", "3.0"))  # 300%

# ── Demo mode flag ───────────────────────────────────────────────────────
DEMO_MODE = not bool(OPENROUTER_API_KEY)
