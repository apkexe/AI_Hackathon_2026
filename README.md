# CitizenGov - AI-Powered Public Procurement Watchdog

CitizenGov is an AI-powered transparency platform that monitors Greek public sector contracts for signs of fraud, waste, and financial irregularities. It ingests procurement data from [Diavgeia](https://diavgeia.gov.gr/), runs automated anomaly detection, performs AI-driven auditing, and presents the results through an interactive Streamlit dashboard with natural language querying.

Built for **Netcompany Hackathon Thessaloniki 2026** — Challenge 2: AI-Powered Knowledge Base System.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [How the Pipeline Works](#how-the-pipeline-works)
4. [Prerequisites](#prerequisites)
5. [Setup Guide](#setup-guide)
6. [Running the Application](#running-the-application)
7. [Data Ingestion](#data-ingestion)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Design Decisions](#design-decisions)

---

## Architecture Overview

CitizenGov follows a four-stage pipeline architecture:

```
  Diavgeia API                    Rule Engine              AI Watchdog Agent
  (or n8n workflow)               (anomaly flagging)       (LLM via OpenRouter)
       |                               |                         |
       v                               v                         v
 +-----------+    +----------+    +-----------+    +----------+    +-------------+
 | Data      | -> | Category | -> | Budget    | -> | LLM      | -> | ChromaDB    |
 | Fetching  |    | Classify |    | Threshold |    | Auditing |    | Vector Store|
 +-----------+    +----------+    +-----------+    +----------+    +-------------+
                                                                         |
                                                                         v
                                                              +--------------------+
                                                              | Streamlit Dashboard |
                                                              | - RAG Chat         |
                                                              | - Watchdog Map     |
                                                              +--------------------+
```

**Data layer:** ChromaDB vector database stores contract embeddings alongside structured metadata (budget, risk level, municipality, etc.). This enables both semantic search (for the chat interface) and structured filtering (for the watchdog map).

**Compute layer:** A FastAPI backend exposes REST endpoints for contract ingestion. An n8n workflow (or standalone scripts) feeds data into the pipeline. The pipeline evaluates rule-based anomaly flags, then escalates suspicious contracts to an LLM for deeper analysis.

**Presentation layer:** A multi-page Streamlit dashboard provides a RAG-powered chat interface ("Chat-to-Chart") and a risk monitoring view ("Watchdog Map") with color-coded anomaly tables and Plotly visualizations.

---

## Project Structure

```
CitizenGov/
|
|-- app/                              # Main application package
|   |-- config.py                     # Centralized configuration (env vars, defaults)
|   |-- api.py                        # FastAPI backend (webhook receiver for n8n)
|   |
|   |-- data_ingestion/              # Module A: Data Collection & Storage
|   |   |-- scraper.py               #   Task 1: Diavgeia API client + mock data loader
|   |   |-- embeddings.py            #   Task 2: Sentence-transformer embeddings + ChromaDB
|   |
|   |-- watchdog/                    # Module B: Anomaly Detection
|   |   |-- rules.py                 #   Task 1: Rule-based budget threshold engine
|   |   |-- agent.py                 #   Tasks 2-3: LLM auditing + output mapping
|   |
|   |-- prompts/                     # Module C: Prompt Engineering
|   |   |-- templates.py             #   Task 1: Few-shot prompt templates (watchdog + chat)
|   |   |-- parser.py                #   Task 2: Pydantic JSON parser with retry logic
|   |
|   |-- dashboard/                   # Streamlit Frontend
|       |-- Home.py                  #   Main page: RAG chat interface with dynamic charts
|       |-- pages/
|           |-- Watchdog_Map.py      #   Risk monitoring dashboard with conditional formatting
|
|-- data/
|   |-- sample_contracts.json        # 10 mock contracts (English, includes fraud test case)
|
|-- scripts/
|   |-- ingest.py                    # CLI: run full pipeline with mock or real data
|   |-- fetch_diavgeia.py            # CLI: standalone Diavgeia fetcher (replaces n8n)
|
|-- n8n_flow_CitizenGov.json         # n8n workflow definition (Diavgeia -> FastAPI)
|-- docker-compose.yml               # Docker services (ChromaDB, app, API)
|-- Dockerfile                       # Python 3.10 image for containerized deployment
|-- requirements.txt                 # Pinned Python dependencies
|-- .env                             # Environment variables (API keys, config)
```

---

## How the Pipeline Works

### Stage 1: Data Fetching (`app/data_ingestion/scraper.py`)

Contracts enter the system in one of three ways:
- **n8n workflow** — An automated flow queries Diavgeia's advanced search API for specific organization UIDs and decision types, then POSTs each contract to the FastAPI `/api/ingest` endpoint.
- **Standalone script** — `scripts/fetch_diavgeia.py` replicates the n8n logic in pure Python, useful for development without n8n running.
- **Mock data** — `scripts/ingest.py` loads 10 pre-built contracts from `data/sample_contracts.json` for offline testing.

Each contract is normalized into a standard dict with: `id`, `contractor`, `budget`, `date`, `description`, `municipality`, and `category`.

**Category inference** (`_infer_category`): Since real Diavgeia data is in Greek, the classifier uses bilingual keyword matching (both English and Greek stems) to assign one of 7 categories: IT Services, Construction, Consulting, Supplies, Maintenance, Events, or Miscellaneous.

### Stage 2: Rule-Based Anomaly Detection (`app/watchdog/rules.py`)

The rule engine computes average budgets per procurement category, then flags any contract whose budget exceeds **3x the category average** AND is above **EUR 10,000** (to filter out noise from small purchases).

Flagged contracts receive `risk_level: "Medium"` and a descriptive `risk_summary` explaining why they were flagged.

**Small batch handling:** When contracts arrive one at a time (via n8n webhooks), computing a meaningful average from a single data point is impossible. The system falls back to hardcoded `BASELINE_AVERAGES` derived from historical procurement data when the batch size is less than 5.

### Stage 3: AI Auditing (`app/watchdog/agent.py`)

Contracts flagged as "Medium" risk are escalated to an LLM (via OpenRouter) for deeper analysis. The agent:

1. Receives a few-shot prompt (`app/prompts/templates.py`) designed to enforce strict JSON output at low temperature (0.1).
2. Returns a structured risk assessment with `risk_level` (Low/Medium/High) and `risk_summary`.
3. The response is validated through a Pydantic parser (`app/prompts/parser.py`) that strips markdown artifacts, extracts JSON, and validates the schema. On validation failure, it automatically retries up to 3 times, feeding the error details back to the LLM.

**Demo mode:** If no `OPENROUTER_API_KEY` is set, the agent returns simulated "High risk" responses so the dashboard can be demonstrated without API costs.

### Stage 4: Vector Storage (`app/data_ingestion/embeddings.py`)

Each contract's text is embedded using the `all-MiniLM-L6-v2` sentence-transformer model and stored (via upsert) in a ChromaDB collection alongside all metadata fields including `risk_level` and `risk_summary`. This enables:
- **Semantic search** — The chat interface finds relevant contracts by meaning, not just keywords.
- **Metadata filtering** — The Watchdog Map retrieves all contracts and renders risk-level-based visualizations.

### Dashboard (`app/dashboard/`)

**Home.py — Chat-to-Chart (RAG Interface):**
1. User types a natural language question (e.g., "Which municipalities spend the most on IT?").
2. The system performs semantic search against ChromaDB to retrieve the top 10 relevant contracts.
3. Retrieved contracts are injected as context into an LLM prompt.
4. The LLM generates a natural language answer grounded in the retrieved data.
5. A Plotly pie chart is dynamically rendered from the retrieved contracts.

**Watchdog_Map.py — Risk Monitoring Dashboard:**
- Displays KPI cards: total contracts monitored, High risk flags, Medium risk flags.
- Shows a full audit log table with conditional row highlighting (red for High, orange for Medium, green for Low).
- Renders a Plotly bar chart of flagged budgets grouped by category.

---

## Prerequisites

1. **Docker Desktop** — Required only for running ChromaDB.
2. **Python 3.10+** (64-bit) — Tested with Python 3.12.
3. **An OpenRouter API key** — Free tier works; set in `.env`. Without it, the system runs in demo mode with simulated AI responses.

---

## Setup Guide

### 1. Clone and enter the project

```powershell
cd "NetCompany Hackathon 2026"
```

### 2. Create and activate a virtual environment

```powershell
# Create (first time only)
py -3.12-64 -m venv myvenv

# Activate (every time)
.\myvenv\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Edit the `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
LLM_MODEL=openai/gpt-oss-120b:free
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

| Variable | Description | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Your OpenRouter API key. Leave empty for demo mode. | `""` |
| `LLM_MODEL` | The model ID to use via OpenRouter. | `mistralai/mistral-7b-instruct` |
| `CHROMA_HOST` | ChromaDB hostname. Use `localhost` for local dev. | `localhost` |
| `CHROMA_PORT` | ChromaDB port. | `8000` |
| `EMBEDDING_MODEL` | Sentence-transformer model for embeddings. | `all-MiniLM-L6-v2` |
| `ANOMALY_MULTIPLIER` | Budget anomaly threshold multiplier (e.g., 3.0 = 300%). | `3.0` |

---

## Running the Application

You need three things running simultaneously: ChromaDB, the FastAPI backend, and the Streamlit dashboard. Each runs in its own terminal.

### Terminal 1: Start ChromaDB (Docker)

```powershell
docker-compose up -d chromadb
```

Wait a few seconds for it to become healthy. Verify with:

```powershell
curl http://localhost:8000/api/v1/heartbeat
```

### Terminal 2: Start the FastAPI Backend

```powershell
.\myvenv\Scripts\activate
uvicorn app.api:app --reload --port 8001
```

The `--reload` flag enables hot-reloading: any change to a `.py` file restarts the server automatically. The API will be available at `http://localhost:8001`.

### Terminal 3: Start the Streamlit Dashboard

```powershell
.\myvenv\Scripts\activate
python -m streamlit run app/dashboard/Home.py
```

The dashboard opens at `http://localhost:8501`. Use the sidebar to navigate between the Chat-to-Chart home page and the Watchdog Map.

---

## Data Ingestion

### Option A: Mock data (quick demo)

Loads 10 sample contracts from `data/sample_contracts.json`, including a deliberate fraud test case (Contract 6: a EUR 150,000 website update awarded to a 3-day-old company).

```powershell
python scripts/ingest.py
```

### Option B: Real Diavgeia data (standalone)

Fetches live contracts from the Diavgeia advanced search API and runs them through the full pipeline locally:

```powershell
python scripts/fetch_diavgeia.py --limit 20
```

Or POST them to the running FastAPI backend (same as n8n would):

```powershell
python scripts/fetch_diavgeia.py --mode api --limit 20
```

### Option C: n8n workflow (automated)

Import `n8n_flow_CitizenGov.json` into an n8n instance. The workflow queries Diavgeia's advanced search API for contracts from specific Greek municipalities and decision types, then POSTs each contract to `http://localhost:8001/api/ingest`.

### Wiping the database

If ChromaDB gets into a bad state or you want to start fresh:

```powershell
docker-compose down -v
docker-compose up -d chromadb
```

The `-v` flag removes the Docker volume, deleting all stored embeddings.

---

## API Reference

The FastAPI backend runs on port **8001** and exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check. Returns `{"status": "ok"}`. |
| `GET` | `/api/contracts` | Lists up to 100 contracts stored in ChromaDB. |
| `POST` | `/api/ingest` | Ingests a single contract (used by n8n). Processes in background. |
| `POST` | `/api/ingest/batch` | Ingests multiple contracts at once. Processes in background. |

### POST `/api/ingest` — Request body

```json
{
  "ada": "ΨΩΞΗ46ΜΤΛ6-ΝΔ3",
  "subject": "Προμήθεια εξοπλισμού πληροφορικής",
  "issue_date": "2026-03-10",
  "contractor": "TechCorp A.E.",
  "budget": 85000.0,
  "municipality": "Municipality of Thessaloniki"
}
```

`contractor`, `budget`, and `municipality` are optional (default to `"Unknown"`, `0.0`, and `"Unknown"` respectively).

---

## Configuration

All configuration is centralized in `app/config.py`, which reads from environment variables with sensible defaults. Key settings:

| Setting | Source | Default | Purpose |
|---|---|---|---|
| `DEMO_MODE` | Auto-detected | `True` if no API key | Skips LLM calls, returns simulated responses |
| `ANOMALY_MULTIPLIER` | `ANOMALY_MULTIPLIER` env var | `3.0` | How many times above average triggers a flag |
| `CHROMA_COLLECTION` | `CHROMA_COLLECTION` env var | `procurement_contracts` | ChromaDB collection name |
| `LLM_TEMPERATURE` | `LLM_TEMPERATURE` env var | `0.1` | Low temp for deterministic JSON output |
| `LLM_MAX_TOKENS` | `LLM_MAX_TOKENS` env var | `1024` | Max tokens per LLM response |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | env vars | `500` / `50` | Text chunking parameters |

---

## Design Decisions

### Why ChromaDB as a vector database?

ChromaDB provides a lightweight, self-hosted vector store that runs in a single Docker container. It supports metadata filtering alongside semantic search, which is essential for the dual use case: the chat interface needs semantic similarity, while the watchdog map needs structured queries (e.g., "all High risk contracts"). ChromaDB handles both without requiring a separate relational database.

### Why OpenRouter instead of a direct API?

OpenRouter acts as a unified gateway to multiple LLM providers. This lets us switch models (Mistral, Llama, GPT) by changing a single environment variable, without modifying any code. The free-tier models (`openai/gpt-oss-120b:free`) make it viable for hackathon demos without incurring API costs.

### Why few-shot prompting with Pydantic validation?

The LLM must return structured JSON that maps directly to risk assessments. Few-shot examples in the system prompt train the model on the exact output format, while Pydantic validation (`app/prompts/parser.py`) acts as a safety net. If the LLM produces malformed JSON, the parser feeds the validation error back to the LLM and retries (up to 3 times). This closed-loop approach ensures reliable structured output even from smaller, less instruction-following models.

### Why baseline averages for single-contract evaluation?

When n8n sends contracts one at a time, the rule engine can't compute meaningful category averages from a single data point (a contract can never exceed 3x its own budget). Hardcoded baseline averages derived from historical procurement data solve this by providing a reference point for anomaly detection regardless of batch size.

### Why bilingual keyword matching for categorization?

Real Diavgeia data is in Greek, but mock data and the dashboard UI use English categories. The `_infer_category` function uses Greek word stems (e.g., `"πληροφορικ"` for IT, `"κατασκευ"` for Construction) to correctly classify real contracts while maintaining backward compatibility with English test data.

### Why sentence-transformers (`all-MiniLM-L6-v2`)?

This model offers an excellent balance of embedding quality and speed. It runs locally (no API calls needed), generates 384-dimensional vectors, and handles both English and Greek text reasonably well. For a hackathon context, it eliminates external embedding API dependencies and associated latency.

### Why FastAPI with background tasks?

Contract processing (rule evaluation + LLM auditing + embedding + ChromaDB storage) can take several seconds per contract, especially when the LLM is involved. By using FastAPI's `BackgroundTasks`, the API returns immediately with a 200 status, allowing n8n to continue sending contracts without waiting. This prevents webhook timeouts and enables parallel processing.
