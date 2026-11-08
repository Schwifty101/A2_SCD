"""Stage 4: Embed. One vector per chunk, from the pinned model only.

Local ONNX embeddings (fastembed): Groq has no embeddings API, and a local model keeps the
indexer and the API on byte-identical vectors. Fails loudly: a fake vector here would be a
silent index/query disagreement (section 4.4).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from .config import IndexerSettings

log = logging.getLogger("rahbar.indexer.embed")


@lru_cache(maxsize=1)
def _model(name: str):  # type: ignore[no-untyped-def]
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else."""
    if not texts:
        return []
    return [v.tolist() for v in _model(settings.embed_model).embed(texts, batch_size=8)]
