# bloom-ledger: Darkbloom tax-record ingest (+ optional earnings archiver) for Unraid (amd64).
# Build context = this folder (Dockerfile, ingest/, lib/).
FROM python:3.12-slim

# OpenTimestamps client (`ots`) for the daily manifest proofs. Pinned major; no other runtime deps.
RUN pip install --no-cache-dir "opentimestamps-client>=0.7,<0.8" \
 && useradd --uid 99 --gid 100 --no-create-home --home-dir /state bloom 2>/dev/null || true

WORKDIR /app
COPY lib/ /app/
COPY ingest/server.py ingest/bloom_ingest.py ingest/bloom_ingest_ledger.py ingest/bloom_alerts.py ingest/bloom_summary.py ingest/dashboard.html /app/
COPY earnings-loop.sh /app/earnings-loop.sh
RUN chmod 0755 /app/earnings-loop.sh

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BLOOM_DATA=/data BLOOM_TOKENS=/run/secrets/bloom_tokens BLOOM_PORT=8787
EXPOSE 8787
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).status == 200 else 1)"
USER 99:100
CMD ["python3", "/app/server.py"]
