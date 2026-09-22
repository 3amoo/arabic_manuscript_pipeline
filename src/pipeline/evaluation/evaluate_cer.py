"""
CER/WER measurement harness (AGENTS.md §4.12 / §8 / Phase 4).

Compares manual ground truth (GT) pages against the deterministic raw OCR
evidence under the SAME normalization, computing per-page and aggregate
CER (character error rate) and WER (word error rate) via `jiwer`.

WHY THIS EXISTS: AGENTS.md §4.12 forbids claiming an OCR/preprocessing
improvement without a measurement. That measurement must compare against
a MANUAL ground truth (أرضية صحيحة يدوية) - never the model output
itself, and never the cache (which would trivially score 0).

Layout:
    ground_truth/<document>/page_NNN.txt   manual transcription
    output/<document>/raw_text/page_NNN.txt  OCR evidence (unchanged, §6)

Normalization applied to BOTH sides before scoring:
  - every line whose stripped content starts with '#' is dropped (raw_text
    page headers like "# Page N" / "# OCR Method" / "# Page Confidence";
    GT files may carry a "# GT TODO / note" line too);
  - tatweel U+0640 removed;
  - in --diacritics strip mode (the default): tashkeel U+064B..U+0652 and
    U+0670 are removed from both sides, so the score measures *letter*
    accuracy. The project's core goal is preserving tashkeel, but a hand
    GT that is letter-accurate is far more reliable than a GT whose
    diacritics are guessed - measuring diacritic recovery on top of a
    solid letter-accurate GT is a later refinement (--diacritics keep
    exists to score the raw forms once such GT is available);
  - Unicode whitespace collapsed, lines joined, leading/trailing trimmed.

Usage:
    myenv/bin/python evaluate_cer.py --document "عمود النسب نسخة 2" \
        --pages 24-26
    myenv/bin/python evaluate_cer.py --document X --pages 20,24-27 \
        --diacritics keep

Exit codes: 0 = scores computed and printed; 2 = one or more pages had no
GT file, or only a placeholder (a GT file whose only content is '#'-comment
lines - e.g. the # GT-PENDING files created by bootstrap_ground_truth.py -
is NOT ready yet). The measurement cannot run honestly in that case and
this is NOT reported as 0 error.

Scores are per-page (CER%, WER%) plus an aggregate over all requested
pages (ref/hyp concatenated with single spaces for WER, summed Levenshtein
for CER is approximated by jiwer on the concatenated strings as well), so
the aggregate is comparable across runs.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import jiwer

TATWEEL = "\u0640"
TASHKEEL = re.compile(r"[\u064B-\u0652\u0670]")


def normalize_text(text: str, keep_diacritics: bool = False) -> str:
    """
    Canonical form for scoring. Applied identically to GT and raw text.
    Dropped: header/todo lines (leading '#'), tatweel. Optionally
    tashkeel. Whitespace collapsed. All other characters are kept as-is
    (Latin watermark tokens like 'wmw' count - honesty over cosmetics).
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ]
    joined = " ".join(lines)
    if not keep_diacritics:
        joined = TASHKEEL.sub("", joined)
    joined = joined.replace(TATWEEL, "")
    return " ".join(joined.split())


def load_page_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def has_usable_gt_content(text: str) -> bool:
    """
    A GT file counts as actionable only if it contains at least one
    non-comment, non-blank line. Placeholders that carry only '#'-comment
    lines (see bootstrap_ground_truth.py) are treated as not ready, so a
    measurement over them honestly exits 2 instead of scoring against an
    empty reference.
    """
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if line.strip():
            return True
    return False


def score_page(gt_path: Path, raw_path: Path, keep_diacritics: bool) -> dict:
    ref = normalize_text(load_page_text(gt_path), keep_diacritics)
    hyp = normalize_text(load_page_text(raw_path), keep_diacritics)
    return {
        "ref_len_chars": len(ref),
        "ref_words": len(ref.split()),
        "cer": jiwer.cer(ref, hyp),
        "wer": jiwer.wer(ref, hyp),
    }


