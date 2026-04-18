FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tini \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
  && rm -rf /var/lib/apt/lists/*

COPY app /workspace/app
COPY tests /workspace/tests
COPY README.md /workspace/README.md
COPY requirements /workspace/requirements
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r /workspace/requirements/production.txt

ENTRYPOINT ["tini", "--"]

FROM base AS api
CMD ["python", "-m", "app.run_service"]

FROM base AS rag
CMD ["python", "-m", "app.run_service"]

FROM base AS ops
CMD ["python", "-m", "app.run_service"]

FROM base AS reranker
CMD ["python", "-m", "app.run_service"]

FROM base AS worker
CMD ["python", "-m", "app.run_service"]

FROM base AS beat
CMD ["python", "-m", "app.run_service"]
