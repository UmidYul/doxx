FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml scrapy.cfg ./
COPY application ./application
COPY config ./config
COPY domain ./domain
COPY infrastructure ./infrastructure

RUN pip install .

# Default command is overridden by docker-compose (scrapy crawl <spider>).
CMD ["scrapy", "crawl", "mediapark"]
