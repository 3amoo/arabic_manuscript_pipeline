# Arabic Manuscript Pipeline — Fix Plan

> **Purpose:** This document is a complete, atomic-task implementation plan for Claude (or any agent).
> Every task is self-contained, lists the exact file(s) to change, the exact lines where the change
> goes, and why the change matters. Tasks are ordered so later tasks never depend on something
> earlier that has not yet landed.

---

## Background — Project Architecture

The project is an end-to-end OCR pipeline for classical Arabic manuscripts (poetry + commentary).

```
arabic_manuscript_pipeline/
├── main.py                            # entry point & orchestrator (1 102 lines)
├── config/
│   ├── settings.yaml                  # all runtime configuration
│   └── prompts.yaml                   # LLM prompts
├── src/pipeline/
│   ├── ingestion/
│   │   └── input_handler.py           # PDF + image loading
│   ├── preprocessing/
│   │   ├── preprocessing.py           # deskew / CLAHE / denoise
│   │   ├── page_layout_detector.py    # content bbox, footnote boundary
│   │   └── segment_text_rows.py      # row segmentation, gutter detection
│   ├── ocr/
│   │   ├── ocr_engine.py             # PaddleOCR wrapper
│   │   ├── ocr_cache.py              # SQLite BLAKE2b cache
│   │   ├── vision_fallback.py        # per-line LLM vision escalation
│   │   └── surya_line_detector.py    # optional ML line detector
│   ├── correction/
│   │   ├── text_correction_engine.py  # LLM text correction backends
│   │   └── repeated_verbatim_tracker.py  # hallucination rejection DB
│   ├── output/
│   │   ├── output_generator.py        # page + manuscript saving
│   │   └── review_manuscript.py       # second-stage correction runner
│   └── evaluation/                    # CER/WER/diacritics metrics
├── tests/                             # 193 tests; 2 currently failing
├── .env                               # ⚠️ CONTAINS LIVE KEYS - see Task 01
├── .gitignore
├── requirements.txt
├── verify_all.py                      # 4-check end-to-end verification tool
└── README.md                          # ⚠️ STALE - describes old flat layout
```

**Pipeline flow (main.py):**
1. `InputHandler.load_file()` renders PDF pages → numpy BGR arrays  
2. `preprocess_page()` → deskew → CLAHE → denoise  
3. `layout.binarize()` + `layout.find_components()` + `layout.remove_border_components()`
   → **missing:** `layout.remove_page_footer_components()` → `layout.compute_content_bbox()`  
4. `layout.find_footnote_boundary()` splits poetry body from prose/commentary  
5. `rowseg` detects rows + gutter; routes each page to `extract_poetry_region()` or `extract_prose_region()`  
6. `OCREngine.extract_segments_batch()` runs PaddleOCR; `vision_fallback` escalates low-confidence lines  
7. **BUG:** `output_generator.save_page()` receives `page_result['prose_text']` but only saves `page_result['text']` — commentary is lost  
8. Optional: `review_manuscript.py` sends each page through `TextCorrectionEngine`

**Test runner:** `HOME=/path/that/exists ./myenv/bin/pytest tests/`  
PaddleX tries to `mkdir($HOME/.paddlex)` at import time; run tests with a writable `HOME`.

**Current test status (2026-09-20):** 189 pass, 2 fail (see Task 03), 2 skip.

---

## Group A — Security & Credentials (Do First)

### Task 01 — Revoke & Remove Live API Keys from Repository
**Priority: CRITICAL**  
**Files:** `.env`, `.gitignore`

**Problem:**  
`.env` (10 lines) contains live production keys committed to the repository:
```
GEMINI_API_KEY1=AQ.Ab8RN6J4...
GEMINI_API_KEY2=AQ.Ab8RN6J...
GROQ_API_KEY1=gsk_qmAq8At...
GROQ_API_KEY2=gsk_iBDq63...
OPENROUTER_API_KEY=sk-or-v1-...
GITHUB_API_KEY=github_pat_11A66...
COHERE_API_KEY=cohere_KXBn7...
SOVEREIGN_API_KEY=sk-wGX7B2c...
ATRIA_API_KEY=atr_fYsJ9n...
```

**Actions:**
1. Revoke every key listed above on the provider dashboards (Gemini/Google AI Studio, Groq console, OpenRouter, GitHub, Cohere, Sovereign, Atria).
2. Generate fresh replacement keys on each provider.
3. Replace the content of `.env` with fresh keys (never commit it — it is in `.gitignore`).

---

### Task 02 — Fix `.gitignore` Corruption + Create `.env.example`
**Priority: CRITICAL**  
**Files:** `.gitignore`, `.env.example` (new file)

