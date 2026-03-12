# Use Python 3.10 slim as the base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
# This ensures cross-platform compilation works securely
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Set python path so Streamlit can locate the "app" and "scripts" packages
ENV PYTHONPATH=/app

# The startup script will first run ingestion, then start the dashboard
CMD sh -c "python -m scripts.ingest && streamlit run app/dashboard/Home.py --server.port=8501 --server.address=0.0.0.0"
