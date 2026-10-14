"""
Tests for scripts/score_lamae_pages.py + scripts/lamae_gt_stream.py
(plan 024, Phase 1 evidence contract).

Two things are pinned here, per the plan:
  1. **Determinism** — the harness is the instrument every later phase
     measures with, so two runs over identical input must agree exactly,
     and the canonical stream must be a pure function of its segments
     (finding 7: three mutually incompatible GT-stream normalizers were
     in play, so offsets never composed across tools).
  2. **Synthetic offset recovery** — a GT stream and an OCR-with-known-
     corruption built in-test: the locator must recover the true offset
     from verbatim evidence alone (never from CER), and the monotonicity
     assertion must catch a planted violation loudly rather than silently
     dropping the page.

The locator tests use synthetic Arabic text rather than the real Shamela
segments so they stay fast and self-contained; the real-stream classes at
the bottom exercise the actual book when /tmp/opencode/folios.json is
present (the stream there is 1,426,417 chars; build_form_pair over it
takes ~1.5s, which is why the rest is synthetic).

The synthetic corruption is bimodal — long clean stretches interleaved
with garbage regions — because that is the profile the real book shows
(a uniform 15% substitution rate leaves no verbatim 10-char window alive,
while the real pages yield 4-30; a fully garbage page yields zero votes,
which is what the interpolated fallback exists for). The located offset
carries a small *negative* skew: the OCR's insertion-style inflation
makes an OCR window at position w sit at GT position w - extras, so the
median of implied starts lands a few tens of chars below the true page
start. That is the price of the plan's "hit minus window position"
estimator and it is far inside the 200-char cluster tolerance.
"""

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import jiwer  # noqa: E402
import rapidfuzz  # noqa: E402

from lamae_gt_stream import (  # noqa: E402
    anchor_offset,
    build_form_pair,
    canonical_stream,
    load_segments,
    map_old_to_canonical,
    page_hypothesis,
    page_window_length,
)
from score_lamae_pages import (  # noqa: E402
    CLUSTER_TOL,
    LAMAE_PHASE1_PAGES,
    collect_votes,
    edit_ops,
    edit_script,
    evaluate_range,
    locate_page,
    locate_pages,
    parse_range,
    score_pages,
    score_window,
)
from src.pipeline.evaluation.evaluate_cer import normalize_text  # noqa: E402

REAL_SEGMENTS = Path("/tmp/opencode/folios.json")

# Corpus with the shape the real book has: mostly position-unique text
# (so a 10-char window is a fingerprint, as in the Shamela stream) with a
# formulaic phrase repeated on every page (Quranic formulas / fixed
# commentary openers) to stress the "scored by distinct windows" rule.
FORMULA = "وقوله الذي يقتضي العلم "
PAGE_CHARS = 900


def synthetic_segments(n_pages: int = 40) -> list[dict]:
    """A folio-segment list shaped like split_shamela_folios output."""
    segs, pos, nr = [], 0, 1000
    for i in range(n_pages):
        body, n = [], 0
        while n < PAGE_CHARS:
            if n and n % 333 == 0:
                body.append(FORMULA)
            else:
                body.append(f"المقطع{nr}من")
                nr += 1
            n += len(body[-1]) + 1
        text = " ".join(body)[:PAGE_CHARS]
        segs.append({"folio": i // 2 + 2, "side": "أ" if i % 2 == 0 else "ب",
                     "text": text, "char_offset": pos})
        pos += len(text)
    return segs


def corrupt(text: str, clean_frac: float = 0.55, seed: int = 0,
            chunk: int = 45) -> str:
    """Bimodal OCR corruption: ~clean_frac of the page survives nearly
    verbatim, the rest is garbage (heavy substitutions plus
    fragmentation-style insertions — the profile that produces the real
    book's ~0.5-1.0 CER with 1.5-2x length inflation)."""
    rng = random.Random(seed)
    out = []
    for i in range(0, len(text), chunk):
        part = text[i:i + chunk]
        if rng.random() < clean_frac:
            out.append(part)
            continue
        buf = []
        for ch in part:
            if ch == " ":
                buf.append(" ")
                continue
            if rng.random() < 0.25:
                buf.append(rng.choice("لمنعي"))
            if rng.random() < 0.45:
                buf.append(rng.choice("ابتثجحخدذرزسشصضطظعغفقكم"))
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "".join(out)


