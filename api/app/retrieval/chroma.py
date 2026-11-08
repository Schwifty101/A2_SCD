"""The real retriever (sections 3.2 and 4.4).
Reads from ChromaDB; never writes to it.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, cast

from ..config import Settings
from ..schemas import Passage

log = logging.getLogger("rahbar.retrieval.chroma")


@lru_cache(maxsize=1)
def _model(name: str):  # type: ignore[no-untyped-def]
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _embed_query(self, query: str) -> list[float]:
        """Embed the query with the pinned EMBED_MODEL (local fastembed; must match the indexer)."""
        return [float(x) for x in _model(self.settings.embed_model).query_embed(query).__next__()]

    def retrieve(self, question: str, k: int) -> list[Passage]:
        """Embed the question with EMBED_MODEL, query Chroma for top-k,
        filter out superseded documents unless an older version was requested,
        and convert cosine distance to similarity (1 - distance).
        """
        collection = self.client.get_collection(self.settings.collection)
        query_vector = self._embed_query(question)

        # Check if the user specifically asked about an older / repealed version
        asks_older = bool(
            re.search(r"\b(2023|previous|older|repealed|former|prior)\b", question, re.IGNORECASE)
        )
        metadata_filter = None if asks_older else {"superseded": False}

        results = collection.query(
            query_embeddings=cast(Any, [query_vector]),
            n_results=k,
            where=cast(Any, metadata_filter),
            include=["documents", "metadatas", "distances"],
        )

        passages: list[Passage] = []
        res = cast(dict[str, Any], results)
        ids = res.get("ids", [[]])[0] or []
        docs = res.get("documents", [[]])[0] or []
        metas = res.get("metadatas", [[]])[0] or []
        distances = res.get("distances", [[]])[0] or []

        for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
            # Chroma returns cosine distance; convert to similarity
            similarity = max(0.0, 1.0 - float(dist))
            passages.append(
                Passage(
                    chunk_id=chunk_id,
                    text=text,
                    source=str(meta.get("source", "unknown")),
                    section=str(meta.get("section", "General")),
                    page=int(meta["page"]) if meta.get("page") is not None else None,
                    score=similarity,
                )
            )

        return passages
