# Quoteline. Targets are added as each checkpoint lands; nothing here is a placeholder.
SHELL := /bin/bash
# Homebrew on Apple Silicon is not on PATH in non-login shells. Recipes run through the shell
# (cd x && ...) so that this PATH is the one used to find uv and npm.
export PATH := /opt/homebrew/bin:$(PATH)
PORT ?= 8000

.PHONY: help setup demo serve rehearse seed reset send inbox ingest check-a check-c check-e eval video voice voiced api web test

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

demo: setup ## One command: seed state, send the RFx, receive and read the five replies, open the UI
	@test -f .env || { echo "Create .env from .env.example with ANTHROPIC_API_KEY and GEMINI_API_KEY first."; exit 1; }
	cd backend && uv run python -m app.cli reset
	cd backend && uv run python -m app.cli send
	cd backend && uv run python -m app.cli deliver
	cd backend && uv run python -m app.cli ingest
	cd frontend && npm run build --silent
	cd backend && uv run python -m app.cli serve --open --port $(PORT)

serve: ## Serve the API and the built frontend on http://localhost:8000 (no reset, no model calls)
	cd frontend && npm run build --silent
	cd backend && uv run python -m app.cli serve --open --port $(PORT)

rehearse: ## Undo every human decision (review, overrides, scenarios, award) but keep the readings
	cd backend && uv run python -m app.cli clear-decisions

setup: ## Install backend (uv, Python 3.12) and frontend (npm) dependencies
	cd backend && uv sync --quiet
	cd frontend && npm install --silent --no-audit --no-fund

seed: ## Regenerate the RFx, the five vendor replies, attachments and golden set (deterministic)
	cd backend && uv run python ../data/gen/seed.py

reset: ## Delete all app state: database, snapshots, inbox and outbox
	cd backend && uv run python -m app.cli reset

send: ## Send the RFx to the five vendors (the email stub writes .eml files to mail/outbox)
	cd backend && uv run python -m app.cli send

inbox: ## Drop the five seeded vendor replies into mail/inbox/<vendor>/ (the email stub)
	cd backend && uv run python -m app.cli load-rfx && uv run python -m app.cli deliver

ingest: ## Read everything in the inbox with both models (live calls, about 4 minutes)
	cd backend && uv run python -m app.cli ingest

check-c: ## Checkpoint C: score the stored extractions and flags against the golden set
	cd backend && uv run python -m app.eval.checkpoint_c

check-e: ## Checkpoint E: ask the analyst six questions live and check them against the award engine
	cd backend && uv run python -m app.eval.checkpoint_e

eval: ## Full eval: re-read the five replies live, then score against golden and run the judge
	cd backend && uv run python -m app.cli load-rfx && uv run python -m app.cli deliver && uv run python -m app.cli ingest && uv run python -m app.eval.report --doc

video: ## Record the silent walkthrough video from the running app (run `make rehearse` and `make serve` first)
	cd tools/walkthrough && npm install --silent --no-audit --no-fund && npx playwright install chromium
	cd backend && uv run python -m app.cli clear-decisions
	cd tools/walkthrough && node record.mjs
	cd backend && uv run python ../tools/walkthrough/render.py

voice: ## Add deliverables/voiceover.m4a to the walkthrough video
	@test -f deliverables/voiceover.m4a || { echo "Save your recording as deliverables/voiceover.m4a first."; exit 1; }
	ffmpeg -loglevel error -y -i deliverables/quoteline-walkthrough.mp4 -i deliverables/voiceover.m4a -map 0:v -map 1:a -c:v copy -c:a aac -b:a 160k deliverables/quoteline-walkthrough-voiced.mp4
	@echo "Written: deliverables/quoteline-walkthrough-voiced.mp4"

voiced: ## Stitch the narration clips in deliverables/voice/ onto the walkthrough video
	cd backend && uv run python ../tools/walkthrough/voice.py

check-a: ## Checkpoint A: one live traced call per role across both providers
	cd backend && uv run python -m app.llm.check

api: ## Run the FastAPI backend on :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web: ## Run the Vite frontend on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test: ## Backend tests and lint, frontend typecheck, lint and build
	cd backend && uv run ruff check . && uv run pytest -q
	cd frontend && npm run lint && npm run build