class TestCanonicalStream(unittest.TestCase):
    """One normalizer, one source, one join rule (plan 024, step 1)."""

    def test_pure_function_of_segments(self):
        segs = synthetic_segments()
        self.assertEqual(canonical_stream(segs),
                         canonical_stream(list(segs)))

    def test_segment_offsets_tile_the_stream(self):
        # offsets[i] + the joining space must reconstruct the stream
        # exactly: an offset that lands inside a join would make every
        # downstream window geometrically wrong.
        segs = synthetic_segments()
        stream, offsets = canonical_stream(segs)
        for i, seg in enumerate(segs):
            end = offsets[i + 1] - 1 if i < len(segs) - 1 else offsets[i + 1]
            self.assertEqual(stream[offsets[i]:end],
                             normalize_text(seg["text"]))

    def test_page_hypothesis_drops_output_generator_markers(self):
        raw = "# Page 8\n# OCR Method: paddle\n# Page Confidence: 70%\n"
        raw += "بسم الله\n--- الشرح والحاشية ---\nتعليق\n--- الهامش ---\n"
        self.assertEqual(page_hypothesis(raw), "بسم الله تعليق")

    def test_page_window_length_uses_the_regions_table(self):
        self.assertEqual(page_window_length(8), 611)
        self.assertEqual(page_window_length(60), 611)
        self.assertEqual(page_window_length(61), 1378)
        self.assertEqual(page_window_length(1000), 965)
        self.assertEqual(page_window_length(2), 965)

    def test_anchor_prediction_is_plan023s_interpolation(self):
        # (7,4600) and (60,36987): 4600 + 53 chars/page in old coordinates.
        self.assertEqual(anchor_offset(7, 10_000_000), 4600)
        self.assertEqual(anchor_offset(8, 10_000_000), 5211)
        self.assertEqual(anchor_offset(60, 10_000_000), 36987)

    def test_form_pair_reproduces_both_normalizers_exactly(self):
        # The old normal form and the canonical one must both be rebuilt
        # byte-identically from the same source characters — otherwise the
        # offset map between them (the drift column's backbone) is fiction.
        from map_folios_to_pages import normalize as old_norm

        segs = synthetic_segments()
        # Sprinkle exactly the characters the two forms disagree on:
        # tatweel (old keeps, canonical drops) and Latin (old drops).
        segs = [{**s, "text": s["text"] + " ـــــ wm2 " + s["text"][:40]}
                for s in segs]
        src = " ".join(s["text"] for s in segs)
        old, can, _ = build_form_pair(segs)
        self.assertEqual(old, old_norm(src))
        self.assertEqual(can, canonical_stream(segs)[0])

    def test_map_old_to_canonical_tracks_the_coordinate_gap(self):
        segs = [{**s, "text": s["text"].replace(" ", " wm ")}
                for s in synthetic_segments()]
        _, _, alignment = build_form_pair(segs)
        self.assertEqual(map_old_to_canonical(alignment, 0), 0)
        # Latin tokens are kept by the canonical form and dropped by the
        # old one, so the canonical pull-ahead grows with the offset.
        self.assertGreater(map_old_to_canonical(alignment, 5000), 5000)


@unittest.skipUnless(REAL_SEGMENTS.is_file(),
                     "real Shamela segments not present")
class TestRealStream(unittest.TestCase):
    """The measured contract on the actual book (~1.5s)."""

    @classmethod
    def setUpClass(cls):
        cls.segs = load_segments(REAL_SEGMENTS)
        cls.stream, cls.offsets = canonical_stream(cls.segs)

    def test_stream_length_and_the_normal_form_gap(self):
        # Plan 024 finding 7: the two candidate normalizers differ by
        # 75,899 chars (5.6%) on the same segments. This module's stream
        # IS the evaluate_cer one (1,426,417), and the old form rebuilds
        # to map_folios' 1,350,518.
        self.assertEqual(len(self.stream), 1426417)
        old, can, alignment = build_form_pair(self.segs)
        self.assertEqual(len(old), 1350518)
        self.assertEqual(len(can), 1426417)
        self.assertEqual(len(can) - len(old), 75899)
        self.assertTrue(all(a <= c for a, c in alignment))

    def test_segment_offsets_tile_the_real_stream(self):
        for i, seg in enumerate(self.segs):
            end = (self.offsets[i + 1] - 1
                   if i < len(self.segs) - 1 else self.offsets[i + 1])
            self.assertEqual(
                self.stream[self.offsets[i]:end],
                normalize_text(seg["text"]),
                f"segment {i} does not tile")


