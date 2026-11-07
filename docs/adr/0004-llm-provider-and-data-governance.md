# ADR 0004: Pluggable LLM Provider Architecture and Data Governance

## Status
Accepted · 2026-11-06

## Context
Deploying an LLM on Kubernetes introduces significant trade-offs between resource consumption, model inference latency, operational complexity, and data privacy:
1. Running LLM weights inside the minikube cluster (`ollama-incluster`) requires at least 8 GB of RAM allocated to the virtual machine, which frequently overwhelms standard student developer workstations and leads to OOMKills.
2. Relying exclusively on commercial cloud APIs introduces API key leakage risks, cost, and transmits university policy inquiries to third-party endpoints.
3. Model hallucination and non-deterministic text generation threaten the core requirement of grounded question answering. A user must never receive ungrounded assertions or HTTP 500 errors caused by malformed JSON.

## Decision
1. **Pluggable Provider Architecture**: We isolate LLM interaction behind an abstract interface (`LLMProvider`) selectable at runtime via `LLM_PROVIDER` in the ConfigMap:
   - `stub`: Deterministic offline mock for CI/CD, unit testing, and early cluster bring-up.
   - `ollama-host` (Default): Connects from inside the cluster to Ollama running on the developer workstation via `http://host.minikube.internal:11434`. This provides fast local GPU acceleration with minimal cluster memory overhead.
   - `hosted`: Connects to OpenAI-compatible hosted endpoints (e.g., Groq, Google AI Studio) with credentials loaded strictly from a Kubernetes Secret.
2. **Credential Security**:
   - API keys are NEVER committed to version control. Committed manifests contain only `REPLACE_ME` placeholders.
   - Credentials are injected at runtime via Kubernetes Secrets created through the CLI:
     ```bash
     kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY="$LLM_API_KEY"
     ```
3. **Structured Schema Enforcement & Validation**:
   - We require constrained decoding (`format=Answer.model_json_schema()` on Ollama, `response_format={"type": "json_object"}` on hosted endpoints).
   - All model outputs are strictly validated using Pydantic (`Answer.model_validate_json`).
   - If validation fails, the system executes one automated retry with error feedback; if validation fails again, it falls back to a safe, deterministic canned response rather than returning an HTTP 500.
4. **Data Governance & Prompt Injection Defense**:
   - Retrieved passages are treated as untrusted user data. Passages are isolated in dedicated delimiters (`<<<EVIDENCE ... EVIDENCE>>>`) with explicit instructions forbidding the LLM from executing commands found within evidence text.

## Options Considered
1. **In-Cluster Ollama Deployment**: High operational overhead on minikube. Requires startup probes with `failureThreshold: 30` because weight loading takes minutes.
2. **Hardcoded Hosted Provider**: Discards local offline development capability and creates vendor lock-in.
3. **Pluggable Interface with Ollama-Host as Default (Chosen)**: Delivers lowest memory footprint on minikube while maintaining 100% code compatibility with hosted alternatives and stub-based CI testing.

## Consequences
- **Positive**:
  - Offline CI test suites execute in seconds using `StubProvider` without network requests.
  - Development cluster runs smoothly within standard 6 GB minikube memory boundaries.
  - Zero risk of committing API tokens to GitHub history.
- **Negative / Trade-offs**:
  - Requires developers running `ollama-host` to configure `OLLAMA_HOST=0.0.0.0` so host listening sockets are accessible from the minikube network bridge.

