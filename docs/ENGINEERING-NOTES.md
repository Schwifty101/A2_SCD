# Engineering Notes: Seven Questions on Production RAG Architecture

Author: Omama Mubashir (Solo Submission)  
Repository: `omama-mubashir/rahbar`

---

## 1. Indexing in API Startup: What Breaks with 3 Replicas and One Chroma Volume?

### The Failure
If vector indexing is invoked during API startup (e.g., inside FastAPI's startup hook or `lifespan` in [main.py](file:///d:/Assignments/SCD/Assignment2/api/app/main.py#L28-L44)), booting 3 API replicas causes a catastrophic **Concurrent Multi-Writer Volume Race Condition**.
Because ChromaDB persists vectors to a single directory (SQLite database file and HNSW binary indexes) mounted over a shared PersistentVolumeClaim, three separate processes concurrently open write transactions, chunk documents, and attempt to write embeddings into the same database files simultaneously. This leads to SQLite database locking errors (`sqlite3.OperationalError: database is locked`), corrupted indices with torn page writes, and non-deterministic chunk duplications. Furthermore, every subsequent pod restart (caused by an OOM blip or rolling update) triggers full re-indexing, stalling readiness across all replicas.

### The Object That Prevents It
We prevent this architectural flaw by decoupling indexing into a dedicated, one-shot Kubernetes **Job** ([indexer-job.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/indexer-job.yaml#L2-L47)) and scheduled **CronJob** ([reindex-cronjob.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/reindex-cronjob.yaml#L2-L49)).
The API deployment contains zero indexing logic; its container image runs purely in read-only query mode. In the API deployment manifest ([api.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/api.yaml#L56-L61)), the read-only operational boundary is enforced at line 58 (`readOnlyRootFilesystem: true`), while the indexer Job is the sole entity with batch write capability.

---

## 2. Readiness and Liveness Swapped, Chroma Slow for 90 Seconds: What Happens?

### The Failure Cascade (Restart Storm)
- **Liveness Probe**: Asks *"Is the process healthy and responsive?"* If it fails, the kubelet kills the container and initiates a restart.
- **Readiness Probe**: Asks *"Can this container currently accept user traffic?"* If it fails, the container is temporarily withheld from the Service endpoints without being restarted.

If the probes are swapped (wiring `livenessProbe -> /readyz` and `readinessProbe -> /healthz`):
When ChromaDB experiences a 90-second latency spike (e.g., during heavy index serialization or disk I/O contention), `/readyz` returns `HTTP 503` or times out. Because the liveness probe is incorrectly watching this endpoint, the kubelet interprets Chroma's transient slowness as a fatal process crash in the API container.
The kubelet immediately kills the API pod. When the replacement pod boots up, it connects to Chroma, which is still busy; the probe fails again, and the pod is killed again. All 3 replicas enter a simultaneous, cluster-wide **CrashLoopBackOff restart storm**. Live user requests are dropped, and an issue that was merely high retrieval latency escalates into complete service unavailability.

In our implementation ([api.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/api.yaml#L68-L82) and [health.py](file:///d:/Assignments/SCD/Assignment2/api/app/routes/health.py#L19-L23)):
- `livenessProbe` checks `/healthz`, which only inspects internal Python process health and touches zero external dependencies.
- `readinessProbe` checks `/readyz`, safely isolating slow pods from the Service without triggering destructive restarts.

---

## 3. What Does a CPU-Based HPA Actually Measure on a Generation Service, and What Should Scale It?

### The 8% Paradox
During question answering, the API pod's CPU utilization remains remarkably low (averaging 8% to 15%), as seen in `kubectl top pods`:
```text
NAME                     CPU(cores)   MEMORY(bytes)
api-79b88cfbb8-4f8x2     14m          84Mi
```
Generation is fundamentally an **I/O-bound operation** from the perspective of the API pod. The API process spends 95% of its wall-clock latency awaiting network responses over HTTP from the LLM inference server (Ollama or hosted GPU providers). Because the API pod's CPU is idle in `epoll_wait` while awaiting tokens, a CPU-based HorizontalPodAutoscaler ([hpa.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/hpa.yaml#L1-L24)) measuring `averageUtilization: 70%` will **never trigger a scale-up**, even if 50 concurrent student queries are queued and response latency degrades from 1 second to 45 seconds.

### The Signal That Should Scale It
A generation service should scale on **Concurrent In-Flight Requests (Queue Depth / HTTP Concurrency)** or **P95 Request Latency**.
To implement this in production, one would deploy the Prometheus Adapter (`k8s-prometheus-adapter`) to expose custom Kubernetes metrics from our `/metrics` endpoint ([metrics.py](file:///d:/Assignments/SCD/Assignment2/api/app/routes/metrics.py#L18-L32)), configuring the HPA to scale out when `http_requests_in_flight > 10` per pod.

---

## 4. The Indexer's Peak Memory, Limit, Margin, and Exit Code When Wrong

### Real Resource Numbers from `kubectl top`
Measured during full indexing of the 9 FAST-NUCES corpus documents (>170 pages):
```text
$ kubectl top pods -n rahbar
NAME                     CPU(cores)   MEMORY(bytes)
indexer-manual-49xkl     342m         788Mi
```
- **Peak Memory Observed**: `788 MiB`
- **Configured Request**: `512 MiB` ([indexer-job.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/indexer-job.yaml#L38-L42))
- **Configured Limit**: `1536 MiB` (1.5 GiB)
- **Safety Margin**: $\frac{1536}{788} \approx 1.95\times$ (~95% headroom above peak).

### What Happens If Set Wrong
If the indexer's memory limit is set below ~750 MiB (e.g. 512 MiB), extracting multi-page PDF DOM trees and generating 768-dimensional vector batches exceeds the cgroup memory threshold. The Linux kernel OOM-killer terminates the process with **Exit Code 137** (`128 + SIGKILL (9)`). The pod enters `CrashLoopBackOff`, and the Kubernetes Job fails after exhausting its `backoffLimit: 3`.

---

## 5. recall@5 by Question Type: Where Is It Worst, and Why?

### Empirical Results from Golden Evaluation (`eval/results.json`)
- **Ordinary Answerable Questions**: `recall@5 = 1.0000` (100%)
- **Version-Sensitive Questions**: `recall@5 = 1.0000` (100%)
- **Prompt Injection Probes**: `recall@5 = 1.0000` (100%)
- **Exact-Term Questions**: `recall@5 = 0.7500` (75.0%)

### Why Embeddings Struggle on Exact Terms
Exact-term retrieval (`0.7500`) is visibly worse than definitional retrieval (`1.0000`).
Dense embedding models (such as `nomic-embed-text`) project sentences into continuous semantic manifold representations. In semantic space, phrases like *"attendance requirement"*, *"minimum lecture percentage"*, and *"mandatory classroom presence"* cluster tightly together. However, exact numerical markers—such as Clause `"1.21"`, course code `"CS3001"`, and CGPA threshold `"2.00"`—carry negligible semantic weight compared to the surrounding vocabulary. Dense embeddings blur specific tokens with syntactically similar numbers (e.g., Clause 1.21 vs Clause 1.22).

### The Technique That Addresses It
The AI Engineering lecture identified **Hybrid Retrieval (Dense Semantic Embedding + Sparse Lexical BM25 Search)** combined with **Cross-Encoder Re-ranking**. BM25 guarantees that exact tokens (clause identifiers, course codes, and monetary figures) receive high lexical match scores, while dense embeddings capture conceptual semantic similarity. Reciprocal Rank Fusion (RRF) merges the candidate lists to eliminate exact-term retrieval blindspots.

---

## 6. EMBED_MODEL Changed in ConfigMap and Only API Restarted: What Happens?

### What Our System Does (The Guardrail)
When an operator updates `EMBED_MODEL` in [configmap.yaml](file:///d:/Assignments/SCD/Assignment2/k8s/base/configmap.yaml#L14) from `nomic-embed-text` to another model (e.g. `all-minilm`) and restarts the API deployment:
1. During pod startup, the API initializes the Chroma client in [health.py](file:///d:/Assignments/SCD/Assignment2/api/app/routes/health.py#L48-L62).
2. It fetches collection metadata written by the indexer (`indexed_model = collection.metadata["embed_model"]`).
3. Comparing `indexed_model != settings.embed_model`, the guardrail triggers:
   ```json
   {"logger": "rahbar.health", "level": "ERROR", "msg": "Embedding pin guardrail conflict - mismatch: collection was indexed with nomic-embed-text but runtime EMBED_MODEL is all-minilm"}
   ```
4. The `/readyz` probe immediately responds with `HTTP 503 Service Unavailable`.
5. Kubernetes detects the failed readiness probe and withholds the pod from the Service endpoints. `kubectl get pods -n rahbar` shows `0/1 READY (Running)`. Zero user requests are sent to the mismatched pod.

### What It Would Have Done Without the Guardrail
Without this programmatic guardrail, the API would have booted into `1/1 READY`. When a student asked a question, the API would embed the query into a 384-dimensional vector and submit it to Chroma, which holds 768-dimensional vectors (or, if dimensions matched, vectors trained on different semantic coordinate spaces). Cosine distance calculations would return completely arbitrary, nonsense passages. The LLM would confidently generate incorrect policy answers citing unrelated clauses. The failure would be **completely silent**: zero exceptions, zero HTTP 500 errors, and total factual breakdown.

---

## 7. The Failure That Cost More Than an Hour

### The Symptoms
During initial testing of the submission checker script ([check_submission.py](file:///d:/Assignments/SCD/Assignment2/scripts/check_submission.py#L1-L260)), running `python scripts/check_submission.py` hung indefinitely without output, eventually failing with a 60-second subprocess timeout.

### What Was Wrongly Believed First
I initially believed that the Python script was freezing while recursively walking the large PDF binary files in `corpus/raw/` or getting stuck in a CPU-bound regex loop across `rglob("*")`. I spent over an hour profiling directory exclusion paths in `SKIP` and attempting to optimize `os.walk` calls.

### The Truth Revealed by Command Diagnosis
Running `git` commands individually in PowerShell revealed the true culprit:
```powershell
$ git shortlog -sn --all --no-merges
```
The command sat blocking indefinitely, waiting for user input on `stdin`!
In Git, when a repository is freshly initialized (`git init`) and has zero commits, `git shortlog` defaults to reading revisions from standard input. In [check_submission.py](file:///d:/Assignments/SCD/Assignment2/scripts/check_submission.py#L63), `subprocess.run(["git", *args], capture_output=True, timeout=60)` did not pass `stdin=subprocess.DEVNULL`. Consequently, `git shortlog` hung waiting for stdin until the 60-second timeout expired!
The immediate solution was creating the initial commit: once Git history contains at least one revision, `git shortlog` parses commits directly from `.git` and exits in 20 milliseconds.
