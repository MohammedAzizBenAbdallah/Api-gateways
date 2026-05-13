FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --fix-missing \
    gcc \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only torch first (250 MB vs 800 MB for the default CUDA wheel).
# Must run before the full requirements install so the CPU wheel isn't overwritten.
RUN pip install --no-cache-dir \
    torch \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies (torch already satisfied, so pip skips it).
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

RUN python -m spacy download en_core_web_sm

# Bake the DistilBERT injection model into the image so startup warm-up is
# instant — no download on first boot.  The model lands in HF_HOME which the
# K8s manifest sets to /var/cache/huggingface (emptyDir, pre-populated here).
ENV HF_HOME=/var/cache/huggingface
RUN python -c "\
from transformers import pipeline; \
pipeline('text-classification', model='fmops/distilbert-prompt-injection', \
         device=-1)"

COPY . .

# Environment variables will be provided by docker-compose
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
