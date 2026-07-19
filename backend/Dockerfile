# GenUI backend image — used by deploy/docker-compose.yml (one deployment
# per customer, see deploy/README.md). Build context = backend/.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Optional extras are opt-in to keep the image lean; add before COPY . if needed:
#   anthropic  (LLM_PROVIDER=anthropic)
#   docling    (EXTRACTOR_BACKEND=docling)

COPY . .

RUN useradd --create-home genui
USER genui

EXPOSE 8000

# WORKERS = uvicorn worker processes. REDIS_URL is REQUIRED with WORKERS > 1:
# profiles, rate limits, LLM budget and the single-flight render lock are
# cross-process state (the deploy compose wires Redis in).
CMD exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-4}