**Problem 1:** Line 2 of `.gitignore` reads:
```
echo ".env" >> .gitignore
```
This is a shell command accidentally inserted as a file entry. It does nothing useful and pollutes the ignore list.

**Fix:** Delete line 2 of `.gitignore` entirely.

**Problem 2:** `.env.example` does not exist. `README.md:37` refers to it but it's missing.

**Fix:** Create `.env.example` at the repo root with all key names and placeholder values:
```bash
# Copy this file to .env and fill in your real API keys.
# Never commit .env to version control.

GEMINI_API_KEY1=your_gemini_api_key_here
GEMINI_API_KEY2=your_second_gemini_api_key_here
GROQ_API_KEY1=your_groq_api_key_here
GROQ_API_KEY2=your_second_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
GITHUB_API_KEY=your_github_models_api_key_here
COHERE_API_KEY=your_cohere_api_key_here
SOVEREIGN_API_KEY1=your_sovereign_api_key_1_here
SOVEREIGN_API_KEY2=your_sovereign_api_key_2_here
ATRIA_API_KEY=your_atria_api_key_here
```

**Note on key name mismatch (also fix in this task):**  
`config/settings.yaml` lines 196–199 expect `SOVEREIGN_API_KEY1` and `SOVEREIGN_API_KEY2`, but the current `.env` only defines `SOVEREIGN_API_KEY` (no suffix). The `.env.example` above already uses the correct names. Update the new `.env` accordingly.

---

## Group B — Data Loss Fixes (Do Second)

### Task 03 — Save Prose/Commentary Text in `save_page()`
**Priority: CRITICAL**  
**File:** `src/pipeline/output/output_generator.py`

**Problem:**  
`main.py:959–968` builds `page_result` with both `'text'` (poetry) and `'prose_text'` (commentary):
```python
page_result = {
    'page_num': page_num,
    'text': page_ocr['text'],
    'prose_text': page_ocr['prose_text'],   # <-- extracted but never saved
    ...
}
output_generator.save_page(document_name, page_result)
```

`save_page()` at `output_generator.py:83` only reads `text = page.get('text', '')`. The `prose_text` value is silently ignored. All commentary/margin text is lost for every page where the layout detector found it.

**Fix:**  
In `output_generator.py`, in `save_page()`, after line 83 (`text = page.get('text', '')`), add:

```python
prose_text = page.get('prose_text') or ''
if prose_text:
    full_body = f"{text}\n\n--- الشرح والحاشية ---\n\n{prose_text}"
else:
    full_body = text
```

Then on lines 97–100, change `{text}` to `{full_body}`:
```python
filename.write_text(
    f"{chr(10).join(header_lines)}\n\n{full_body}",
    encoding='utf-8',
)
```

Also update `_page_texts` on line 102 to store the full combined body:
```python
self._page_texts.setdefault(document_name, {})[page_num] = full_body
```

**Verify:** After this change, pages with commentary (where `prose_text is not None`) will have their commentary appended in `page_XXX.txt` and included in `full_manuscript.txt`.

---

### Task 04 — Apply Footer Filter Before Content BBox Computation
**Priority: CRITICAL**  
**File:** `main.py`

**Problem:**  
`page_layout_detector.py` exports `remove_page_footer_components()` (line 449) specifically to strip isolated page-number blobs (e.g., `{21}`) that would otherwise stretch `compute_content_bbox()` downward past the real content. However, in `main.py:729–754`, the boxes from `remove_border_components()` flow directly into `compute_content_bbox()` without calling `remove_page_footer_components()`.

**Exact location in `main.py`:** around line 731:
```python
# BEFORE (current):
boxes = layout.remove_border_components(
    layout.find_components(dilated), image.shape[1], image.shape[0]
)
# ... boxes fed directly to compute_content_bbox() at line 754
```

**Fix:** Insert one line between `remove_border_components()` and the `if not boxes:` guard:
```python
boxes = layout.remove_border_components(
    layout.find_components(dilated), image.shape[1], image.shape[0]
)
boxes = layout.remove_page_footer_components(boxes, image.shape[1], image.shape[0])
```

The `if not boxes:` guard that follows still works correctly (if the footer was the only component, the page is correctly flagged as blank/unclear).

---

## Group C — Crash Fixes (Do Third)

### Task 05 — Fix Unhandled Image Modes in `_load_image()`
**Priority: CRITICAL**  
**File:** `src/pipeline/ingestion/input_handler.py`

**Problem:**  
`_load_image()` at lines 165–167 only converts `(H, W, 3)` RGB arrays to BGR. It passes through:
- Grayscale images → `(H, W)` 2D array → `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)` in `deskew_page()` crashes with `!scn || scn == 3 || scn == 4`.
- RGBA PNGs → `(H, W, 4)` 4-channel array → same crash.
- 1-bit (palette/mode-P) images → also fails.

