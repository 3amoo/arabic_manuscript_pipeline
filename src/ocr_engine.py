"""
Local OCR Engine Module using PaddleOCR
Optimized for high-accuracy Arabic text extraction with GPU support.

Compatible with PaddleOCR >= 3.0 (new predict() API).

VRAM NOTES (important on small GPUs like GTX 1650 / 4GB):
- By default Paddle pre-allocates a large chunk of GPU memory at once.
  We switch to "auto_growth" so it only takes what it actually needs.
- We disable the doc-orientation and doc-unwarping sub-models
  (use_doc_orientation_classify / use_doc_unwarping). These load two
  extra models and are meant for photographed/crooked documents; a
  clean flatbed/PDF scan doesn't need them, and skipping them saves a
  meaningful chunk of VRAM before OCR even starts.
- We cap text_det_limit_side_len so very high-DPI page images don't
  blow up the detector's memory use.
- extract_segments_batch() groups many already-cropped line images into
  shared predict() calls (see its own docstring) instead of the older
  one-call-per-line pattern extract_segment() still uses for single-image
  callers - this amortizes each call's fixed overhead across a whole
  page's worth of lines instead of paying it per line.
- extract_segments_batch() also checks ocr_cache.py's SQLite cache
  before running anything through PaddleOCR at all - a repeated/resumed
  run over pages already seen skips the GPU call entirely for any crop
  whose exact bytes were cached before, under the current recognition
  model. See ocr_cache.py's module docstring for the full reasoning.
"""

import os
from paddleocr import PaddleOCR, TextRecognition

# Must be set BEFORE `import paddle` (paddleocr imports paddle internally),
# otherwise it has no effect. Grows GPU memory incrementally instead of
# reserving a big block upfront.
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

import numpy as np
from typing import Dict, Any, Optional
import logging
from paddleocr import PaddleOCR

from ocr_cache import OCRCache

logger = logging.getLogger(__name__)



class OCREngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        use_gpu = config.get('use_gpu', True)
        device = 'gpu:0' if use_gpu else 'cpu'

        rec_model = config.get('text_recognition_model_name', 'arabic_PP-OCRv5_mobile_rec')

        # Default batch size for extract_segments_batch() below - how many
        # already-cropped line images get stacked into ONE PaddleOCR
        # predict() call. Every predict() call pays a fixed Python/data-
        # transfer overhead regardless of how small the images are, so
        # looping it once per line (the old behavior, still what
        # extract_segment() does for single-image call sites) pays that
        # overhead on every single line. 16 is a conservative default for
        # a small (4GB) GPU - override via config['segment_batch_size'] in
        # settings.yaml if VRAM allows a larger batch, or if a 4GB card
        # OOMs on 16 wide verse-line crops, lower it instead.
        self.segment_batch_size = int(config.get('segment_batch_size', 16) or 16)

        # Optional SQLite result cache - see ocr_cache.py's module
        # docstring for the full reasoning. Keyed on (image bytes, model
        # name), so pointing text_recognition_model_name at a different
        # model later naturally starts a fresh set of cache entries
        # instead of ever serving a stale result from the old model.
        # Enabled by default (settings.yaml's ocr.caching.enabled) since
        # it is lossless for plain OCR (see the module docstring on why
        # this differs from vision_fallback/text_correction, which are
        # NOT cached) - set to false to disable entirely, e.g. while
        # debugging OCR output changes from a fresh model/settings tweak.
        caching_cfg = config.get('caching', {}) or {}
        self.cache: Optional[OCRCache] = None
        if caching_cfg.get('enabled', True):
            self.cache = OCRCache(
                db_path=caching_cfg.get('db_path', 'output/.cache/ocr_cache.sqlite3'),
                model_key=rec_model,
            )

        logger.info(f"Initializing PaddleOCR for Arabic (device={device})...")
        self.ocr = PaddleOCR(
            text_detection_model_name=config.get('text_detection_model_name', 'PP-OCRv5_mobile_det'),
            text_recognition_model_name=rec_model,
            use_textline_orientation=True,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            text_det_limit_side_len=config.get('text_det_limit_side_len', 960),
            device=device,
        )

        # موديل تعرّف منفصل لاستخدامه فقط على قصاصات مقصوصة مسبقًا
        # (extract_segment). لو استخدمنا self.ocr هنا، محرك الكشف
        # جواها بيكبّر أي قصاصة رفيعة (سطر واحد) لحد text_det_limit_side_len
        # وده بيشوّه نسبة الطول للعرض بشكل فظيع (تأكدنا عمليًا: قصاصة
        # 174x1303 بكسل اتكبرت لـ 960x7133) وبيطلّع هلوسة بدل نص حقيقي.
        self.rec_only = TextRecognition(model_name=rec_model)
        logger.info("PaddleOCR initialized successfully.")


    @staticmethod
    def _box_center(box):
        """
        Return (center_x, center_y, height) for one detected text box,
        regardless of whether PaddleOCR gave us an axis-aligned box
        (x1, y1, x2, y2) or a 4-point polygon
        ([[x, y], [x, y], [x, y], [x, y]]).
        """
        box = np.asarray(box, dtype=np.float32)

        if box.ndim == 1 and box.size >= 4:
            x1, y1, x2, y2 = box[:4]
            return float((x1 + x2) / 2.0), float((y1 + y2) / 2.0), float(y2 - y1)

        xs = box[:, 0]
        ys = box[:, 1]
        return float(xs.mean()), float(ys.mean()), float(ys.max() - ys.min())

    @staticmethod
    def _reorder_rtl(items, boxes):
        """
        Reorder detected (text, score) pairs into Arabic reading order:
        top-to-bottom by text row, and right-to-left within each row.

        PaddleOCR's own detection order is top-to-bottom then
        left-to-right (its sorted_boxes(), tuned for LTR/CJK reading).
        That is backwards for Arabic: within one line, the rightmost
        word comes first when reading, not last. Appending rec_texts in
        PaddleOCR's raw order scrambled multi-word Arabic lines - verified
        against actual pipeline output, where reversing a garbled line
        like "وجمل بشرا، ادم قدرته خلق جلت فان القه متهم" recovers real
        word order.

        Boxes are grouped into rows using ONE shared tolerance derived
        from the median box height across the whole set (not each box's
        own height). An earlier version used each box's own height as its
        row tolerance, which broke on short glyphs - a lone dash "-" or a
        single letter has a small height, so it got a tiny tolerance and
        was kicked into its own row even though it sat on the same
        baseline as its neighbors (verified against actual pipeline
        output: "متهم -" was splitting off the end of an otherwise
        correctly-reordered line for exactly this reason).
        """
        n = len(items)
        if n <= 1 or boxes is None or len(boxes) != n:
            return items

        centers = [OCREngine._box_center(box) for box in boxes]

        heights = [h for (_, _, h) in centers if h > 0]
        median_height = float(np.median(heights)) if heights else 1.0
        row_tolerance = max(median_height * 0.6, 4.0)

        # Sort top-to-bottom first so row-grouping below sees boxes in
        # roughly increasing y order.
        order = sorted(range(n), key=lambda i: centers[i][1])

        rows = []
        for i in order:
            cx, cy, h = centers[i]

            if rows and abs(cy - rows[-1]["y"]) <= row_tolerance:
                rows[-1]["indices"].append(i)
                # Keep the row's reference y as a running average so a
                # long row doesn't drift as more boxes are added.
                row = rows[-1]
                row["y"] = (row["y"] * (len(row["indices"]) - 1) + cy) / len(row["indices"])
            else:
                rows.append({"y": cy, "indices": [i]})

        result = []
        for row in rows:
            row_indices = sorted(
                row["indices"],
                key=lambda i: centers[i][0],
                reverse=True,  # rightmost box first within the row (RTL)
            )
            result.extend(items[i] for i in row_indices)

        return result

    def _predict_lines(self, image: np.ndarray):
        """
        Run PaddleOCR.predict() once and return the (text, score) pairs for
        every detected text box, reordered into Arabic reading order (see
        _reorder_rtl). Shared by extract() (whole page/region) and
        extract_segment() (one pre-cropped line) so both paths use the
        exact same call and the exact same PaddleOCR instance - important
        on a 4GB card where re-initializing the model per call would be
        wasteful and slow.
        """
        results = self.ocr.predict(image)

        texts = []
        scores = []

        for res in results:
            rec_texts = res.get('rec_texts', [])
            rec_scores = res.get('rec_scores', [])
            # rec_boxes is the per-text axis-aligned box PaddleOCR 3.x
            # returns alongside rec_texts/rec_scores (one entry each,
            # same order). Fall back to rec_polys if a build doesn't
            # expose rec_boxes.
            rec_boxes = res.get('rec_boxes')
            if rec_boxes is None:
                rec_boxes = res.get('rec_polys')

            items = list(zip(rec_texts, rec_scores))

            if rec_boxes is not None and len(rec_boxes) == len(items):
                items = self._reorder_rtl(items, rec_boxes)
            else:
                logger.warning(
                    "No per-text box info from PaddleOCR result - "
                    "cannot apply RTL ordering, using raw detection order."
                )

            for text, score in items:
                text = text.strip()
                if not text:
                    continue
                texts.append(text)
                scores.append(float(score))

        return texts, scores

    @staticmethod
    def _is_noise_line(text: str) -> bool:
        """
        Heuristic filter for footnote/margin garbage: lines where most
        "words" are a single isolated character (typical symptom of OCR
        struggling with very small footnote font). This does NOT try to
        clean up the main body text — it only screens out the clearest
        noise so the margin garbage doesn't pollute the main narrative.
        """
        tokens = text.split()
        if not tokens:
            return True
        single_char_tokens = sum(1 for t in tokens if len(t) <= 1)
        ratio = single_char_tokens / len(tokens)
        # سطر مكوّن غالبًا من رموز/حروف منفردة (زي "ي   ي يي") = هامش مشوش
        return len(tokens) >= 3 and ratio > 0.55

    def extract(self, image: np.ndarray, method: str = 'paddle',
                quality_info: Optional[Dict] = None) -> Dict[str, Any]:

        try:
            # --- DEBUG مؤقت: احفظ أول صورة بتتبعت فعليًا للموديل عشان نعاينها ---
            import os as _os
            if not hasattr(self, '_debug_saved'):
                _os.makedirs('debug', exist_ok=True)
                try:
                    import cv2 as _cv2
                    _cv2.imwrite('debug/page_fed_to_ocr.png', image)
                    logger.info(f"DEBUG: saved raw image fed to OCR -> debug/page_fed_to_ocr.png "
                                f"(shape={image.shape}, dtype={image.dtype})")
                except Exception as _dbg_e:
                    logger.warning(f"DEBUG save failed: {_dbg_e}")
                self._debug_saved = True
            # --- نهاية كود الـ DEBUG ---

            # PaddleOCR 3.x: .ocr() is deprecated, use .predict()
            texts, scores = self._predict_lines(image)

            extracted_lines = []
            noise_skipped = 0
            min_confidence = self.config.get('min_confidence', 0.4)

            logger.info(f"PaddleOCR detected {len(texts)} text line(s) on this image.")

            for text, confidence in zip(texts, scores):
                if confidence <= min_confidence:
                    continue
                if self._is_noise_line(text):
                    noise_skipped += 1
                    continue
                extracted_lines.append(text)

            if noise_skipped:
                logger.info(f"Filtered out {noise_skipped} likely footnote/noise line(s).")

            final_text = "\n".join(extracted_lines)
            logger.info(f"Successfully extracted {len(final_text)} characters using PaddleOCR.")

            return {
                'text': final_text.strip(),
                'confidence': 100.0,
                'word_count': len(final_text.split()),
                'method': 'paddle'
            }

        except Exception as e:
            logger.error(f"PaddleOCR failed with exception: {e}", exc_info=True)
            raise RuntimeError(f"OCR method failed: paddle") from e

    def extract_segment(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Single-image convenience wrapper around extract_segments_batch()
        (see that method's docstring for the batching/caching behavior
        both share) - kept for any call site that only has one crop at a
        time. main.py itself always goes through extract_segments_batch()
        directly now, but this is still the right entry point for a
        single ad-hoc crop (e.g. from a debug script).
        """
        return self.extract_segments_batch([image])[0]

    def extract_segments_batch(self, images: list, batch_size: Optional[int] = None) -> list:
        """
        Batched, cache-aware sibling of the old per-line extract_segment()
        call pattern. Returns one result dict per input image, in the
        SAME ORDER as `images` - {'text', 'confidence', 'likely_noise'}.

        TWO layers of savings, applied in order for every call:
          1. CACHE (ocr_cache.py, if enabled): each image is hashed
             (together with the recognition model name) and looked up in
             a persistent SQLite cache. A hit reuses that exact prior
             result with NO PaddleOCR call at all - this is what makes a
             repeated/resumed run over the same manuscript pages cheap.
             See ocr_cache.py's module docstring for why this is safe
             (OCR recognition is deterministic given a fixed model) and
             why vision_fallback/text_correction results are deliberately
             NOT cached here.
          2. BATCHING: whatever images are left after cache lookups (cache
             misses, or every image if caching is disabled) are grouped
             into chunks of `batch_size` and OCR'd together in shared
             predict() calls, instead of one call per image - see
             _run_paddle_batch()'s docstring for the reasoning (a typical
             page has a dozen-plus lines, and PaddleOCR's per-call
             overhead was being paid that many times per page).

        Every freshly-computed (non-cached) result is written back to the
        cache before this method returns, so the NEXT time this exact
        crop is seen (a re-run, or a genuinely duplicate line elsewhere
        in the manuscript) it becomes a cache hit instead.

        An empty `images` list returns an empty list immediately without
        touching the cache or PaddleOCR at all - a region can genuinely
        have zero retained line bands (e.g. every band in it turned out
        to be a horizontal rule and got filtered out upstream).
        """
        if not images:
            return []

        results: list = [None] * len(images)
        pending_indices = []
        pending_images = []
        pending_hashes = []

        for i, image in enumerate(images):
            if self.cache is not None:
                cached = self.cache.lookup(image)
                if cached is not None:
                    results[i] = cached
                    continue
            pending_indices.append(i)
            pending_images.append(image)

        if pending_images:
            fresh_results = self._run_paddle_batch(pending_images, batch_size)
            for idx, result in zip(pending_indices, fresh_results):
                results[idx] = result
                if self.cache is not None:
                    self.cache.store(images[idx], result)

        return results

    def _run_paddle_batch(self, images: list, batch_size: Optional[int] = None) -> list:
        """
        The actual PaddleOCR call, with no cache awareness - always runs
        every image in `images` through self.rec_only.predict(), chunked
        into groups of `batch_size`. Split out from
        extract_segments_batch() so the cache-lookup/cache-store bookkeeping
        there stays separate from the OCR-calling mechanics here.

        WHY BATCHING HELPS: each predict() call pays a fixed overhead
        (Python round-trip into PaddleOCR's predictor, data transfer to
        the GPU) regardless of how small the cropped image is. Grouping
        many line crops into shared predict() calls amortizes that fixed
        cost across the whole batch instead of paying it once per line -
        this matters on a small (4GB) GPU where every wasted round-trip is
        proportionally more expensive.

        Each image is still an individual, already-cropped, normal-
        aspect-ratio line (see extract_prose_region()'s docstring in
        main.py for why that pre-cropping step itself is required -
        PaddleOCR's own detector badly distorts a whole short/wide region
        if sent through in one piece). Batching only changes how many of
        those already-safe crops share one predict() call.
        """
        if batch_size is None:
            batch_size = self.segment_batch_size

        results: list = []

        try:
            for start in range(0, len(images), batch_size):
                chunk = images[start:start + batch_size]
                output = self.rec_only.predict(input=chunk, batch_size=len(chunk))
                chunk_results = list(output)

                # Defensive: predict() is expected to return exactly one
                # result per input image, in order - but if a future
                # PaddleOCR release ever returns fewer (e.g. it silently
                # drops one malformed crop from the batch), padding the
                # missing tail with empty results here keeps every
                # subsequent result in this chunk correctly aligned with
                # its own crop, instead of every result after the gap
                # silently shifting onto the WRONG line for the rest of
                # the batch.
                if len(chunk_results) < len(chunk):
                    logger.warning(
                        f"PaddleOCR batch returned {len(chunk_results)} "
                        f"result(s) for {len(chunk)} input image(s) - "
                        f"padding the missing result(s) with empty text "
                        f"rather than misaligning the rest of the batch."
                    )

                for i in range(len(chunk)):
                    if i >= len(chunk_results):
                        results.append({'text': '', 'confidence': None, 'likely_noise': False})
                        continue

                    res = chunk_results[i].json['res']
                    text = res.get('rec_text', '').strip()
                    confidence = res.get('rec_score')
                    results.append({
                        'text': text,
                        'confidence': confidence,
                        'likely_noise': self._is_noise_line(text) if text else False,
                    })

        except Exception as e:
            logger.error(f"PaddleOCR failed on batched segments with exception: {e}", exc_info=True)
            raise RuntimeError("OCR method failed: paddle (segment batch)") from e

        return results