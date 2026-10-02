# Registration specification — Gemini crossread → `data/reviewed_corrections.jsonl`

**Date:** 2026-10-02 · **Status:** specification only — **nothing has been appended.**
The crossread data (`logs/gemini_crossread.jsonl`) is still being produced; this
document pins the record format so the append (Agent D, later) is mechanical.

**One rule above all others (from `logs/gemini_crossread_plan.md`):** a vision-LLM
reading is programmatic evidence, not a human confirmation. Every record derived
from the crossread is `confidence: "partial"`. **No `full_line` ever comes from
Gemini.** Partial records are counted and held back from the gold layer — they
enter nothing, gate nothing, and can be reverted as a set via the `source` marker.

---

## 1. The ingester contract (verbatim from `scripts/ingest_reviewed_corrections.py`)

```
REQUIRED_FIELDS = ("queue", "page", "line", "ocr_text", "corrected_text", "confidence")
VALID_QUEUES    = ("manual_review_queue", "genealogy_crossref_review", "vote_corrections")
VALID_TRIAGE    = ("real_text", "not_text")
VALID_COVERS    = ("whole_line", "hemistich")
VALID_CONFIDENCE = ("full_line", "partial")
```

### 1.1 Validation rules in `load_corrections()` (the gate every appended record must pass)

1. Blank lines are skipped. Anything not valid JSON is rejected.
2. `triage`, if present, must be in `VALID_TRIAGE`, else rejected.
3. `triage == "not_text"` **relaxes the reading requirements, not the identity
   requirements**: it still requires `page` and `queue`, then accepts the record
   with **no** `corrected_text`/`confidence`. `file` is defaulted to
   `page_%03d.txt`. It is counted and never becomes gold.
4. For every other record (real text, or no `triage` field): all six
   `REQUIRED_FIELDS` must be present and non-falsy — **except `line`, which is a
   zero-based index, so `line: 0` is legitimate** (`load_corrections` line 176).
5. `queue` must be in `VALID_QUEUES`.
6. **`corrected_text.strip() == ocr_text.strip()` → rejected** as
   "corrected_text equals ocr_text - nothing to record". (See §6.4 — this is a
   live risk for this batch.)
7. `confidence` is required and must be in `VALID_CONFIDENCE`.
8. `covers`, if present, must be in `VALID_COVERS`.
9. **`covers == "hemistich"` and `confidence == "full_line"` together →
   rejected** ("the crop shows both halves and only one was read"). At
   `confidence: "partial"`, `covers: "hemistich"` is **allowed**.
10. `file` is defaulted to `page_%03d.txt` if omitted.
11. **There is no "unknown field" check.** Extra JSON keys are preserved by
    `json.loads` and never validated — the ingester only ever reads the fields
    listed above.

### 1.2 Rules in `build_gold_layer()` — what happens to these records

- `triage == "not_text"` → counted (`n_not_text`), never gold.
- **`confidence != "full_line"` → counted (`n_partial`), held back from the gold
  layer entirely** — no verse is emitted, no alignment entry is created, no
  go/no-go gate sees it. If `covers == "hemistich"` it is also counted in
  `n_hemistich`. **This is the fate of every Gemini-derived record.**
- Only `full_line` records reach the gold layer, and only then does the pairing
  gate fire: `_pairing_unverified(rec)` (crop present in
  `data/review_crops/pairing.json` with `verified: false`) **downgrades the record
  to `partial` unless it carries `pairing_confirmed: true`**. The downgrade path
  is inert for this batch (everything is already partial) — **here
  `pairing_confirmed` is documentary and forward-looking only**: it pre-certifies
  the crop↔line link for a future human upgrade to `full_line`.
- `_resolve_line_index()` resolves each record's content-line index in the
  priority order **manifest `content_line_index` → content line containing
  `ocr_text`'s skeleton → the record's own `line`**. It runs on all records but
  its result is only consumed for gold-layer records, so for partials it is
  harmless.

