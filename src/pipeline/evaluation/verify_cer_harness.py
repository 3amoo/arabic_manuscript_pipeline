"""
Mechanical end-to-end self-check for the CER/WER harness (evaluate_cer.py).

Builds a synthetic GT and raw page with KNOWN differences in a temp dir,
runs evaluate_cer.py via subprocess, and asserts the reported aggregate
CER/WER match hand-computed values. Proves normalization + jiwer wiring +
exit codes work. It does NOT validate any ground truth (there is no GT
yet - see data/ground_truth/README.md fill-status table).

Synthetic math (default strip mode, ref 31 chars / 5 words):
  ref:  السلامُ عليكم ورحمةُ الله وبركاته   (tashkeel stripped -> 31 chars)
  hyp:  السلام علكم ورحمة الله وبركاته      (one letter deleted: ي in عليكم)
  CER ~= 1/31 = 3.23% ;  WER = 1/5 = 20%

--diacritics keep must score HIGHER (the two stripped tashkeel marks on
GT's "السلامُ" and "ورحمةُ" become differencing characters).

Run with:  myenv/bin/python verify_cer_harness.py
"""

import re
import subprocess
import tempfile
from pathlib import Path

PYTHON = str(Path(__file__).resolve().parents[3] / "myenv" / "bin" / "python")
EVALUATE_CER = str(Path(__file__).resolve().parent / "evaluate_cer.py")
DOC = "عمود النسب نسخة 2"
GT_REF = """السلامُ عليكم ورحمةُ الله
وَبَرَكَاتُه
"""
RAW_HYP = """# Page 001
# OCR Method: paddle
# Page Confidence: 80.0%
# Binarization Attempt: 1

السلام علكم ورحمة الله
وَبَرَكَاتُه
"""


def run_scorer(tmp: Path, pages: str, diacritics: str = "strip"):
    return subprocess.run(
        [PYTHON, EVALUATE_CER,
         "--document", DOC, "--pages", pages,
         "--diacritics", diacritics,
         "--output-root", str(tmp / "output"),
         "--gt-root", str(tmp / "ground_truth")],
        capture_output=True, text=True,
    )


def aggregate_cer_wer(stdout: str):
    m = re.search(
        r"aggregate \(1 pages, (\d+) chars, (\d+) words\): "
        r"CER=([0-9.]+)%  WER=([0-9.]+)%", stdout)
    if not m:
        raise AssertionError(f"no aggregate line in:\n{stdout}")
    return (int(m.group(1)), int(m.group(2)),
            float(m.group(3)), float(m.group(4)))


def main() -> int:
    with tempfile.TemporaryDirectory(dir="/tmp/opencode") as d:
        tmp = Path(d)
        gt = tmp / "ground_truth" / DOC
        raw = tmp / "output" / DOC / "raw_text"
        gt.mkdir(parents=True)
        raw.mkdir(parents=True)
        (gt / "page_001.txt").write_text(GT_REF, encoding="utf-8")
        (raw / "page_001.txt").write_text(RAW_HYP, encoding="utf-8")

        p = run_scorer(tmp, "1", "strip")
        assert p.returncode == 0, f"strip exit {p.returncode}: {p.stdout}{p.stderr}"
        chars, words, cer, wer = aggregate_cer_wer(p.stdout)
        assert chars == 31, f"ref chars {chars} != 31"
        assert words == 5, f"ref words {words} != 5"
        assert 3.0 <= cer <= 3.5, f"CER {cer} out of [3.0,3.5]"
        assert 19.0 <= wer <= 21.0, f"WER {wer} out of [19,21]"
        print(f"strip-mode OK: CER={cer}% WER={wer}% (expected 3.23/20)")

        p_keep = run_scorer(tmp, "1", "keep")
        assert p_keep.returncode == 0, f"keep exit {p_keep.returncode}"
        cer_keep = aggregate_cer_wer(p_keep.stdout)[2]
        assert cer_keep > cer, f"keep CER {cer_keep} not > strip CER {cer}"
        print(f"keep-mode OK: CER={cer_keep}% > strip {cer}% (tashkeel counted)")

        (raw / "page_002.txt").write_text("x", encoding="utf-8")
        p_missing = run_scorer(tmp, "1,2", "strip")
        assert p_missing.returncode == 2, f"missing-GT exit {p_missing.returncode} != 2"
        assert "NO MEASUREMENT" in p_missing.stdout
        print("missing-GT exit-code OK (2 = no GT, not silent 0)")

    print("verify_cer_harness: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())