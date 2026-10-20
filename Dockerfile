# One image for the API and the jobs; the command picks the entrypoint:
#   docker run IMAGE serve                 -> FastAPI on $PORT (default 8000)
#   docker run IMAGE train|evaluate|optimize|geolift|report|pipeline
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTENSOR_FLAGS="compiledir=/tmp/pytensor" MMM_REGISTRY_PATH=/app/models/registry PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[bigquery]"
COPY config ./config
RUN useradd --create-home app && mkdir -p /app/models /app/reports && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')" || exit 1
ENTRYPOINT ["mmm"]
CMD ["serve"]
