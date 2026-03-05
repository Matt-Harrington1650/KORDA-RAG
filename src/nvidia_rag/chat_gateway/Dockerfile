ARG BASE_IMAGE_URL=python
ARG BASE_IMAGE_TAG=3.12-slim

FROM ${BASE_IMAGE_URL}:${BASE_IMAGE_TAG}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl file libmagic1 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md LICENSE /workspace/
COPY src /workspace/src
COPY examples /workspace/examples
COPY deploy/config /workspace/deploy/config

RUN pip install --no-cache-dir uv && \
    uv sync --locked --no-dev --extra all

EXPOSE 8083

ENTRYPOINT ["uv", "run", "uvicorn", "nvidia_rag.chat_gateway.server:app", "--host", "0.0.0.0", "--port", "8083"]

