# Batch 4-6 pairing audit — all 57 crops on pages 68-111

**What this is.** An independent re-check of whether each crop image actually shows the
line the queue row points at. Motivated by the `p059_10` error (`logs/batch3_verification.md`):
that record was registered from the wrong half of the right verse, and the mistake survived
because on in-GT pages a high GT-match score makes a wrong reading *look* verified. Pages
68-111 have **no ground truth at all**, so nothing masks a pairing error there — this audit
is the only structural check available before a human opens the crops.

**Method.** Every crop was re-OCRed with the same engine the pipeline uses
(`arabic_PP-OCRv5_mobile_rec`), diacritics and non-letters stripped, then compared by
`difflib.SequenceMatcher` against its own indexed content line and against **every other
content line on the same page**. If a crop's best match is another line by a wide margin,
the crop is mis-paired — the renderer drew the wrong band. Margin = best-other − own.

**This model cannot view images.** Every number here is PaddleOCR character similarity. It
establishes *pairing*, not *reading*. A high score means the crop and the line are the same
text; it does not mean the text is a correct transcription of the manuscript. Nothing here
is confirmed, and no record was created or changed by this audit.

## Result: 57 crops in four groups

| Group | Crops | Meaning |
|---|---|---|
| **A. Strong mis-pair** (other line wins by ≥0.35) | **7** | crop definitively shows a different line |
| **B. Suspect pair** (margin 0.12–0.35) | **3** | another line edges ahead; pairing unproven |
| **C. Clean pairing, crop unreadable** (own <0.45) | **4** | pairing fine, but OCR too weak to transcribe |
| **D. Clean pairing, crop readable** (own ≥0.45) | **43** | pairing holds and a candidate reading exists |

### A. Strong mis-pair — 7 crops

These **cannot be read as the row they are filed under.** Grouped by what the crop really is:

**Prose/gloss lines, not verse — 2 crops**

| Crop | Filed as | Crop actually shows | Margin |
|---|---|---|---|
| `p084_15.png` | cl14 `نَالُوا بخَدْع زَهْرة الحياقِ…` | cl19 `الخدع من الخديعة…` — a شرح gloss line | +0.65 |
| `p094_07.png` | cl5 `ووَِأتبنِِأل الْيمَنْ…` (near-noise) | cl13 `عوف بن عفرا…` | +0.57 |

`p084_15` is the clearest case in the set: the crop OCR is *identical* prose
(`الخدع من الخديعة والخردل`) at 0.95 against a commentary line. The queue asked about a
verse; the crop is a footnote to it. Confirms the sheet's `p084_15` call.

**Crop belongs to a different line index entirely — 5 crops**

| Crop | Filed as | Best match | Margin |
|---|---|---|---|
| `p111_01.png` | cl3 (0.00) | cl1 (1.00) | +1.00 |
| `p111_14.png` | cl11 (0.00) | cl10 (0.67) | +0.67 |
| `p092_01.png` | cl2 (0.15) | cl1 (0.74) | +0.59 |
| `p090_11.png` | cl14 (0.31) | cl11 (0.85) | +0.54 |
| `p111_17.png` | cl14 (0.32) | cl13 (0.67) | +0.35 |

`p111_01` is total: the crop has **zero** overlap with its filed line and a **perfect** 1.00
match to a different line. These are renderer/queue-offset defects, not OCR noise — the
image is clean, it is simply the wrong band.

`p090_11` and `p092_01` are filed `BOTH` (queue rows 82/83 and 85/86), so each mis-pair
silently invalidates **two** queue rows. That is 4 of the 51 rows in the decision sheet.

### B. Suspect pair — 3 crops

Another line wins, but by too little to call on OCR alone. **Do not register as clean.**

| Crop | Filed as | Best match | Margin | Note |
|---|---|---|---|---|
| `p111_09.png` | cl9 (0.10) | cl5 (0.38) | +0.28 | filed guess is a page-number fragment; low absolute scores throughout |
| `p111_11.png` | cl12 (0.19) | cl18 (0.39) | +0.20 | crop OCR is a 2-char fragment `يو`; pairing untestable |
| `p111_10.png` | cl8 (0.40) | cl3 (0.57) | +0.17 | closest call in the group; both scores low |

All three are page-111 crops with near-empty OCR, so the margin reflects noise rather than a
real competing line. They need a human, not a threshold.

### C. Clean pairing, crop unreadable — 4 crops

Pairing holds (own line wins or ties) but the crop yields too little to transcribe. These are
**not** mis-pairs; they are simply unreadable at this crop width.

| Crop | Own line | Own sim | Best | Note |
|---|---|---|---|---|
| `p111_13.png` | cl13 | 0.17 | cl8 (0.29) | index furniture; low scores, best line irrelevant |
| `p108_03.png` | cl3 | 0.33 | cl3 (0.33) | **own line still the best match** — pairing fine, glyphs unreadable |
| `p107_09.png` | cl12 | 0.37 | cl17 (0.45) | own sim below the 0.45 read floor |
| `p090_14.png` | cl14 | 0.44 | cl14 (0.44) | own line wins; one notch under the read floor |

Note the sheet calls `p107_09`'s PaddleOCR output "the cleanest OCR in the batch" (0.79) —
that is the *engine's* confidence, which this audit shows is misleading: the text it produced
(`الحذم القاطع الشجاع`) matches no line on the page. Confident and wrong is the exact failure
mode a confidence number invites.

