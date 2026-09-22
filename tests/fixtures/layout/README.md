# Page-layout regression fixtures (`page_layout_detector`)

Golden fixtures for `tests/test_page_layout_detector.py`, locking the
current tuned behavior of:

- `detect_horizontal_gaps()`
- `detect_separator_lines()`
- `find_footnote_boundary()`

in `src/pipeline/preprocessing/page_layout_detector.py`.

## How they were generated

`generate_fixtures.py` replays the **exact production chain** that
`main.py` runs for every page:

```
pymupdf render @ 200 DPI            (main.py:904)
  -> cv2 RGB->BGR                   (input_handler.py:158)
  -> preprocess_page                (deskew -> CLAHE -> denoise, main.py:970)
  -> layout.binarize                (adaptive threshold, text=255 / bg=0)
  -> layout.dilate_text
  -> layout.find_components
  -> layout.remove_border_components
  -> layout.compute_content_bbox
```

Source: `data/input/عمود النسب نسخة 2.pdf`, pages **4, 8, 27, 28, 95, 111**.
DPI is pinned at **200**, the resolution every absolute-pixel constant in
`page_layout_detector.py` was tuned at (see the spec-010 block); at 200 DPI
`layout.set_dpi_scale()` is the identity.

The generator then snapshots the three functions' actual outputs as the
golden values. The goldens are therefore a *regression lock*, not an
independent re-derivation of "what the answer should be".

## Files

Per page `NNN`:

| File | Contents |
|---|---|
| `page_NNN_binary.png` | full-page post-binarize `uint8` image, 0/255 (text white) |
| `page_NNN_boxes.json` | `{"page": N, "boxes": [[x,y,w,h], ...]}` |
| `page_NNN_cb.json` | `{"page": N, "content_bbox": [x1,y1,x2,y2]}` |
| `page_NNN_expected.json` | golden `boundaries` (10 fields), `gaps`, `separators`, `note` |
| `manifest.json` | index of pages + score class + file names |

The tests load only these files — never the PDF, OCR stack, or
`preprocess_page` (which are out of scope for these unit-level regression
tests).

## Fixture coverage

| Page | Score class | What it locks |
|---|---|---|
| 28 | 3/3, cut | gap + separator + smaller-text all agree |
| 4 | 2/3, cut, **no separator** | gap + smaller-text is enough to cut |
| 95 | 2/3, cut | gap + separator (same-size text below) |
| 27 | 1/3, **not cut** | **a separator WAS detected but isolated** — near-miss for the review's false-positive risk #1/#2 |
| 8 | 1/3, not cut | many gaps, no separator → gap-only never cuts |
| 111 | 1/3, not cut | sparse page, no separator |

Page 27's `note` explicitly records that `has_separator=True` at y=3421 and
that the page stays uncut only because no gap lies within `match_tolerance`.
It must **not** be read as an absence-of-detection case.

Behavior that no real manuscript page exercises deterministically (the
adversarial gap+rule coincidence, the `MIN_GAP_HEIGHT_PX` 11-vs-12 px
boundary, the bottom-exclusion band, the trailing-gap hole, empty regions)
is covered by synthetic, in-test fixtures in
`tests/test_page_layout_detector.py`.

## Regenerating

```bash
myenv/bin/python tests/fixtures/layout/generate_fixtures.py
```

The generator fails loudly if an upstream change moves any page into a
different score class (`EXPECTED_CLASS`), so fixtures cannot silently lose
their intended coverage. Otherwise it rewrites the JSON goldens in place.

**If the detector's tuned constants, scoring, or upstream preprocessing
change, re-run the generator and review the resulting git diff of the JSON
goldens deliberately** — do not accept the overwrite without confirming the
new values are intended.
