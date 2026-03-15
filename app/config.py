"""
CitizenGov – Centralized Configuration
Reads from environment variables with sensible defaults for demo mode.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env file from project root
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_CONTRACTS_PATH = DATA_DIR / "sample_contracts.json"

# ── LLM / OpenRouter (fallback) ─────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "mistralai/mistral-7b-instruct")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# ── OpenAI (primary – for GPT-5.1) ─────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")

# ── Azure OpenAI ───────────────────────────────────────────────────────
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "") 
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# ── Provider selection ──────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "azure")  # "azure", "openai", or "openrouter"

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
DEMO_MODE = not bool(OPENROUTER_API_KEY) and not bool(OPENAI_API_KEY) and not bool(AZURE_OPENAI_API_KEY)