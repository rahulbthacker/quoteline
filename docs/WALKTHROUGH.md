# Walkthrough script

Eight to ten minutes, recorded from a fresh `make demo`. Everything on screen is live: the
five files were read by two models during `make demo`, and every answer below is generated
while you record. Figures can differ slightly between runs, so read them off the screen
rather than from this script.

**Before recording:** run `make demo` (about two minutes, about ₹170 of model spend) and wait
for the browser to open on Compare. Set the window to roughly 1440 × 900. Stay in the Category
buyer persona until step 8.

| # | Time | Screen | Do | Say |
|---|---|---|---|---|
| 1 | 0:00 | Compare | Let the grid sit for a moment. Point at the assumptions bar, the five vendor headers, the footer totals and the amber banner. | "Five vendors replied in five formats: a spreadsheet in their own layout, a PDF on letterhead, a Word letter in prose and US dollars, a phone photo of a rate card, and a two-line email. Nobody used the template. This is all of them in rupees per thousand pieces. Amber cells are not in any total." |
| 2 | 0:50 | Compare | Click **Kaveri L01**. Walk down the popover: source, the highlighted snippet, both readings, why flagged, the arithmetic, the two interpretations. | "Every number is one click from its source. Both models read 0.65 dollars per box. The problem is the unit: the same sentence says packed 100 per bundle. As a piece it is 0.8% from the other vendors. As a bundle it is 99 times cheaper. The system does not guess." Click **One box is one piece**. |
| 3 | 1:50 | Responses | Open **NorthBox Ltd**, "Raw beside extraction". Show the photo beside the rows; scroll to row 5. | "This is a photo at an angle with an ink blot on one digit. One model declined to read it, the other offered a value and alternatives. That disagreement is why the cell is flagged." Open the Questionnaire tab: "It also fails a mandatory question, one production site where we need two, with the evidence quoted." |
| 4 | 3:00 | Review queue | Resolve in this order: **Sri Balaji** discount: read both options aloud, choose "rate above ₹1,00,000". **NorthBox L05**: choose the 3,935 option. **Anand** L25, L27: "Treat as not quoted". Then click **Ask Kaveri** on the freight item and show the drafted email. Acknowledge the remaining items (currency, freight, not quoted). | "A footnote says 4% off lines above one lakh. Read as a rate that is one line; read as line value it is all thirty. The system computed both and asks. Anand wrote 'rest same as last year', and two lines are new this year, so there is nothing to carry forward. The clarification is drafted for me and saved to the outbox. Nothing is ever sent automatically." |
| 5 | 4:40 | Compare | Return. The banner is gone. Click **Anand L01**, choose Override, enter a value and the reason "confirmed by phone". | "Every cell now counts. An override needs a reason, shows with an underline, and can be reverted." |
| 6 | 5:10 | Analyse | Click the first suggestion (the VP's question). While it runs: "It writes a query, the query runs in a sandbox on counted cells only, and the answer is written from the rows." When it returns, open **Query I ran**. Click **Save as award scenario**. | "The split across the three vendors who cleared quality against the best single vendor. Here is the query. Every figure in the answer is checked against these rows." |
| 7 | 6:40 | Analyse | Type: **Which vendor has the best on-time delivery record?** | "It declines, and says what data it would need. It does not answer an easier question instead." Then click **Export XLSX** on the previous answer and open the file: result sheet and query sheet. |
| 8 | 7:30 | Award | Choose the saved scenario, **Draft the award**. Walk the four stat cards, the allocation, rules applied, excluded and why with the cost of the quality rule, the audit log. Click **Send for approval**. Switch persona to **VP Supply Chain** and click **Approve**. Download the award pack PDF. | "The award is computed by an engine, not a model. It shows what the quality rule costs us. Approval was blocked until the queue was clear; you can see every decision I made in the audit log." |
| 9 | 8:50 | Run inspector | Open it. Point at the eval panel and the call list. | "Every model call is traced: role, model, prompt version, tokens, latency, cost. Because we fabricate the data we know the truth: 99.3% of prices read correctly by each model, the one miss was flagged, and nothing wrong reached a counted cell." |
| 10 | 9:30 | Draft, co-pilot tab | Optional if time allows: **Paste sample buyer notes**, Send. | "The RFx itself was drafted this way. It structures thirty lines and leaves blank what I did not give it." |

## If something goes wrong on camera

- **A model call fails.** It is retried once and traced. If a whole read fails, every cell for
  that vendor is flagged `model_error`. Say so; it is the designed behaviour.
- **The analyst's query fails.** It repairs once using the error. If it fails twice you see the
  error and no answer, never a guessed one.
- **A number differs from a previous run.** The readings are live. The golden set is in
  `data/golden/` if you want to show the truth beside it.

## Questions worth trying off-script

- "What do we lose by excluding NorthBox?"
- "Which lines got more expensive than last year?"
- "If Sri Balaji's freight is included, is the split still cheaper than Meridian alone?"
- "Who is cheapest on the printed items?"
- "What would Kaveri's total be if L01 were per bundle?" (It should say the cell is not counted
  and point you to the review queue.)
