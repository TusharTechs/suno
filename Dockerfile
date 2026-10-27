# SUNO web app: FastAPI + the teacher web app. One container, SQLite inside it.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server ./server
COPY web ./web
COPY prompts ./prompts
COPY schemas ./schemas
COPY config ./config
COPY samples ./samples
ENV SUNO_VAR=/data PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "/app/.venv/bin/uvicorn server.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