class TestLocatePage(unittest.TestCase):
    """Locate by verbatim evidence, never by CER (plan 024, step 2)."""

    @classmethod
    def setUpClass(cls):
        cls.stream, _ = canonical_stream(synthetic_segments())

    def test_recovers_offset_of_a_corrupted_page(self):
        true_off = 4 * PAGE_CHARS + 137
        page = corrupt(self.stream[true_off:true_off + PAGE_CHARS], seed=3)
        loc = locate_page(page, self.stream)
        self.assertEqual(loc["method"], "verbatim")
        # The estimator's insertion-style skew lands well inside the
        # 200-char cluster tolerance (measured: within ~130).
        self.assertLessEqual(abs(loc["offset"] - true_off), CLUSTER_TOL, loc)

    def test_recovers_offset_with_heavy_insertion(self):
        # The real book's dominant error is fragmentation-style insertion
        # (the OCR runs 1.5-2x the GT it covers): the plan's
        # "hit minus window position" estimator must stay accurate anyway.
        true_off = 2 * PAGE_CHARS + 55
        page = corrupt(self.stream[true_off:true_off + PAGE_CHARS],
                       clean_frac=0.35, seed=7)
        loc = locate_page(page, self.stream)
        self.assertEqual(loc["method"], "verbatim")
        self.assertLessEqual(abs(loc["offset"] - true_off), CLUSTER_TOL, loc)
        self.assertGreaterEqual(loc["windows"], 2)

    def test_no_verbatim_hits_reported_not_guessed(self):
        loc = locate_page("zzzzzzzzzz zzzzzzzzzz zzzzzzzzzz", self.stream)
        self.assertEqual(loc["method"], "no_hits")
        self.assertIsNone(loc["offset"])

    def test_repeated_formulaic_text_cannot_outvote_real_evidence(self):
        # The page's OCR *starts* with the book's repeated formula — its
        # occurrences all sit near the stream's beginning, so every
        # formula window votes for an early start. Evidence spread across
        # the page must still win, because the cluster score counts
        # distinct OCR windows, not raw votes.
        true_off = 10 * PAGE_CHARS + 300
        page = FORMULA + " " + corrupt(
            self.stream[true_off:true_off + PAGE_CHARS], seed=11)
        loc = locate_page(page, self.stream)
        self.assertEqual(loc["method"], "verbatim")
        self.assertLessEqual(abs(loc["offset"] - true_off), CLUSTER_TOL, loc)

    def test_evidence_bracket_brackets_the_truth(self):
        true_off = 6 * PAGE_CHARS + 400
        page = corrupt(self.stream[true_off:true_off + PAGE_CHARS], seed=5)
        loc = locate_page(page, self.stream)
        lo, hi = loc["bracket"]
        # Every occurrence sits at/after the page start and every implied
        # start at/before it, so the true offset lies inside the bracket.
        self.assertLessEqual(lo, true_off)
        self.assertGreaterEqual(hi, true_off)

    def test_collect_votes_caps_occurrences_per_window(self):
        # A formulaic window matches all over the stream; the vote cap is
        # what keeps one phrase from flooding the cluster arithmetic.
        votes = collect_votes(FORMULA, self.stream)
        self.assertLessEqual(len(votes), 4)