Verified empirically: appending 3 records built to the template in §4 to a scratch
copy of the record file and dry-running the ingester yields **0 rejected**, and the
gold layer is unchanged (20 verses across 18 pages, exactly as the 92-record
baseline) — only the partial count moves (65 → 68). `myenv/bin/python -m pytest
tests/test_ingest_reviewed_corrections.py` → 35 passed.

---

## 2. Field set of the existing record file vs. the ingester

The 92 existing records use:

| field | status per ingester | notes |
|---|---|---|
| `queue` | **required** | batch 2-3 records use `vote_corrections`; batch 1 and 4-6 rows use `manual_review_queue` |
| `page` | **required** | int |
| `line` | **required** | 0-based; 0 is legitimate |
| `file` | optional | defaulted to `page_%03d.txt`; existing records carry it explicitly |
| `ocr_text` | **required** | |
| `corrected_text` | **required** (empty string allowed **only** for `triage: "not_text"`) | |
| `confidence` | **required** for real-text rows | must be in `VALID_CONFIDENCE` |
| `crop` | optional | bare filename, e.g. `p068_03.png`; `_pairing_unverified` strips any directory itself |
| `covers` | optional; **required for `full_line` on verse rows** | at `partial` either value is accepted |
| `pairing_confirmed` | optional | only consulted on `full_line` records |
| `triage` | optional | the 7 NOT_TEXT closures carry `triage: "not_text"` |
| `note` | optional | |

**Confirmed against the ingester, not by example:** `queue/page/line/ocr_text/
corrected_text/confidence` are the six required fields; everything else
(`file`, `crop`, `covers`, `pairing_confirmed`, `triage`, `note`) is optional and
defaults cleanly. The batch 2-3 records' field set is exactly this — there is no
field in use today that the ingester rejects.

---

## 3. The provenance marker: `source: "gemini_crossread"` is SAFE

The plan proposes tagging each record with `source: "gemini_crossread"`. Checked
against every consumer of the record file:

- **`load_corrections()` never reads a `source` key.** It reads only `triage`,
  the six `REQUIRED_FIELDS`, `queue`, `confidence`, `covers`, and `file`. A
  `source` key is carried through untouched.
- **`build_gold_layer()` writes a `source` key but does not read one from the
  record.** Line 345 hardcodes `"source": "reviewed_corrections"` into every
  *alignment entry it emits* — that is a constant in a different artifact
  (the gold-layer `reviewed_corrections.alignment.json`), not a field lifted from
  the record.
- **`measure_der.py:368` reads `entry.get("source")` off the alignment JSON**
  (again: the gold-layer output file, not the record file) to decide how to slice
  the OCR page. Gemini records never produce alignment entries (they are all
  partial), so this read is unaffected.
- No other script consumes `data/reviewed_corrections.jsonl`.

**Verdict: `source` is an unused-at-validation extra field → safe.** Use
`source: "gemini_crossread"`.

**One consequence to record in the spec:** because the alignment entry's `source`
is a hardcoded constant, a Gemini record that is *later* upgraded to `full_line`
by a human would enter the gold layer with `source: "reviewed_corrections"`,
silently losing its provenance. **The record's `note` must therefore begin with
the literal marker `gemini_crossread`** — that is the durable, in-band provenance
trail. (This is also why every note template below starts with it.)

---

## 4. The record template, field by field

One record per crop, appended to `data/reviewed_corrections.jsonl` as a single
JSON line, UTF-8, no trailing comma. Field order follows the existing file.

```
{"queue": "manual_review_queue",
 "page": <int: crop's page from data/review_crops/pairing.json>,
 "line": <int: the crop's content_line_index from pairing.json — NOT the triage sheet's "l.N" numbers>,
 "file": "page_%03d.txt",
 "ocr_text": <verbatim string: the queue's stored guess for this crop, pairing.json["<crop>"]["guess"]>,
 "corrected_text": <string: the adopted Gemini reading, per §4.1>,
 "confidence": "partial",
 "crop": "<bare filename, e.g. p068_03.png>",
 "covers": "<hemistich|whole_line, from the crop's region — §4.3>",
 "pairing_confirmed": <true|false, per §4.4 — omit when false is intended; see §4.4>,
 "source": "gemini_crossread",
 "note": "<per §4.5>"}
```