def parse_page_spec(spec: str) -> list:
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return sorted(set(pages))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--document", required=True)
    ap.add_argument("--pages", help="e.g. 24-26 or 20,24-27 (ignored with --alignment)")
    ap.add_argument("--diacritics", choices=["strip", "keep"], default="strip")
    ap.add_argument("--output-root", default="data/output")
    ap.add_argument("--gt-root", default="data/ground_truth")
    # --- spec 006 additions (contracts/cli.md) ---
    ap.add_argument(
        "--alignment",
        default=None,
        help="alignment.json from align_ground_truth (spec 006 mode)",
    )
    ap.add_argument(
        "--diacritics-metrics",
        action="store_true",
        help="add correct/missing/wrong diacritic stats (needs --alignment)",
    )
    ap.add_argument(
        "--report-dir",
        default="data/evaluation_reports/006",
        help="where to write quality_report.* and heatmap.txt",
    )
    ap.add_argument(
        "--heatmap",
        action="store_true",
        help="write ASCII heatmap of per-page CER",
    )
    ap.add_argument(
        "--layer",
        default="raw_text",
        help=(
            "evidence directory to score: raw_text (the immutable OCR "
            "record, §6) or vault_corrected_text (the Phase 1 corrected "
            "layer). Defaults to raw_text. Alignment-mode only."
        ),
    )
    args = ap.parse_args()

    if args.alignment:
        if args.diacritics_metrics:
            pass  # handled inside _run_alignment_mode
        return _run_alignment_mode(args)

    pages = parse_page_spec(args.pages)
    keep = args.diacritics == "keep"
    raw_dir = Path(args.output_root) / args.document / "raw_text"
    gt_root = Path(args.gt_root)
    gt_dir = gt_root / args.document

    missing = []
    results = {}
    for num in pages:
        raw_path = raw_dir / f"page_{num:03d}.txt"
        gt_path = gt_dir / f"page_{num:03d}.txt"
        if not gt_path.exists() or not has_usable_gt_content(
            load_page_text(gt_path)
        ):
            missing.append(num)
            continue
        if not raw_path.exists():
            print(f"ERROR: raw page missing: {raw_path}", file=sys.stderr)
            return 1
        results[num] = score_page(gt_path, raw_path, keep)

    if missing:
        print("NO MEASUREMENT - ground truth missing for pages: "
              f"{sorted(missing)}")
        print(f"GT directory: {gt_dir}  (create page_NNN.txt per "
              "data/ground_truth/README.md)")
        return 2

    print(f"CER/WER vs manual ground truth  (document: {args.document}, "
          f"diacritics: {args.diacritics})\n")
    print(f"{'page':>5}  {'CER%':>7}  {'WER%':>7}  {'ref_chars':>9}  "
          f"{'ref_words':>9}")
    tot_ref_chars = 0
    tot_ref_words = 0
    concat_ref = []
    concat_hyp = []
    for num in pages:
        r = results[num]
        tot_ref_chars += r["ref_len_chars"]
        tot_ref_words += r["ref_words"]
        concat_ref.append(normalize_text(
            load_page_text(gt_dir / f"page_{num:03d}.txt"), keep))
        concat_hyp.append(normalize_text(
            load_page_text(raw_dir / f"page_{num:03d}.txt"), keep))
        print(f"{num:>5}  {r['cer'] * 100:>6.2f}  {r['wer'] * 100:>6.2f}  "
              f"{r['ref_len_chars']:>9}  {r['ref_words']:>9}")

    ref_all = " ".join(concat_ref)
    hyp_all = " ".join(concat_hyp)
    cer_all = jiwer.cer(ref_all, hyp_all) * 100
    wer_all = jiwer.wer(ref_all, hyp_all) * 100
    print(f"\naggregate ({len(pages)} pages, {tot_ref_chars} chars, "
          f"{tot_ref_words} words): CER={cer_all:.2f}%  WER={wer_all:.2f}%")
    return 0



# --- spec 006 additions -------------------------------------------------
# Alignment-based scoring (FR-004..FR-007) + diacritic metrics (FR-005).
# These EXTEND the original per-page-GT mode; the original `--pages`
# mode above is preserved unchanged (Constitution II: evolve, no rewrite).

import unicodedata  # noqa: E402  (kept local to the additions)

DIACRITIC_RANGES = (
    "\u064B",  # fathatan
    "\u064C",  # dammatan
    "\u064D",  # kasratan
    "\u064E",  # fatha
    "\u064F",  # damma
    "\u0650",  # kasra
    "\u0651",  # shadda
    "\u0652",  # sukun
    "\u0670",  # superscript alef
)


def _is_diacritic(ch: str) -> bool:
    return ch in DIACRITIC_RANGES


