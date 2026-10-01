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

## Open questions for Rahul

1. The brief lists seven ReviewItem kinds; validation and the line matcher also need
   `unmatched` and `currency_mismatch`. Added to the schema; say if they should fold into others.
