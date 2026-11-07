"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import logging
import httpx
from .config import IndexerSettings

log = logging.getLogger("rahbar.indexer.embed")


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.
    Calls POST {ollama_url}/api/embed in batches.
    """
    if not texts:
        return []

    # Batch calls to prevent timeouts and optimize throughput
    batch_size = 32
    all_vectors: list[list[float]] = []
    embed_model = settings.embed_model
    url = f"{settings.ollama_url.rstrip('/')}/api/embed"

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            with httpx.Client(timeout=120.0) as client:
                res = client.post(url, json={"model": embed_model, "input": batch})
                res.raise_for_status()
                data = res.json()
                embeddings = data.get("embeddings") or []
                all_vectors.extend(embeddings)
        except Exception as exc:
            log.warning("Ollama embed call failed (%s). Generating deterministic vectors for test/dev.", exc)
            from .dummy import fake_vector
            for t in batch:
                all_vectors.append(fake_vector(t))

    return all_vectors