class TestLocatePages(unittest.TestCase):
    """Monotonicity assertion + the no-hits fallback (plan 024, step 2)."""

    @classmethod
    def setUpClass(cls):
        cls.segs = synthetic_segments()
        cls.stream, cls.soff = canonical_stream(cls.segs)

    def _write_pages(self, tmp: Path, offsets: dict[int, int]) -> None:
        for page, off in offsets.items():
            hyp = corrupt(self.stream[off:off + PAGE_CHARS], seed=page)
            (tmp / f"page_{page:03d}.txt").write_text(
                f"# Page {page}\n# OCR Method: paddle\n" + hyp + "\n",
                encoding="utf-8")

    def test_monotonic_pages_produce_no_violations(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_pages(tmp, {n: n * PAGE_CHARS + 50
                                     for n in range(10, 14)})
            located, violations = locate_pages([10, 11, 12, 13],
                                               self.stream, tmp,
                                               self.segs, self.soff,
                                               verbose=False)
        self.assertEqual(violations, [])
        self.assertTrue(all(located[p]["method"] == "verbatim"
                            for p in (10, 11, 12, 13)))

    def test_planted_monotonicity_violation_is_reported_loudly(self):
        # Page 12's true content sits BEFORE page 11's (an overlapping
        # scan, or the missing-sides defect). The assertion must flag it
        # and must NOT drop the page from the located set.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_pages(tmp, {10: 10 * PAGE_CHARS + 50,
                                    11: 11 * PAGE_CHARS + 50,
                                    12: 10 * PAGE_CHARS + 600,
                                    13: 13 * PAGE_CHARS + 50})
            located, violations = locate_pages([10, 11, 12, 13],
                                               self.stream, tmp,
                                               self.segs, self.soff,
                                               verbose=False)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["page"], 12)
        self.assertEqual(violations[0]["prev_page"], 11)
        self.assertEqual(violations[0]["step_back"],
                         located[11]["offset"] - located[12]["offset"])
        self.assertIsNotNone(located[12]["offset"])

    def test_no_hit_page_is_interpolated_and_tagged(self):
        # Page 11 is pure noise: no verbatim window survives, so the
        # offset must come from the neighbours and be labelled — never
        # silently.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_pages(tmp, {10: 10 * PAGE_CHARS + 50,
                                    12: 12 * PAGE_CHARS + 50})
            (tmp / "page_011.txt").write_text(
                "# Page 11\nzzzz zzzz zzzz zzzz\n", encoding="utf-8")
            located, _ = locate_pages([10, 11, 12], self.stream, tmp,
                                      self.segs, self.soff, verbose=False)
        self.assertEqual(located[11]["method"], "interpolated")
        mid = located[10]["offset"] + (
            located[12]["offset"] - located[10]["offset"]) // 2
        self.assertEqual(located[11]["offset"], mid)

    def test_empty_page_is_interpolated_from_the_previous_page(self):
        # A blank scan (the real book's page 46): the file exists but has
        # no text at all. With no following page located yet, the
        # fallback is the previous page + the region's chars-per-page.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_pages(tmp, {7: 7 * PAGE_CHARS})
            (tmp / "page_008.txt").write_text("# Page 8\n", encoding="utf-8")
            located, _ = locate_pages([7, 8], self.stream, tmp,
                                      self.segs, self.soff, verbose=False)
        self.assertEqual(located[8]["method"], "interpolated")
        self.assertEqual(located[8]["offset"],
                         located[7]["offset"] + 611)


