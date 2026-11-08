FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd -u 10001 -m -s /bin/sh rahbar

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the pinned embedding model into the image: pods are read-only / egress-restricted.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" \
    && chmod -R a+rX /opt/fastembed

COPY app/ ./app/

USER rahbar

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

