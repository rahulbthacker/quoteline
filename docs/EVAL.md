# Eval report

Snapshot of `make eval` on 2026-10-01 (ingest run `ingest-388f57a2`). Regenerate with `make eval`; the live version is in the Run inspector.

Truth is exact because the generator that wrote the five reply files also wrote the golden set. Field accuracy counts a row as correct only if it is matched to the right RFx line and the raw value, unit and currency equal the golden values. A flagged cell with a wrong value is not a missed problem; a counted cell with a wrong value is.

## Headline

| Measure | Result |
|---|---|
| Rows scored per model | 139 |
| Value accuracy, Claude Opus 5.5 | 99.3% |
| Value accuracy, Gemini 3.1 Pro | 99.3% |
| Line match, unit, currency (both models) | 100%, 100%, 100% |
| Agreement between the two models | 99.3% |
| Flag precision (flags raised that are real problems) | 100% of 9 |
| Missed problems (expected flag not raised, or a wrong value in a counted cell) | 0 |
| Free-text conditions captured faithfully (judge model) | 100% |
| Questionnaire verdicts matching golden | 100% |
| Model calls and cost for one full ingest | 24 calls, ₹167 |
| Mean extraction latency per call | 69.6 s |

## Per vendor, per model

| Vendor | Format | Model | Rows | Line | Value | Unit | Currency | Free text | Latency | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Meridian Packaging | xlsx | claude-opus-5-5 | 30 | 100% | 100.0% | 100% | 100% | 100% | 66.6 s | ₹19.72 |
| Meridian Packaging | xlsx | gemini-3.1-pro-preview | 30 | 100% | 100.0% | 100% | 100% | 100% | 96.2 s | ₹16.37 |
| Sri Balaji Corrugators | pdf | claude-opus-5-5 | 30 | 100% | 100.0% | 100% | 100% | 100% | 74.2 s | ₹21.90 |
| Sri Balaji Corrugators | pdf | gemini-3.1-pro-preview | 30 | 100% | 100.0% | 100% | 100% | 100% | 96.8 s | ₹16.37 |
| Kaveri Boards | docx | claude-opus-5-5 | 29 | 100% | 100.0% | 100% | 100% | 100% | 53.8 s | ₹15.47 |
| Kaveri Boards | docx | gemini-3.1-pro-preview | 29 | 100% | 100.0% | 100% | 100% | 100% | 102.5 s | ₹16.29 |
| NorthBox Ltd | image | claude-opus-5-5 | 27 | 100% | 96.3% | 100% | 100% | 100% | 70.2 s | ₹18.19 |
| NorthBox Ltd | image | gemini-3.1-pro-preview | 27 | 100% | 96.3% | 100% | 100% | 100% | 95.1 s | ₹15.11 |
| Anand Papers | eml | claude-opus-5-5 | 23 | 100% | 100.0% | 100% | 100% | 100% | 11.6 s | ₹3.54 |
| Anand Papers | eml | gemini-3.1-pro-preview | 23 | 100% | 100.0% | 100% | 100% | 100% | 29.0 s | ₹3.91 |

## Flags and wrong readings

- **Meridian Packaging**: expected flags raised: none expected.
- **Sri Balaji Corrugators**: expected flags raised: footnote_condition.
- **Kaveri Boards**: expected flags raised: unit_ambiguity, not_quoted, currency_mismatch, missing_freight.
- **NorthBox Ltd**: expected flags raised: ocr_disagreement, not_quoted.
  - claude-opus-5-5 wrong reading: L05: read None per_100 INR; golden 3935.0 per_100 INR
  - gemini-3.1-pro-preview wrong reading: L05: read 3995.0 per_100 INR; golden 3935.0 per_100 INR
- **Anand Papers**: expected flags raised: carry_forward_unresolved, missing_freight.

The only wrong readings are on NorthBox L05, where an ink blot covers one digit in the photo. The cell was flagged, so it is not a missed problem.
