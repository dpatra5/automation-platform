# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir build==1.2.2
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LT_API_RUNS_DIR=/data/runs \
    LT_API_EXAMPLES_DIR=/app/examples \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin lt \
    && mkdir -p /app /data/runs \
    && chown lt:lt /data/runs
COPY --from=build /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*
COPY examples /app/examples
WORKDIR /app
USER lt
VOLUME ["/data/runs"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
# Binding 0.0.0.0 requires LT_API_TOKEN; the server refuses to start unauthenticated.
CMD ["lt", "serve", "--host", "0.0.0.0", "--port", "8000"]