def analyze_diacritics(gt_text: str, out_text: str) -> dict:
    """
    Diacritic preservation metric (FR-005, research.md R6).

    Two complementary signals:

    1. **Density ratio** (primary): marks-per-Arabic-base-letter in each
       text. The output's density divided by GT's density is the
       fraction of diacritics the pipeline retained. This does NOT
       require word alignment and is therefore robust to OCR character
       errors — a word-level comparison was measured to be useless here
       (only 2% of output words are byte-identical in their base form,
       because the OCR misreads letters throughout).
    2. **Per-word counts** (secondary, best-effort): for the subset of
       words whose base letters match exactly, count correct / missing
       / wrong / extra. These are lower bounds and are labelled as such
       — they are not a complete census.

    `accuracy` = the density ratio, the honest headline number.
    """
    def density(s):
        marks = sum(1 for c in s if unicodedata.combining(c))
        base = sum(
            1
            for c in s
            if "ARABIC" in unicodedata.name(c, "")
            and not unicodedata.combining(c)
        )
        return marks / base if base else 0.0

    gt_dens = density(gt_text)
    out_dens = density(out_text)
    ratio = out_dens / gt_dens if gt_dens else 0.0

    # Best-effort per-word census on exactly-matching base words.
    def split_words(s):
        out = []
        for w in s.split():
            base = "".join(c for c in w if not unicodedata.combining(c))
            marks = [c for c in w if unicodedata.combining(c)]
            out.append((base, marks))
        return out

    gw = split_words(gt_text)
    ow = split_words(out_text)
    stats = {"correct": 0, "missing": 0, "wrong": 0, "extra": 0}
    n = min(len(gw), len(ow))
    for i in range(n):
        gb, gm = gw[i]
        ob, om = ow[i]
        if gb != ob:
            continue
        if gm and om and gm == om:
            stats["correct"] += 1
        elif gm and not om:
            stats["missing"] += 1
        elif gm and om and gm != om:
            stats["wrong"] += 1
        elif not gm and om:
            stats["extra"] += 1

    stats["gt_density"] = round(gt_dens, 4)
    stats["out_density"] = round(out_dens, 4)
    stats["total_gt"] = stats["correct"] + stats["missing"] + stats["wrong"]
    stats["accuracy"] = round(ratio, 4)
    stats["loss_pct"] = round((1.0 - ratio) * 100, 1)
    stats["note"] = (
        "accuracy = density ratio (marks/base letter). Per-word counts "
        "are a lower bound on exactly-base-matched words only."
    )
    return stats


def score_aligned_page(gt_verses, raw_path, entry, keep_diacritics=False):
    """
    Score one page against its aligned GT slice (spec 006 FR-004).

    gt_verses: full normalized GT list (diacritics stripped).
    entry: AlignmentEntry dict (gt_start/gt_end are 1-based).
    Returns None when the page cannot be scored honestly.
    """
    if entry["gt_start"] is None or entry["gt_end"] is None:
        return None
    status = entry["status"]
    if status in ("out_of_gt_scope", "empty_page", "prose_only"):
        return None
    # An unmatched page is now scored when it carries a recovered
    # best-effort window (spec 008, FR-002/FR-006): the window exists
    # to keep the GT cursor honest, and excluding the page would
    # silently understate the corpus CER by dropping exactly the worst
    # pages (measured: p59/p67 excluded at 0.0% in the spec-006 report
    # while their true-window CER is 54.1%/42.3%). The page is still
    # flagged recovered + unmatched so nobody mistakes it for clean.
    if status == "unmatched" and not entry.get("recovered"):
        return None

    lo = entry["gt_start"] - 1
    hi = entry["gt_end"]  # exclusive
    ref_verses = gt_verses[lo:hi]
    if not ref_verses:
        return None

    hyp_verses = [
        normalize_text(l, keep_diacritics)
        for l in load_page_text(raw_path).splitlines()
        if l.strip() and not l.lstrip().startswith("#") and " ... " in l
    ]
    n = min(len(ref_verses), len(hyp_verses))
    if n == 0:
        return None

    ref = " ".join(ref_verses[:n])
    hyp = " ".join(hyp_verses[:n])
    return {
        "cer": jiwer.cer(ref, hyp),
        "wer": jiwer.wer(ref, hyp),
        "gt_verses_count": len(ref_verses),
        "out_verses_count": len(hyp_verses),
        "evaluated_verses_count": n,
        "ref_chars": len(ref),
        "ref_words": len(ref.split()),
        "status": status,
    }