**Fix:** Replace lines 157–167 in `_load_image()` with unconditional normalization:
```python
# Open with PIL and normalize to RGB before any further processing.
# Handles grayscale, RGBA, palette, 1-bit, and any other PIL mode.
img = Image.open(file_path).convert("RGB")

import numpy as np
import cv2
# PIL is RGB; OpenCV (and everything downstream) expects BGR.
img_array = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
```

Remove the old `if len(img_array.shape) == 3 and img_array.shape[2] == 3:` conditional block.

---

### Task 06 — Guard Zero-Width / Zero-Height Crops Before PaddleOCR
**Priority: CRITICAL**  
**File:** `main.py`

**Problem:**  
In `main.py:452–474`, verse-row crops from `rowseg.crop_nonempty_x()` are appended to `all_crops` unconditionally. When the gutter estimate places a boundary at or beyond the image edge (e.g., `gutter_left <= 0`), the crop has shape `(H, 0, 3)`. Passing a zero-dimension array to PaddleOCR triggers an unhandled low-level crash.

**Fix:** Wrap the `all_crops.append()` calls inside a dimension guard. Change lines 460–463:
```python
# BEFORE:
right_idx = len(all_crops)
all_crops.append(right_img)
left_idx = len(all_crops)
all_crops.append(left_img)
```

```python
# AFTER:
right_idx = len(all_crops)
if right_img.shape[0] > 0 and right_img.shape[1] > 0:
    all_crops.append(right_img)
else:
    right_img = None  # will produce an empty OCR result below

left_idx = len(all_crops)
if left_img.shape[0] > 0 and left_img.shape[1] > 0:
    all_crops.append(left_img)
else:
    left_img = None
```

Then wherever `right_img` / `left_img` are used for OCR results later in the same function, check for `None` and emit an empty string result.

---

### Task 07 — Fix Bare `except:` in `get_file_info()`
**Priority: CRITICAL**  
**File:** `src/pipeline/ingestion/input_handler.py`

**Problem:**  
`get_file_info()` at lines 209–210:
```python
except:
    info['pages'] = None
```
A bare `except:` catches `KeyboardInterrupt`, `SystemExit`, and `MemoryError`, preventing Ctrl-C from stopping the pipeline.

**Fix:** Change to:
```python
except Exception:
    info['pages'] = None
```

---

## Group D — Test Failures (Fix the CI)

### Task 08 — Fix 2 Failing Unit Tests in `test_atria_text_backend.py`
**Priority: CRITICAL**  
**File:** `tests/test_atria_text_backend.py`

**Problem:**  
2 tests fail because `TextCorrectionEngine` cannot initialize the `atria` backend when `ATRIA_API_KEY` is not set in the environment. The OpenAI client raises a credentials error during `__init__`, the engine catches it, logs a warning, and `eng._slots` ends up empty (`[]`). The tests then immediately fail:
- `test_engine_marks_backend_dead_on_persistent_429`: `AssertionError: 0 != 1`
- `test_engine_falls_back_on_failed_validation`: `IndexError: list index out of range`

**Fix:** Add `setUp` / `tearDown` to the two affected test classes (`RetryAfterHandling` and `ResponseValidation`) to inject a dummy key:

```python
class RetryAfterHandling(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.get("ATRIA_API_KEY")
        os.environ["ATRIA_API_KEY"] = "mock-atria-key-for-testing"

    def tearDown(self):
        if self._old_key is not None:
            os.environ["ATRIA_API_KEY"] = self._old_key
        else:
            os.environ.pop("ATRIA_API_KEY", None)
```

Apply the same `setUp`/`tearDown` to the `ResponseValidation` class (the second failing test lives there at line 377).

**Verify:** After this fix, run:
```bash
HOME=./data/temp ./myenv/bin/pytest tests/test_atria_text_backend.py -v
```
All tests should pass (2 currently failing → 0 failing).

---

## Group E — Dependencies & Configuration

### Task 09 — Add Missing Packages to `requirements.txt`
**Priority: CRITICAL**  
**File:** `requirements.txt`

**Problem:**  
The following packages are imported by the pipeline but absent from `requirements.txt`:
- `openai` — used by `AtriaTextBackend`, `VisionFallbackEngine` (OpenRouter, Sovereign, GitHub Models)
- `groq` — used by `GroqTextBackend` and `GroqVisionBackend`
- `google-generativeai` — used by `GeminiTextBackend` and `GeminiVisionBackend`
- `cohere` — used by `CohereVisionBackend`
- `httpx` — test dependency (`test_atria_text_backend.py` imports it directly)
- `pytest` — needed to run the test suite

