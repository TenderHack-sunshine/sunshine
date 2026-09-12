FROM python:3.12-slim

WORKDIR /app
COPY src ./src
COPY scripts/serve.py scripts/run_runtime_smoke.py scripts/index_official_qdrant.py ./scripts/

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "scripts/serve.py", "--host", "0.0.0.0", "--port", "8000"]
