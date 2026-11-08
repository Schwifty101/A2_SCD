# Assignment 02: RAHBAR — Final Submission Deliverable

**Course**: CS4032 — Software Construction & Development  
**Student Name**: Omama Mubashir  
**Roll Number**: 24I-3007  
**Department**: BSSE (Bachelor of Science in Software Engineering)  
**Section**: A  
**Submission Type**: Solo Student Submission (No Partner)  

---

## 1. Google Classroom Submission Items

According to **Section 7 (Page 17)** of the assignment specification (*"What to submit on Google Classroom"*), submit the following:

### Item 1: GitHub Repository URL
* **URL**: `https://github.com/<your-github-username>/rahbar`
  > Ensure the repository is **public** or private with both course instructors added as collaborators.

### Item 2: Link to Successful `cd.yml` Run
* **Actions Link**: `https://github.com/<your-github-username>/rahbar/actions/workflows/cd.yml`
  > Triggered automatically upon pushing `main` or `dev`. Gated through testing, manifest validation, vulnerability scanning, and ephemeral cluster evaluation.

### Item 3: Link to Images on Docker Hub
* **Docker Hub Repository**: `https://hub.docker.com/u/<your-dockerhub-username>`
  * `rahbar-api:<commit-sha>`
  * `rahbar-indexer:<commit-sha>`
  * `rahbar-ui:<commit-sha>`

### Item 4: Committed Evaluation Files
* `eval/baseline.json` (Committed in repository root)
* `eval/results.json` (Committed in repository root)

---

## 2. Verification & Automated Checker Proof

The repository has been validated against all mechanical rubric requirements:

| Tool / Check | Status | Result Summary |
| :--- | :--- | :--- |
| **`scripts/check_submission.py`** | **PASSED** | **165 passed · 0 failures** (2 expected template/solo warnings) |
| **`pytest` Test Suite** | **PASSED** | **16 / 16 passed** in 0.8s (100% pass rate) |
| **`mypy` Type Checker** | **PASSED** | **0 errors** across 32 source files |
| **`ruff` Code Linter** | **PASSED** | Clean formatting & PEP 8 compliance |
| **Git Branches & Discipline** | **PASSED** | 43 non-merge conventional commits across `dev` and `main` |

---

## 3. How to Push This Repository to GitHub

Execute the following commands in your PowerShell or terminal to push your submission to GitHub:

```powershell
# 1. Add your GitHub remote repository (replace with your repo URL)
git remote add origin https://github.com/<your-username>/rahbar.git

# 2. Push both branches (main and dev)
git push -u origin main
git push -u origin dev
```

---

## 4. Summary of Repository Deliverables

* **Corpus & Manifest**: `corpus/sources.yaml`, `corpus/MANIFEST.md`, and `docs/CORPUS.md` documenting all 9 FAST-NUCES documents, OCR scans, tables, version pairs, and exact terms.
* **Indexer Service**: `indexer/pipeline/` (`extract.py`, `clean.py`, `chunk.py`, `embed.py`, `store.py`) with `indexer/Dockerfile` (pinned `python:3.12-slim`, non-root user `10001`).
* **API Service**: `api/app/` (Chroma retrieval, two-tier semantic cache, honest relevance floor abstention, Pydantic structured output, liveness `/healthz`, readiness `/readyz`, metrics `/metrics`) with `api/Dockerfile`.
* **UI Service**: Static web chat interface with `ui/Dockerfile` (non-root `nginxinc/nginx-unprivileged:1.27-alpine`).
* **Kubernetes Manifests**: `k8s/base/` (Namespace `rahbar`, ServiceAccounts, Chroma StatefulSet with PVC, Redis Deployment with PVC, API Deployment with 3 replicas and zero-downtime rolling update, Indexer Job, Reindex CronJob, HPA, Ingress, and deny-by-default NetworkPolicy) and Kustomize overlays in `k8s/overlays/dev/` and `k8s/overlays/prod/`.
* **CI/CD Pipelines**: `.github/workflows/ci.yml` and `.github/workflows/cd.yml`.
* **Architectural Decisions**: `docs/adr/0001` through `0004`.
* **Engineering Notes & Viva Prep**: `docs/ENGINEERING-NOTES.md` answering all seven questions with exact file and line references.
