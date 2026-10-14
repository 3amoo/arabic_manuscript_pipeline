#!/usr/bin/env python3
"""
The Phase 2 error budget for اللامع العزيزي (plan 024).

Answers "where does the ~1.0 (distance/GT) live?" with one instrument. It
reuses the Phase 1 locator (`scripts/score_lamae_pages.py`) to place every
page, then decomposes the resulting edit distance five ways:

  1. **Length decomposition.** The distance splits into substitutions
     (recognizer letter errors), insertions (OCR text with no GT
     counterpart), and deletions (GT text the OCR never produced). The
     share of each says whether the headline is recognizer-type or
     length/segmentation-type error.

  2. **Coverage classification.** A per-page alignment (the harness's own
     `edit_script`) marks each GT character as matched or dropped and each OCR
     character as matched or extra. The extra OCR characters are attributed to
     the OCR line they came from, and each line is classed as verse (carries
     the pipeline's ' ... ' hemistich separator) or prose, and prose lines as
     textbook apparatus-like (Arabic-Indic digits or a citation marker) or
     not. This separates the edition's footnote/citation apparatus from
     genuine recognizer spill. A rolling k-gram membership test then asks the
     decisive question: does the extra OCR text appear ANYWHERE in the GT
     stream (one edition, just mislocated — a locating defect) or nowhere
     (content this held-out GT does not carry)? Aligned text is the control:
     it is ~73% present at k=12, so the near-zero rate on extra text is a real
     absence, not a measurement floor.

  3. **Tashkeel split.** The whole thing is scored twice — once with the
     canonical normalizer (tashkeel stripped: letter accuracy) and once with
     `keep_diacritics=True` (marks retained). The delta isolates the marks.
     Caveat carried in the output: the Shamela GT is only lightly vocalized
     (~1% marks/base) while the OCR emits ~4%, so the keep-mode distance is
     dominated by mark MISMATCH (OCR adding marks the GT lacks) rather than
     by wrong marks on shared letters.

  4. **Per-page distribution.** Where the error concentrates: is it uniform
     or a bad tail? Reports the mean/median/min/max page CER, how many pages
     exceed CER 2.0, and the share of the total distance held by the five
     worst pages.

  5. **Confidence vs error.** Each raw page's stored `# Page Confidence`
     against its measured CER — is the confidence at all predictive on this
     book (plan 024 finding 6), or flat?

The ' ... ' verse/prose split and the apparatus marker set are heuristics,
labelled as such in the output. The op counts and coverage come from the
alignment itself, not the heuristic.

Usage:
    HOME=./data/temp ./myenv/bin/python scripts/lamae_error_budget.py
    HOME=./data/temp ./myenv/bin/python scripts/lamae_error_budget.py \
        --range 7-60 --json-out /tmp/opencode/error_budget.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline.evaluation.evaluate_cer import normalize_text  # noqa: E402

from lamae_gt_stream import (  # noqa: E402
    DOC,
    OCR_DIR,
    SEGMENTS_PATH,
    SECTION_MARKERS,
    canonical_stream,
    load_segments,
    page_window_length,
)
from score_lamae_pages import (  # noqa: E402
    edit_ops,
    edit_script,
    locate_page,
    locate_pages,
    score_window,
)

_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
# Strong citation-apparatus markers: an editor's source citation almost always
# names the reference work or the verb "في <work>". Kept as a named set so the
# classification is auditable, not a magic regex.
_CITATION_MARKERS = (
    "ديوان", "الأغاني", "اللسان", "تاج العروس", "شرح", "الطبقات",
    "الوفيات", "الفهرست", "المقاييس", "الخصائص", "أساس البلاغة",
    "المنصف", "جمهرة", "برواية", "الصحاح", "القاموس", "معجم", "سيرة",
)
_PAGE_CONF_RE = re.compile(r"#\s*Page Confidence:\s*([0-9]+(?:\.[0-9]+)?)")


def page_confidence(raw_text: str) -> float | None:
    """The stored '# Page Confidence: NN%' of one raw page, or None."""
    m = _PAGE_CONF_RE.search(raw_text)
    return float(m.group(1)) if m else None


def is_apparatus_like(line: str) -> bool:
    """Heuristic: does a prose line look like editor's source apparatus?

    True when it carries an Arabic-Indic digit (page/volume numbers) or any
    named citation marker. Verse lines are excluded by the caller.
    """
    if any(ch in _ARABIC_DIGITS for ch in line):
        return True
    return any(marker in line for marker in _CITATION_MARKERS)


class OcrLine:
    """One normalized OCR line, tagged verse/prose + apparatus, with its
    character span in the joined hypothesis."""

    __slots__ = ("text", "is_verse", "is_apparatus", "start", "end")

    def __init__(self, text: str, is_verse: bool):
        self.text = text
        self.is_verse = is_verse
        self.is_apparatus = not is_verse and is_apparatus_like(text)
        self.start = 0
        self.end = 0


def load_ocr_lines(raw_text: str) -> tuple[list[OcrLine], str]:
    """Normalized OCR lines (verse/prose tagged) and the joined hypothesis.

    Matches `lamae_gt_stream.page_hypothesis` exactly so the alignment runs
    on the same string the Phase 1 harness scores.
    """
    out: list[OcrLine] = []
    for raw_line in raw_text.splitlines():
        if raw_line.strip() in SECTION_MARKERS:
            continue
        text = normalize_text(raw_line)
        if not text:
            continue
        out.append(OcrLine(text, is_verse=" ... " in raw_line))
    pos = 0
    for line in out:
        line.start = pos
        pos += len(line.text) + 1  # joining space
        line.end = pos - 1
    return out, " ".join(line.text for line in out)


def line_class_at(lines: list[OcrLine], pos: int) -> OcrLine | None:
    """The OCR line whose span contains character `pos` (binary search)."""
    lo, hi = 0, len(lines) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if pos < lines[mid].start:
            hi = mid - 1
        elif pos > lines[mid].end:
            lo = mid + 1
        else:
            return lines[mid]
    return None


def _blank_coverage() -> dict:
    return {
        "gt_chars": 0, "ocr_chars": 0,
        "gt_matched": 0, "gt_dropped": 0,
        "ocr_matched": 0, "ocr_extra": 0,
        "extra_verse": 0, "extra_apparatus": 0, "extra_other_prose": 0,
        "substitutions": 0,
    }


def cover_page(ref: str, lines: list[OcrLine], hyp: str,
               script: list[tuple[str, int, int]] | None = None) -> dict:
    """Exact minimum-edit coverage for one page, extra OCR attributed to line.

    Uses the harness's own edit script (`score_lamae_pages.edit_script`), so
    replace + extra + dropped equals exactly the sub + ins + del the Phase 1
    scorer reports for the page — one alignment, one split. (difflib was
    rejected: it is not a minimum-edit aligner. rapidfuzz.editops returns a
    minimal script too, but a different one, e.g. sub 7,461 / ins 30,657 /
    del 4,366 on the same pages.)

    Pass `script` to reuse an alignment already computed for the page.
    """
    if script is None:
        script = edit_script(ref, hyp)
    cov = _blank_coverage()
    cov["gt_chars"] = len(ref)
    cov["ocr_chars"] = len(hyp)
    for tag, _ref_pos, hyp_pos in script:
        if tag == "replace":
            cov["substitutions"] += 1
        elif tag == "insert":
            _add_extra(cov, lines, hyp_pos)
        elif tag == "delete":
            cov["gt_dropped"] += 1
    cov["gt_matched"] = (
        cov["gt_chars"] - cov["gt_dropped"] - cov["substitutions"])
    cov["ocr_matched"] = (
        cov["ocr_chars"] - cov["ocr_extra"] - cov["substitutions"])
    return cov


def _add_extra(cov: dict, lines: list[OcrLine], pos: int) -> None:
    """Charge one extra hypothesis character to its source line's class."""
    cov["ocr_extra"] += 1
    line = line_class_at(lines, pos)
    if line is not None and line.is_verse:
        cov["extra_verse"] += 1
    elif line is not None and line.is_apparatus:
        cov["extra_apparatus"] += 1
    else:
        cov["extra_other_prose"] += 1


