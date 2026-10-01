# Quoteline: decisions note

Take-home for Aerchain, "Kill the Quote Spreadsheet". Rahul Thacker, 1 October 2026.

**What it is.** One flow for corrugated packaging: draft an RFx with a co-pilot, send it, take five vendor replies in whatever form they arrive, compare them in one grid in ₹ per 1,000 pcs, resolve what is uncertain, ask questions in plain language, and produce an award a VP can sign. `make demo` runs all of it.

## Decisions

1. **Uncertainty is a state.** A cell is confident, needs review, not quoted or overridden. A cell in review shows a provisional value and stays out of every total, the analyst and the award until a person resolves it. Not quoted is never zero.
2. **Models read; code decides.** Claude Opus 5.5 and Gemini 3.1 Pro read every quote independently. Units, packs, FX, line matching, totals and the award are deterministic Python over an editable conversion table.
3. **Provenance is checked, not asserted.** Every reading carries file, locator and verbatim snippet, and code confirms the value is really there. A photo cannot be checked this way, so it relies on the two readers agreeing.
4. **Conditions are never applied by a model.** A footnote discount, "freight extra" or "rest same as last year" becomes a review item with each interpretation computed.
5. **The analyst cannot make up a number.** It writes one SQL query, run in a sandbox on counted cells only. Code checks every figure in the answer against the rows and states what was excluded. It declines what the data cannot answer.
6. **The award is computed by an engine**, shows what each rule costs, and cannot be approved while a review item is open.

## Results

The script that fabricates the replies also writes the golden set, so truth is exact. On a fresh clone (`docs/EVAL.md`):

- Each model read 138 of 139 prices correctly (99.3%); line match, unit and currency were 100%.
- The one miss is a digit under an ink blot in the photo. It was flagged on every run.
- Flag precision 100% (9 raised), no missed problems, no wrong value in a counted cell.
- Questionnaire verdicts matched on 40 of 40.
- The analyst answered the VP's split-award question and five others correctly against the award engine.
- `make demo` reached Compare in 126 seconds for ₹167 of model spend.

## Things I refused to fake

- No simulation mode and no cached extraction. Only email transport is stubbed: sending writes .eml files, receiving is a folder.
- The ambiguous digit is a physical blot in the image, not a label in the data.
- Unknown model prices show as unpriced rather than estimated.
- The co-pilot left two GSM values blank because the buyer's notes did not give them.

## Deliberate omissions

Real email and a vendor portal; more than one foreign currency; contract-terms extraction; ERP integration; authentication (the persona switcher is a demo device); a scanned-volume OCR pipeline; negotiation rounds; multi-step approval. OpenAI was dropped from scope, so the eval judge shares a family with one extractor; it grades against exact truth, which limits the bias.

## The better problem

The spreadsheet is a symptom. Two things underneath it are worth more than the grid.

**A normalisation ontology.** "Per box", "bundle of 100", "₹42/kg" and "4% above ₹1 L" are not parsing problems. They are a vocabulary every category has and nobody has written down. Here it is a 60-line YAML file and a category template. Owned as a product and versioned, it makes the tenth category cheap, and it turns a review decision ("for this vendor, a box is a piece") into something the system remembers.

**Query provenance.** A VP trusts a number when they can see where it came from. The cell has that today. The same contract should hold one level up: every answer, scenario and award carries its query, snapshot and exclusions, so "why did we award this?" is answerable a year later from the record.
