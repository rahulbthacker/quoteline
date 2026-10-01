# Quoteline design notes

Working document. The 13 questions and the traceability matrix are completed in build step 11;
this file records decisions as they are made so they are not reconstructed from memory.

## Decisions so far

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

Note for step 4: with five vendors, a plain ">2σ from the line median" rule fires on harmless
2 to 5% deviations (8 to 10 cells in this dataset). The outlier check needs a materiality
floor alongside the σ test.

## Open questions for Rahul

1. The brief lists seven ReviewItem kinds; validation and the line matcher also need
   `unmatched` and `currency_mismatch`. Added to the schema; say if they should fold into others.
