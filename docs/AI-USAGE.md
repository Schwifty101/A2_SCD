# AI Usage Disclosure

**Student**: Omama Mubashir (Roll No: **24I-3007**, Department: **BSSE**, Section: **A**) — Solo Submission  
**Course**: CS4032 Software Construction & Development — Assignment 02: RAHBAR

In accordance with Section 8 of the course policy, this document provides an honest, comprehensive disclosure of the AI tools utilized throughout the design, implementation, and evaluation of this assignment.

---

## Tool Disclosure Summary

| Tool | What It Wrote or Shaped | What I Changed Afterwards, and Why |
| :--- | :--- | :--- |
| **Google Antigravity Agent (Gemini 3.8 Flash)** | • Initial boilerplate drafting for K8s manifests (`k8s/base/`)<br>• Regex drafting for PDF/HTML cleaning in `clean.py`<br>• Pydantic schema validation structures in `ollama.py` & `hosted.py`<br>• Structure-aware chunking skeleton in `chunk.py`<br>• GitHub Actions workflow skeleton (`ci.yml`, `cd.yml`) | • Rewrote readiness probe logic in `health.py` to ensure strict non-empty Chroma collection validation and embedding-pin comparison.<br>• Tuned chunk size from 250 to 400 tokens and overlap to 50 based on empirical `recall@5` measurements.<br>• Added explicit non-root user IDs (`10001`, `101`) and security contexts (`readOnlyRootFilesystem: true`, capabilities drop `ALL`).<br>• Configured NetworkPolicy to strictly forbid UI pods from communicating with ChromaDB.<br>• Implemented safe fallback responses to guarantee zero HTTP 500 errors on invalid LLM JSON outputs. |
| **GitHub Copilot / IDE autocomplete** | • Standard Python type annotations and boilerplate docstrings across `api/` and `indexer/`. | • Verified all imports and type hints manually to ensure compatibility with Python 3.12/3.14 and strict `mypy` typechecking. |

---

## Solo Developer Statement

I am completing this assignment individually as a solo student. All architectural trade-offs, Kubernetes manifests, retrieval measurements, failure mode analyses, and code implementations have been authored, tested, verified, and understood by me.
