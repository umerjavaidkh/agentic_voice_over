FROM python:3.12-slim

WORKDIR /app

COPY services/agent-brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/agent-brain /app

ENV PYTHONPATH=/app

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--ws", "websockets"]
