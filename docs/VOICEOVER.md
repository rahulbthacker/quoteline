# Voiceover script

Timed to `deliverables/quoteline-walkthrough.mp4` (9 min 28 s, recorded 1 October 2026 by
`make video`). Each row is one scene; the caption at the bottom of the video changes when the
next row starts. The narration fits the scene at an unhurried pace, with a second or two spare.

Every figure below is what is on screen in this recording. If you re-record, the readings are
live, so read the numbers off your own screen.

## How to add your voice

1. Open the video in QuickTime Player and mute it.
2. In QuickTime: File → New Audio Recording. Press record, then start the video and read the
   script, changing lines when the caption changes.
3. Save the recording as `deliverables/voiceover.m4a`.
4. Run `make voice`. It writes `deliverables/quoteline-walkthrough-voiced.mp4`.

Record it in one take if you can. If you stumble, keep going; a natural take is better than a
perfect one. iMovie works too: drop the video in and use its voiceover button.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:02 | Compare. The cursor runs along the assumptions bar, the five vendor headers, four highlighted cells, then scrolls to the totals and the amber banner. | "This is Quoteline. We sent one RFx for corrugated packaging to five vendors: thirty lines, about three point seven crore a year. They replied in five formats, and nobody used our template. A spreadsheet in their own layout, a PDF on letterhead, a letter in prose and US dollars, a phone photo of a rate card, and a two-line email. This grid is all of them, line by line, in rupees per thousand pieces. The assumptions sit at the top. Green is the lowest price on a line. Amber needs a decision, and until I make it, that cell is in no total." |
| 0:44 | Toggle to "Raw as quoted" and back. | "Here is the same grid as each vendor wrote it: per piece, per thousand, dollars per box, per hundred, per kilo. Five units, one comparison." |
| 0:58 | Click Meridian L01. Popover: source, readings, arithmetic. | "Every number is one click from its source. The file, the cell, what each model read, and the arithmetic. 'Found in file' is checked by code, not by a model." |
| 1:11 | Click Kaveri L01. The quoted sentence, why flagged, two interpretations. Click "One box is one piece". | "This one is flagged. Both models read sixty-five cents per box. The trouble is the same sentence says 'packed one hundred per bundle'. Read as a piece, it is within one percent of the other vendors. Read as a bundle, it is ninety-nine times cheaper. The system computes both and does not guess. I choose per piece, and the cell counts." |
| 1:37 | Responses → NorthBox → "Raw beside extraction". The photo, the flagged row, then the Questionnaire tab. | "NorthBox sent a photo, at an angle, with an ink blot over one digit. On the left is exactly what arrived; on the right, what was read. Two models read it independently, and on that digit they disagree, so it is flagged. The same photo answers our questionnaire. NorthBox has one production site, we need two, so it fails a mandatory question, with the evidence quoted." |
| 2:08 | Review queue. Sri Balaji's discount: both options shown, the first chosen. NorthBox's digit resolved. Anand's two lines set to not quoted. | "Everything uncertain lands in one queue. Sri Balaji's footnote says four percent off lines above one lakh. As a rate, that is one line. As a line value, it is all thirty. I take the first reading. I pick the reading for the blotted digit. And Anand wrote 'rest same as last year', but two lines are new this year, so there is nothing to carry forward. I treat those as not quoted." |
| 2:42 | "Ask Kaveri" on the freight item. A drafted email appears. | "Kaveri quoted FOB Chennai and never priced freight to Pune. Instead of deciding, I ask. The system drafts the clarification: their exact words, the question, and a reply format. It is saved as a draft. Nothing is ever sent on its own." |
| 3:09 | The remaining items are acknowledged one by one. | "The rest I acknowledge: the dollar conversion at the RBI rate, unpriced freight carried as a condition, and lines that were simply not quoted. Not quoted is never treated as zero." |
| 3:28 | Sent: the outbox log. | "The outbox shows the RFx to all five vendors, and my clarification, still a draft." |
| 3:39 | Compare again: the totals, then an override on Anand L01 with a reason. | "Back on the grid, the banner is gone and every cell counts. If I know something the documents do not, I can override a value, but only with a reason. It is underlined, it is in the audit log, and I can revert it." |
| 4:10 | Analyse. The VP's question is asked; the system works for about a minute. | "Now the question a VP actually asks. If we split the award, cheapest per line, but only among vendors who cleared quality, how does that compare with giving it all to one vendor? This is not a canned report. The system writes a query for this question, runs it in a sandbox against only the cells that count, and then writes the answer from the rows that come back. It is not allowed to state a number that is not in those rows, and code checks that. This takes about a minute because it is happening live. Two model calls and one query." |
| 5:14 | The answer, the table, the chart, the caveat, then "Query I ran" opened, then Save as award scenario and Export. | "The split comes to three point six four crore across all thirty lines. That is six point six lakh, about one point eight percent, below the cheapest single vendor, Sri Balaji. It also warns me that freight could narrow that gap. Below the answer is what was left out, written by code. And here is the query itself, so anyone can check it. I save this as an award scenario and export it to Excel." |
| 5:59 | A second question is typed: on-time delivery. The system declines. | "Now one it cannot answer. Which vendor has the best on-time delivery record? We never collected that. It says so, says what data it would need, and does not answer an easier question instead." |
| 6:23 | Award. Four stat cards, the allocation, rules applied, excluded and why, the audit log. | "The award is computed by an engine, not by a model. Three point six four crore across three vendors. Six point six lakh below the best single vendor, and eight and a half percent below last year's contract. These are the rules that were applied. These are the two vendors excluded and why, and what that rule costs us: three point four lakh. The audit log has every decision I made, with my reasons." |
| 7:13 | Send for approval, switch persona to VP, Approve, download the pack. | "I send it for approval. As the VP, I see the same page, read-only, and I can sign. Approval was blocked until the review queue was clear. The award pack downloads as a PDF." |
| 7:34 | Run inspector: the eval panel, then the list of calls. | "How do I know the AI is right? Every model call is traced. And because we built the test files ourselves, we know the truth. Each model read ninety-nine point three percent of prices correctly. The one miss was the blotted digit, and it was flagged. Nothing wrong reached a counted cell." |
| 7:59 | Draft → co-pilot. Buyer notes are pasted and sent; after about fifty seconds a thirty-line draft appears; the "still missing" list. | "Finally, where this starts. The buyer pastes rough notes: an item list, quantities, a few requirements. The co-pilot turns them into a structured RFx: thirty lines, a questionnaire with the three mandatory questions I named, and terms. What matters is what it does not do. It never invents a quantity or a specification. Here it has left two fields blank and listed them as missing, because my notes did not give them. Everything lands in a form I can edit before anything is sent." *(pause while the draft loads, then, over the finished draft)* "So: any format in, one grid out, every number traceable, every uncertainty resolved by a person, and an award a VP can defend." |
| 9:25 | End card. | "One command runs all of it. Thank you." |

## If you would rather record it yourself, live

Run `make rehearse`, then `make serve`, and follow the same rows: the "On screen" column is
the click list. `docs/WALKTHROUGH.md` has the same flow with fallback notes. Start a screen
recording with QuickTime (File → New Screen Recording) and talk as you click.
