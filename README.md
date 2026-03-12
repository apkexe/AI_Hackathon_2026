# CitizenGov Hackathon Project

CitizenGov is an AI-powered watchdog application built to monitor and audit public sector contracts for signs of irregular activity or fraud. 

This guide explains how to run the application locally for heavy development. By running the Python backend and Streamlit dashboard natively on your Windows machine, you can make instant code changes without waiting for Docker to rebuild the Python containers!

## Prerequisites
1. **Docker Desktop** (running in the background)
2. **Python 3.12 (64-bit)** installed on your machine.
3. Your OpenRouter API key saved in the `.env` file.

---

## Setting up your Local Environment (First Time Only)

Since we are running the code natively, we need to create a Python "Virtual Environment" to hold all our dependencies locally (instead of inside the Docker container).

Open your terminal in the project folder and run:

```powershell
# 1. Create a 64-bit virtual environment
py -3.12-64 -m venv myvenv

# 2. Activate it
.\myvenv\Scripts\activate

# 3. Install the lightweight dependencies
pip install -r requirements.txt

## 🚀 How to Run the App Locally (Every Time)

Whenever you sit down to work on the project, you need to start three things: the Database, the Backend API, and the Frontend Dashboard.

### Step 1: Start the Database (Docker)
We use Docker **only** to run the ChromaDB Vector Database. This gives us a stable place to store our embeddings without compiling database engines locally.

Open your `.env` file and completely ensure that you are pointing to your local machine:
```env
CHROMA_HOST=localhost
```

Then, run this command to start the database in the background:
```powershell
docker-compose up -d chromadb
```

### Step 2: Start the FastAPI Backend
Open a new terminal window, activate your environment, and start the API server. This server will handle processing N8N webhooks and AI auditing.

```powershell
# Activate the environment
.\myvenv\Scripts\activate.ps1

# Run the API with hot-reloading enabled
uvicorn app.api:app --reload --port 8000
```
*(Because of the `--reload` flag, any time you save a `.py` file in the `app/` folder, the server will instantly restart!)*

### Step 3: Start the Streamlit Dashboard
Open a **third** final terminal window, activate your environment, and start the visual dashboard:

```powershell
# Activate the environment
.\myvenv\Scripts\activate

# Start Streamlit
python -m streamlit run app/dashboard/Home.py
```
Streamlit also has hot-reloading. When you save a change to a dashboard file, you can just click "Rerun" in the top right corner of your browser.

---

## 🛠️ Useful Commands

**How do I ingest test data locally?**
If your dashboard is empty, you can run the ingestion script locally to trigger the OpenRouter AI and populate your ChromaDB Docker container:
```powershell
python scripts/ingest.py
```

**How do I completely wipe the database and start fresh?**
If you mess up your vectors or ChromaDB throws a metadata error, you can nuke the Docker volume:
```powershell
docker-compose down -v
# Then restart it
docker-compose up -d chromadb
```