Fresh `pip install -r requirements.txt` will crash with `ModuleNotFoundError` on any LLM call.

**Fix:** Append to `requirements.txt`:
```
# LLM backends (vision fallback + text correction)
openai>=1.0.0
groq>=0.9.0
google-generativeai>=0.8.0
cohere>=5.0.0
httpx>=0.27.0

# Testing
pytest>=7.0.0
```

---

### Task 10 — Fix Invalid Model Names in `config/settings.yaml`
**Priority: IMPORTANT**  
**File:** `config/settings.yaml`

**Problem:**  
The following model identifiers in `config/settings.yaml` are invalid, nonexistent, or possibly decommissioned:

| Line | Setting | Current Value | Suggested Replacement | Confidence |
|------|---------|--------------|-------------------|-----------|
| 180 | `vision_fallback.backends.gemini.model` | `gemini-3.6-flash` | `gemini-2.5-flash` | Verify before applying |
| 183 | `vision_fallback.backends.gemini_2.model` | `gemini-3.6-flash` | `gemini-2.5-flash` | Verify before applying |
| 186 | `vision_fallback.backends.groq.model` | `qwen/qwen3.6-27b` | `meta-llama/llama-4-scout-17b-16e-instruct` | Confirmed active on Groq |
| 189 | `vision_fallback.backends.groq_2.model` | `qwen/qwen3.6-27b` | `meta-llama/llama-4-scout-17b-16e-instruct` | Confirmed active on Groq |
| 195 | `vision_fallback.backends.sovereign.model` | `claude-sonnet-5` | — | **Do not blindly replace — see caution below** |
| 198 | `vision_fallback.backends.sovereign_2.model` | `claude-sonnet-5` | — | **Do not blindly replace — see caution below** |
| ~~204~~ | ~~`vision_fallback.backends.claude.model`~~ | ~~`claude-sonnet-5`~~ | *(row removed — the `claude` backend itself is deleted in Task 21, this line becomes moot)* | — |
| 230 | `text_correction.backends.groq.model` | `llama-3.3-70b-versatile` | `openai/gpt-oss-120b` | Verify before applying |

**⚠️ CAUTION — do not treat `claude-sonnet-5` as invalid:** an earlier version of this plan assumed `claude-sonnet-5` was a fake/nonexistent model name and proposed downgrading it to `claude-3-5-sonnet-20241022`. That assumption was wrong — `claude-sonnet-5` is a real, current Anthropic model. **Do not apply that specific substitution.** The `sovereign` backend's model name is left unresolved here on purpose: `sovereign` is a separate proxy service (its own API key, own vendor) and it isn't clear from this document alone which underlying model catalogue it actually uses or whether `claude-sonnet-5` is even a valid identifier *on that specific proxy*. Check the Sovereign provider's own docs/dashboard for its current valid model names before touching lines 195/198 — do not guess, and do not copy an Anthropic-direct model string onto a third-party proxy without confirming it's supported there.

**Note on `llama-3.3-70b-versatile`:** the engine's docstring in `text_correction_engine.py:346–354` claims Groq decommissioned this model (2026-06-17) and names `openai/gpt-oss-120b`/`gpt-oss` family as the replacement. Treat this as a lead, not a confirmed fact — some Groq documentation snapshots still list `llama-3.3-70b-versatile` as an active production model. Check `https://console.groq.com/docs/models` directly at the time you apply this task before deciding whether to replace it or just leave it.

**Additional Note on Groq vision models:** Groq's vision models change frequently. Verify that the chosen model name is listed on `https://console.groq.com/docs/models` before finalizing.

**General rule for this whole task:** LLM model catalogues shift fast and this document's author (human or AI) can be wrong about which model names are current. Before committing any row in the table above, check the provider's live docs/console yourself — don't apply a replacement here on faith.

---

## Group F — Performance Improvements

### Task 11 — Fix $O(N^2)$ Disk I/O in `_rewrite_full_manuscript()`
**Priority: IMPORTANT**  
**File:** `src/pipeline/output/output_generator.py`

**Problem:**  
`_rewrite_full_manuscript()` is called after every page (`save_page()` line 103). The function re-reads **all** previously saved `page_*.txt` files from disk every time (lines 112–119):
```python
for f in raw_dir.glob('page_*.txt'):
    content = f.read_text(encoding='utf-8')
    disk_pages[page_num] = _extract_text_body(content)
```
For a 300-page book: call 1 reads 1 file, call 2 reads 2 files, ... call 300 reads 300 files → **≈45,000 disk reads**.

There is already a correct in-memory cache: `self._page_texts[document_name]` on line 59.
The disk re-read exists for "resume after crash" support (pick up pages from prior runs).

