# Data Model — spec 008 (Alignment Cursor Recovery)

Extends the spec-006 data model. Only the **AlignmentEntry** changes; everything else is an output-location change.

## Entities

### AlignmentEntry (per output page) — MODIFIED

One entry per page in `alignment.json["alignment"]`. Existing fields unchanged:

| Field | Type | Meaning |
|---|---|---|
| `page` | int | 1-based output page number (`page_NNN.txt`) |
| `gt_start` | int\|null | 1-based first GT verse aligned to this page |
| `gt_end` | int\|null | 1-based last GT verse aligned to this page |
| `status` | string | one of the statuses below |
| `confidence` | float | fraction of this page's verses within the hallucination threshold |
| `out_verses_count` | int | verse lines (` ... `) found in this page's output |
| `gt_verses_count` | int | verses spanned by the assigned window |
| `skipped_gt` | int | GT verses skipped between the cursor and this page's start |
| `hallucination_verses` | int[] | 1-based indices of suspected-hallucinated output verses (diagnostic only) |
| `anchor_distance` | float\|null | levenshtein at the middle anchor |

**NEW field (FR-002, R5)**:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `recovered` | bool | `false` | `true` when this page had no trusted anchor but still consumed a best-effort GT span to keep the cursor moving. The `status` stays `unmatched` — this flag is what lets the scorer distinguish "excluded, no window" from "recovered, distrust but measure". |

### Statuses (unchanged vocabulary)

```
matched          — clean: confidence ≥ 0.7, |Δcount| ≤ 2, anchor < threshold
low_confidence   — weak (0.3 ≤ conf < 0.7) but placed
count_mismatch   — placed, but |gt_count − out_count| > 2
unmatched        — not trustably placed. NEW: may now carry a recovered window.
prose_only       — no verse lines on the page (cursor does NOT advance)
out_of_gt_scope  — before GT start or after GT end (cursor does NOT advance)
empty            — no content lines at all
```

### QualityReport (per corpus + per page) — EXTENDED

Per-page records gain a `recovered` mirror of the alignment flag, and the corpus summary gains:

| Field | Type | Meaning |
|---|---|---|
| `pages_clean` | int | count of `matched` pages actually scored |
| `pages_low_confidence` | int | `low_confidence` + `count_mismatch` |
| `pages_recovered` | int | scored pages carrying `recovered: true` (new — previously excluded) |
| `pages_excluded` | int | genuinely windowless (prose/empty/out-of-scope) |

The headline `weighted_cer` / `weighted_wer` now average over clean + low-confidence + **recovered** pages (the honest denominator, R9).

## State Transitions

```
page with verse lines
   │
   ├─ anchor found, conf ≥ 0.7, |Δ|≤2 ────────────► matched          (recovered=false)
   ├─ anchor found, 0.3 ≤ conf < 0.7 ─────────────► low_confidence   (recovered=false)
   │                                                / count_mismatch
   ├─ anchor found but conf < 0.3 ─────────────────► unmatched + recovered=true
   │      window = anchor's window (directionally usable, kept for the cursor)
   └─ no usable anchor ────────────────────────────► unmatched + recovered=true
          window = [cursor, cursor + out_verses_count − 1]  (advance-by-count, clamped)

page with NO verse lines ──► prose_only / empty          (cursor unchanged, recovered=false)
before GT start / after GT end ──► out_of_gt_scope       (cursor unchanged, recovered=false)
```

## Validation Rules

- **Monotonicity**: for consecutive entries with windows, `gt_start_next > gt_end_prev` (enforced by `_enforce_monotonic`, unchanged).
- **Bounds**: `1 ≤ gt_start ≤ gt_end ≤ 620` (GT length); recovered windows clamp to `[cursor, gt_len]`.
- **Determinism**: two runs over the same inputs are byte-identical (FR-008).
- **Regression**: the 26 pages that were `matched` in the spec-006 alignment keep identical `gt_start`/`gt_end`/`status` (FR-004).
- **Immutability**: sha256 over every `.txt` under `data/output` + `data/ground_truth` remains `91b3f61101170b233619` (FR-009).
