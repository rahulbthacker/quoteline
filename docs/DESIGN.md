# Quoteline design

How the system answers the brief, where each requirement lives, and why each decision was made.
Read `NOTE.md` for the one-page version and `EVAL.md` for the measured results.

## 1. Architecture in one picture

```
 mail/inbox/<vendor>/                    (the only stub: email is a folder)
        │
        ▼
  parsers ── every value gets an address: sheet!cell, page, paragraph, email line
        │
        ▼
  router (Claude Haiku) ── quote | questionnaire | certificate | MSDS | spec sheet; needs vision?
        │
        ├──────────────► extractor, Claude Opus 5.5 ─┐   raw value, verbatim unit, currency,
        ├──────────────► extractor, Gemini 3.1 Pro ──┤   snippet, locator, conditions. No conversion.
        └──► evaluator (questionnaire verdicts with evidence)
                                                     ▼
  line matcher (deterministic; Haiku only breaks ties) ── row → RFx line
                                                     ▼
  source check (no model) ── is the value really at the cited place in the file?
                                                     ▼
  validation ── agreement, ambiguity, conditions, missing freight, outliers → flags
                                                     ▼
  normalisation (conversion table, RFx weights, FX policy) ── ₹ per 1,000, with every step recorded
                                                     ▼
  GRID  5 × 30 cells: confident | needs_review | not_quoted | overridden   +  review items with options
        │                         ▲
        │                         └── decisions (resolve, override, exclude, ask vendor), all audited
        ▼
  DuckDB snapshot of counted cells ──► analyst: plan → SQL in sandbox → answer from rows → figure check
        ▼
  award engine ── allocation by rule, exclusions and what they cost, open items block approval
```

Backend: FastAPI, SQLite (state), DuckDB (analyst), Pydantic everywhere. Frontend: Vite, React 18,
Tailwind v4 on the design tokens, TanStack Table and Query, Radix primitives, Recharts.
Every model call goes through one gateway that retries once, walks a per-role fallback chain
and writes a trace row for every attempt.

## 2. The 13 questions this design had to answer

| # | Question | Answer | Where |
|---|---|---|---|
| 1 | What is the unit of trust? | The cell. Each one carries its state, both readings, the source and the arithmetic. | `services/grid.py`, provenance popover |
| 2 | Who reads the files? | Two models from different families, independently. Image reads lead with Gemini, text with Claude. | `agents/extractor.py`, `services/ingest.py` |
| 3 | How do we know a reading is real? | Code checks the value is at the cited place in the file. Photos cannot be checked, so they rely on agreement. | `agents/extractor.py: verify_source` |
| 4 | Who does the arithmetic? | Code, from an editable conversion table, the RFx board weights and the FX policy. A model never converts. | `services/normalization.py`, `config/conversion_table.yaml` |
| 5 | How does a row find its RFx line with no template? | A deterministic specification score, one-to-one; a model only breaks ties; below a floor the row is flagged. | `services/line_matcher.py` |
| 6 | What happens when something is uncertain? | It becomes a state. The cell shows a provisional value, is flagged, and is out of every total until resolved. | `services/validation.py`, `services/grid.py` |
| 7 | What does silence mean? | Not quoted. Never zero, never blank, never estimated. | grid cell state, Compare |
| 8 | What happens to conditions? | Reported verbatim, never applied by a model. Each becomes a review item with every reading computed. | `validation._discount_flag`, `grid._options` |
| 9 | How does a person resolve something? | Pick a computed option, type a value with a reason, exclude, or have a clarification email drafted. All audited, all reversible. | `services/review.py`, `agents/clarifier.py` |
| 10 | How is quality judged? | A model gives a verdict per question with verbatim evidence; the Pass, Partial, Fail rule is code; an evaluator can override with a reason. | `agents/evaluator.py`, `grid.quality_result` |
| 11 | How can a VP ask anything and trust the answer? | One SQL query, sandboxed, on a snapshot of counted cells. Figures in the answer are checked against the rows. Exclusions are stated by code. Unanswerable questions are declined. | `agents/analyst.py`, `services/sandbox.py` |
| 12 | What makes an award defensible? | An engine, not a model: rules, exclusions and their cost, like-for-like comparisons, an audit log, and approval blocked while anything is open. | `services/award.py`, Award screen |
| 13 | How do we know it works? | A golden set written by the same generator as the files, an eval harness, and a trace of every call. | `app/eval/`, `docs/EVAL.md`, Run inspector |