**Fix:** Do the disk scan **once** at start of each document, then use only the in-memory cache for subsequent pages.

Change `_rewrite_full_manuscript()` to never read disk for pages already in `self._page_texts`:
```python
def _rewrite_full_manuscript(self, document_name: str, doc_dir: Path) -> None:
    current_run = self._page_texts.get(document_name, {})
    
    # Only scan disk once per document for pages from prior runs.
    # After the first page of this document, all new pages are in-memory.
    if document_name not in self._disk_scan_done:
        self._disk_scan_done.add(document_name)
        raw_dir = doc_dir / 'raw_text'
        if raw_dir.is_dir():
            for f in raw_dir.glob('page_*.txt'):
                m = re.match(r'^page_(\d{3})\.txt$', f.name)
                if m:
                    page_num = int(m.group(1))
                    if page_num not in current_run:  # don't overwrite current run
                        content = f.read_text(encoding='utf-8')
                        self._prior_run_pages.setdefault(document_name, {})[page_num] = _extract_text_body(content)

    prior = self._prior_run_pages.get(document_name, {})
    merged = {**prior, **current_run}
    ...
```

Add `self._disk_scan_done: set = set()` and `self._prior_run_pages: Dict[str, Dict[int, str]] = {}` to `__init__`. This reduces disk reads from O(N²) to O(N) total.

---

### Task 12 — Pass `start_page` / `end_page` into `_load_pdf()` to Avoid Eager Rendering
**Priority: IMPORTANT**  
**File:** `src/pipeline/ingestion/input_handler.py` & `main.py`

**Problem:**  
`_load_pdf()` renders **all** PDF pages to numpy arrays before returning, even when `--start 24 --end 26` is requested. For a 300-page book at 200 DPI, this renders ≈2.4 GB of pixel data for 297 pages that will be immediately discarded.

**Fix:**  
1. Add `start_page: int = 1, end_page: int = None` parameters to `_load_pdf()`.  
2. Inside the `for page_num in range(len(doc)):` loop, add a check:
   ```python
   one_indexed = page_num + 1
   if start_page is not None and one_indexed < start_page:
       continue
   if end_page is not None and one_indexed > end_page:
       break
   ```
3. In `load_file()`, pass `start_page` and `end_page` to `_load_pdf()`.
4. In `main.py:904`, change the call:
   ```python
   pages = input_handler.load_file(file_path, dpi=detection_dpi,
                                   start_page=start_page, end_page=end_page)
   ```
5. Remove the post-load page-range filter at `main.py:906–912` (now redundant, but keep the logging).

---

### Task 13 — Downscale Full-Resolution Image Before Skew Search
**Priority: NICE-TO-HAVE**  
**File:** `src/pipeline/preprocessing/preprocessing.py`

**Problem:**  
`_estimate_skew_angle()` at line 119 performs ≈32 affine transformations on the full-resolution binary image. At 200 DPI, a typical page is `~2338 × 3307` pixels. Downscaling by 4× before the projection search gives identical angular accuracy with ≈16× less work.

**Fix:** At the start of `_estimate_skew_angle()`, after `binary = adaptive_binarize_gray(gray)`, add:
```python
# Downscale for projection-profile search: 4× reduction is invisible
# to angle precision (variance peaks at the same angle regardless of scale)
# but gives ~16× speedup on the affine-transform inner loop.
scale = 4
h_small = max(1, binary.shape[0] // scale)
w_small = max(1, binary.shape[1] // scale)
binary = cv2.resize(binary, (w_small, h_small), interpolation=cv2.INTER_NEAREST)
center = (w_small / 2.0, h_small / 2.0)
```

Remove the existing `height, width = binary.shape` / `center = ...` lines that come after.

---

## Group G — Code Quality & Architecture

### Task 14 — Extract Shared LLM Response Helpers to `common/response_validation.py`
**Priority: IMPORTANT**  
**Files:** 
- `src/pipeline/common/response_validation.py` (new file)
- `src/pipeline/ocr/vision_fallback.py`
- `src/pipeline/correction/text_correction_engine.py`

**Problem:**  
The following functions are **duplicated line-for-line** between `vision_fallback.py` and `text_correction_engine.py`:
- `_extract_openai_compatible_text()` (with slight divergence: engine version has extra `finish_reason == "length"` branch)
- `_looks_like_permanent_error()` + `PERMANENT_ERROR_MARKERS`
- `_strip_reasoning_blocks()` + `_THINK_BLOCK_RE`
- `_looks_like_refusal()` + `REFUSAL_MARKERS`
- `_looks_like_plausible_arabic()` + `_ARABIC_CHAR_RE` + `_LETTER_RE` + constants

