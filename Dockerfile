# CitizenGov – AI-Powered Public Procurement Watchdog
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so first startup is faster
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# Make startup script executable
RUN chmod +x scripts/start.sh

# Expose ports: 8501 = Streamlit, 8000 = FastAPI
EXPOSE 8501 8000

ENV PYTHONPATH=/app
ENV PYTHONIOENCODING=utf-8

# Startup: auto-ingest from cache if needed, then run Streamlit + API
CMD ["bash", "scripts/start.sh"]
