# RAHBAR starter Makefile. `make` or `make help` lists the targets.
# Targets marked (needs yours) work once you have written the Dockerfiles or manifests.

SHELL := /bin/bash
NS ?= rahbar
TAG ?= dev
PY ?= python3
VENV ?= .venv
BIN := $(abspath $(VENV))/bin
# The Ingress address. On Linux this is the minikube IP. On macOS or Windows with the
# docker driver, run `minikube tunnel` in another terminal and use INGRESS_IP=127.0.0.1.
INGRESS_IP ?= $(shell minikube ip 2>/dev/null)
HOST ?= rahbar.local

.DEFAULT_GOAL := help
.PHONY: help install test lint dev cluster images apply secret corpus index ask fetch eval eval-fixtures check

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

install: ## create .venv and install the api, indexer and tool dependencies
	$(PY) -m venv $(VENV)
	"$(BIN)/pip" install -q --upgrade pip
	"$(BIN)/pip" install -q -r api/requirements-dev.txt -r indexer/requirements-dev.txt

test: ## run the api and indexer tests (stubs only: no cluster, no model, no network)
	cd api && "$(BIN)/pytest" -q
	cd indexer && "$(BIN)/pytest" -q

lint: ## ruff and mypy over everything in Python
	"$(BIN)/ruff" check api indexer eval corpus
	cd api && "$(BIN)/mypy" app
	cd indexer && "$(BIN)/mypy" pipeline

dev: ## run the API with stubs on http://localhost:8000, serving the chat UI too
	cd api && SERVE_UI_DIR=../ui RETRIEVER=stub LLM_PROVIDER=stub "$(BIN)/uvicorn" app.main:app --reload --port 8000

cluster: ## start minikube with Calico, then enable metrics-server and ingress
	minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
	minikube addons enable metrics-server
	minikube addons enable ingress

images: ## build the three images and load them into minikube (needs yours: Dockerfiles)
	docker build -t rahbar-api:$(TAG) api
	docker build -t rahbar-indexer:$(TAG) indexer
	docker build -t rahbar-ui:$(TAG) ui
	minikube image load rahbar-api:$(TAG)
	minikube image load rahbar-indexer:$(TAG)
	minikube image load rahbar-ui:$(TAG)

apply: ## apply the dev overlay (needs yours: manifests)
	kubectl apply -k k8s/overlays/dev

secret: ## create rahbar-secret from LLM_API_KEY, or GROQ_API_KEY in .env; never from a committed file
	@set -a; [ -f .env ] && . ./.env; set +a; K="$${LLM_API_KEY:-$$GROQ_API_KEY}"; \
	  test -n "$$K" || { echo "export LLM_API_KEY=... (or put GROQ_API_KEY in .env) first"; exit 1; }; \
	  kubectl create secret generic rahbar-secret -n $(NS) --from-literal=LLM_API_KEY="$$K" \
	    --dry-run=client -o yaml | kubectl apply -f -

corpus: ## copy corpus/raw (from `make fetch`) into the corpus PVC read by the indexer
	kubectl run corpus-loader -n $(NS) --image=busybox:1.37 --restart=Never \
	  --overrides='{"spec":{"containers":[{"name":"corpus-loader","image":"busybox:1.37","command":["sleep","600"],"volumeMounts":[{"name":"c","mountPath":"/corpus"}]}],"volumes":[{"name":"c","persistentVolumeClaim":{"claimName":"corpus-data"}}]}}'
	kubectl wait -n $(NS) --for=condition=Ready pod/corpus-loader --timeout=120s
	kubectl cp corpus/raw/. $(NS)/corpus-loader:/corpus
	kubectl delete pod corpus-loader -n $(NS) --now

index: ## run the indexer once, from the CronJob's template (needs yours: CronJob reindex)
	kubectl create job --from=cronjob/reindex reindex-$$(date +%s) -n $(NS)
	@echo "watch it with: kubectl get jobs -n $(NS) -w"

ask: ## ask through the Ingress: make ask Q="What CGPA puts a student on academic warning?"
	@curl -s -X POST "http://$(INGRESS_IP)/api/ask" -H "Host: $(HOST)" \
	  -H 'Content-Type: application/json' -d "$$(Q="$(Q)" $(PY) -c 'import json,os; print(json.dumps({"question": os.environ["Q"]}))')" \
	  | $(PY) -m json.tool

fetch: ## download the documents listed in corpus/sources.yaml
	"$(BIN)/python" corpus/fetch.py

eval: ## score eval/golden.yaml through the Ingress and apply the CI gate
	"$(BIN)/python" eval/run_eval.py --api "http://$(INGRESS_IP)" --host $(HOST)

eval-fixtures: ## score the CI fixture golden set against a local `make dev`
	"$(BIN)/python" eval/run_eval.py --api http://localhost:8000 --golden eval/fixtures/golden.fixture.yaml --out /tmp/rahbar-fixture-results.json

check: ## run the submission checker
	$(PY) scripts/check_submission.py