**Fix:**
1. Create `src/pipeline/common/__init__.py` (empty).
2. Create `src/pipeline/common/response_validation.py` containing the unified versions of all five functions/constants. Use the **engine's** version of `_extract_openai_compatible_text()` since it has the superior `finish_reason == "length"` transient-error handling.
3. In `vision_fallback.py`, delete the duplicated definitions and add:
   ```python
   from src.pipeline.common.response_validation import (
       _extract_openai_compatible_text, _looks_like_permanent_error,
       _strip_reasoning_blocks, _looks_like_refusal, _looks_like_plausible_arabic,
       PERMANENT_ERROR_MARKERS, REFUSAL_MARKERS,
   )
   ```
4. Do the same import in `text_correction_engine.py`.

---

### Task 15 — Rename `binarize()` to Expose Return-Type Contract
**Priority: IMPORTANT**  
**Files:** `src/pipeline/preprocessing/page_layout_detector.py`, `src/pipeline/preprocessing/segment_text_rows.py`, `main.py`

**Problem:**  
Both modules define a function named `binarize()` with **incompatible return types**:
- `layout.binarize()` returns a `0`/`255` `uint8` image (normal OpenCV style)
- `rowseg.binarize()` returns a `0`/`1` `uint8` boolean mask

`main.py:12–21` has a long warning comment about never importing these by bare name. This is a contract-collision landmine.

**Fix:**
1. In `page_layout_detector.py`, rename `def binarize(` → `def binarize_to_255(`.
2. In `segment_text_rows.py`, rename `def binarize(` → `def binarize_to_mask(`.
3. In `main.py`, update all call sites:
   - `layout.binarize(image)` → `layout.binarize_to_255(image)`
   - `rowseg.binarize(image)` → `rowseg.binarize_to_mask(image)`
4. Remove or update the warning comment in `main.py:12–21` once the rename removes the ambiguity.
5. Search for any other callers (tests, debug scripts) that reference the old names.

---

### Task 16 — Fix CQS Violation in `_maybe_escalate_line()`
**Priority: IMPORTANT**  
**File:** `main.py`

**Problem:**  
`_maybe_escalate_line()` (lines 234–309) **both** returns a list of escalation audit records **and** mutates `result["text"]` and `result["likely_noise"]` in place. This is a Command-Query Separation violation: callers cannot know from the function's signature that calling it has side effects on their input dictionary.

**Fix:** Change the function signature and return type:
```python
def _maybe_escalate_line(vision_engine, result: dict, crop_img, region: str) -> tuple[dict, list]:
    """
    Returns (updated_result, escalations).
    Does NOT mutate the input `result` dict — returns a new dict instead.
    """
    result = dict(result)  # shallow copy — avoid mutating caller's dict
    ...
    # Replace:  result["text"] = final_text
    # With:     result = {**result, "text": final_text, "likely_noise": ...}
    return result, escalations
```

Update all call sites in `main.py` to unpack the tuple:
```python
result, line_escalations = _maybe_escalate_line(vision_engine, result, crop_img, region)
```

---

### Task 17 — Fix Overly-Aggressive `RepeatedVerbatimTracker` (Rejecting Real Verses)
**Priority: IMPORTANT**  
**File:** `src/pipeline/correction/repeated_verbatim_tracker.py`

**Problem:**  
`register()` at line 127 returns `True` (rejected as hallucination) the moment `count > 0` — i.e., the second time any text phrase is ever seen. This also rejects:
- Legitimate refrain lines ("وَمَا لِلْعَيْنِ مِنْ دَمْعٍ" appearing on multiple pages as a real refrain)
- Common Islamic formulas ("بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ")
- Section-opening patterns

**Fix:** Add a `min_occurrences` threshold configurable in `settings.yaml`. The tracker should only flag as repeated when `count >= min_occurrences` (default: 3). This allows a phrase to appear twice across the whole manuscript before being treated as a hallucination pattern.

In `settings.yaml`, add under `vision_fallback`:
```yaml
repeated_verbatim_min_occurrences: 3  # flag after this many cross-crop occurrences
```

In `repeated_verbatim_tracker.py` `__init__`, read this setting and store as `self.min_occurrences = config.get('repeated_verbatim_min_occurrences', 3)`.

In `register()`, change:
```python
is_repeated = count > 0
```
to:
```python
is_repeated = count >= self.min_occurrences
```

---

### Task 18 — Fix Duplicate `PaddleOCR` Import in `ocr_engine.py`
**Priority: NIT**  
**File:** `src/pipeline/ocr/ocr_engine.py`

**Problem:**  
`from paddleocr import PaddleOCR` is imported twice:
- Line 30: `from paddleocr import PaddleOCR, TextRecognition`
- Line 40: `from paddleocr import PaddleOCR`