def _merge(target: dict, part: dict) -> None:
    for key in target:
        target[key] += part[key]


# --- verbatim-presence-in-GT test (coverage: is extra text in the GT at all?) ---
#
# The per-page alignment only says text is extra for THIS page's GT span. The
# decisive question is whether that extra text exists ANYWHERE in the GT stream
# (a mislocated match: the same edition, placed elsewhere) or nowhere (content
# the held-out GT does not carry at all). We answer it with a rolling k-gram
# membership test, calibrated by the SAME test on aligned (matched) text: on
# this book aligned text is ~73% present at k=12 (the recognizer's garbling
# costs the rest), so a near-zero rate on extra text is a real absence, not a
# measurement floor.
_GT_K = 12
_HASH_BASE = 1000003
_HASH_MASK = (1 << 64) - 1


def build_gt_kgrams(stream: str, k: int = _GT_K) -> tuple[set[int], int]:
    """Hashed k-grams of the whole canonical GT stream (for O(1) membership)."""
    base_pow = pow(_HASH_BASE, k - 1, 1 << 64)
    grams: set[int] = set()
    h = 0
    for i, ch in enumerate(stream):
        if i >= k:
            h = (h - ord(stream[i - k]) * base_pow) & _HASH_MASK
        h = (h * _HASH_BASE + ord(ch)) & _HASH_MASK
        if i >= k - 1:
            grams.add(h)
    return grams, base_pow


