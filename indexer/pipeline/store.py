"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

import logging
import time
from typing import Any

from .config import IndexerSettings
from .models import Chunk

log = logging.getLogger("rahbar.indexer.store")


def get_client(settings: IndexerSettings) -> Any:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count.
    """
    if not chunks:
        return 0

    client = get_client(settings)
    dimension = len(vectors[0]) if vectors else 768
    collection_metadata = {
        "embed_model": settings.embed_model,
        "embedding_model": settings.embed_model,
        "dimension": dimension,
    }
    indexed_at = str(time.time())  # the API keys its semantic cache on this: re-index = new epoch

    # A different pinned model means the old vectors are incomparable: rebuild from scratch.
    try:
        old = client.get_collection(settings.collection)
        if (old.metadata or {}).get("embed_model") != settings.embed_model:
            log.warning(
                "embed model changed (%s -> %s): rebuilding collection",
                (old.metadata or {}).get("embed_model"),
                settings.embed_model,
            )
            client.delete_collection(settings.collection)
    except Exception:
        pass  # no collection yet

    # Get or recreate collection with explicit embedding pin metadata
    try:
        collection = client.get_or_create_collection(
            name=settings.collection,
            metadata=collection_metadata,
        )
    except Exception:
        collection = client.create_collection(
            name=settings.collection,
            metadata=collection_metadata,
        )

    # Upsert chunks in batches
    batch_size = 100
    total = len(chunks)
    for i in range(0, total, batch_size):
        chunk_batch = chunks[i : i + batch_size]
        vec_batch = vectors[i : i + batch_size]

        ids = [c.id for c in chunk_batch]
        docs = [c.text for c in chunk_batch]
        metas = [c.metadata() for c in chunk_batch]

        collection.upsert(
            ids=ids,
            documents=docs,
            embeddings=vec_batch,
            metadatas=metas,
        )

    # Drop chunks of documents that left the corpus, then publish the new epoch (expires the cache).
    stale = set(collection.get(include=[])["ids"]) - {c.id for c in chunks}
    if stale:
        collection.delete(ids=list(stale))
    collection.modify(metadata={**collection_metadata, "indexed_at": indexed_at})
    log.info("stored %d chunks in collection %s", total, settings.collection)
    return total
