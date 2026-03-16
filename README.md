# CitizenGov - AI-Powered Public Procurement Watchdog

CitizenGov is an AI-powered transparency platform that monitors Greek public sector contracts for signs of fraud, waste, and financial irregularities. It ingests procurement data from [Diavgeia](https://diavgeia.gov.gr/), runs automated anomaly detection, performs AI-driven auditing via GPT-5.1, and presents the results through an interactive Streamlit dashboard with a RAG chat interface.

Built for **Netcompany Hackathon Thessaloniki 2026** — Challenge 2: AI-Powered Knowledge Base System.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Diavgeia API Integration](#diavgeia-api-integration)
3. [How the Pipeline Works](#how-the-pipeline-works)
4. [RAG Architecture](#rag-architecture)
5. [Prerequisites](#prerequisites)
6. [Setup Guide](#setup-guide)
7. [Running the Application](#running-the-application)
8. [Data Ingestion](#data-ingestion)
9. [API Reference](#api-reference)
10. [Configuration](#configuration)
11. [Design Decisions](#design-decisions)

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

**Data layer:** ChromaDB vector database stores contract embeddings alongside structured metadata (budget, risk level, organization, contractor, date). This enables both semantic search and metadata-filtered retrieval through a single store.

**Compute layer:** A FastAPI backend exposes REST endpoints for contract ingestion. An n8n workflow (or standalone scripts) feeds data into the pipeline. The pipeline evaluates rule-based anomaly flags, then escalates suspicious contracts to GPT-5.1 for deeper analysis.

**Presentation layer:** A multi-page Streamlit dashboard provides a Hybrid RAG chat interface ("Chat-to-Chart") and a risk monitoring view ("Watchdog Map") with color-coded anomaly tables and Plotly visualizations.

---


## Diavgeia API Integration

CitizenGov integrates with the [Diavgeia OpenData API](https://diavgeia.gov.gr/api/help) — Greece's official public transparency portal where all government decisions are legally required to be published.

### API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /search/advanced.json` | Paginated search with Lucene-style query syntax |
| `GET /luminapi/api/decisions/{ada}` | Full decision details including `documentText` (plain-text body) |
| `GET /organizations/{uid}.json` | Resolve organization UID to human-readable label |

### Query Design

The advanced search query targets **7 Greek Ministries** and decision type **Δ.1 (Σύμβαση / Contract)** — the only type that contains actual contractor names:

```
organizationUid:"{uid}" AND decisionTypeUid:"Δ.1"
```

Each ministry is queried individually with equal limits to ensure balanced representation across all 7.

| Organization UID | Label | English |
|---|---|---|
| `6` | Υπουργείο Εθνικής Άμυνας | Ministry of National Defence |
| `15` | Υπουργείο Οικονομικών | Ministry of Finance |
| `100054486` | Υπουργείο Ψηφιακής Διακυβέρνησης | Ministry of Digital Governance |
| `100054489` | Υπουργείο Προστασίας του Πολίτη | Ministry of Citizen Protection |
| `100054492` | Υπουργείο Εσωτερικών | Ministry of Interior |
| `100056663` | Υπουργείο Μετανάστευσης και Ασύλου | Ministry of Migration and Asylum |
| `100081880` | Υπουργείο Παιδείας, Θρησκευμάτων και Αθλητισμού | Ministry of Education |

| Decision Type | Description | Has Contractor? |
|---|---|---|
| **`Δ.1`** | **ΣΥΜΒΑΣΗ — Contract awards** | **Yes** (`person[].name` + AFM) |
| `Β.1.3` | ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ — Budget commitments | No |
| `Β.2.1` | ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ — Expenditure approvals | No |

We focus exclusively on **Δ.1** because it is the only decision type that includes the contractor's identity (company name and tax ID / ΑΦΜ). Types Β.1.3 and Β.2.1 are internal budget acts that never specify a contractor, making them unsuitable for procurement fraud analysis.

### Field Extraction from API Response

The Diavgeia API returns decisions with structured metadata. We extract:

| Our Field | Diavgeia Source | Notes |
|---|---|---|
| `id` | `ada` | Unique decision identifier (Αριθμός Διαδικτυακής Ανάρτησης) |
| `description` | `subject` + `documentText` | Subject line; optionally enriched with full decision text via `/luminapi/api/decisions/{ada}` |
| `date` | `issueDate` | Unix timestamp (ms from epoch) |
| `organization` | `organizationId` → lookup | Numeric org ID mapped to ministry label via `ORG_ID_TO_LABEL` dict |
| `budget` | `extraFieldValues.awardAmount.amount` | Contract award amount; fallback to `amountWithTaxes` / `amountWithVAT` |
| `contractor` | `extraFieldValues.person[].name` | Company name from the `person` array (Δ.1 decisions); includes AFM (tax ID) |

**Decision text enrichment:** When `--fetch-text` is used, the fetcher calls `/luminapi/api/decisions/{ada}` for each decision to retrieve the `documentText` field — the plain-text body of the actual decision document. This is appended to the description (first 500 chars) to provide richer context for the AI auditor and RAG search. This adds ~0.2s per decision due to the extra API call.

> **Known limitation:** In practice, most Diavgeia decisions (especially Δ.1 contracts) are uploaded as signed PDF attachments only. The `documentText` field is empty for these decisions, so `--fetch-text` returns no additional text. The `subject` field remains the primary source of description content. Extracting text from the PDF attachments (`documentUrl`) would require downloading and OCR-ing each file, which is outside the scope of this project.

**Organization ID resolution:** The API returns `organizationId` as a numeric string (e.g., `"6114"`), not a human-readable name. We maintain a static mapping (`ORG_ID_TO_LABEL`) from organization UIDs to Greek labels, derived from the `/organizations/{uid}` endpoint.

### Pagination & Rate Limiting

The Diavgeia API enforces a **180-day window** on `issueDate` queries and caps page sizes at 500 results (1000 for authenticated users). Our fetcher (`scripts/fetch_diavgeia.py`) paginates through results with 0.5s delays between requests to avoid rate limiting, and deduplicates by ADA before storage (the API occasionally returns the same decision across page boundaries).

---

## How the Pipeline Works

### Stage 1: Data Fetching (`app/data_ingestion/scraper.py`, `scripts/fetch_diavgeia.py`)

Contracts enter the system in one of three ways:
- **n8n workflow** — An automated flow queries Diavgeia's advanced search API, then POSTs each contract to the FastAPI `/api/ingest` endpoint.
- **Standalone script** — `scripts/fetch_diavgeia.py` replicates the n8n logic in pure Python, useful for bulk ingestion without n8n. Supports `--from-cache` to skip re-fetching and re-auditing.
- **Mock data** — `scripts/ingest.py` loads 10 pre-built contracts from `data/sample_contracts.json` for offline dummy testing.

Each contract is normalized into a standard dict with: `id`, `contractor`, `budget`, `date`, `description`, and `organization`.

### Stage 2: Rule-Based Anomaly Detection (`app/watchdog/rules.py`)

The rule engine computes average budgets per procurement category, then flags any contract whose budget exceeds **3x the category average** AND is above **EUR 10,000** (to filter out noise from small purchases).

Flagged contracts receive `risk_level: "Medium"` and a descriptive `risk_summary` explaining why they were flagged. In our dataset of ~3.500 real Diavgeia decisions, the rule engine flags approximately **1.6%** of contracts for AI review — a realistic anomaly rate.

**Small batch handling:** When contracts arrive one at a time (via n8n webhooks), computing a meaningful average is impossible. The system falls back to hardcoded `BASELINE_AVERAGES` derived from historical procurement data when the batch size is less than 5.

### Stage 3: AI Auditing (`app/watchdog/agent.py`)

Contracts flagged as "Medium" risk are escalated to GPT-5.1 for deeper analysis. The agent:

1. Receives a few-shot prompt (`app/prompts/templates.py`) designed to enforce strict JSON output at low temperature (0.1).
2. Returns a structured risk assessment with `risk_level` (Low/Medium/High) and `risk_summary`.
3. The response is validated through a Pydantic parser (`app/prompts/parser.py`) that strips markdown artifacts, extracts JSON, and validates the schema. On validation failure, it automatically retries up to 3 times, feeding the error details back to the LLM.

**LLM Provider:** The system supports OpenAI (primary, for GPT-5.1) and OpenRouter (fallback, for free models). Set `LLM_PROVIDER=openai` or `openrouter` in `.env`.

**Demo mode:** If no API key is set for either provider, the agent returns simulated "High risk" responses so the dashboard can be demonstrated without API costs.

### Stage 4: Vector Storage (`app/data_ingestion/embeddings.py`)

Each contract's text is embedded using the `all-MiniLM-L6-v2` sentence-transformer model and stored (via upsert) in a ChromaDB collection alongside all metadata fields including `risk_level` and `risk_summary`.

**Deduplication & batching:** The Diavgeia API may return the same contract (ADA) across paginated requests. The ingestion layer automatically deduplicates contracts by ID before embedding. Large datasets are upserted in batches of 500 to stay within ChromaDB's request limits.

This enables:
- **Semantic search** — The chat interface finds relevant contracts by meaning, not just keywords.
- **Metadata-filtered search** — Hybrid retrieval combines semantic similarity with structured filters (organization, category, risk level, budget range).
- **Watchdog visualization** — The Watchdog Map retrieves all contracts and renders risk-level-based visualizations.

---

## RAG Architecture

The Chat-to-Chart interface implements a **Hybrid RAG** (Retrieval-Augmented Generation) pipeline specifically designed for semi-structured procurement data. The pipeline has 5 stages:

```
User Query: "Which Thessaloniki contracts have the highest risk?"
         |
         v
  [1. Query Analyzer]   → Extracts: organization="Thessaloniki", risk_level="High"
         |                          semantic_query="contracts highest risk"
         v
  [2. Hybrid Retriever]  → ChromaDB where_filter={organization, risk_level}
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
- `where`: `{"$and": [{"organization": {"$contains": "Εσωτερικών"}}, {"budget": {"$gte": 100000}}]}`
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
5. A Plotly pie chart is dynamically rendered showing spending by organization.

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

Create your `.env` and fill in your API keys:

```powershell
copy .env.example .env
```

Then edit `.env`:

```env
# === LLM Provider ===
LLM_PROVIDER=openai

# === OpenAI (primary — recommended) ===
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-5.1

# === OpenRouter (free fallback) ===
# OPENROUTER_API_KEY=sk-or-your-key-here
# LLM_MODEL=openai/gpt-oss-120b:free

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | `"openai"` (recommended) or `"openrouter"` (free fallback). | `openai` |
| `OPENAI_API_KEY` | Your OpenAI API key (for GPT-5.1). | `""` |
| `OPENAI_MODEL` | OpenAI model name. | `gpt-5.1` |
| `OPENROUTER_API_KEY` | OpenRouter API key (free models as fallback). | `""` |
| `LLM_MODEL` | OpenRouter model identifier. | `openai/gpt-oss-120b:free` |
| `CHROMA_HOST` | ChromaDB hostname. Use `localhost` for local dev, `chromadb` in Docker. | `localhost` |
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

> **Note:** The first time Streamlit loads, it downloads and initializes the sentence-transformer embedding model (~90 MB). This causes an expected delay of some minutes.

---

## Data Ingestion

### Option A: Mock data

Loads 10 sample contracts from `data/sample_contracts.json` — realistic Greek Δ.1 decisions from 7 ministries, including deliberate anomaly test cases (e.g., a €450K website contract awarded to a company founded 5 days prior, and a €15.8M multi-year obligation with no named contractor).

```powershell
python scripts/ingest.py
```

### Option B: Real Diavgeia data — bulk ingestion

Fetches live **Δ.1 (contract) decisions** from the Diavgeia OpenData advanced search API with pagination and runs them through the full pipeline (rules + AI audit + ChromaDB). Only Δ.1 decisions are fetched because they are the only type that includes the contractor's identity.

```powershell
# Fetch 14,000 real contracts (2,000 per ministry), audit flagged ones, store in ChromaDB
python scripts/fetch_diavgeia.py --limit 14000

# Same, but also fetch the full decision text for richer RAG context (~0.2s extra per decision). Since Diavgeia's API is not 100% working, during our tests, there was high probability of no text being returned.
python scripts/fetch_diavgeia.py --limit 14000 --fetch-text

# Re-ingest from cache (skips re-fetching and re-auditing — instant)
python scripts/fetch_diavgeia.py --from-cache
```

Smaller batches for testing:

```powershell
python scripts/fetch_diavgeia.py --limit 50
python scripts/fetch_diavgeia.py --limit 50 --fetch-text
```

Or POST them to the running FastAPI backend (same as n8n would):

```powershell
python scripts/fetch_diavgeia.py --mode api --limit 50
```

**Repair script:** If organization or metadata needs fixing without re-auditing:
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
  "subject": "Σύμβαση για την ανάπτυξη πληροφοριακού συστήματος διαχείρισης ηλεκτρονικών εγγράφων",
  "issue_date": "2026-02-18",
  "contractor": "INTRASOFT INTERNATIONAL A.E.",
  "budget": 248000.0,
  "organization": "Υπουργείο Ψηφιακής Διακυβέρνησης"
}
```

`contractor`, `budget`, and `organization` are optional (default to `"Unknown"`, `0.0`, and `"Unknown"` respectively).

---

## Configuration

All configuration is centralized in `app/config.py`, which reads from environment variables with sensible defaults. Key settings:

| Setting | Source | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | `LLM_PROVIDER` env var | `openai` | Which LLM backend to use (`openai` or `openrouter`) |
| `OPENAI_MODEL` | `OPENAI_MODEL` env var | `gpt-5.1` | OpenAI model for auditing and chat |
| `DEMO_MODE` | Auto-detected | `True` if no API keys set | Skips LLM calls, returns simulated responses |
| `ANOMALY_MULTIPLIER` | `ANOMALY_MULTIPLIER` env var | `3.0` | How many times above average triggers a flag |
| `CHROMA_COLLECTION` | `CHROMA_COLLECTION` env var | `procurement_contracts` | ChromaDB collection name |
| `LLM_TEMPERATURE` | `LLM_TEMPERATURE` env var | `0.1` | Low temp for deterministic JSON output |
| `LLM_MAX_TOKENS` | `LLM_MAX_TOKENS` env var | `1024` | Max tokens per LLM response |

---

## RAG Evaluation

The `eval/` directory contains an automated evaluation framework that measures the quality of the RAG pipeline's answers against reference answers.

### Files

| File | Description |
|---|---|
| `eval/questions.csv` | 15 evaluation questions (Greek) with expected answers — covering both quantitative queries (specific contract lookups, risk counts per ministry) and qualitative queries (transparency recommendations, risk pattern analysis) |
| `eval/evaluate_rag.py` | Evaluation script that runs each question through the full RAG pipeline, then uses GPT-5.1 as an impartial judge to score the answer (1–5) against the reference |
| `eval/results.csv` | Output: actual RAG answers, scores, and per-question reasoning |

### Running the evaluation

```powershell
python eval/evaluate_rag.py
```

### Results (3,284 contracts dataset)

| Metric | Value |
|---|---|
| **Average Score** | **3.67 / 5** |
| Score 5 (Perfect) | 6 questions |
| Score 4 (Good) | 3 questions |
| Score 3 (Acceptable) | 3 questions |
| Score 2 (Poor) | 1 question |
| Score 1 (Fail) | 2 questions |

Filtered queries (e.g., "high-risk contracts of Ministry X") consistently score 4–5. Weaker scores come from questions requiring aggregation across the full dataset — the RAG window retrieves 50 contracts and re-ranks to 15, so questions about totals or frequencies across all 3,284 contracts may receive incomplete answers.

---

## Design Decisions

### Why Hybrid RAG over naive semantic search?

Our data is **semi-structured**: each contract has structured fields (budget, organization, category, risk level) alongside unstructured text (description). Pure semantic search fails on queries like "show me IT contracts over €100K in Thessaloniki" because embeddings don't reliably encode numbers, categories, or entity names. Hybrid retrieval — combining ChromaDB metadata `where` filters with semantic search — handles both structured and unstructured queries in a single pass. See `thought.md` for a detailed comparison of RAG approaches.

### Why ChromaDB as a vector database?

ChromaDB provides a lightweight, self-hosted vector store that runs in a single Docker container. It supports `where` metadata filtering alongside semantic search, which is essential for the hybrid RAG approach. ChromaDB handles both without requiring a separate relational database.

### Why a keyword-based query analyzer instead of an LLM?

The query analyzer uses regex/keyword matching instead of an LLM call. This adds zero latency and zero cost to every chat query. For the structured filters we need (organization names, category keywords, budget patterns, risk keywords), keyword matching is deterministic and sufficient. Using an LLM to parse queries would add ~1 second latency and ~$0.003 per query for no meaningful accuracy gain on these well-defined patterns.

### Why re-ranking after retrieval?

ChromaDB's L2 distance only measures semantic similarity. But when a user asks about "expensive risky contracts," the most relevant result isn't necessarily the most semantically similar — it's the one that's both semantically relevant AND has high budget AND high risk. Re-ranking with domain-specific boosts (budget relevance, risk relevance) produces better results than pure semantic ranking.

### Why sentence-transformers (`all-MiniLM-L6-v2`)?

This model offers an excellent balance of embedding quality and speed. It runs locally (no API calls needed), generates 384-dimensional vectors, and handles both English and Greek text reasonably well. For a hackathon context, it eliminates external embedding API dependencies and associated latency.