### D. Clean pairing, readable — 43 crops

Own line is the best match by a clear margin (typically 0.62–0.91). Pairing is sound and a
candidate reading exists for each. **Still not confirmations** — a human must read the crop
before any of these becomes `full_line`, and none of them can become `full_line` from
automation at all, since pages 68-111 are outside ground truth.

## Cross-check against the decision sheet

The sheet's existing calls are **corroborated**:
- Its 4 named mis-pairs — `p084_15`, `p090_11`, `p092_01`, `p094_07` — all appear in group A.
- Its "suspect" rows `p111_09` and `p111_11` appear in group B.
- Its reading of `p107_09` as misleadingly confident is confirmed.

This audit **adds** three crops the sheet did not flag:
- `p111_01.png` — strongest mis-pair in the entire set (margin +1.00), unflagged by the sheet.
- `p111_14.png` — clear mis-pair (own sim 0.00), unflagged.
- `p111_17.png` — mis-pair at +0.35, the sheet had it only as a low-confidence row.

All three are page-111 crops, consistent with page 111's already-known index-furniture and
band-offset problems. Together with `p111_01`, `p111_14`, `p111_17` this brings the confirmed
mis-pair count for pages 68-111 to **7**.

One apparent discrepancy is **not** a conflict: the sheet cites `p084_15`'s gloss as "p.84
l.30" and the queue target as "l.21", while this audit reports cl19/cl14. Those are the same
lines under two numbering schemes (raw file line vs content-line index after headers are
stripped) — verified to land on identical text.

## Addendum: `verified: true` was not a text claim, and the correct band is not text-findable

Two follow-ups, both established by re-rendering the affected pages and re-reading the
renderer's pairing logic.

### The `verified` flag meant "index arithmetic", not "text confirmed"

All 7 group-A crops carried `verified: true` in `data/review_crops/pairing.json`. That flag is
**not** evidence that the crop matches its guess. `render_review_crops.py` sets it from how the
band was *chosen* — `"paired" in tag` — which is true for both the positional shortcut
(`counts_agree`: stored index **is** band index, no text check at all) and the text-searched
path. It never compares the rendered band to the stored guess. So `verified: true` means "we
used an index", and the guard at `ingest_reviewed_corrections.py:281` that refuses to grade an
unverified crop `full_line` was **inert for these 7 rows** — the flag it checks was asserting a
confirmation that the audit disproves.

The renderer does have a textual floor (0.25, `render_review_crops.py:247`), but it is far too
low to catch this: `p084_15`'s 66-char guess scores 0.30 against the *wrong* band and passes.

`verified` has been retracted to `false` on all 7, each tagged `MISPAIRED(...)` with a
`pairing_audit` block naming the line the crop actually shows, its similarity, and the source.
Nothing else in the manifest changed.

### Why the crops were NOT re-rendered at the "correct" band

Re-rendering all 117 crops and scoring guess-vs-assigned-band similarity shows the score **cannot
separate mis-pairs from sound pairings**:

| guess-vs-band score | crops | of which mis-paired |
|---|---|---|
| 0.00–0.25 | 3 | 0 |
| 0.25–0.35 | 9 | 3 |
| 0.35–0.45 | 5 | 3 |
| 0.45–0.55 | 12 | 0 |
| 0.55–0.70 | 24 | 1 |
| 0.70–1.00 | 57 | 0 |

6 of the 7 mis-pairs sit under 0.45, but so do 17 crops that are paired correctly, and
`p111_14` — whose crop scores **0.00** against its own line — reaches 0.60 against the wrong one.
The score compares a *stored guess* from an older OCR run against a *fresh* band read, so it
carries OCR drift, and page-111 dot-leader lines are near-identical to each other by
construction. Any floor that catches these 6 also condemns ~17 good crops; any floor that
preserves the good ones lets `p111_14` through.

So the correct band was **not** re-rendered for these rows. Picking one would mean guessing from
noise, which is the same failure that produced `p059_10`. Only `p092_01` has even a suggestive
case (its guess prefers band2 at 0.54 over the current band1 at 0.38), and 0.54 is not a
confirmation.

**What this needs:** a human reading the crop, or a vision model once image quota allows. Both
have to answer "which line of this page is this image?", which OCR on a drifted guess cannot.
Until then these 10 queue rows are correctly *blocked* — `verified: false` is the honest state,
and it stops them from being registered as `full_line` off a crop that shows the wrong line.

- **7 crops (10 queue rows)** must not be read as filed. `p090_11` and `p092_01` are `BOTH`
  rows, so each costs two rows. These need re-cropping at the correct band, not review.
- **3 crops** are unprovable pairings; treat as unread until a human looks.
- **4 crops** are correctly paired but unreadable; re-crop wider before spending review time.
- **43 crops** are sound candidates, and are the only realistic source of movement on pages
  68-111 — but they need human eyes, because no gold exists to confirm them against.

The Gemini cross-read does **not** rescue any of this. A vision LLM reading a mis-paired crop
returns a fluent reading of the *wrong* line, and two keys agreeing on the wrong line is still
the wrong line. Pairing has to be fixed by re-cropping first; the cross-read is only worth
running on group D.