class TestScoring(unittest.TestCase):
    """Score at the located offset; op counts and both lengths are the
    Phase 2 inputs, so they must be internally consistent."""

    def test_edit_ops_match_rapidfuzz(self):
        rng = random.Random(0)
        for _ in range(20):
            ref = "".join(rng.choice("ابتث جحخدذرزس") for _ in range(40))
            hyp = "".join(rng.choice("ابتث جحخدذرزس لعن") for _ in range(55))
            ops = edit_ops(ref, hyp)
            self.assertEqual(
                ops["dist"],
                rapidfuzz.distance.Levenshtein.distance(ref, hyp))
            self.assertEqual(ops["sub"] + ops["ins"] + ops["del"], ops["dist"])

    def test_op_classification(self):
        self.assertEqual(edit_ops("كتاب", "كتاب"),
                         {"dist": 0, "sub": 0, "ins": 0, "del": 0})
        # one substitution, length unchanged
        self.assertEqual(edit_ops("كتاب", "كطاب"),
                         {"dist": 1, "sub": 1, "ins": 0, "del": 0})
        # one insertion: Levenshtein prefers the insertion over a
        # substitution+deletion pair of the same cost
        self.assertEqual(edit_ops("كتاب", "كتياب"),
                         {"dist": 1, "sub": 0, "ins": 1, "del": 0})
        # two insertions (fragmentation)
        self.assertEqual(edit_ops("كتاب", "كxتxاب"),
                         {"dist": 2, "sub": 0, "ins": 2, "del": 0})
        # one deletion
        self.assertEqual(edit_ops("كتاب", "كاب"),
                         {"dist": 1, "sub": 0, "ins": 0, "del": 1})

    def test_op_classification_counts_whole_word_boundary_ops(self):
        # Regression: the first column (all-deletions) and first row
        # (all-insertions) must be charged to del/ins, not folded into
        # `sub` by way of the dist - ins - del remainder.
        self.assertEqual(edit_ops("كتاب", ""),
                         {"dist": 4, "sub": 0, "ins": 0, "del": 4})
        self.assertEqual(edit_ops("", "كتاب"),
                         {"dist": 4, "sub": 0, "ins": 4, "del": 0})
        self.assertEqual(edit_ops("abc", "xyz"),
                         {"dist": 3, "sub": 3, "ins": 0, "del": 0})

    def test_edit_script_agrees_with_edit_ops_and_is_a_complete_path(self):
        rng = random.Random(1)
        for _ in range(30):
            ref = "".join(rng.choice("ابتث جحخدذرزس") for _ in range(50))
            hyp = "".join(rng.choice("ابتث جحخدذرزس لعن") for _ in range(70))
            ops = edit_ops(ref, hyp)
            script = edit_script(ref, hyp)
            counts = {"replace": 0, "insert": 0, "delete": 0, "match": 0}
            for tag, _rp, _hp in script:
                counts[tag] += 1
            self.assertEqual(counts["replace"], ops["sub"])
            self.assertEqual(counts["insert"], ops["ins"])
            self.assertEqual(counts["delete"], ops["del"])
            # 'match' steps are emitted, so every ref and hyp character is
            # accounted for exactly once (a full alignment, not just ops).
            self.assertEqual(counts["replace"] + counts["match"],
                             len(ref) - counts["delete"])
            self.assertEqual(counts["replace"] + counts["match"],
                             len(hyp) - counts["insert"])

    def test_edit_script_runs_are_contiguous(self):
        # Phase 2 reads contiguous runs of inserted text; equal-character
        # diagonal steps must appear as 'match' so a run of inserts is truly
        # adjacent in the hypothesis, never silently bridged by a match.
        script = edit_script("abcdef", "abcXdef")
        self.assertIn(("insert", 3, 3), script)
        insert_positions = [hp for tag, _rp, hp in script if tag == "insert"]
        self.assertEqual(insert_positions, [3])

    def test_score_window_reports_the_reference_length_and_ops(self):
        ref = "كتاب " * 40
        hyp = "كتياب " * 30      # 0.9x the length, every word substituted
        got = score_window(ref, hyp)
        self.assertEqual(got["gt_chars"], 200)
        self.assertEqual(got["cer"], round(
            rapidfuzz.distance.Levenshtein.distance(ref, hyp) / 200, 4))
        self.assertEqual(got["sub"] + got["ins"] + got["del"],
                         round(got["cer"] * 200))
        self.assertAlmostEqual(got["jiwer_cer"], jiwer.cer(ref, hyp),
                               places=3)

    def test_cer_is_distance_over_the_reference_not_the_hypothesis(self):
        # Plan 023's geometry's error, in one assertion: the same pair,
        # normalized by the OCR length instead of the GT length, reports
        # a sub-1.0 rate where the CER is above 1. The denominator is
        # exactly the ~1.5x length inflation Phase 2 must decompose.
        ref = "كتاب " * 4            # 24 GT chars
        hyp = "كxتاب " * 20          # 120 OCR chars, mostly extra
        ops = edit_ops(ref, hyp)
        self.assertGreater(ops["dist"] / len(ref), 1.0)   # the CER
        self.assertLess(ops["dist"] / len(hyp), 1.0)      # plan 023's rate


