# Next-step plan — 2026-10-02 (after the ingest→measure wiring fix)

**Where we are:** 85 correction records (20 full_line / 65 partial), the
Phase 2 machinery works end-to-end (one-command step-5 measurement), the
vault's base-letter class is fully resolved (0 open), and batches 4-6 are
triaged (32 recovered / 19 degraded / 7 not-text). The crop-pairing audit
confirmed no registered record sits on a mis-paired crop.

**The one binding constraint that shapes everything below:** `full_line`
means a person read and confirmed the line. Nothing in this plan
auto-registers `full_line`. Every item either (a) removes work from the
human's plate so their review time buys the most gate progress possible,
or (b) closes a documented loose end that does not need the human at all.

---

## Step 1 — Close the 7 NOT_TEXT rows without a human (do now)

The 7 batch 4-6 rows classified NOT_TEXT are all on p.111's index and are
dot-leader / page-number furniture, not text. Each one is currently an open
review-queue row that will cost the human a "no, this isn't text" judgment.

`scripts/ingest_reviewed_corrections.py` already supports
`triage: "not_text"` — such records are counted and never become gold. So
these 7 rows can be closed **by the model**, because the evidence is OCR
text (dot runs + digits), not image content. The human's judgment adds
nothing the OCR doesn't already show.

Deliverable: 7 `triage: "not_text"` records appended, plus a short doc note
recording that the p.111 leader rows were closed on OCR evidence and that
the 2 rule+text p.111 bands from the escalation audit remain the gate's
known open gap (they are a *different* set — those mix a rule with real
text; the 7 closed here are pure furniture).

## Step 2 — Build the batch 4-6 RECOVERED rows into a decision sheet (do now)

32 rows have fresh crop OCR that reads real Arabic. There is no GT for
pages 68+, so a human must still read each crop to register `full_line` —
but the sheet can do the triage work in advance: for each row, show the
stored guess, the fresh OCR, and a one-line verdict on whether the fresh
OCR is a plausible reading, so the human is confirming rather than
deciphering. The 4 mis-paired crops (p084_15, p090_11, p092_01, p094_07)
get their corrected line shown, since the stored guess is wrong.

Deliverable: `logs/batch456_decisions.md` — one section per row, ordered by
how much the fresh OCR recovered, with the crop path so the human can open
it. This is a writing task; it must NOT register records.

## Step 3 — Re-measure and report (after step 1)

Step 1 changes the record file, so re-run the now-working one-command
measurement and confirm the headline didn't move (the 7 closed rows
contribute no gold, so only the partial count should change). Also check
`docs/accuracy_history.md` for duplicate same-day rows — the earlier
debugging run appended four stale 64.0% rows; confirm only the correct one
remains.

## Step 4 — Update the plan docs to reflect reality (do now)

Three facts the plans currently get wrong, all established this session:

- `NEXT_DEVELOPMENT_PLAN_2.md` Phase 1 says the 67 base-letter rows "need a
  human confirm." They are already confirmed (37 applied, 30 rejected).
  Phase 1 is **done**; the doc should say so and point at
  `logs/vault_crossref_status.md`.
- The same plan's Phase 2 step 5 says the measurement needs a throwaway
  harness. It no longer does — the wiring is fixed and is one command.
- `logs/autonomous_session.md` should record the wiring fix as the session's
  substantive code change, not just a footnote.

Deliverable: edits to `plans/NEXT_DEVELOPMENT_PLAN_2.md` and
`logs/autonomous_session.md` only. Do not rewrite history or soften any
recorded negative result.

---

## What this plan deliberately does NOT do

- **No auto-`full_line`.** Steps 1-2 prepare the human's decisions; they do
  not make them.
- **No corpus regeneration.** `data/output` stays frozen; the 251-file
  invariant must keep passing.
- **No new tashkeel attempt.** Phase 3's gate needs ~50 full_line; at 20 it
  is not ready, and the plan's own §8 bar (≥80% vault agreement) is the
  same one that rejected the last attempt at ~13%.
- **The 56 diacritics-only vault rows stay open.** They cannot move CER and
  they need a human judgment per row; they are not worth the review time
  until the gate is closer.

## Agent split

- **Agent A:** step 1 (close the 7 NOT_TEXT rows) — appends records, re-runs
  the ingester, verifies.
- **Agent B:** step 2 (batch 4-6 decision sheet) — writing only, touches
  `logs/` only.
- **Agent C:** steps 3+4 (re-measure + plan-doc updates) — measurement and
  doc edits.