def build_corpus_report(document, entries, gt_verses, raw_dir, report_dir,
                        diacritics_metrics=False, gt_file=None):
    """
    Assemble the full CorpusReport (data-model.md) for aligned pages.
    Writes quality_report.json + quality_report.txt.
    """
    pages = []
    total_ref_chars = 0
    total_ref_words = 0
    concat_ref = []
    concat_hyp = []
    hall_total = 0

    for e in entries:
        raw_path = raw_dir / f"page_{e['page']:03d}.txt"
        scored = score_aligned_page(gt_verses, raw_path, e)
        hall_total += len(e.get("hallucination_verses") or [])

        pq = {
            "page": e["page"],
            "status": e["status"],
            "recovered": bool(e.get("recovered")),
            "cer": None,
            "wer": None,
            "diacritics": None,
            "gt_verses_count": e.get("gt_verses_count", 0),
            "out_verses_count": e.get("out_verses_count", 0),
            "evaluated_verses_count": 0,
            "hallucination_count": len(e.get("hallucination_verses") or []),
        }
        if scored:
            pq.update(scored)
            pq.pop("status", None)
            pq["status"] = scored["status"]
            concat_ref.append(" ".join(
                gt_verses[e["gt_start"] - 1: e["gt_end"]]
            ))
            concat_hyp.append(" ".join(
                normalize_text(l)
                for l in load_page_text(raw_path).splitlines()
                if l.strip() and not l.lstrip().startswith("#")
                and " ... " in l
            ))
            total_ref_chars += scored["ref_chars"]
            total_ref_words += scored["ref_words"]

            if diacritics_metrics and gt_file is not None:
                raw_gt = _raw_gt_slice(gt_file, e)
                raw_out = _raw_out_verses(raw_path)
                n = min(len(raw_gt), len(raw_out))
                pq["diacritics"] = analyze_diacritics(
                    "\n".join(raw_gt[:n]), "\n".join(raw_out[:n])
                )
        pages.append(pq)

    ref_all = " ".join(concat_ref)
    hyp_all = " ".join(concat_hyp)
    weighted_cer = jiwer.cer(ref_all, hyp_all) if ref_all else 0.0
    weighted_wer = jiwer.wer(ref_all, hyp_all) if ref_all else 0.0

    dia_total = {"correct": 0, "missing": 0, "wrong": 0, "extra": 0,
                 "total_gt": 0, "accuracy": 0.0,
                 "gt_density": 0.0, "out_density": 0.0, "loss_pct": 0.0,
                 "note": ""}
    if diacritics_metrics:
        # Weighted density across the whole evaluated corpus.
        marks_gt = 0
        base_gt = 0
        marks_out = 0
        base_out = 0
        for p in pages:
            if p.get("diacritics"):
                for k in ("correct", "missing", "wrong", "extra"):
                    dia_total[k] += p["diacritics"][k]
        # recompute aggregate density from concatenated raw text
        for e in entries:
            # Only genuinely windowless pages stay out of the diacritic
            # aggregate. A recovered unmatched page (spec 008) now has a
            # window and IS scored, so it contributes here too.
            if e["gt_start"] is None or gt_file is None:
                continue
            import unicodedata as _ud
            raw_gt = "\n".join(_raw_gt_slice(gt_file, e))
            raw_out = "\n".join(_raw_out_verses(
                raw_dir / f"page_{e['page']:03d}.txt"
            ))
            for c in raw_gt:
                if _ud.combining(c):
                    marks_gt += 1
                elif "ARABIC" in _ud.name(c, ""):
                    base_gt += 1
            for c in raw_out:
                if _ud.combining(c):
                    marks_out += 1
                elif "ARABIC" in _ud.name(c, ""):
                    base_out += 1
        gtd = marks_gt / base_gt if base_gt else 0.0
        outd = marks_out / base_out if base_out else 0.0
        dia_total["gt_density"] = round(gtd, 4)
        dia_total["out_density"] = round(outd, 4)
        dia_total["accuracy"] = round(outd / gtd, 4) if gtd else 0.0
        dia_total["loss_pct"] = round((1.0 - outd / gtd) * 100, 1) if gtd else 0.0
        dia_total["total_gt"] = (
            dia_total["correct"] + dia_total["missing"] + dia_total["wrong"]
        )

    scored_pages = [p for p in pages if p["cer"] is not None]
    worst = sorted(scored_pages, key=lambda p: -p["cer"])[:10]
    best = sorted(scored_pages, key=lambda p: p["cer"])[:5]

    # Honest denominator split (spec 008 FR-007, SC-005): the aggregate
    # CER now includes recovered pages, so the report must say how many
    # of the scored pages are clean vs. distrusted. Otherwise the number
    # could be misread as if every scored page were a clean measurement.
    pages_clean = sum(1 for p in scored_pages if p["status"] == "matched")
    pages_low_confidence = sum(
        1 for p in scored_pages
        if p["status"] in ("low_confidence", "count_mismatch")
    )
    pages_recovered = sum(
        1 for p in scored_pages if p.get("recovered")
    )
    pages_excluded = len(pages) - len(scored_pages)

    report = {
        "document": document,
        "note": "Distance to a working benchmark (Constitution VI), not "
                "absolute truth.",
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "gt_source": "data/ground_truth/عمود النسب/عمود_النسب.clean.md",
        "pages_total": len(entries),
        "pages_evaluated": len(scored_pages),
        "pages_clean": pages_clean,
        "pages_low_confidence": pages_low_confidence,
        "pages_recovered": pages_recovered,
        "pages_excluded": pages_excluded,
        "pages_out_of_scope": sum(
            1 for e in entries if e["status"] == "out_of_gt_scope"
        ),
        "pages_prose_only": sum(
            1 for e in entries if e["status"] == "prose_only"
        ),
        "verses_evaluated": sum(p["evaluated_verses_count"] for p in pages),
        "weighted_cer": weighted_cer,
        "weighted_wer": weighted_wer,
        "diacritics_total": dia_total,
        "hallucination_total": hall_total,
        "worst_pages": worst,
        "best_pages": best,
        "pages": pages,
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_text_report(report, report_dir / "quality_report.txt")
    return report


def _raw_gt_slice(gt_file, entry):
    """
    Raw (diacritics-intact) GT verses for one aligned page.
    Needed because analyze_diacritics must see the marks that
    normalize_text strips.
    """
    import re as _re
    from pathlib import Path as _Path

    text = _Path(gt_file).read_text(encoding="utf-8")
    verses = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _re.match(r"^\s*[\u0660-\u0669]+[\s\u060c\u061b\.]*", s)
        if m:
            s = s[m.end():]
        if s.strip():
            verses.append(s.strip())
    lo = max(0, entry["gt_start"] - 1)
    hi = entry["gt_end"]
    return verses[lo:hi]


def _raw_out_verses(raw_path):
    """Raw (diacritics-intact) output verse lines for one page."""
    out = []
    for line in load_page_text(raw_path).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if " ... " in s:
            out.append(s)
    return out


def _write_text_report(report, path):
    r = report
    lines = []
    lines.append(f"=== تقرير جودة المخطوط: {r['document']} ===")
    lines.append(f"Generated: {r['generated_at']}")
    lines.append("")
    lines.append(
        "المرجع: 620 بيت (عمود_النسب.clean.md). الأرقام = مسافة إلى "
        "benchmark عمل (Constitution §VI)، مش حقيقة مطلقة."
    )
    lines.append("")
    lines.append(
        f"الصفحات: {r['pages_total']} | قِيست: {r['pages_evaluated']} "
        f"| خارج نطاق GT: {r['pages_out_of_scope']} "
        f"| نثرية: {r['pages_prose_only']}"
    )
    # Honest denominator (spec 008 SC-005): how trustworthy are the
    # scored pages? recovered = نُقِّلت بنافذة تقديرية (مستعادة) بعد
    # أن فشل ربطها — تُقاس لكن لا تُعتبر قياسًا نظيفًا.
    lines.append(
        f"  من المقيسة: نظيفة {r.get('pages_clean', 0)} | "
        f"ضعيفة الثقة {r.get('pages_low_confidence', 0)} | "
        f"مستعادة (recovered) {r.get('pages_recovered', 0)} — "
        f"خارج القياس {r.get('pages_excluded', 0)}"
    )
    lines.append("")
    lines.append(f"CER المرجَّح: {r['weighted_cer'] * 100:.1f}%")
    lines.append(f"WER المرجَّح: {r['weighted_wer'] * 100:.1f}%")
    d = r["diacritics_total"]
    if d.get("gt_density"):
        lines.append(
            f"التشكيل: كثافة GT {d['gt_density']:.3f} مقابل "
            f"{d['out_density']:.3f} في الإخراج — استُرجع "
            f"{d['accuracy'] * 100:.1f}% من الحركات "
            f"(فقد {d['loss_pct']:.1f}%)"
        )
        lines.append(
            f"  إحصاء الكلمات المتطابقة base-only (حد أدنى): "
            f"correct {d['correct']} / missing {d['missing']} / "
            f"wrong {d['wrong']} / extra {d['extra']}"
        )
    lines.append("")
    lines.append(
        f"أبيات الهلوسة المشتبهة (تشخيصي): {r['hallucination_total']}"
    )
    lines.append("")
    if r["worst_pages"]:
        lines.append("أسوأ 5 صفحات:")
        for p in r["worst_pages"][:5]:
            tag = p["status"]
            if p.get("recovered"):
                tag = f"{tag}+recovered"
            lines.append(
                f"  ص{p['page']}: CER {p['cer'] * 100:.1f}% "
                f"WER {p['wer'] * 100:.1f}% [{tag}]"
            )
    lines.append("")
    lines.append("أفضل 3 صفحات:")
    for p in r["best_pages"][:3]:
        lines.append(
            f"  ص{p['page']}: CER {p['cer'] * 100:.1f}% "
            f"WER {p['wer'] * 100:.1f}%"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_alignment_mode(args):
    """spec 006: --alignment mode (contracts/cli.md)."""
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    from pathlib import Path as _Path

    align_path = _Path(args.alignment)
    if not align_path.exists():
        print(f"ERROR: alignment file not found: {align_path}", file=sys.stderr)
        return 1
    payload = _json.loads(align_path.read_text(encoding="utf-8"))
    entries = payload["alignment"]
    payload_gt_file = payload["gt_file"]

    # Rebuild the normalized GT list (same normalizer as align tool).
    from src.pipeline.evaluation.align_ground_truth import extract_gt_verses
    gt_verses = extract_gt_verses(_Path(payload["gt_file"]))
    # --layer selects which evidence directory to score: raw_text (the
    # immutable OCR record, §6) or vault_corrected_text (the Phase 1
    # corrected layer). The alignment is page-number keyed, so it stays
    # valid for either layer.
    layer_dir = _Path(args.output_root) / args.document / args.layer
    if not layer_dir.is_dir():
        print(
            f"ERROR: evidence layer not found: {layer_dir}\n"
            f"available layers are raw_text and (if the corrector ran) "
            f"vault_corrected_text",
            file=sys.stderr,
        )
        return 1
    raw_dir = layer_dir

    report = build_corpus_report(
        args.document,
        entries,
        gt_verses,
        raw_dir,
        _Path(args.report_dir),
        diacritics_metrics=args.diacritics_metrics,
        gt_file=payload_gt_file,
    )

    print(f"spec 006 report -> {args.report_dir}")
    print(
        f"pages evaluated: {report['pages_evaluated']}/{report['pages_total']}"
    )
    print(f"CER: {report['weighted_cer'] * 100:.1f}%")
    print(f"WER: {report['weighted_wer'] * 100:.1f}%")
    if report["diacritics_total"]["total_gt"]:
        print(
            f"diacritics accuracy: "
            f"{report['diacritics_total']['accuracy'] * 100:.1f}%"
        )

    if args.heatmap:
        _write_heatmap(report, _Path(args.report_dir) / "heatmap.txt")
    if report["pages_out_of_scope"] or report["pages_prose_only"]:
        return 2
    return 0


HEATMAP_LEGEND = (
    "المفتاح: . = لم تُقس  _ = prose  # = <5%  o = 5-15%  "
    "O = 15-30%  X = 30-60%  ! = >60%  ? = low_conf"
)


def _heat_cell(page):
    if page["cer"] is None:
        if page["status"] == "prose_only":
            return "_"
        if page["status"] == "low_confidence":
            return "?"
        return "."
    c = page["cer"]
    if page["status"] == "low_confidence":
        return "?"
    if c < 0.05:
        return "#"
    if c < 0.15:
        return "o"
    if c < 0.30:
        return "O"
    if c < 0.60:
        return "X"
    return "!"


def _write_heatmap(report, path):
    pages = report.get("pages", [])
    total = report["pages_total"]
    lines = [f"توزيع CER عبر الصفحات ({total}):"]
    row = []
    labels = []
    for i in range(1, total + 1):
        p = next((x for x in pages if x["page"] == i), None)
        row.append(_heat_cell(p) if p else ".")
        if i % 10 == 1:
            labels.append(f"{i:>5}")
    lines.append("        " + "".join(labels))
    lines.append("        " + "".join(row))
    lines.append("")
    lines.append(HEATMAP_LEGEND)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