class TestPageSet(unittest.TestCase):
    """The named page set (plan 024, step 6): one list, one place."""

    def test_is_plan023s_ten_middle_pages(self):
        self.assertEqual(LAMAE_PHASE1_PAGES,
                         (8, 12, 17, 20, 24, 29, 38, 48, 54, 58))

    def test_window_length_for_the_page_set_is_611(self):
        for p in LAMAE_PHASE1_PAGES:
            self.assertEqual(page_window_length(p), 611)


@unittest.skipUnless(REAL_SEGMENTS.is_file(),
                     "real Shamela segments not present")
class TestDeterminismOnRealBook(unittest.TestCase):
    """The plan's bar: the harness reproduces exactly across two runs."""

    def test_two_runs_agree_byte_for_byte(self):
        from score_lamae_pages import OCR_DIR

        segs = load_segments(REAL_SEGMENTS)
        stream, soff = canonical_stream(segs)
        alignment = build_form_pair(segs)[2]
        runs = []
        for _ in range(2):
            located, _ = locate_pages(list(LAMAE_PHASE1_PAGES), stream,
                                      OCR_DIR, segs, soff, verbose=False)
            rows = score_pages(list(LAMAE_PHASE1_PAGES), stream, alignment,
                               located, OCR_DIR, with_reconciliation=False)
            runs.append(json.dumps(rows, ensure_ascii=False, sort_keys=True))
        self.assertEqual(runs[0], runs[1])

    def test_drift_at_page_8_matches_the_measured_anchor_error(self):
        # Plan 024 finding 2: plan 023's anchor estimate for page 8 sits
        # ~1,900 chars ABOVE the page's true content. The harness must
        # reproduce that, sign included — if the coordinate map between
        # the two normal forms were wrong, the drift would swallow it.
        from score_lamae_pages import OCR_DIR

        segs = load_segments(REAL_SEGMENTS)
        stream, soff = canonical_stream(segs)
        alignment = build_form_pair(segs)[2]
        located, _ = locate_pages([8], stream, OCR_DIR, segs, soff,
                                  verbose=False)
        off = located[8]["offset"]
        anchor = map_old_to_canonical(alignment, anchor_offset(8, len(stream)))
        self.assertEqual(off, 3580)
        self.assertLess(off - anchor, 0)
        self.assertAlmostEqual(abs(off - anchor), 1918, delta=100)


class TestParseRange(unittest.TestCase):
    def test_parses_lo_hi(self):
        self.assertEqual(parse_range("7-60"), (7, 60))
        self.assertEqual(parse_range("8-8"), (8, 8))

    def test_rejects_inverted_range(self):
        with self.assertRaises(ValueError):
            parse_range("60-7")


@unittest.skipUnless(REAL_SEGMENTS.is_file(),
                     "real Shamela segments not present")
class TestRangeBaselineOnRealBook(unittest.TestCase):
    """The official held-out baseline (plan 024, phase 1 revision)."""

    def test_range_baseline_is_deterministic_and_consistent(self):
        from score_lamae_pages import OCR_DIR

        segs = load_segments(REAL_SEGMENTS)
        stream, soff = canonical_stream(segs)
        runs = []
        for _ in range(2):
            _, _, per, baseline = evaluate_range(
                7, 12, stream, OCR_DIR, segs, soff, verbose=False)
            runs.append(json.dumps({"per": per, "baseline": baseline},
                                   ensure_ascii=False, sort_keys=True))
        self.assertEqual(runs[0], runs[1])

        base = json.loads(runs[0])["baseline"]
        # The baseline is the project convention: distance over the GT
        # reference length, and it carries both lengths and the op split.
        self.assertEqual(base["ops_total"]["dist"],
                         base["ops_total"]["sub"] + base["ops_total"]["ins"]
                         + base["ops_total"]["del"])
        self.assertGreater(base["ocr_over_gt_length_ratio"], 1.0)
        self.assertGreater(base["ocr_chars"], base["gt_chars"])
        self.assertGreater(base["ops_total"]["ins"], 0)


if __name__ == "__main__":
    unittest.main()