Line 40 is redundant.

**Fix:** Delete line 40 entirely.

---

## Group H — Documentation

### Task 19 — Rewrite `README.md` to Match Current `src/pipeline/` Structure
**Priority: IMPORTANT**  
**File:** `README.md`

**Problem:**  
`README.md:73–94` (the "Project structure" section) describes a flat layout at the repo root that no longer exists:
```
main.py
preprocessing.py        ← does not exist at root
input_handler.py        ← does not exist at root
page_layout_detector.py ← does not exist at root
...
sync_vision_backends.py ← does not exist anywhere
```

The setup instructions also say:
- `pip install -r requirements.txt` → will fail (packages missing, see Task 09)
- `python review_manuscript.py` → file does not exist at root
- References `.env.example` which does not exist (see Task 02)

**Fix:** Replace the "Project structure" section with the actual layout:
```
main.py                              # entry point
config/
  settings.yaml                      # all configuration
  prompts.yaml                       # LLM prompts
src/pipeline/
  ingestion/input_handler.py         # PDF + image loading
  preprocessing/preprocessing.py    # deskew / CLAHE / denoise
  preprocessing/page_layout_detector.py
  preprocessing/segment_text_rows.py
  ocr/ocr_engine.py                  # PaddleOCR wrapper
  ocr/vision_fallback.py             # per-line LLM escalation
  correction/text_correction_engine.py
  output/output_generator.py
  output/review_manuscript.py        # second-stage correction
data/
  input/                             # place PDFs here
  output/                            # pipeline writes here
tests/
requirements.txt
.env.example                         # copy to .env, fill in keys
```

Update run instructions:
- `python main.py --start 20 --end 30`
- `python -m src.pipeline.output.review_manuscript --document my_book`

---

## Group I — Verification Tooling

### Task 20 — Fix `verify_all.py` Sandbox / Read-Only Home Failure
**Priority: IMPORTANT**  
**File:** `verify_all.py`

**Problem:**  
`verify_all.py` launches subprocesses via `subprocess.run(cmd, cwd=REPO, ...)`. PaddleX's `TempFileManager.__init__()` tries to `mkdir($HOME/.paddlex/temp)` on import. In environments where `$HOME` is read-only (CI, dev sandboxes), this crashes with `OSError: [Errno 30] Read-only file system`, causing the unit test check to fail even when all tests pass.

**Fix:** In `check_tests()` and `check_smoke()`, pass `HOME=<writable path>` in the subprocess environment:
```python
def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # PaddleX creates $HOME/.paddlex/temp at import; override HOME to a
    # writable project-local directory so this works in read-only $HOME
    # environments (CI, dev sandboxes).
    env["HOME"] = str(REPO / "data" / "temp")
    (REPO / "data" / "temp").mkdir(parents=True, exist_ok=True)
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env, **kw)
```

Add `import os` to `verify_all.py` imports.

---

## Group J — Remove Claude/Anthropic Vision Backend

### Task 21 — Remove `ClaudeVisionBackend` and All References to It
**Priority: IMPORTANT**  
**Files:** `src/pipeline/ocr/vision_fallback.py`, `config/settings.yaml`, `requirements.txt`, `.env`, `.env.example`, `README.md`

**Problem:**  
The pipeline currently ships a direct Anthropic vision backend (`ClaudeVisionBackend`, using the `anthropic` package and `ANTHROPIC_API_KEY`) alongside Gemini, Groq, Cohere, OpenRouter, GitHub Models, and Sovereign. This backend is being removed entirely — the project should no longer call Claude/Anthropic directly as a vision-fallback provider.

