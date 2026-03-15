# CitizenGov - AI-Powered Public Procurement Watchdog

CitizenGov is an AI-powered transparency platform that monitors Greek public sector contracts for signs of fraud, waste, and financial irregularities. It ingests procurement data from [Diavgeia](https://diavgeia.gov.gr/), runs automated anomaly detection, performs AI-driven auditing via GPT-5.1, and presents the results through an interactive Streamlit dashboard with a Hybrid RAG chat interface.

Built for **Netcompany Hackathon Thessaloniki 2026** — Challenge 2: AI-Powered Knowledge Base System.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Diavgeia API Integration](#diavgeia-api-integration)
4. [How the Pipeline Works](#how-the-pipeline-works)
5. [RAG Architecture](#rag-architecture)
6. [Prerequisites](#prerequisites)
7. [Setup Guide](#setup-guide)
8. [Running the Application](#running-the-application)
9. [Data Ingestion](#data-ingestion)
10. [API Reference](#api-reference)
11. [Configuration](#configuration)
12. [Design Decisions](#design-decisions)

---

## Architecture Overview

CitizenGov follows a four-stage pipeline architecture:

```
  Diavgeia API                    Rule Engine              AI Watchdog Agent
  (or n8n workflow)               (anomaly flagging)       (GPT-5.1 via OpenAI)
       |                               |                         |
       v                               v                         v
 +-----------+    +-----------+    +-----------+    +----------+    +-------------+
 | Data      | -> | Org ID    | -> | Budget    | -> | LLM      | -> | ChromaDB    |
 | Fetching  |    | Mapping   |    | Threshold |    | Auditing |    | Vector Store|
 +-----------+    +-----------+    +-----------+    +----------+    +-------------+
                                                                         |
                                                                         v
                                                              +--------------------+
                                                              | Streamlit Dashboard |
                                                              | - Hybrid RAG Chat  |
                                                              | - Watchdog Map     |
                                                              +--------------------+
```

**Data layer:** ChromaDB vector database stores contract embeddings alongside structured metadata (budget, risk level, municipality, contractor, date). This enables both semantic search and metadata-filtered retrieval through a single store.

**Compute layer:** A FastAPI backend exposes REST endpoints for contract ingestion. An n8n workflow (or standalone scripts) feeds data into the pipeline. The pipeline evaluates rule-based anomaly flags, then escalates suspicious contracts to GPT-5.1 for deeper analysis.

**Presentation layer:** A multi-page Streamlit dashboard provides a Hybrid RAG chat interface ("Chat-to-Chart") and a risk monitoring view ("Watchdog Map") with color-coded anomaly tables and Plotly visualizations.

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
|   |   |-- embeddings.py            #   Task 2: Embeddings + ChromaDB + hybrid search + re-ranking
|   |
|   |-- watchdog/                    # Module B: Anomaly Detection
|   |   |-- rules.py                 #   Task 1: Rule-based budget threshold engine
|   |   |-- agent.py                 #   Tasks 2-3: LLM auditing via OpenAI/OpenRouter + output mapping
|   |
|   |-- rag/                         # RAG Pipeline Components
|   |   |-- query_analyzer.py        #   Query analysis: extracts structured filters from natural language
|   |
|   |-- prompts/                     # Module C: Prompt Engineering
|   |   |-- templates.py             #   Few-shot prompts (watchdog), RAG prompt, context formatter
|   |   |-- parser.py                #   Pydantic JSON parser with retry logic
|   |
|   |-- dashboard/                   # Streamlit Frontend
|       |-- Home.py                  #   Main page: Hybrid RAG chat with dynamic charts
|       |-- pages/
|           |-- Watchdog_Map.py      #   Risk monitoring dashboard with conditional formatting
|
|-- data/
|   |-- sample_contracts.json        # 10 mock contracts (English, includes fraud test case)
|
|-- scripts/
|   |-- ingest.py                    # CLI: run full pipeline with mock data
|   |-- fetch_diavgeia.py            # CLI: paginated Diavgeia fetcher (replaces n8n for bulk ingestion)
|
|-- n8n_flow_CitizenGov.json         # n8n workflow definition (Diavgeia -> FastAPI)
|-- docker-compose.yml               # Docker services (ChromaDB, app, API)
|-- Dockerfile                       # Python 3.10 image for containerized deployment
|-- requirements.txt                 # Pinned Python dependencies
|-- .env.example                     # Template environment variables
|-- .env                             # Your actual environment variables (git-ignored)
```

---

## Diavgeia API Integration

CitizenGov integrates with the [Diavgeia OpenData API](https://diavgeia.gov.gr/api/help) — Greece's official public transparency portal where all government decisions are legally required to be published.

### API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /search/advanced.json` | Paginated search with Lucene-style query syntax |
| `GET /organizations/{uid}.json` | Resolve organization UID to human-readable label |

### Query Design

The advanced search query targets **7 Greek Ministries** and specific **decision types**:

```
organizationUid:["6","15","100054486","100054489","100054492","100056663","100081880"]
AND decisionTypeUid:["Β.1.3","Β.2.1"]
```

| Organization UID | Label | English |
|---|---|---|
| `6` | Υπουργείο Εθνικής Άμυνας | Ministry of National Defence |
| `15` | Υπουργείο Οικονομικών | Ministry of Finance |
| `100054486` | Υπουργείο Ψηφιακής Διακυβέρνησης | Ministry of Digital Governance |
| `100054489` | Υπουργείο Προστασίας του Πολίτη | Ministry of Citizen Protection |
| `100054492` | Υπουργείο Εσωτερικών | Ministry of Interior |
| `100056663` | Υπουργείο Μετανάστευσης και Ασύλου | Ministry of Migration and Asylum |
| `100081880` | Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού | Ministry of Education |

| Decision Type | Description |
|---|---|
| `Β.1.3` | ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ — Budget commitment decisions |
| `Β.2.1` | ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ — Expenditure approval decisions |

### Field Extraction from API Response

The Diavgeia API returns decisions with structured metadata. We extract:

| Our Field | Diavgeia Source | Notes |
|---|---|---|
| `id` | `ada` | Unique decision identifier (Αριθμός Διαδικτυακής Ανάρτησης) |
| `description` | `subject` | Decision subject line |
| `date` | `issueDate` | Unix timestamp (ms from epoch) |
| `municipality` (ministry) | `organizationId` → lookup | Numeric org ID mapped to label via `ORG_ID_TO_LABEL` dict |
| `budget` | `extraFieldValues.amountWithTaxes` or `extraFieldValues.amountWithVAT.amount` | Budget with VAT; fallback to amount field |
| `contractor` | `extraFieldValues.sponsorName` | Available on some decision types |

**Organization ID resolution:** The API returns `organizationId` as a numeric string (e.g., `"6114"`), not a human-readable name. We maintain a static mapping (`ORG_ID_TO_LABEL`) from organization UIDs to Greek labels, derived from the `/organizations/{uid}` endpoint.

### Pagination & Rate Limiting

The Diavgeia API enforces a **180-day window** on `issueDate` queries and caps page sizes at 500 results (1000 for authenticated users). Our fetcher (`scripts/fetch_diavgeia.py`) paginates through results with 0.5s delays between requests to avoid rate limiting, and deduplicates by ADA before storage (the API occasionally returns the same decision across page boundaries).

---

## How the Pipeline Works

### Stage 1: Data Fetching (`app/data_ingestion/scraper.py`, `scripts/fetch_diavgeia.py`)

Contracts enter the system in one of three ways:
- **n8n workflow** — An automated flow queries Diavgeia's advanced search API, then POSTs each contract to the FastAPI `/api/ingest` endpoint.
- **Standalone script** — `scripts/fetch_diavgeia.py` replicates the n8n logic in pure Python with pagination support (up to 10,000+ contracts), useful for bulk ingestion without n8n. Supports `--from-cache` to skip re-fetching and re-auditing.
- **Mock data** — `scripts/ingest.py` loads 10 pre-built contracts from `data/sample_contracts.json` for offline testing.

Each contract is normalized into a standard dict with: `id`, `contractor`, `budget`, `date`, `description`, and `municipality`.

### Stage 2: Rule-Based Anomaly Detection (`app/watchdog/rules.py`)

The rule engine computes average budgets per procurement category, then flags any contract whose budget exceeds **3x the category average** AND is above **EUR 10,000** (to filter out noise from small purchases).

Flagged contracts receive `risk_level: "Medium"` and a descriptive `risk_summary` explaining why they were flagged. In our dataset of ~10,000 real Diavgeia decisions, the rule engine flags approximately **1.6%** of contracts for AI review — a realistic anomaly rate.

**Small batch handling:** When contracts arrive one at a time (via n8n webhooks), computing a meaningful average is impossible. The system falls back to hardcoded `BASELINE_AVERAGES` derived from historical procurement data when the batch size is less than 5.

### Stage 3: AI Auditing (`app/watchdog/agent.py`)

Contracts flagged as "Medium" risk are escalated to GPT-5.1 (via OpenAI API) for deeper analysis. The agent:

1. Receives a few-shot prompt (`app/prompts/templates.py`) designed to enforce strict JSON output at low temperature (0.1).
2. Returns a structured risk assessment with `risk_level` (Low/Medium/High) and `risk_summary`.
3. The response is validated through a Pydantic parser (`app/prompts/parser.py`) that strips markdown artifacts, extracts JSON, and validates the schema. On validation failure, it automatically retries up to 3 times, feeding the error details back to the LLM.

**LLM Provider:** The system supports Azure OpenAI (primary, for GPT-5.1), direct OpenAI, and OpenRouter (fallback, for free models). Set `LLM_PROVIDER=azure`, `openai`, or `openrouter` in `.env`.

**Demo mode:** If no API key is set for either provider, the agent returns simulated "High risk" responses so the dashboard can be demonstrated without API costs.

### Stage 4: Vector Storage (`app/data_ingestion/embeddings.py`)

Each contract's text is embedded using the `all-MiniLM-L6-v2` sentence-transformer model and stored (via upsert) in a ChromaDB collection alongside all metadata fields including `risk_level` and `risk_summary`.

**Deduplication & batching:** The Diavgeia API may return the same contract (ADA) across paginated requests. The ingestion layer automatically deduplicates contracts by ID before embedding. Large datasets are upserted in batches of 500 to stay within ChromaDB's request limits.

This enables:
- **Semantic search** — The chat interface finds relevant contracts by meaning, not just keywords.
- **Metadata-filtered search** — Hybrid retrieval combines semantic similarity with structured filters (municipality, category, risk level, budget range).
- **Watchdog visualization** — The Watchdog Map retrieves all contracts and renders risk-level-based visualizations.

---

## RAG Architecture

The Chat-to-Chart interface implements a **Hybrid RAG** (Retrieval-Augmented Generation) pipeline specifically designed for semi-structured procurement data. The pipeline has 5 stages:

```
User Query: "Which Thessaloniki contracts have the highest risk?"
         |
         v
  [1. Query Analyzer]   → Extracts: municipality="Thessaloniki", risk_level="High"
         |                          semantic_query="contracts highest risk"
         v
  [2. Hybrid Retriever]  → ChromaDB where_filter={municipality, risk_level}
         |                  + semantic search on remaining text (20 candidates)
         v
  [3. Re-ranker]          → Scores by: similarity + budget relevance + risk relevance
         |                  → Returns top 10
         v
  [4. Context Formatter]  → Structured markdown table (token-efficient)
         |
         v
  [5. GPT-5.1 Generator]  → Answers with citations to specific contract IDs
         |
         v
  [Response + Plotly Chart]
```

### 1. Query Analyzer (`app/rag/query_analyzer.py`)

Extracts structured filters from natural language without any LLM calls (zero latency, zero cost). Detects:
- **Ministries** — English and Greek keywords (e.g., "finance" → Υπουργείο Οικονομικών, "εσωτερικ" → Υπουργείο Εσωτερικών)
- **Risk levels** — Keywords like "risky", "suspicious", "flagged" → High; "moderate" → Medium
- **Budget ranges** — Patterns like "over 100k", "between 50k and 200k", "under €1 million"

### 2. Hybrid Retriever (`embeddings.py → hybrid_search()`)

Combines ChromaDB metadata `where` filters with semantic search. For example, "decisions from the Ministry of Interior over €100K" becomes:
- `where`: `{"$and": [{"municipality": {"$contains": "Εσωτερικών"}}, {"budget": {"$gte": 100000}}]}`
- Plus semantic search on the remaining query text

Falls back to pure semantic search if filters return no results.

### 3. Re-ranker (`embeddings.py → rerank_results()`)

After retrieving 20 candidates, scores each by combining:
- **Semantic similarity** — Inverse of ChromaDB L2 distance
- **Budget boost** — If the query mentions money/cost, high-budget contracts get a relevance boost
- **Risk boost** — If the query mentions fraud/risk, high-risk contracts get boosted

Returns the top 10 after re-ranking.

### 4. Context Formatter (`templates.py → format_contracts_as_context()`)

Formats retrieved contracts as a structured markdown table:
```
| ID | Contractor | Budget | Risk | Ministry | Description |
```
This is ~40% more token-efficient than raw text dumps and improves LLM comprehension of tabular data.

### 5. GPT-5.1 Generator

The RAG system prompt instructs GPT-5.1 to:
- Answer ONLY based on the provided context (no hallucination)
- Reference specific contract IDs in claims (verifiable)
- Format budgets with Euro signs and thousand separators
- Explicitly state when data is insufficient to answer

---

### Dashboard Pages

**Home.py — Chat-to-Chart (Hybrid RAG Interface):**
1. User types a natural language question (e.g., "Πόσα ξοδεύει ο Δήμος Θεσσαλονίκης;" or "Which contracts have the highest risk?").
2. Query Analyzer extracts structured filters + semantic query.
3. Hybrid search retrieves and re-ranks the most relevant contracts.
4. GPT-5.1 generates a grounded, citation-backed answer.
5. A Plotly pie chart is dynamically rendered showing spending by municipality.

**Watchdog_Map.py — Risk Monitoring Dashboard:**
- Displays KPI cards: total decisions monitored, High risk flags, Medium risk flags.
- Interactive filters by risk level and ministry.
- Shows a full audit log table with conditional row highlighting (red for High, orange for Medium, green for Low).
- Side-by-side charts: flagged budgets by ministry (bar chart) and overall risk distribution (pie chart).

---

## Prerequisites

1. **Docker Desktop** — Required only for running ChromaDB.
2. **Python 3.10+** (64-bit) — Tested with Python 3.12.
3. **An OpenAI API key** (recommended) — For GPT-5.1 auditing and chat. Alternatively, an OpenRouter key for free models.

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
.\myvenv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your API keys:

```powershell
copy .env.example .env
```

Then edit `.env`:

```env
# Primary: Azure OpenAI (for GPT-5.1)
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=your-azure-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | `"azure"`, `"openai"`, or `"openrouter"`. | `azure` |
| `AZURE_OPENAI_API_KEY` | Your Azure OpenAI API key. | `""` |
| `AZURE_OPENAI_ENDPOINT` | Azure resource endpoint URL. | `""` |
| `AZURE_OPENAI_DEPLOYMENT` | Azure deployment name (e.g., your GPT-5.1 deployment). | `""` |
| `AZURE_OPENAI_API_VERSION` | Azure API version. | `2024-12-01-preview` |
| `OPENAI_API_KEY` | Alternative: direct OpenAI API key. | `""` |
| `OPENROUTER_API_KEY` | Fallback: OpenRouter API key (free models). | `""` |
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
.\myvenv\Scripts\Activate.ps1
uvicorn app.api:app --reload --port 8001
```

The `--reload` flag enables hot-reloading: any change to a `.py` file restarts the server automatically. The API will be available at `http://localhost:8001`.

### Terminal 3: Start the Streamlit Dashboard

```powershell
.\myvenv\Scripts\Activate.ps1
python -m streamlit run app/dashboard/Home.py
```

The dashboard opens at `http://localhost:8501`. Use the sidebar to navigate between the Chat-to-Chart home page and the Watchdog Map.

---

## Data Ingestion

### Option A: Mock data

Loads 10 sample contracts from `data/sample_contracts.json`, including a deliberate fraud test case (Contract 6: a EUR 150,000 website update awarded to a 3-day-old company).

```powershell
python scripts/ingest.py
```

### Option B: Real Diavgeia data — bulk ingestion

Fetches live contracts from the Diavgeia OpenData advanced search API (`/search/advanced.json`) with pagination and runs them through the full pipeline (rules + AI audit + ChromaDB). Duplicate contracts (same ADA across pages) are automatically deduplicated before storage.

```powershell
# Fetch 10,000 real contracts, audit flagged ones with GPT-5.1, store in ChromaDB
python scripts/fetch_diavgeia.py --limit 10000

# Re-ingest from cache (skips re-fetching and re-auditing — instant)
python scripts/fetch_diavgeia.py --from-cache
```

Smaller batches for testing:

```powershell
python scripts/fetch_diavgeia.py --limit 50
```

Or POST them to the running FastAPI backend (same as n8n would):

```powershell
python scripts/fetch_diavgeia.py --mode api --limit 50
```

**Repair script:** If municipality or metadata needs fixing without re-auditing:
```powershell
python scripts/repair_cache.py --reingest
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
| `LLM_PROVIDER` | `LLM_PROVIDER` env var | `openai` | Which LLM backend to use (`openai` or `openrouter`) |
| `OPENAI_MODEL` | `OPENAI_MODEL` env var | `gpt-5.2` | OpenAI model for auditing and chat |
| `DEMO_MODE` | Auto-detected | `True` if no API keys set | Skips LLM calls, returns simulated responses |
| `ANOMALY_MULTIPLIER` | `ANOMALY_MULTIPLIER` env var | `3.0` | How many times above average triggers a flag |
| `CHROMA_COLLECTION` | `CHROMA_COLLECTION` env var | `procurement_contracts` | ChromaDB collection name |
| `LLM_TEMPERATURE` | `LLM_TEMPERATURE` env var | `0.1` | Low temp for deterministic JSON output |
| `LLM_MAX_TOKENS` | `LLM_MAX_TOKENS` env var | `1024` | Max tokens per LLM response |

---

## Design Decisions

### Why Hybrid RAG over naive semantic search?

Our data is **semi-structured**: each contract has structured fields (budget, municipality, category, risk level) alongside unstructured text (description). Pure semantic search fails on queries like "show me IT contracts over €100K in Thessaloniki" because embeddings don't reliably encode numbers, categories, or entity names. Hybrid retrieval — combining ChromaDB metadata `where` filters with semantic search — handles both structured and unstructured queries in a single pass. See `thought.md` for a detailed comparison of RAG approaches.

### Why GPT-5.1?

GPT-5.1 provides the best reasoning quality for both contract auditing (detecting fraud patterns) and RAG chat (synthesizing answers from tabular data). At $1.25/1M input tokens and $10/1M output tokens, auditing 500 flagged contracts costs ~$0.71 and 100 chat queries cost ~$0.29 — well within a $10 budget.

### Why ChromaDB as a vector database?

ChromaDB provides a lightweight, self-hosted vector store that runs in a single Docker container. It supports `where` metadata filtering alongside semantic search, which is essential for the hybrid RAG approach. ChromaDB handles both without requiring a separate relational database.

### Why a keyword-based query analyzer instead of an LLM?

The query analyzer uses regex/keyword matching instead of an LLM call. This adds zero latency and zero cost to every chat query. For the structured filters we need (municipality names, category keywords, budget patterns, risk keywords), keyword matching is deterministic and sufficient. Using an LLM to parse queries would add ~1 second latency and ~$0.003 per query for no meaningful accuracy gain on these well-defined patterns.

### Why re-ranking after retrieval?

ChromaDB's L2 distance only measures semantic similarity. But when a user asks about "expensive risky contracts," the most relevant result isn't necessarily the most semantically similar — it's the one that's both semantically relevant AND has high budget AND high risk. Re-ranking with domain-specific boosts (budget relevance, risk relevance) produces better results than pure semantic ranking.

### Why few-shot prompting with Pydantic validation?

The LLM must return structured JSON that maps directly to risk assessments. Few-shot examples in the system prompt train the model on the exact output format, while Pydantic validation (`app/prompts/parser.py`) acts as a safety net. If the LLM produces malformed JSON, the parser feeds the validation error back to the LLM and retries (up to 3 times). This closed-loop approach ensures reliable structured output.

### Why baseline averages for single-contract evaluation?

When n8n sends contracts one at a time, the rule engine can't compute meaningful category averages from a single data point (a contract can never exceed 3x its own budget). Hardcoded baseline averages derived from historical procurement data solve this by providing a reference point for anomaly detection regardless of batch size.

### Why static organization ID mapping instead of live API lookups?

The Diavgeia API returns `organizationId` as a numeric string (e.g., `"6114"`), not a human-readable name. We could call `/organizations/{uid}` for each decision, but that would add 10,000 extra API calls during bulk ingestion. Instead, we maintain a static `ORG_ID_TO_LABEL` dict for the 7 organizations we monitor. This is a conscious trade-off: zero extra latency in exchange for maintaining the mapping manually when adding new organizations.

### Why sentence-transformers (`all-MiniLM-L6-v2`)?

This model offers an excellent balance of embedding quality and speed. It runs locally (no API calls needed), generates 384-dimensional vectors, and handles both English and Greek text reasonably well. For a hackathon context, it eliminates external embedding API dependencies and associated latency.

### Why FastAPI with background tasks?

Contract processing (rule evaluation + LLM auditing + embedding + ChromaDB storage) can take several seconds per contract, especially when the LLM is involved. By using FastAPI's `BackgroundTasks`, the API returns immediately with a 200 status, allowing n8n to continue sending contracts without waiting. This prevents webhook timeouts and enables parallel processing.

### Why dual LLM providers (OpenAI + OpenRouter)?

OpenAI provides GPT-5.1 for high-quality auditing and chat. OpenRouter provides free fallback models for development and demo mode. Switching between them requires changing a single environment variable (`LLM_PROVIDER`), with no code changes. Both use the OpenAI-compatible chat completions format.
