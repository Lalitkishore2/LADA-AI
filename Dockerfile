FROM python:3.11-slim

LABEL maintainer="LADA Team"
LABEL description="LADA - Language Agnostic Digital Assistant v11.0"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ffmpeg \
    tesseract-ocr \
    libasound2-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash lada
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/vector_memory data/rag_knowledge data/code_backups \
    data/conversations data/demonstrations data/workflows \
    config/prompts/modes logs

# Set ownership
RUN chown -R lada:lada /app

USER lada

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    LADA_MODE=text \
    LADA_PORT=5000 \
    DATA_DIR=/app/data \
    LOGS_DIR=/app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${LADA_PORT}/health')" || exit 1

# Expose ports (5000=API, 8765=webhook)
EXPOSE 5000 8765

# Default: run webui in headless mode (API server on 0.0.0.0:5000)
ENTRYPOINT ["python"]
CMD ["lada_webui.py", "--no-browser"]