**Fix — do all of the following:**
1. **`src/pipeline/ocr/vision_fallback.py`:** Delete the `ClaudeVisionBackend` class definition in full, and remove its entry from wherever backends are registered/instantiated (the backend factory/dict that `settings.yaml`'s `vision_fallback.backends.*` keys map to). Search the file for every reference to `Claude`, `anthropic`, or `ANTHROPIC_API_KEY` and remove each one.
2. **`config/settings.yaml`:** Delete the entire `vision_fallback.backends.claude` block (the one at the former line 204 referenced in Task 10). Do **not** touch `sovereign` / `sovereign_2` — those are a separate proxy backend and are out of scope here (see the caution note in Task 10).
3. **`requirements.txt`:** Do not add the `anthropic` package (Task 09 and the `.env.example` block above have already been updated to exclude it in this revision of the plan). If `anthropic` is already present in the current `requirements.txt` from before this plan, remove that line.
4. **`.env` / `.env.example`:** Remove the `ANTHROPIC_API_KEY` line (already excluded from the `.env.example` template in Task 02 above). If a live `ANTHROPIC_API_KEY` exists in the real `.env`, it can be revoked along with the other keys in Task 01, or simply left unused — it no longer needs regenerating.
5. **`README.md`:** Search for any mention of "Claude" or "Anthropic" as a vision/text backend and remove it from the provider list/setup instructions (this is in addition to the general README rewrite in Task 19 — do this removal as part of that same rewrite, not as a separate pass).
6. **Tests:** Search `tests/` for any test that imports or mocks `ClaudeVisionBackend` (e.g. a `test_claude_vision_backend.py` or similar) and delete or update it accordingly so the suite doesn't fail on a now-missing class.

**Verify:** `grep -ri "claude\|anthropic" -r src/ config/ requirements.txt .env.example README.md` should return nothing except, if you chose to keep it, an unrelated code comment — confirm no active backend, config key, or dependency still references Claude/Anthropic.

**Note:** This task should run **before** Task 10, since Task 10's table treats the `vision_fallback.backends.claude.model` row as moot once this backend no longer exists — no point fixing a model name in a config block you're about to delete.

---

## Summary Table

| # | Group | Priority | File(s) | Bug Type |
|---|-------|----------|---------|----------|
| 01 | A | 🔴 CRITICAL | `.env` (provider dashboards) | Security |
| 02 | A | 🔴 CRITICAL | `.gitignore`, `.env.example` | Security / Docs |
| 03 | B | 🔴 CRITICAL | `output_generator.py` | Data Loss |
| 04 | B | 🔴 CRITICAL | `main.py` | Layout Bug |
| 05 | C | 🔴 CRITICAL | `input_handler.py` | Crash |
| 06 | C | 🔴 CRITICAL | `main.py` | Crash |
| 07 | C | 🔴 CRITICAL | `input_handler.py` | Swallowed Exceptions |
| 08 | D | 🔴 CRITICAL | `tests/test_atria_text_backend.py` | Test Failure |
| 09 | E | 🔴 CRITICAL | `requirements.txt` | Missing Dependencies |
| 10 | E | 🟠 IMPORTANT | `config/settings.yaml` | Invalid Config |
| 11 | F | 🟠 IMPORTANT | `output_generator.py` | Performance O(N²) |
| 12 | F | 🟠 IMPORTANT | `input_handler.py`, `main.py` | Performance / Memory |
| 13 | F | 🟡 NICE | `preprocessing.py` | Performance |
| 14 | G | 🟠 IMPORTANT | 3 files | DRY Violation |
| 15 | G | 🟠 IMPORTANT | 3 files | Naming / Contract |
| 16 | G | 🟠 IMPORTANT | `main.py` | CQS Violation |
| 17 | G | 🟠 IMPORTANT | `repeated_verbatim_tracker.py` | False Negatives |
| 18 | G | 🟡 NIT | `ocr_engine.py` | Duplicate Import |
| 19 | H | 🟠 IMPORTANT | `README.md` | Stale Docs |
| 20 | I | 🟠 IMPORTANT | `verify_all.py` | Tooling / CI |
| 21 | J | 🟠 IMPORTANT | `vision_fallback.py`, `settings.yaml`, `requirements.txt`, `.env*`, `README.md` | Backend Removal (drop Claude/Anthropic) |

---

## Recommended Execution Order

```
Task 01 → Task 02   (security, do before anything else)
Task 09             (install missing deps so code runs)
Task 08             (fix tests so CI is green)
Task 03             (data loss — highest value fix)
Task 04             (layout correctness)
Task 05 → Task 06 → Task 07  (crash prevention)
Task 21             (remove Claude/Anthropic backend before touching model names)
Task 10             (model names — needed for any live LLM call; verify each one against live provider docs, see caution notes)
Task 20             (fix verify_all so it can actually verify)
Task 11 → Task 12   (performance)
Task 14 → Task 15 → Task 16 → Task 17  (code quality)
Task 13 → Task 18 → Task 19  (optional polish; Task 19's README rewrite should also fold in Task 21's README cleanup)
```

---

## Verification After All Tasks

Run the project's own verification tool (with the HOME fix from Task 20 already applied):
```bash
HOME=./data/temp ./myenv/bin/python verify_all.py --skip-smoke
```

Expected output:
```
verify_all — closed-pipeline verification

  invariant OK: 21b1ed2f473218a260dc (expected ..., N files)
  unittest OK: ...  2 failed → 0 failed ...
  benchmark regen OK: CER: 25.0% / WER: 59.9% / diacritics accuracy: 81.3%

All checks passed — the closed pipeline is reproducible.
```

After Task 03 (prose text saved), the `invariant` hash will change (more text in the output files). Update the `INVARIANT` constant in `verify_all.py:27` to the new hash after confirming the output is correct.