### 4.1 `corrected_text` — the adopted reading

**Never merge, edit, or normalize the two readings.** The corrected text is
always one of `key1` or `key2` verbatim; the letters are doubly attested and the
choice is only about diacritics.

- **If `key1 == key2`** (byte-identical): `corrected_text` = that value.
- **If they differ only in diacritics** (identical skeleton — the case for every
  AGREE row that is not byte-identical, and by definition for every MINOR row):
  `corrected_text` = **whichever of the two carries more diacritical marks**
  (count characters in `[ً-ٰٟۖ-ۭ]`, the same class the ingester's own `_skel()`
  strips). Ties → `key1`. The note must say which key was chosen.

Justification for "more fully vocalized": the letters are identical across both
keys, so no letter-level information is being invented either way; the project's
diacritics metric is diacritics-sensitive, and discarding a confident single-key
vocalization throws away evidence a human upgrader could confirm; and because the
record is `partial` it **cannot** reach the gold layer until a human looks at the
crop, so a wrong singly-attested diacritic never corrupts anything. The note
flags exactly which parts are singly attested.

- **AGREE rows:** letters identical, diacritics identical or near. Note the
  agreement score.
- **MINOR rows:** letters identical, diacritics contested. The note must state
  that **no diacritic in the reading is doubly attested** — every haraka comes
  from one key only. Everything else is identical to the AGREE case.

### 4.2 `ocr_text` — the queue's stored guess

`ocr_text` = `data/review_crops/pairing.json["<crop>"]["guess"]`, **verbatim**,
including any ` ... ` hemistich separator. This is the PaddleOCR guess the queue
row escalated with — the same `ocr_text` the batch 2-3 records use, and the field
`_resolve_line_index()` falls back on. For the 4 mis-paired crops this guess is
text of the *wrong* line; that is intentional and must be explained in the note
(§4.6).

### 4.3 `page`, `line`, `file`, `crop`, `covers`

- `page` = the crop's `page` in `pairing.json`.
- `line` = the crop's **`content_line_index`** in `pairing.json`. This equals the
  queue row's own line marker and is what the ingester resolves to first. ⚠ The
  triage/decision sheets cite lines as "p.NN l.Y" in a **different counting**
  (raw-file lines, 5 header lines included) — **do not use those numbers for
  `line`.** Verified against existing records: `p020_09` → `line: 9`, `p044_08`
  → `line: 8`, `p066_08` → `line: 8`, all matching `content_line_index`.
- `file` = `"page_%03d.txt"`.
- `crop` = the bare filename (`p068_03.png`), matching the existing records'
  style. Full paths from the crossread file also work — `_pairing_unverified()`
  applies `Path(...).name` — but bare is the house style.
