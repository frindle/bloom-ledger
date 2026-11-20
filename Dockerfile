# bloom-ledger: Darkbloom earnings, power and tax ledger. Runs on any Docker host (amd64 or arm64), as a non-root user.
# Health: GET /healthz. Doctor: docker compose exec bloom-ledger python3 /app/server.py doctor
# Build context = this folder (Dockerfile, ingest/, lib/, client/).
FROM python:3.12-slim

# No runtime deps beyond the Python standard library.
RUN useradd --uid 99 --gid 100 --no-create-home --home-dir /state bloom 2>/dev/null || true

WORKDIR /app
COPY lib/ /app/
COPY ingest/server.py ingest/bloom_*.py ingest/dashboard.html ingest/settings.html /app/
COPY ingest/static/ /app/static/
COPY client/ /app/client/
COPY earnings-loop.sh /app/earnings-loop.sh
RUN chmod 0755 /app/earnings-loop.sh && mkdir -p /data /state && chown 99:100 /data /state

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BLOOM_DATA=/data BLOOM_KEYS=/data/secrets BLOOM_TOKENS=/data/secrets/bloom_tokens BLOOM_PORT=8787
EXPOSE 8787
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).status == 200 else 1)"
USER 99:100
VOLUME ["/data"]
CMD ["python3", "/app/server.py"]
