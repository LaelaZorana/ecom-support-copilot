# Single-stage, slim image. Runs the offline stub by default — no API keys required.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code and seed data.
COPY supportcopilot ./supportcopilot
COPY data ./data

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Hugging Face Spaces / Render set $PORT; default to 8000 locally.
CMD ["sh", "-c", "python -m uvicorn supportcopilot.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
