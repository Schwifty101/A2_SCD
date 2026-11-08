"""Liveness and readiness probes (sections 4.3 and 4.4).
They answer different questions:
- /healthz: Is the Python process alive? Never touches external dependencies.
- /readyz: Can this replica serve traffic? Checks Chroma reachability, non-empty collection,
  Redis cache reachability, and embedding model pin match.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from ..config import Settings

router = APIRouter()
log = logging.getLogger("rahbar.health")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must NEVER touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Readiness probe: validates Chroma, non-empty collection, Redis, and embedding model pin."""
    settings: Settings = request.app.state.settings
    checks: dict[str, str] = {}
    failed_dependencies: list[str] = []

    # If running with stubs (local dev / CI), report ready
    if settings.retriever == "stub" and settings.llm_provider == "stub":
        return {"status": "ready", "checks": {"stub": "ok"}}

    # 1. Chroma Reachability & Non-Empty Collection Check
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        chroma_client.heartbeat()
        checks["chroma_reachability"] = "ok"

        # Check collection exists
        collection = chroma_client.get_collection(settings.collection)
        chunk_count = collection.count()
        if chunk_count == 0:
            failed_dependencies.append("chroma_collection_empty")
            checks["collection"] = "empty"
        else:
            checks["collection"] = f"ok ({chunk_count} chunks)"

        # 2. Enforce the Embedding Model Pin Guardrail (Section 4.4)
        col_meta = collection.metadata or {}
        indexed_model = col_meta.get("embed_model") or col_meta.get("embedding_model")
        if indexed_model and indexed_model != settings.embed_model:
            # Embedding model mismatch guardrail: refusal to serve garbage
            mismatch_msg = f"mismatch: collection was indexed with {indexed_model} but runtime EMBED_MODEL is {settings.embed_model}"
            log.error("Embedding pin guardrail conflict - %s", mismatch_msg)
            failed_dependencies.append(f"embedding_model_mismatch: {mismatch_msg}")
            checks["embed_model_pin"] = mismatch_msg
        else:
            checks["embed_model_pin"] = "ok"

    except Exception as exc:
        log.error("Chroma readiness check failed: %s", exc)
        failed_dependencies.append(f"chroma: {exc}")
        checks["chroma"] = f"failed: {exc}"

    # 3. Redis Reachability Check (if cache enabled)
    if settings.cache_enabled:
        try:
            import redis

            r_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                socket_connect_timeout=2.0,
            )
            r_client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            log.warning("Redis readiness check failed: %s", exc)
            failed_dependencies.append(f"redis: {exc}")
            checks["redis"] = f"failed: {exc}"

    # Determine readiness status
    if failed_dependencies:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        log.warning("Readiness probe failed on dependencies: %s", failed_dependencies)
        return {
            "status": "not_ready",
            "failed_dependencies": failed_dependencies,
            "checks": checks,
        }

    return {"status": "ready", "checks": checks}
