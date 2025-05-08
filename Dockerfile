FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /qwen2api

WORKDIR /qwen2api
RUN uv sync --frozen --no-cache

# Run the application.

CMD ["/qwen2api/.venv/bin/python", "run.py"]