## 3. Traceability to the brief

| Req | Requirement | Where it is met | How it was verified |
|---|---|---|---|
| R1 | Buyer drafts RFx conversationally | Draft screen, co-pilot tab; `agents/intake.py`; `POST /rfx` | Live: the sample buyer notes produced 30 lines matching the seeded RFx on every stated field; it left the two partition GSMs blank and listed them as missing |
| R2 | RFx goes out over a channel | `POST /rfx/{id}/send`; Sent screen | `make send` writes five .eml files with the template attached and logs them |
| R3 | Vendors reply in any format | `services/parsers.py`; mail stub inbox | xlsx, pdf, docx, jpg and eml all ingested; nothing rejects a reply for ignoring the template |
| R4 | System reads every response | Dual extraction; Responses screen, "Raw beside extraction" | `make check-c`: all five extracted by both models |
| R5 | One comparison, same lines, units, currency | `GET /rfx/{id}/grid`; Compare screen with Normalised and Raw views | `tests/test_grid.py`: 150 cells, golden states and values |
| R6 | Questionnaire and attachments alongside | Quality pill in every vendor header; Attachments; evaluator evidence | Verdicts match golden on 40 of 40 |
| R7 | NL analysis: text, tables, charts, exports | Analyse screen; `POST /rfx/{id}/analyse`; XLSX and CSV export | `make check-e`: six questions checked against the award engine |
| R8 | Real analysis to a defensible award | `services/award.py`; Award screen | `tests/test_award_and_sandbox.py`, `tests/test_api.py` (approval blocked while items are open) |
| R9 | Demo scale, credible data | `data/gen/`: 5 vendors, 30 lines, 8 questions, 3 attachments | `tests/test_dataset.py`; prices from a board-weight model |
| R10 | Stubbed plumbing, real AI loops | Only `services/mail_stub.py` is a stub | grep finds no simulated path; a missing key fails loudly and is traced |
| R11 | Ugly edges handled and shown | Photo, 27 of 30, USD, per-box, footnote each raise a review item with options | `make check-c`: every vendor raises exactly its expected flags |
| R12 | Trust at ₹4 crore | Provenance on every cell, dual-model agreement, assumptions bar, audit log, eval report | Source check tests; eval report in the Run inspector |
| R13 | Judgment stated | `docs/NOTE.md` | |
| R14 | Deliverables | `make demo`; `docs/WALKTHROUGH.md`; `docs/NOTE.md` | Fresh clone reached Compare in 126 seconds |
| R15 | The better problem | Closing section of `docs/NOTE.md` | |

## 4. Decision log

### Platform (Checkpoint A)

| # | Decision | Why |
|---|---|---|
| D1 | Every model call goes through `app/llm/gateway.call()`. | One place to enforce tracing, the retry-once rule and the per-role fallback chain. |
| D2 | SDK-level retries are switched off (`max_retries=0`); the gateway retries. | SDK retries are invisible. A retried call that is not traced breaks non-negotiable 7. |
| D3 | A call whose output fails its Pydantic schema is a failed call. | "LLMs propose, code decides" starts with refusing malformed proposals. |
| D4 | Default chains have one model per role; the extractors do not fall back to each other. | If the primary fell back to the secondary's model, "two models agree" would be one model agreeing with itself. |
| D5 | Cost comes from `app/llm/pricing.yaml`; a model with no entry is traced as unpriced. | A guessed price is a fabricated number. |
| D6 | No server-side refusal fallback on Claude calls. | A silent model switch would make the traced model wrong. A refusal is traced as a failure and goes down the configured chain. |
| D8 | OpenAI is out of scope (Rahul, 1 Oct). Two providers: Anthropic and Gemini. Image reads lead with Gemini; routing, analysis, judging and clarification run on Claude. | Owner's call. Consequence: the eval judge shares a family with the primary extractor. It grades free-text against exact golden truth, which limits self-preference, and the note says so. |
| D9 | The conditional 4% footnote discount sits on Sri Balaji's PDF, as the brief's dataset table says. The mockups show it on Kaveri; the mockups are a visual reference, the brief is the spec. | Rahul: go with what the case study asks for. |
| D7 | There is no offline mode. Without a key, the call fails and the failure is traced. | Non-negotiable 1. |

