# cropcast API image (Render free: 512 MB RAM). Only the `api` dependency group is installed:
# the API reads tables and never loads models (no pandas / MLflow / LightGBM).
FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv venv /opt/venv \
 && uv export --frozen --only-group api --no-hashes -o /tmp/requirements.txt \
 && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r /tmp/requirements.txt
COPY src ./src
RUN VIRTUAL_ENV=/opt/venv uv pip install --no-cache --no-deps .

FROM python:3.11-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 ENV=prod
COPY --from=build /opt/venv /opt/venv
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /home/app
# Render injects $PORT (default 10000 for web services).
EXPOSE 10000
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3   CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"10000\")}/health', timeout=8)" || exit 1
# Shell form so ${PORT} expands; exec so uvicorn is PID 1 and gets SIGTERM. One worker keeps
# memory well under Render free's 512 MB. Proxy headers: rate limiting sees the client IP.
CMD exec uvicorn cropcast.api.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers --forwarded-allow-ips='*'
