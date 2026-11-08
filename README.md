# RAHBAR: Grounded Question-Answering on Kubernetes

[![CI](https://github.com/omama-mubashir/rahbar/actions/workflows/ci.yml/badge.svg)](https://github.com/omama-mubashir/rahbar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://python.org)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.30%2B-blue.svg)](https://kubernetes.io)

**RAHBAR** is a grounded, schema-constrained question-answering system over statutory FAST-NUCES university policy documents. Built for production resilience on Kubernetes, it answers strictly from authoritative document evidence, cites specific policy clauses and pages, and abstains honestly when information is absent.

Developed by **Omama Mubashir** (Roll No: **24I-3007**, Department: **BSSE**, Section: **A**) — Solo Submission for CS4032 / Software Construction & Development.

---

## 1. System Architecture

RAHBAR enforces a strict **Single-Writer, Multi-Reader** separation between index ingestion and query serving:

```mermaid
flowchart TD
    User([User / Browser]) --> Ingress["Ingress (rahbar.local)"]
    Ingress -->|/api/*| APIService["Service: api (ClusterIP:8000)"]
    Ingress -->|/*| UIService["Service: ui (ClusterIP:8080)"]

    subgraph Namespace: rahbar
        subgraph Serving Tier
            APIService --> APIDeployment["Deployment: api (3 Replicas, HPA 3->8)"]
            UIService --> UIDeployment["Deployment: ui (2 Replicas, Non-Root)"]
        end

        subgraph Storage Tier
            ChromaDB[("StatefulSet: chroma (1 Replica, PVC: chroma-data)")]
            Redis[("Deployment: redis (1 Replica, PVC: redis-data)")]
        end

        subgraph Ingestion Tier
            IndexerJob["Job: indexer / CronJob: reindex (Weekly)"]
            Corpus[("Corpus / Fixtures (PDF, HTML, MD)")]
            Corpus --> IndexerJob
            IndexerJob -->|Exclusive Writer| ChromaDB
        end
    end

    APIDeployment -->|Read Only (superseded filter)| ChromaDB
    APIDeployment <-->|Semantic Cache Lookups| Redis
    APIDeployment -->|Generate JSON with Citations| LLMHost["LLM Provider (Ollama / Hosted API)"]
```

---

## 2. API Contract

The core API is served at `http://rahbar.local/api`:

| Method | Endpoint | Description | Contract / Behavior |
| :--- | :--- | :--- | :--- |
| POST | `/api/ask` | Primary question-answering endpoint | Accepts `{"question": "..."}` (3 to 500 characters). Returns grounded `AskResponse` with citations and retrieved passages. |
| GET | `/healthz` | Process Liveness Probe | Returns `{"status": "alive"}`. Touches no external dependencies to prevent cascade restart storms. |
| GET | `/readyz` | Readiness Probe | Returns `200` only if Chroma is reachable, collection is non-empty (`count() > 0`), Redis is reachable, and the embedding pin matches `EMBED_MODEL`. Returns `503` otherwise. |
| GET | `/metrics` | Prometheus Metrics Endpoint | Exposes request latency, retrieval latency, generation latency, cache hit ratios, abstention counts, and token counts. |

---

## 3. Cluster Setup and Minikube Instructions

Start minikube using Docker and Calico CNI (required for NetworkPolicy enforcement):

```bash
# 1. Start minikube with Calico CNI and adequate resources
minikube start --driver=docker --cni=calico --memory=6144 --cpus=4

# 2. Enable essential addons
minikube addons enable metrics-server
minikube addons enable ingress

# 3. Pull required Ollama models on your host workstation (default: ollama-host)
OLLAMA_HOST=0.0.0.0 ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

---

## 4. Exact Kubernetes Manifest Apply Order

To deploy from a clean clone without dependency race conditions:

```bash
# Step 1: Create the namespace
kubectl apply -f k8s/base/namespace.yaml

# Step 2: Create ServiceAccounts and RBAC
kubectl apply -f k8s/base/serviceaccounts.yaml

# Step 3: Create the ConfigMap
kubectl apply -f k8s/base/configmap.yaml

# Step 4: Create the Secret from the command line (NEVER commit real keys)
kubectl create secret generic rahbar-secret -n rahbar \
  --from-literal=LLM_API_KEY="${LLM_API_KEY:-dev-dummy-key}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Step 5: Deploy data tier (Chroma StatefulSet and Redis Cache)
kubectl apply -f k8s/base/chroma-statefulset.yaml
kubectl apply -f k8s/base/redis.yaml

# Step 6: Deploy serving tier and routing
kubectl apply -f k8s/base/api.yaml
kubectl apply -f k8s/base/ui.yaml
kubectl apply -f k8s/base/ingress.yaml
kubectl apply -f k8s/base/hpa.yaml
kubectl apply -f k8s/base/networkpolicy.yaml

# Alternatively, apply everything at once via Kustomize:
kubectl apply -k k8s/overlays/dev
```

---

## 5. How to Run the Indexer

Indexing must NEVER run on API startup. To build or update the vector index:

```bash
# Method A: Trigger an on-demand re-indexing Job from the CronJob template
kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar

# Method B: Run the standalone indexer Job manifest
kubectl apply -f k8s/base/indexer-job.yaml

# Watch the indexer progress
kubectl logs -l app.kubernetes.io/name=indexer -n rahbar -f
```

---

## 6. Local Development and Testing (Offline)

Run without a cluster or external models using stubs:

```bash
# Install dependencies into virtualenv
python -m venv .venv
.venv/Scripts/pip install -r api/requirements-dev.txt -r indexer/requirements-dev.txt

# Run the 16 unit tests (including prompt injection and abstention)
python -m pytest

# Run linter and typechecker
ruff check api indexer eval corpus
mypy api/app indexer/pipeline

# Verify submission requirements
python scripts/check_submission.py
```