### Dataset (Checkpoint B)

| # | Decision | Why |
|---|---|---|
| D10 | Prices come from a physical model: blank area from style and dimensions, board grammage from ply and GSM, a conversion rate per kg, then vendor positioning and noise. | Board weights, per-kg quotes and per-1,000 rates stay mutually consistent, which is what makes Anand's ₹/kg email convertible and the whole set credible to a packaging buyer. |
| D11 | Contract is about ₹3.7 Cr across 30 lines; rates run from ₹1.6k (layer pads) to ₹1.2 L (7-ply export cartons) per 1,000. | Brief: "trust at ₹4 crore". |
| D12 | Each vendor quotes in a different basis: Meridian ₹ per piece, Sri Balaji ₹ per 1,000, Kaveri USD per thousand (L01 per box), NorthBox ₹ per 100, Anand ₹ per kg. | Exercises every row of the conversion table with real inputs. |
| D13 | Anand's "42 for the 5-ply, 38 for the 3-ply" applies to every line of that ply; "rest" is the 7-ply and ancillary lines. Two of the rest (L25, L27) are new this year, so "same as last year" cannot resolve and must flag. | The natural reading of a two-line email against a 30-line RFx, and it produces an honest unresolved case instead of a contrived one. |
| D14 | NorthBox's ambiguous digit is an ink blot over the left half of the tens digit on L05: 3,935 or 3,985. | A 3 and an 8 differ only in the half the blot hides, so the ambiguity is physical, not a rendering trick. Both readings are plausible prices. |
| D15 | Sri Balaji's footnote reads "4% discount on lines above ₹1 L". The vendor's intent in the golden set is rate above ₹1,00,000 per 1,000 (only L04); the other reading, line value above ₹1 L, would hit all 30 lines. | The condition is genuinely ambiguous in the way real footnotes are, and the two readings differ by about ₹14 L. |
| D16 | PDF pages are rasterised with pypdfium2, not pdf2image. | pdf2image needs a system install of poppler, which would break "one command on a fresh clone". Deviation from brief section 2. |
| D17 | Reply files are committed as ordinary git blobs, not Git LFS. | The largest is 640 KB. LFS would make a fresh clone without git-lfs check out pointer files and fail. |
| D18 | `make seed` is byte-deterministic (fixed seed, fixed timestamps, bundled DejaVu fonts). | "Golden JSON matches the generators" is then checkable by `git status` after a re-seed. |
| D19 | Vendor domains use `.example`; fabricated certificates carry a one-line demo footer. | No collision with real companies, no document that could pass as a real certificate. |

### Extraction (Checkpoint C)

| # | Decision | Why |
|---|---|---|
| D20 | The extractor reports raw value, verbatim unit, currency, snippet and locator. It never converts. Units are then read by the conversion table's alias list; the model's own unit label is only a fallback and is marked as such. | "LLMs propose, code decides", applied to the first thing that could go wrong: a unit. |
| D21 | Every reading is checked against the file without a model. Workbook: the cited cell must hold exactly that value. Text: the snippet must appear in the file and contain the number. Photo: cannot be checked, so it relies on two-model agreement. A failed check flags the cell. | Provenance that is asserted by the model is not provenance. This catches a hallucinated or misattributed number. |
| D22 | Line matching is deterministic first (dimensions 0.40, item type 0.25, ply 0.15, GSM 0.10, print 0.10), one-to-one, with Haiku only as a tie-break and "unmatched" below a floor. A different item type caps the score. | On this dataset all 139 rows match by code alone; the model is there for the row a vendor describes badly, not as the default. |
| D23 | A buyer line number reported by the model only counts if the row itself leads with that number. | Gemini filled in RFx line ids for Meridian, whose sheet has none. The guard stops a model's guess becoming "evidence". |
| D24 | Agreement needs the same value (within 0.5%), unit and currency from both models. Self-reported confidence flags a cell only when both models are below 0.80 or either is below 0.50. | Two families agreeing is strong evidence; one model hedging on an elliptical phrase ("38 for the 3-ply") is not a reason to block 11 cells. |
| D25 | Image reads lead with Gemini, text reads with Claude; the other model is always the second reader. | Rahul's rule: image work to Gemini, the rest to Anthropic. |
| D26 | A failed extraction is stored as a failure and flags every line of that vendor `model_error`. | Non-negotiable: never silently dropped. |