- `covers`, from the crop's region in the batch sheets:
  - region `verse_left` or `verse_right` → **`"hemistich"`**
  - region `BOTH` or `full_width` → **`"whole_line"`**

  This mirrors the batch 2-3 convention the plan explicitly invokes ("the same
  gate as batches 2-3"). Note Gemini reads the *whole band*, which for a
  verse-region crop shows both hemistichs; `covers` records **what the record
  claims for its own queue row**, not what the OCR engine sampled. This only
  matters for the `n_hemistich` count, since both values are held back at
  `partial`.

### 4.4 `pairing_confirmed`

**Rule:** set `true` **only when the adopted Gemini reading is a reading of the
queue row's own line** — i.e. its skeleton matches the page content line at the
crop's `content_line_index` better than any other content line of that page. A
reading of a *different* line on the page (or of nothing on the page) is pairing
evidence for that other line, not for the row's own.

**How to determine it, in order:**

1. **Primary — skeleton test.** Read
   `data/output/عمود النسب نسخة 2/raw_text/page_%03d.txt`; build the content
   lines (non-blank, not starting with `#`, stripped) — this is the ingester's
   own `_content_lines()`. Skeletonize the adopted reading and every content line
   with the ingester's own `_skel()`: strip `[ً-ٰٟۖ-ۭـ]`, then drop every char
   outside `[ء-ي]`. `pairing_confirmed = true` iff the line at
   `content_line_index` is the unique best skeleton match for the reading.
2. **Shortcut — inherit the triage verdict**, which already ran this comparison
   against the fresh crop OCR. If the adopted Gemini reading agrees with the
   fresh crop OCR at skeleton level, take the triage classification: a note
   reading "Same line as guess (p.NN l.Y)" → `true`; "MIS-PAIRED" or "SUSPECT"
   → `false`. **Record in the note which path was used.**
3. **The manifest `verified` flag is NOT the test** — `logs/crop_pairing_audit.md`
   warns it is set at a 0.25 similarity bar and 14 `verified: true` crops score
   below 0.45 on re-OCR. Among the 48, `p111_09` is `verified: false`; the flag
   is irrelevant to `pairing_confirmed` at `partial` anyway (the downgrade gate
   only fires at `full_line`).

`false` and absent are identical to the ingester (`rec.get("pairing_confirmed")`
is a truthiness check). Prefer **explicit `false`** for the mis-paired and
suspect crops so the negative claim is visible in the data; prefer **absent**
where the test simply was not run.

### 4.5 `note` — templates

The note must name **both readings** and the **agreement score**, and must begin
with the `gemini_crossread` marker (§3). Use guillemets «» as the project's other
notes do.

**AGREE (byte-identical keys):**
```
gemini_crossread AGREE skeleton_agreement=<score>: key1=«<k1>» key2=«<k2>»; readings identical. Registered partial — no human has seen the crop (a vision-LLM reading is programmatic evidence, same rule as batch 2-3); ocr_text is the queue's stored guess. pairing_confirmed=true: reading matches p.<page> content line <line> (<which test: skeleton-test|triage verdict>).
```

**AGREE (differ only in diacritics) / MINOR:**
```
gemini_crossread <AGREE|MINOR> skeleton_agreement=<score>: key1=«<k1>» key2=«<k2>»; corrected_text = key<N> (more fully vocalized); letters identical across keys, diacritics<contest wording>. Registered partial — no human has seen the crop (a vision-LLM reading is programmatic evidence, same rule as batch 2-3); ocr_text is the queue's stored guess. pairing_confirmed=true: reading matches p.<page> content line <line> (<which test>).
```
- AGREE diacritic-difference contest wording: "differ only in diacritics — the chosen vocalization is singly attested".
- MINOR contest wording: "**contested between the keys — no diacritic in this reading is doubly attested**".

### 4.6 The 4 mis-paired crops — exact rule

`p084_15` (row 68), `p090_11` (rows 82+83), `p092_01` (rows 85+86), `p094_07`
(row 93) — confirmed mis-pairs by the independent 117-crop re-OCR
(`logs/crop_pairing_audit.md`: each scores 0.74–0.95 against a *different* line
and 0.15–0.31 against its own guess). **The queue row's stored guess is the wrong
line; the crop shows something else.**

For these, register the record as follows:

- `queue`, `page`, `file`, `crop`, `covers`, `ocr_text`, `corrected_text`,
  `confidence: "partial"` — **unchanged from the standard template.** The
  reading is still valid evidence about the *crop*, which is what the record
  documents; `ocr_text` remains the stored guess verbatim (it is the wrong line's
  text — say so in the note).
- `line` = the crop's `content_line_index` as always, **so the record stays
  anchored to the queue row it discharges.**
- **`pairing_confirmed: false` — explicitly.** The crop does not show the queue
  row's line, so the reading is *not* pairing evidence for that row. Do not set
  it true.
- The note must state, in this order:
  1. MIS-PAIRED CROP, citing `logs/crop_pairing_audit.md` / the triage sheet;
  2. **which line the crop actually shows** (from the triage sheet: p.84 l.30
     prose gloss; p.90 l.18; p.92 l.7; p.94 l.20) and that the reading is of
     *that* line;
  3. **the queue row's own line remains unread — this record does NOT confirm
     it**, and no crop in this queue shows it;
  4. **the upgrade warning:** before any future `full_line` upgrade, `line` must
     be changed to the crop's *actual* content-line index and pairing re-checked,
     because `_resolve_line_index()` resolves to the manifest's
     `content_line_index` (the wrong line) first.

**The three SUSPECT crops are handled the same way** (`p107_09` row 102 — reads
a clean prose epithet matching nothing on p.107; `p111_09` row 111 and `p111_11`
row 113 — guesses are page-number/2-char furniture from a scrambled band): the
crop's line is not the queue row's line, so `pairing_confirmed: false` and the
note explains what the crop actually shows.

### 4.7 Shared (BOTH) crops — one record, not two

`p088_03` (rows 74+75), `p090_11` (rows 82+83), `p092_01` (rows 85+86) are
full-bayt crops carrying two queue rows. **Register ONE record per crop, keyed
to the crop's own `content_line_index`, with `covers: "whole_line"`, and name
both queue rows in the note.** This follows the existing precedent (record for
`p044_08`, which notes "queue rows 36+37 share this one crop so it is one
whole_line entry, not two hemistichs"). Do not emit two hemistich records with
duplicated text.

---

## 5. Inclusion and exclusion sets

### 5.1 Inclusion set — the 48 crops of `logs/batch456_decisions.md`

All 48 are `queue: "manual_review_queue"`. `pairing` column is the default before
the §4.4 test runs on the actual Gemini readings.

**RECOVERED (29 crops, 32 queue rows):**

| crop | rows | pg | region | cl | covers | pairing default |
|---|---|---|---|---|---|---|
| p068_03 | 61 | 68 | verse_right | 3 | hemistich | true (same line) |
| p070_10 | 62 | 70 | verse_left | 10 | hemistich | true |
| p074_15 | 64 | 74 | verse_left | 15 | hemistich | true |
| **p084_15** | 68 | 84 | verse_left | 14 | hemistich | **false — MIS-PAIRED (§4.6)** |
| p086_10 | 69 | 86 | verse_left | 10 | hemistich | true |
| p087_09 | 71 | 87 | verse_left | 9 | hemistich | true |
| p087_13 | 72 | 87 | verse_right | 13 | hemistich | true |
| p088_02 | 73 | 88 | verse_right | 2 | hemistich | true |
| p088_03 | 74+75 | 88 | BOTH | 3 | whole_line | true (one record, §4.7) |
| p089_01 | 79 | 89 | verse_left | 1 | hemistich | true |
| **p090_11** | 82+83 | 90 | BOTH | 14 | whole_line | **false — MIS-PAIRED (§4.6)** |
| p092_00 | 84 | 92 | verse_right | 0 | hemistich | true |
| **p092_01** | 85+86 | 92 | BOTH | 2 | whole_line | **false — MIS-PAIRED (§4.6)** |
| p092_04 | 87 | 92 | full_width | 4 | whole_line | true (MARGINAL, still same line) |
| p092_07 | 89 | 92 | verse_right | 7 | hemistich | true |
| p093_00 | 90 | 93 | verse_left | 0 | hemistich | true (MARGINAL) |
| p093_02 | 91 | 93 | verse_left | 2 | hemistich | true (MARGINAL) |
| **p094_07** | 93 | 94 | verse_left | 5 | hemistich | **false — MIS-PAIRED (§4.6)** |
| p098_00 | 94 | 98 | verse_left | 0 | hemistich | true |
| p098_12 | 95 | 98 | verse_left | 12 | hemistich | true |
| p098_15 | 96 | 98 | verse_right | 15 | hemistich | true |
| p104_00 | 99 | 104 | verse_left | 0 | hemistich | true (MARGINAL) |
| p104_05 | 100 | 104 | verse_left | 5 | hemistich | true |
| p106_15 | 101 | 106 | verse_right | 15 | hemistich | true (MARGINAL) |
| **p107_09** | 102 | 107 | verse_left | 12 | hemistich | **false — SUSPECT (§4.6)** |
| p108_13 | 104 | 108 | verse_left | 13 | hemistich | true |
| p110_07 | 105 | 110 | verse_left | 7 | hemistich | true |
| **p111_09** | 111 | 111 | full_width | 9 | whole_line | **false — SUSPECT (§4.6)** |
| **p111_11** | 113 | 111 | full_width | 12 | whole_line | **false — SUSPECT (§4.6)** |

**DEGRADED (19 crops, 19 queue rows)** — `pairing` must be decided by the §4.4
skeleton test on the Gemini reading; the PaddleOCR similarity the triage sheet
reports is **not** the test:

| crop | row | pg | region | cl | covers | pairing note |
|---|---|---|---|---|---|---|
| p071_11 | 63 | 71 | verse_right | 11 | hemistich | test — best page match is own line (sim 0.23) |
| p077_14 | 65 | 77 | verse_left | 14 | hemistich | test — own line (0.14) |
| p082_06 | 66 | 82 | verse_right | 6 | hemistich | test — own line (0.36) |
| p084_03 | 67 | 84 | verse_left | 3 | hemistich | test — own line (0.21) |
| p086_14 | 70 | 86 | verse_left | 14 | hemistich | test — own line (0.30) |
| p088_05 | 76 | 88 | verse_right | 5 | hemistich | test — own line (0.18) |
| p088_06 | 77 | 88 | verse_left | 6 | hemistich | test — own line (0.11) |
| p088_07 | 78 | 88 | verse_left | 7 | hemistich | test — own line (0.08) |
| p089_12 | 80 | 89 | verse_left | 12 | hemistich | test — own line (0.21) |
| p090_08 | 81 | 90 | verse_left | 8 | hemistich | test — 5 fragmentary letters |
| p092_06 | 88 | 92 | verse_right | 6 | hemistich | test — own line (0.14) |
| p093_06 | 92 | 93 | verse_left | 6 | hemistich | test — own line (0.23) |
| p100_01 | 97 | 100 | verse_left | 1 | hemistich | test — OCR diverges from guess, likely false |
| p101_12 | 98 | 101 | verse_left | 12 | hemistich | test — both readings fragments |
| p108_03 | 103 | 108 | verse_left | 3 | hemistich | test — 8 usable letters |
| p111_00 | 106 | 111 | full_width | 0 | whole_line | test — p.111 band↔line mapping scrambled |
| p111_05 | 109 | 111 | full_width | 5 | whole_line | test — scrambled page |
| p111_17 | 117 | 111 | full_width | 14 | whole_line | **false — audit mis-pair (own 0.32 vs cl 13 at 0.67)** |
| p111_21 | 118 | 111 | full_width | 18 | whole_line | test — scrambled page |

### 5.2 Exclusions — crops that get NO record from the crossread

1. **`status: "error"` in the crossread file** (API failure / timeout / one key
   returned nothing) — no reading pair to compare.
2. **Blank-control failure** for either key on that crop's call — a key that
   hallucinated on the blank produced an unusable reading; the plan aborts the
   run on control failure, and any per-crop control failure excludes that crop.
3. **Verdict DISAGREE** — the keys differ at the letter level, so no part of the
   reading is doubly attested. Needs a human.
4. **The 7 NOT_TEXT crops, already closed** as `triage: "not_text"` in the record
   file (records for `p111_01`, `p111_02`, `p111_06`, `p111_10`, `p111_12`,
   `p111_13`, `p111_14`) — a second record would duplicate the closure. These sit
   outside the 48 anyway.
5. **Any crop whose adopted reading byte-equals its stored guess** — the ingester
   rejects it as a no-op ("nothing to record", §1.1 rule 6). Skip it; log it.

**⚠ Explicitly NOT an exclusion criterion: the PaddleOCR triage class.** A
DEGRADED crop is only "degraded" for PaddleOCR; Gemini is a different reader. A
DEGRADED crop whose two Gemini keys AGREE registers as partial. Conversely a
RECOVERED crop whose keys DISAGREE is excluded. **Only the Gemini verdict gates
registration.**

---

## 6. Worked examples

Values below are **illustrative examples** (the first mirrors the real first
crossread row, `p068_03`, whose two keys differ only in diacritics and an
Arabic-vs-Persian two; verdicts and scores are placeholders pending the
reconciliation step).

### 6.1 MINOR, verse-region, pairing confirmed

```json
{"queue": "manual_review_queue", "page": 68, "line": 3, "file": "page_068.txt",
 "ocr_text": "وعاادَقَلَهُمربكَُلْ مُرَْق ... مَصَالالِح قَبْلُْ وَْ يََّْْق",
 "corrected_text": "وَعَادٌ فَلَهُمْ (٢) بِكُلِّ مُزَمَّقٍ مَصَالِحُ قَبْلُ وَلَمْ يُمَزَّقِ",
 "confidence": "partial", "crop": "p068_03.png", "covers": "hemistich",
 "pairing_confirmed": true, "source": "gemini_crossread",
 "note": "gemini_crossread MINOR skeleton_agreement=0.97: key1=«وَعَادَ فَلَهُمْ (۲) بِكُلِّ مُمَزَّقٍ مَصَالِحُ قَبْلُ وَلَمْ يُمَزَّقِ» key2=«وَعَادٌ فَلَهُمْ (٢) بِكُلِّ مُزَمَّقٍ مَصَالِحُ قَبْلُ وَلَمْ يُمَزَّقِ»; corrected_text = key2 (more fully vocalized); letters identical across keys, diacritics contested between the keys — no diacritic in this reading is doubly attested. Registered partial — no human has seen the crop (a vision-LLM reading is programmatic evidence, same rule as batch 2-3); ocr_text is the queue's stored guess. pairing_confirmed=true: reading matches p.68 content line 3 (triage verdict: same line as guess)."}
```

### 6.2 AGREE, BOTH crop shared by two queue rows

```json
{"queue": "manual_review_queue", "page": 88, "line": 3, "file": "page_088.txt",
 "ocr_text": "نَسَََْيُْمَُْمََينَا ... عشررَ االأزْدَالاسشعَرينَا",
 "corrected_text": "نَسَبَ حَيُّ رُمْرُمٍ بَيْنَا عَشَرَةُ الأَزْدِ الأَشْعَرِينَا",
 "confidence": "partial", "crop": "p088_03.png", "covers": "whole_line",
 "pairing_confirmed": true, "source": "gemini_crossread",
 "note": "gemini_crossread AGREE skeleton_agreement=1.00: key1=«<k1>» key2=«<k2>»; readings identical. BOTH crop carrying queue rows 74+75 as one whole_line entry (§4.7), not two hemistich records. Registered partial — no human has seen the crop (a vision-LLM reading is programmatic evidence, same rule as batch 2-3); ocr_text is the queue's stored guess. pairing_confirmed=true: reading matches p.88 content line 3 (skeleton-test)."}
```

### 6.3 AGREE on a mis-paired crop (the §4.6 rule)

```json
{"queue": "manual_review_queue", "page": 84, "line": 14, "file": "page_084.txt",
 "ocr_text": "نَالُوا بخَدْع زَهْرة الحياقِ ... ومَا لَهُمْ حَردَّلَةَرفي الآَِي",
 "corrected_text": "الخَدْعُ مِنَ الخَدِيعَةِ والخَرْدَلِ خَبَرٌ شَحْرٌ أَيُّ القَلِيلِ التَّافِه",
 "confidence": "partial", "crop": "p084_15.png", "covers": "hemistich",
 "pairing_confirmed": false, "source": "gemini_crossread",
 "note": "gemini_crossread AGREE skeleton_agreement=0.98: key1=«<k1>» key2=«<k2>»; readings identical. MIS-PAIRED CROP (logs/crop_pairing_audit.md: own-line sim 0.30 vs 0.95 for the prose gloss): the reading is of the شرح/حاشية gloss the crop actually shows (p.84 l.30 raw), NOT the verse at l.21 named by queue row 68's stored guess — this record does NOT confirm row 68's own line, which remains unread and is shown by no crop in this queue. ocr_text is that wrong-line guess, kept verbatim. Before any full_line upgrade, set line to the crop's actual content-line index and re-check pairing: _resolve_line_index() resolves to the manifest content_line_index (the wrong line) first."}
```

### 6.4 What a rejection looks like (do NOT append)

```json
{"queue": "manual_review_queue", "page": 111, "line": 0, "file": "page_111.txt",
 "ocr_text": "uوباa", "corrected_text": "uوباa", "confidence": "partial",
 "crop": "p111_00.png", "covers": "whole_line", "source": "gemini_crossread",
 "note": "..."}
```
→ rejected by `load_corrections` ("corrected_text equals ocr_text - nothing to
record"). If Gemini returns exactly the stored guess, there is nothing to record —
skip the crop and log it.

---

## 7. Pre-append checklist (run every record through this before writing)

1. `queue` == `"manual_review_queue"` (in `VALID_QUEUES`).
2. `page`, `line`, `ocr_text`, `corrected_text`, `confidence` all present and
   non-falsy; `line` is the crop's `content_line_index` (0 is valid).
3. `corrected_text.strip() != ocr_text.strip()`.
4. `confidence` == `"partial"` — **never `full_line` from Gemini.**
5. `covers` is `"hemistich"` (verse_left/verse_right) or `"whole_line"`
   (BOTH/full_width). (`hemistich`+`partial` is valid; only `hemistich`+`full_line`
   is rejected.)
6. `crop` is the bare filename and exists in `pairing.json`.
7. `pairing_confirmed` is `true` only per the §4.4 test; `false`/absent otherwise.
8. `source` == `"gemini_crossread"`.
9. `note` begins with `gemini_crossread`, names both readings verbatim, gives the
   agreement score, and states the diacritic attestation.
10. Exactly one record per crop (BOTH crops: one record, both rows named).
11. Valid single-line JSON, UTF-8.

**Post-append, before anything else:** dry-run the ingester and require
**0 rejected**:

```
myenv/bin/python scripts/ingest_reviewed_corrections.py
```

Expect the partial count to rise by the number of appended records and the
"gold layer would add" figures to be **identical to the pre-append baseline**
(20 verses across 18 pages). Only if both hold is the batch safe; then and only
then may `--apply` be considered — and it changes nothing for these records,
since partials never reach the gold layer.

---

## 8. What this batch does not do

- **No `full_line`, anywhere.** The conservative rule is the project's core design
  decision; a vision-LLM reading is supporting evidence, not a confirmation.
- **No gold-layer change.** Verified: partials are counted and held back; the
  gold layer output is byte-for-byte unaffected by this batch.
- **No `data/output` regeneration** (the 251-file invariant stays intact), no
  `main.py`, no external API calls (the Gemini budget belongs to the crossread
  agent).
- **No silent adoption.** Every record carries `source: "gemini_crossread"` and a
  note beginning with the same marker, so the whole batch is isolable and
  revertable (`grep '"source": "gemini_crossread"' data/reviewed_corrections.jsonl`).
- **Nothing is appended by this document.** The crossread data does not exist
  yet; this is the specification only.
