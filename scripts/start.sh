#!/bin/bash
set -e

echo "============================================"
echo "  CitizenGov - Starting up..."
echo "============================================"

# Wait for ChromaDB to be ready
echo "Waiting for ChromaDB at ${CHROMA_HOST:-chromadb}:${CHROMA_PORT:-8000}..."
until python -c "
import urllib.request
try:
    urllib.request.urlopen('http://${CHROMA_HOST:-chromadb}:${CHROMA_PORT:-8000}/api/v1/heartbeat')
    print('ChromaDB is ready.')
except Exception as e:
    print(f'Not ready: {e}')
    exit(1)
" 2>/dev/null; do
    echo "  ChromaDB not ready yet, retrying in 3s..."
    sleep 3
done

# Check if ChromaDB already has data
NEEDS_INGEST=$(python -c "
import chromadb
client = chromadb.HttpClient(host='${CHROMA_HOST:-chromadb}', port=int('${CHROMA_PORT:-8000}'))
col = client.get_or_create_collection('procurement_contracts')
count = col.count()
print(f'ChromaDB has {count} contracts.')
if count < 100:
    print('NEEDS_INGEST')
else:
    print('READY')
" 2>&1)

echo "$NEEDS_INGEST"

if echo "$NEEDS_INGEST" | grep -q "NEEDS_INGEST"; then
    echo "============================================"
    echo "  First-time setup: Loading contracts..."
    echo "  This takes ~5 minutes (generating embeddings)"
    echo "============================================"
    python scripts/fetch_diavgeia.py --from-cache
    echo "  Ingestion complete!"
else
    echo "  ChromaDB already has data. Skipping ingestion."
fi

echo "============================================"
echo "  Starting services..."
echo "============================================"

# Start FastAPI backend in background
uvicorn app.api:app --host 0.0.0.0 --port 8000 &

# Start Streamlit dashboard (foreground)
streamlit run app/dashboard/Home.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