Observed on two independent live runs (1 Oct): Meridian, Sri Balaji, Kaveri and Anand 100% on
every field for both models. On NorthBox's blotted digit Claude declined to give a value both
times; Gemini read 3,995 (wrong) on the first run and 3,935 (right) on the second. The cell
was flagged both times. That is the case for a second reader in one line.

### Grid, review and award (Checkpoint D)

| # | Decision | Why |
|---|---|---|
| D27 | The grid is computed on every read from stored readings and decisions. Nothing about a cell is cached. | The grid cannot drift from its sources, and changing the FX rate or the conversion table takes effect everywhere at once. |
| D28 | A cell in review shows a provisional value with a question mark, and that value is never counted. | A blank hides information the buyer needs to decide; a counted guess is worse. |
| D29 | Review items are a function of the readings. Only the person's decision is stored, keyed by a stable id. | Re-reading a file cannot orphan or duplicate a decision. |
| D30 | Choosing one of the system's computed options makes the cell confident; typing a value makes it overridden. | "Overridden" should mean a human number replaced the system's, with a reason. |
| D31 | Currency and missing freight are items to acknowledge; they do not hold cells out of totals. | FX is a stated assumption on screen. Blocking 29 Kaveri cells on it would bury the real problems. They still block approval. |
| D32 | The outlier rule needs both more than 2σ from the line median and a 15% deviation. | With five vendors a bare 2σ test fires on 2 to 5% differences (8 to 10 cells in this dataset). |
| D33 | "Best single vendor" only counts vendors with a counted price on every allocated line. | Otherwise the comparison rewards a vendor for not quoting. |
| D34 | The cost of a rule is measured on the same lines, against a split with no eligibility rule. | Makes "what does the quality rule cost us" a number. |

### Analyst (Checkpoint E)

| # | Decision | Why |
|---|---|---|
| D35 | SQL only, on DuckDB. The brief allowed SQL or pandas. | One read-only statement can be checked before it runs. Arbitrary Python cannot. |
| D36 | The sandbox is a separate process, read-only database, external access off inside DuckDB, memory cap, 12 second timeout, and a static check that rejects anything but one SELECT. | The model's output is never evaluated in the app's process. |
| D37 | The query runs on a snapshot named by the hash of its content, and the hash is shown with the answer. | An answer can be tied to the exact data it ran on. |
| D38 | The query must compute every figure the answer quotes, including crore and lakh conversions. Code then checks each figure in the prose against the rows. | The model never does arithmetic that a buyer reads. |
| D39 | The statement of what was excluded is written by code and shown under every answer. | The most important caveat should not depend on the model remembering it. |
| D40 | A saved scenario stores the rule, not the result. Totals are recomputed by the award engine from the current grid. | A scenario saved before the queue was cleared must not carry a stale total into an award. |

### Interface

| # | Decision | Why |
|---|---|---|
| D41 | Components are hand-written on Radix primitives with class-variance-authority, in the shadcn pattern, instead of running the shadcn generator. | The generator brings its own colour variables. The design rule is that Tailwind reads `tokens.css` and no component hardcodes a hex. |
| D42 | `make demo` builds the frontend and serves it from the API on one port. | One process, one command, nothing to keep running in a second terminal. |
| D43 | The persona switcher sets a header the API enforces (buyer, VP, evaluator, admin). | It is a demo device for roles, not authentication, and says so in its tooltip. |

## 5. Known limits

- The judge shares a family with the primary extractor (see D8).
- A photo's reading has no deterministic source check (see D21), and the popover shows the whole photo rather than a crop of the row.
- Line matching vocabulary is one category template; a second category needs its own.
- The analyst's figure check ignores whole numbers up to 100, so a wrong line count would pass it.
- SQLite schema changes need `make reset`; there are no migrations.
