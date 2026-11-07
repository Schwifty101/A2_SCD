# ADR 0001: Decoupling Indexing as an Independent Kubernetes Job

## Status
Accepted · 2026-11-03

## Context
In a Retrieval-Augmented Generation (RAG) system running on Kubernetes, indexing involves extracting text from diverse documents (PDFs, HTML tables, Markdown), parsing structure, chunking text, generating dense embeddings via an embedding model, and writing vectors with rich metadata into ChromaDB.

A common anti-pattern observed in initial prototypes is running the indexing pipeline inside the API server's startup hook (e.g., FastAPI's `@app.on_event("startup")` or `lifespan`). When transitioning from a single laptop developer environment to a production Kubernetes deployment running 3 API replicas, this architectural shortcut catastrophically breaks in four distinct ways:

1. **Concurrent Multi-Writer Volume Corruption**: Our vector database (ChromaDB) uses SQLite and persistent files on a single persistent volume (PVC). If indexing runs on API pod startup, all 3 replicas boot simultaneously, mount the volume, and race to extract, embed, and write chunks concurrently. Without distributed transactions, concurrent uncoordinated writes leave index files corrupted with torn pages and incomplete document states.
2. **Restart Amplification & Compute Waste**: Every Kubernetes lifecycle event—a rolling update, node drain, OOMKill, or transient probe timeout—triggers container restarts. If indexing is coupled to startup, every pod restart pays the complete computational penalty of re-extracting ~170 pages and running embedding inference, exhausting cluster memory and CPU.
3. **Readiness Probe Incoherence**: Kubernetes uses the readiness probe to determine when a pod can receive ingress traffic. If indexing runs during startup, the pod must either:
   - Report ready prematurely before chunks exist, serving empty or broken retrievals to users; or
   - Delay readiness for minutes while chunking, causing Kubernetes' liveness or startup probes to time out, killing the pod in a perpetual `CrashLoopBackOff`.
4. **Impossibility of In-Place Re-indexing (The "Friday Failure")**: When university policy updates occur (e.g., a revised academic calendar or superseded rule), operators must be able to trigger re-indexing without rebuilding application images or redeploying the serving tier. Coupling indexing to API startup makes vector ingestion contingent on image redeployment.

## Decision
We decouple vector ingestion completely from the serving tier by deploying the indexer as an isolated, one-shot Kubernetes **Job** (`batch/v1`), accompanied by a weekly scheduled **CronJob** (`reindex`).

- The API deployment runs with 3 replicas configured with **read-only access** to ChromaDB.
- The Indexer Job is the **exclusive writer** to ChromaDB.
- The API's `/readyz` probe performs a non-blocking query confirming that the Chroma collection exists, contains at least one chunk (`collection.count() > 0`), and matches the runtime `EMBED_MODEL` pin.
- Manual re-indexing is triggered on-demand via:
  ```bash
  kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar
  ```
  with zero API downtime and zero pod restarts.

## Options Considered
1. **Indexing in API Pod Startup**: Rejected due to multi-writer PVC race conditions, startup probe timeouts, and compute waste on pod rescheduling.
2. **InitContainer in the API Pod Spec**: Rejected because InitContainers run on *every single replica startup*. With 3 replicas, three InitContainers would still compete to write the Chroma volume, and rolling updates would block indefinitely.
3. **Dedicated Indexer Service with HTTP Trigger**: Feasible, but keeps an idle container consuming cluster memory 24/7.
4. **Kubernetes Job / CronJob (Chosen)**: Allocates CPU/memory only while chunking and embedding, writes atomically, expires upon completion (exit code 0), and retries on failure via `backoffLimit: 3`.

## Consequences
- **Positive**:
  - Eliminated concurrent write races; Chroma data consistency is guaranteed.
  - Zero-downtime rolling updates on the API tier without re-indexing penalties.
  - Granular resource management: Indexer Job gets 1.5Gi memory limit to handle heavy PDF embedding, while API pods stay lightweight (512Mi).
- **Negative / Trade-offs**:
  - Requires maintaining separate Dockerfiles and image definitions (`rahbar-api` and `rahbar-indexer`).
  - Cache invalidation must be explicitly triggered when the Job completes so that newly indexed passages supersede cached answers.

