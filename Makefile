# Quoteline. Targets are added as each checkpoint lands; nothing here is a placeholder.
SHELL := /bin/bash
# Homebrew on Apple Silicon is not on PATH in non-login shells. Recipes run through the shell
# (cd x && ...) so that this PATH is the one used to find uv and npm.
export PATH := /opt/homebrew/bin:$(PATH)

.PHONY: help setup seed inbox ingest check-a check-c api web test

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install backend (uv, Python 3.12) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm install

seed: ## Regenerate the RFx, the five vendor replies, attachments and golden set (deterministic)
	cd backend && uv run python ../data/gen/seed.py

inbox: ## Drop the five seeded vendor replies into mail/inbox/<vendor>/ (the email stub)
	cd backend && uv run python -m app.cli load-rfx && uv run python -m app.cli deliver

ingest: ## Read everything in the inbox with both models (live calls, about 4 minutes)
	cd backend && uv run python -m app.cli ingest

check-c: ## Checkpoint C: score the stored extractions and flags against the golden set
	cd backend && uv run python -m app.eval.checkpoint_c

check-a: ## Checkpoint A: one live traced call per role across both providers
	cd backend && uv run python -m app.llm.check

api: ## Run the FastAPI backend on :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web: ## Run the Vite frontend on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test: ## Backend tests and lint, frontend typecheck, lint and build
	cd backend && uv run ruff check . && uv run pytest -q
	cd frontend && npm run lint && npm run build
