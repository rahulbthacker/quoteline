# Quoteline

A working prototype for "Kill the Quote Spreadsheet": one flow, end to end, for corrugated
packaging. A buyer drafts an RFx with a co-pilot, sends it, takes vendor replies in any
format, compares them in one grid with every number traceable to its source, resolves what is
uncertain, asks questions in plain language, and produces an award a VP can sign.

- `docs/NOTE.md`: the one-page decisions note
- `docs/DESIGN.md`: architecture, the 13 design questions, traceability to the brief, decision log
- `docs/EVAL.md`: measured accuracy against the golden set
- `docs/WALKTHROUGH.md`: the demo script
- `CLAUDE.md`: the build brief

## Run it

You need macOS or Linux with [uv](https://docs.astral.sh/uv/), Node 20 or later, and `make`.
uv installs Python 3.12 for you.

```bash
cp .env.example .env    # then add ANTHROPIC_API_KEY and GEMINI_API_KEY
make demo
```

`make demo` installs dependencies, sends the RFx (five .eml files in `mail/outbox/`), drops
the five vendor replies into `mail/inbox/`, reads them live with Claude Opus 5.5 and Gemini
3.1 Pro, builds the frontend and opens http://localhost:8000 on the Compare screen. It takes
about two minutes and about ₹170 of model spend. There is no offline mode: without keys the
calls fail and say so.

## Commands

| Command | What it does | Model calls |
|---|---|---|
| `make demo` | Everything above, from a clean state | yes |
| `make serve` | Serve the app again without resetting or re-reading | no |
| `make test` | 92 backend tests, lint, frontend type-check and build | no |
| `make seed` | Regenerate the RFx, the five replies and the golden set (byte-deterministic) | no |
| `make check-a` | One traced call per role on both providers | yes |
| `make check-c` | Score the stored extraction and flags against the golden set | no |
| `make check-e` | Ask the analyst six questions and check them against the award engine | yes |
| `make eval` | Re-read the five replies, score them, run the judge, write `docs/EVAL.md` | yes |
| `make api` / `make web` | Development servers on :8000 and :5173 | no |
| `make reset` | Delete all state: database, snapshots, inbox, outbox | no |

## What is real and what is stubbed

Everything a model appears to do, it does, live, at request time: routing, extraction by two
models, line-match tie-breaks, questionnaire evaluation, clarification emails, the intake
co-pilot, the analyst. The only stub is email transport: "send" writes an .eml file to
`mail/outbox/`, and "receive" reads files dropped into `mail/inbox/<vendor>/`.

The five vendor replies in `data/replies/` are real files (xlsx, pdf, docx, jpg, eml) written
by the scripts in `data/gen/`, each broken in a specific way. The same scripts write
`data/golden/`, which is used only to score results.

## Layout

```
backend/app/agents/      router, extractor, evaluator, analyst, intake, clarifier
backend/app/services/    parsers, line matcher, normalisation, validation, grid, review,
                         award, sandbox, quote table, export, mail stub
backend/app/llm/         provider clients, gateway with tracing and fallback, prompt registry
backend/app/prompts/     versioned prompt files
backend/app/eval/        golden loader, harness, checkpoint gates, eval report
backend/config/          conversion table and category template (editable)
frontend/src/routes/     draft, sent, responses, compare, review, analyse, award, settings
data/gen/                dataset generators       data/golden/   truth per vendor
data/replies/            the five vendor replies  mail/          inbox and outbox (stub)
```