def _kgram_share(text: str, grams: set[int], base_pow: int,
                 k: int) -> float | None:
    """Fraction of `text`'s k-grams present in `grams`; None if text < k."""
    if len(text) < k:
        return None
    h = 0
    hits = total = 0
    for i, ch in enumerate(text):
        if i >= k:
            h = (h - ord(text[i - k]) * base_pow) & _HASH_MASK
        h = (h * _HASH_BASE + ord(ch)) & _HASH_MASK
        if i >= k - 1:
            total += 1
            if h in grams:
                hits += 1
    return hits / total if total else None


def _script_runs(script: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Contiguous runs of the alignment as (kind, first_hyp, last_hyp).

    kind is 'insert' for inserted OCR text and 'aligned' for matched text
    (match + replace steps, the recognition's own footprint). Runs break at a
    step of the other kind OR at a hypothesis-position gap (a same-kind step
    separated by the opposite kind is already a break; a gap alone cannot
    happen within one kind, but the guard keeps it honest).
    """
    runs: list[tuple[str, int, int]] = []
    kind = None
    start = last = 0
    for tag, _ref_pos, hyp_pos in script:
        if tag == "delete":
            cur = None
        else:
            cur = "insert" if tag == "insert" else "aligned"
        if cur is None:
            if kind is not None:
                runs.append((kind, start, last))
                kind = None
            continue
        if cur == kind and hyp_pos == last + 1:
            last = hyp_pos
            continue
        if kind is not None:
            runs.append((kind, start, last))
        kind, start, last = cur, hyp_pos, hyp_pos
    if kind is not None:
        runs.append((kind, start, last))
    return runs


def containment_page(ref: str, hyp: str, script: list[tuple[str, int, int]],
                     grams: set[int], base_pow: int, k: int = _GT_K) -> dict:
    """Verbatim-presence of inserted vs aligned OCR text in the GT stream."""
    out = {"insert_tested": 0, "insert_in_gt": 0,
           "aligned_tested": 0, "aligned_in_gt": 0}
    for kind, a, b in _script_runs(script):
        if kind is None:
            continue
        text = hyp[a:b + 1]
        share = _kgram_share(text, grams, base_pow, k)
        if share is None:
            continue
        if kind == "insert":
            out["insert_tested"] += len(text)
            out["insert_in_gt"] += len(text) if share >= 0.5 else 0
        else:
            out["aligned_tested"] += len(text)
            out["aligned_in_gt"] += len(text) if share >= 0.5 else 0
    return out


def _blank_containment() -> dict:
    return {"insert_tested": 0, "insert_in_gt": 0,
            "aligned_tested": 0, "aligned_in_gt": 0}


def diacritic_split(segments: list[dict], ocr_dir: Path, pages: list[int]) -> dict:
    """Letter accuracy vs marks: score the range in strip and keep modes.

    Each mode locates pages in its OWN canonical stream (the two normal forms
    have different offsets — plan 024 finding 7), then scores at the located
    span. Returns op totals for both, plus mark densities.
    """
    raw_ocr = " ".join(_page_body(load_raw(p, ocr_dir)) for p in pages)
    out = {"strip": _score_mode(segments, ocr_dir, pages, False),
           "keep": _score_mode(segments, ocr_dir, pages, True)}
    out["gt_marks"] = _mark_count(" ".join(s["text"] for s in segments))
    out["gt_base"] = _base_count(" ".join(s["text"] for s in segments))
    out["ocr_marks_on_pages"] = _mark_count(raw_ocr)
    out["ocr_base_on_pages"] = _base_count(raw_ocr)
    return out


def _score_mode(segments: list[dict], ocr_dir: Path, pages: list[int],
                keep: bool) -> dict:
    stream = normalize_text(
        " ".join(s["text"] for s in segments), keep_diacritics=keep)
    located_pages = pages + [pages[-1] + 1]
    hyps = {page: _page_hyp(load_raw(page, ocr_dir), keep)
            for page in located_pages}
    located = {page: locate_page(hyps[page], stream)["offset"]
               for page in located_pages}
    tot = {"ref_chars": 0, "hyp_chars": 0, "sub": 0, "ins": 0, "del": 0,
           "dist": 0}
    for page in pages:
        o = located.get(page)
        if o is None:
            continue
        o2 = located.get(page + 1)
        span = (o2 - o) if (o2 is not None and o2 > o) \
            else page_window_length(page)
        ref = stream[o:o + span]
        hyp = hyps[page]
        ops = edit_ops(ref, hyp)
        tot["ref_chars"] += len(ref)
        tot["hyp_chars"] += len(hyp)
        for key in ("sub", "ins", "del", "dist"):
            tot[key] += ops[key]
    tot["cer"] = round(tot["dist"] / tot["ref_chars"], 4) if tot["ref_chars"] else None
    return tot


def _page_hyp(raw_text: str, keep: bool) -> str:
    lines = [line for line in raw_text.splitlines()
             if line.strip() not in SECTION_MARKERS]
    return normalize_text("\n".join(lines), keep_diacritics=keep)


def _page_body(raw_text: str) -> str:
    return "\n".join(line for line in raw_text.splitlines()
                     if not line.lstrip().startswith("#"))


def _mark_count(text: str) -> int:
    return sum(1 for ch in text if unicodedata.combining(ch))


def _base_count(text: str) -> int:
    return sum(1 for ch in text
               if "ARABIC" in unicodedata.name(ch, "")
               and not unicodedata.combining(ch))


def load_raw(page: int, ocr_dir: Path) -> str:
    path = Path(ocr_dir) / f"page_{page:03d}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def range_rows(lo: int, hi: int, segments: list[dict], stream: str,
               seg_offsets: list[int], ocr_dir: Path,
               grams: set[int] | None = None,
               base_pow: int | None = None) -> list[dict]:
    """Per-page ref span + OCR lines + coverage + confidence, for lo..hi."""
    located, _ = locate_pages(list(range(lo, hi + 2)), stream, ocr_dir,
                              segments, seg_offsets, verbose=False)
    rows = []
    for page in range(lo, hi + 1):
        rec = located.get(page, {})
        o = rec.get("offset")
        raw = load_raw(page, ocr_dir)
        row = {"page": page, "located_offset": o,
               "confidence_percent": page_confidence(raw)}
        if o is None:
            rows.append(row)
            continue
        o2 = located.get(page + 1, {}).get("offset")
        span = (o2 - o) if (o2 is not None and o2 > o) \
            else page_window_length(page)
        ref = stream[o:o + span]
        lines, hyp = load_ocr_lines(raw)
        row["reference_chars"] = len(ref)
        row["ocr_chars"] = len(hyp)
        sc = score_window(ref, hyp)
        row.update({"cer": sc["cer"], "sub": sc["sub"], "ins": sc["ins"],
                    "del": sc["del"]})
        script = edit_script(ref, hyp)
        row["coverage"] = cover_page(ref, lines, hyp, script)
        if grams is not None:
            row["containment"] = containment_page(ref, hyp, script,
                                                   grams, base_pow)
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    cov = _blank_coverage()
    cont = _blank_containment()
    scored = [r for r in rows if "cer" in r]
    for r in scored:
        _merge(cov, r["coverage"])
        if "containment" in r:
            _merge(cont, r["containment"])
    gt = cov["gt_chars"] or 1
    ocr = cov["ocr_chars"] or 1
    cers = [r["cer"] for r in scored]
    conf = [(r["confidence_percent"], r["cer"]) for r in scored
            if r["confidence_percent"] is not None]
    dists = sorted(((r["sub"] + r["ins"] + r["del"], r["page"])
                    for r in scored), reverse=True)
    total_dist = sum(d for d, _ in dists) or 1
    summary = {
        "pages_scored": len(scored),
        "cer_mean": round(statistics.mean(cers), 4) if cers else None,
        "cer_median": round(statistics.median(cers), 4) if cers else None,
        "cer_min": round(min(cers), 4) if cers else None,
        "cer_max": round(max(cers), 4) if cers else None,
        "pages_cer_over_2": sum(1 for r in scored if r["cer"] > 2.0),
        "top5_pages_share": round(
            sum(d for d, _ in dists[:5]) / total_dist, 4),
        "top5_pages": [{"page": p, "dist": d} for d, p in dists[:5]],
        "coverage": cov,
        "containment": cont,
        "insert_in_gt_rate": round(
            cont["insert_in_gt"] / (cont["insert_tested"] or 1), 4),
        "aligned_in_gt_rate": round(
            cont["aligned_in_gt"] / (cont["aligned_tested"] or 1), 4),
        "gt_matched_rate": round(cov["gt_matched"] / gt, 4),
        "gt_dropped_rate": round(cov["gt_dropped"] / gt, 4),
        "ocr_matched_rate": round(cov["ocr_matched"] / ocr, 4),
        "ocr_extra_rate": round(cov["ocr_extra"] / ocr, 4),
        "extra_apparatus_share": round(
            cov["extra_apparatus"] / (cov["ocr_extra"] or 1), 4),
        "extra_verse_share": round(
            cov["extra_verse"] / (cov["ocr_extra"] or 1), 4),
        "extra_other_prose_share": round(
            cov["extra_other_prose"] / (cov["ocr_extra"] or 1), 4),
        "confidence_vs_cer": confidence_correlation(conf),
    }
    return summary


def confidence_correlation(pairs: list[tuple[float, float]]) -> dict:
    """Pearson r and the two means: is confidence predictive of CER?"""
    if len(pairs) < 2:
        return {"n": len(pairs)}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    r = num / (dx * dy) if dx and dy else 0.0
    return {"n": len(pairs), "pearson_r": round(r, 4),
            "mean_confidence": round(mx, 2), "mean_cer": round(my, 4)}


def _print_report(summary: dict, rows: list[dict], diac: dict) -> None:
    c = summary["coverage"]
    out = sys.stderr
    print("\n=== PHASE 2 ERROR BUDGET — pages 7-60 ===", file=out)
    print(f"pages scored: {summary['pages_scored']}", file=out)
    print(f"page CER  mean/median/min/max: {summary['cer_mean']} / "
          f"{summary['cer_median']} / {summary['cer_min']} / "
          f"{summary['cer_max']}", file=out)
    dist = c["gt_dropped"] + c["ocr_extra"] + c["substitutions"]
    print("\n-- 1. length decomposition --", file=out)
    print(f"GT chars {c['gt_chars']}  OCR chars {c['ocr_chars']}  "
          f"ratio {summary['coverage']['ocr_chars'] / max(1, c['gt_chars']):.4f}",
          file=out)
    for name, val in (("substitutions", c["substitutions"]),
                      ("insertions(extra OCR)", c["ocr_extra"]),
                      ("deletions(dropped GT)", c["gt_dropped"])):
        print(f"  {name:<24} {val:>7}  "
              f"({val / max(1, dist) * 100:5.1f}% of distance)", file=out)
    print("\n-- 2. coverage --", file=out)
    print(f"GT matched {summary['gt_matched_rate'] * 100:.1f}%  "
          f"dropped {summary['gt_dropped_rate'] * 100:.1f}%", file=out)
    print(f"OCR matched {summary['ocr_matched_rate'] * 100:.1f}%  "
          f"extra {summary['ocr_extra_rate'] * 100:.1f}%", file=out)
    print(f"extra OCR chars by source line:", file=out)
    print(f"  apparatus-like prose : {summary['extra_apparatus_share'] * 100:5.1f}%",
          file=out)
    print(f"  verse lines          : {summary['extra_verse_share'] * 100:5.1f}%",
          file=out)
    print(f"  other prose          : {summary['extra_other_prose_share'] * 100:5.1f}%",
          file=out)
    cont = summary["containment"]
    print(f"extra text verbatim in GT anywhere vs aligned text (k={_GT_K} control):",
          file=out)
    print(f"  inserted OCR : {cont['insert_in_gt']}/{cont['insert_tested']} "
          f"= {summary['insert_in_gt_rate'] * 100:5.1f}% found in GT",
          file=out)
    print(f"  aligned  OCR : {cont['aligned_in_gt']}/{cont['aligned_tested']} "
          f"= {summary['aligned_in_gt_rate'] * 100:5.1f}% found in GT (control)",
          file=out)
    print("\n-- 3. tashkeel split --", file=out)
    print(f"strip: CER {diac['strip']['cer']}  "
          f"ops sub/ins/del {diac['strip']['sub']}/{diac['strip']['ins']}/"
          f"{diac['strip']['del']}", file=out)
    print(f"keep : CER {diac['keep']['cer']}  "
          f"ops sub/ins/del {diac['keep']['sub']}/{diac['keep']['ins']}/"
          f"{diac['keep']['del']}", file=out)
    print(f"GT marks/base {diac['gt_marks'] / max(1, diac['gt_base']):.4f}  "
          f"OCR marks/base(pages) "
          f"{diac['ocr_marks_on_pages'] / max(1, diac['ocr_base_on_pages']):.4f}",
          file=out)
    print("  (strip/keep locate independently in their own normal form and "
          "score per-page\n   dist/ref; compare the two columns to each other, "
          "not to the concatenated\n   headline CER.)", file=out)
    print("\n-- 4. per-page distribution --", file=out)
    print(f"pages with CER > 2.0: {summary['pages_cer_over_2']}"
          f"/{summary['pages_scored']}  "
          f"top-5 pages hold {summary['top5_pages_share'] * 100:.1f}% of distance",
          file=out)
    print(f"  worst: "
          + ", ".join(f"p{t['page']}={t['dist']}" for t in summary["top5_pages"]),
          file=out)
    cv = summary["confidence_vs_cer"]
    print("\n-- 5. confidence vs error (page-level) --", file=out)
    if "pearson_r" in cv:
        print(f"pearson r(confidence, CER) = {cv['pearson_r']}  "
              f"(n={cv['n']}, mean conf {cv['mean_confidence']}%, "
              f"mean CER {cv['mean_cer']})", file=out)
    else:
        print(f"insufficient pairs (n={cv.get('n')})", file=out)
    print("  (per-line confidence is not persisted by the pipeline; only the "
          "page-level\n   '# Page Confidence' header is available on stored "
          "output.)", file=out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", default=str(SEGMENTS_PATH))
    ap.add_argument("--ocr-dir", default=str(OCR_DIR))
    ap.add_argument("--range", default="7-60")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    lo, hi = (int(x) for x in args.range.split("-", 1))
    pages = list(range(lo, hi + 1))
    segments = load_segments(args.segments)
    stream, seg_offsets = canonical_stream(segments)
    ocr_dir = Path(args.ocr_dir)

    rows = range_rows(lo, hi, segments, stream, seg_offsets, ocr_dir,
                      *build_gt_kgrams(stream))
    summary = summarize(rows)
    diac = diacritic_split(segments, ocr_dir, pages)
    _print_report(summary, rows, diac)

    payload = {
        "document": DOC,
        "range": [lo, hi],
        "summary": summary,
        "diacritic_split": diac,
        "pages": rows,
    }
    out = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"\njson -> {args.json_out}", file=sys.stderr)
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
