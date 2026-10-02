# Plan — Gemini cross-reader for the batch 4-6 decision sheet

**Date:** 2026-10-02 · **Goal:** use a vision LLM to produce crop readings for
the `out_of_gt_scope` rows, so a human (or a human spot-checking a sample)
can convert them to `full_line` records.

## What the probe established

- **Gemini is the only live vision backend.** Both `GEMINI_API_KEY1` and
  `GEMINI_API_KEY2` respond, pass the blank-white control (reply `NO TEXT`),
  and return diacritized Arabic that reads the actual crop. Two keys = two
  independent readings of the same image, which is the comparison signal.
- **OpenRouter's free vision model is blind.** `llama-4-scout-17b` passes
  the blank control but returns a *different Quranic verse for every crop*
  regardless of content (p088_02 → لا تقف ما ليس لك به علم, p087_09 →
  بسم الله الرحمن الرحيم لا إكراه في الدين). It is hallucinating from an
  Arabic religious-text prior, not reading the image. Rejected.
- **OpenRouter `google/gemini-3.6-flash`** needs credits (HTTP 402).
- **Groq** has zero vision models in its current catalog (11 models, none
  vision-capable) — matching the project's earlier finding.
- **Atria** is text-only by design (rejects images, HTTP 400).

## The conservative rule and how this plan respects it

`full_line` means a person read and confirmed the line. **A Gemini reading is
not a person.** So this plan registers Gemini readings as `partial` with a
new provenance marker — the same standard applied to batch 2-3's programmatic
GT matching. A `full_line` upgrade still requires a human to look at the crop.

What this buys: 48 crops get a *high-quality candidate reading* each, with two
independent Gemini passes to disagree on. The human's job drops from
"decipher this from scratch" to "check whether two Gemini readings agree and
whether the agreed reading matches the crop" — a far faster judgment, and one
that can be spot-checked on a sample rather than done row by row.

## Steps

### Step 1 — Build the cross-reader (do now)

`scripts/gemini_cross_reader.py`: for each of the 48 crops in
`logs/batch456_decisions.md`, OCR it with both Gemini keys (strict
"transcribe only what you see, no completion" prompt, blank-control verified),
and write `logs/gemini_crossread.jsonl` with one record per crop:

```
{crop, page, region, key1_reading, key2_reading,
 skeleton_agreement, disagreements_note}
```

`skeleton_agreement` = normalized-skeleton similarity between the two
readings (diacritics stripped, spaces removed). High agreement = the reading
is likely right at the letter level; low agreement = the crop is genuinely
hard and needs a human.

Cache aggressively (two keys × 48 crops ≈ 96 calls at ~5-15 s each; resume
must not re-call). Include the blank control once per key per run as a
live sanity check, and abort if either key hallucinates on it.

### Step 2 — Reconcile into the decision sheet (do now)

Update `logs/batch456_decisions.md` (or write `logs/gemini_decisions.md`
alongside it) so each row shows: the two Gemini readings side by side, their
skeleton agreement, and a verdict — **AGREE** (adopt the reading as a
candidate), **MINOR** (agree on letters, differ on diacritics — adopt letters,
flag diacritics), **DISAGREE** (needs a human). The 4 mis-paired crops get the
Gemini reading of what the crop *actually* shows, per the audit.

### Step 3 — Register the agreed rows as `partial` (do now)

Append records for AGREE and MINOR rows to
`data/reviewed_corrections.jsonl` with:
- `confidence: "partial"` (NOT full_line — no human has seen the crop)
- `pairing_confirmed: true` where the Gemini reading matches the crop's own
  line (the same gate as batches 2-3)
- `source: "gemini_crossread"` and a note naming both readings and the
  agreement score, so the provenance is auditable and these rows can be
  isolated and reverted if Gemini turns out to have a bias on this text.

This is deliberately the same conservative pattern as the batch 2-3 GT
registrations: programmatic evidence → `partial`, human eyes → `full_line`.

### Step 4 — Human spot-check sample + measurement (needs you, after)

Pick ~5 high-agreement and ~5 low-agreement crops, look at the images, and
tell me which Gemini readings are right. That calibrates whether the
cross-read is trustworthy enough to lean on. Then re-run the one-command
measurement and see what the partial pool did to the diacritics metric.

---

## What this plan does NOT do

- **No `full_line` from Gemini.** The conservative rule is the project's core
  design decision; a vision LLM reading is supporting evidence, not a
  confirmation.
- **No OpenRouter / Groq / Atria vision.** Probed and rejected with evidence
  above; not retried.
- **No corpus regeneration.** `data/output` frozen; the 251-file invariant
  must keep passing.
- **No silent adoption.** Every Gemini-derived record is marked with its
  provenance and can be reverted as a set.

## Agent split (4 agents, parallel)

- **Agent A:** build `scripts/gemini_cross_reader.py` + run it over the 48
  crops (the slow, network-bound task — start first).
- **Agent B:** prepare the reconciliation logic + verdict thresholds on the
  batch 2-3 GT-verified rows as a calibration set (what does skeleton
  agreement look like when the answer is known?).
- **Agent C:** update the decision sheet structure to carry the two Gemini
  columns (doc work, after A produces data).
- **Agent D:** register the AGREE/MINOR rows as `partial` with provenance
  (after A and C), then run the ingester + full verification.
