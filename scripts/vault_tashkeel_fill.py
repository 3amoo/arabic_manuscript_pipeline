#!/usr/bin/env python3
"""
Vault-lookup diacritization restoration (NEXT_DEVELOPMENT_PLAN_2 Phase 3,
option 2: "restrict the fill to tokens the vault itself directly confirms").

WHY THIS EXISTS: `restore_tashkeel.py` (Group B) was evaluated 2026-09-21 and
REJECTED. Its CAMeL MLE disambiguator is MSA-trained; against the genealogy
vault's own diacritized transcription of this exact poem, only 13% of its
filled marks matched. An MSA model cannot supply classical-register tashkeel.

This module works from the opposite direction. Instead of GENERATING marks
from a morphology database, it LOOKS THEM UP in the vault: the vault holds
558 diacritized lines of this poem, and the printed ground truth agrees with
the vault's diacritization on 100% of 1,537 shared tokens across 189
strongly-matched verses (measured 2026-10-05, see docs/vault_tashkeel_fill.md).
So the vault IS a reliable diacritized source for this text.

THE MECHANISM, AND WHY IT IS PHRASE-LEVEL: a bare token like "ان" has several
diacritized forms in the vault (أَنْ / إنْ / أنْ). Filling by token
FREQUENCY picks the most common one and gets it wrong 25/33 of the time - a
disambiguation failure, not a coverage failure, because the correct form IS
present, just rarer. So this module does not rank tokens; it finds the vault
LINE whose skeleton best matches the OCR line, and takes each bare token's
diacritization from that line's own context. That scored 100% agreement on
the measured sample versus 69.4% for frequency-ranking.

THE CONSERVATION RULE (unchanged from restore_tashkeel.py): a token that
already carries Harakat is LEFT UNTOUCHED. Only bare tokens get filled, and
only when the vault line itself carries a diacritized form with the same
skeleton. This cannot introduce a new register bias: every filled mark is
attested in this exact poem.

LIMITS, measured and recorded:
  - the vault covers only ~18.5% of the bare tokens in the GT scope, and
    only lines that match a vault line at skeleton similarity >= LINE_FLOOR.
    Most of the corpus is left untouched, which is the point of the "weaker
    coverage, near-zero risk" option in the plan.
  - pages 68+ are out of ground-truth scope and are not filled.

EVALUATION (plan step 8): the same metric as the rejected attempt -
scripts/measure_der.py against the reviewed gold layer. See
docs/vault_tashkeel_fill.md for the go/no-go numbers.

  myenv/bin/python scripts/vault_tashkeel_fill.py --document "..."
      [--apply] [--report-dir DIR]

--apply writes to data/output/<doc>/vault_tashkeel_text/, never touching
raw_text/. Default is dry-run.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Vault location: the DEFAULT_VAULT constant lives in genealogy_crossref.py
# and is pinned in docs/genealogy_vault_pin.md.
_VAULT = Path("/home/omar/Desktop/Obsidian/علم شرعي/علم الأنساب")

_HARAKAT = frozenset(chr(c) for c in range(0x064B, 0x0653)) | {chr(0x0670)}

# A vault line must match the OCR line this well on skeleton to be trusted as
# the source for its tokens' diacritics. Below this the two lines are
# probably different verses and the fill would be wrong.
LINE_FLOOR = 0.70

# Minimum skeleton length to attempt a line match at all: short OCR fragments
# (page numbers, lone words) match too many vault lines to disambiguate.
MIN_LINE_SKEL = 15

# Ground truth ends at page 67 (logs/batch456_pairing_audit.md); beyond it
# there is no verse-level pairing to score against, so filling is pointless.
GT_LAST_PAGE = 67


def has_diacritics(token: str) -> bool:
    return any(ch in _HARAKAT for ch in token)


def skeleton(token: str) -> str:
    s = unicodedata.normalize("NFKD", token)
    return "".join(c for c in s if not unicodedata.combining(c))


def line_skeleton(line: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", line) if not unicodedata.combining(c)
    )


def _is_content(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith(("#", "---", "title:", "author:", "death_", "birth_", "tags:")):
        return False
    if s in ("- أنساب", "- سيرة", "- شعر", "- رجز"):
        return False
    return True


def load_vault_lines(vault: Path) -> List[str]:
    """The vault's diacritized lines, markdown stripped, verse-number prefix
    removed. These are the only lines that can supply a fill."""
    out: List[str] = []
    for f in sorted(vault.glob("*.md")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not _is_content(line):
                continue
            body = line.strip().lstrip(">").strip().replace("**", "")
            if not any(c in _HARAKAT for c in body):
                continue
            # strip a leading Arabic-Indic or Western verse number
            i = 0
            while i < len(body) and (body[i].isdigit() or body[i] in "٠١٢٣٤٥٦٧٨٩.-"):
                i += 1
            body = body[i:].strip()
            if body:
                out.append(body)
    return out


def token_map(line: str) -> Dict[str, List[str]]:
    """skeleton -> diacritized forms, in order of appearance."""
    m: Dict[str, List[str]] = {}
    for tok in line.replace("...", " ").split():
        k = skeleton(tok)
        if k and has_diacritics(tok):
            m.setdefault(k, []).append(tok)
    return m


def fill_line(line: str, vault_lines: List[str]) -> Tuple[str, Counter]:
    """Fill this line's bare tokens from the best-matching vault line."""
    buckets: Counter = Counter()
    tokens = line.split()
    if not tokens:
        return line, buckets
    kl = line_skeleton(line)
    if len(kl) < MIN_LINE_SKEL:
        return line, buckets
    best = None
    for v in vault_lines:
        r = SequenceMatcher(None, kl, line_skeleton(v)).ratio()
        if best is None or r > best[0]:
            best = (r, v)
            if r > 0.98:
                break
    if best is None or best[0] < LINE_FLOOR:
        buckets["no_vault_line"] += 1
        return line, buckets
    vmap = token_map(best[1])
    out = []
    for tok in tokens:
        k = skeleton(tok)
        if not k:
            out.append(tok)
            continue
        if has_diacritics(tok):
            buckets["kept_ocr_diacritics"] += 1
            out.append(tok)
            continue
        cands = vmap.get(k)
        if not cands:
            buckets["vault_has_no_form"] += 1
            out.append(tok)
            continue
        filled = cands[0]
        if filled != tok:
            buckets["filled_gap"] += 1
        else:
            buckets["fill_equal_to_bare"] += 1
        out.append(filled)
    buckets["line_match"] = round(best[0], 3)
    return " ".join(out), buckets


def restore_corpus(
    records: List[Dict[str, object]], document_dir: Path, apply: bool
) -> Tuple[int, Counter, int]:
    vault_lines = load_vault_lines(_VAULT)
    total: Counter = Counter()
    changed_pages = 0
    out_dir = document_dir / "vault_tashkeel_text"
    # Page outputs are written whole (every line, including the ones this
    # tool leaves untouched), so a reader can diff a filled page against the
    # raw page line-for-line and measure_der.py can score the same pages it
    # scores for raw_text/. Only pages inside GT scope are written: beyond
    # page 67 there is no verse-level pairing to score against, so a filled
    # copy would be unverifiable output.
    by_page: Dict[int, List[str]] = {}
    for rec in records:
        by_page.setdefault(int(rec["page"]), []).append((int(rec["line"]), str(rec["text"])))
    if apply:
        out_dir.mkdir(parents=True, exist_ok=True)
    for page, entries in sorted(by_page.items()):
        if page > GT_LAST_PAGE:
            continue
        lines = [""] * max(e[0] for e in entries)
        for line_no, text in entries:
            lines[line_no - 1] = text
        any_change = False
        for idx, text in enumerate(lines, 1):
            new, buckets = fill_line(text, vault_lines)
            total.update(buckets)
            if new != text:
                total["lines_changed"] += 1
                any_change = True
                lines[idx - 1] = new
        if any_change:
            changed_pages += 1
        if apply:
            (out_dir / ("page_%03d.txt" % page)).write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
    return changed_pages, total, len(vault_lines)


def load_corpus(document_dir: Path) -> List[Dict[str, object]]:
    raw_dir = document_dir / "raw_text"
    if not raw_dir.is_dir():
        raise SystemExit("no raw_text/ under %s - run the pipeline first" % document_dir)
    # EVERY line is kept, including blanks and the "# Page N" header, so the
    # line index is identical to the file's own line number - the index
    # restore_corpus uses to rewrite a single line in place.
    records = []
    for page_file in sorted(raw_dir.glob("page_*.txt")):
        page_num = int(page_file.stem.split("_")[1])
        for line_no, line in enumerate(
            page_file.read_text(encoding="utf-8").splitlines(), 1
        ):
            records.append(
                {"page": page_num, "line": line_no, "text": line, "file": page_file.name}
            )
    return records


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--document",
        default="عمود النسب نسخة 2",
        help="document name under data/output/",
    )
    ap.add_argument("--apply", action="store_true", help="write the filled layer")
    ap.add_argument("--report-dir", default="data/evaluation_reports/020-vault-tashkeel")
    args = ap.parse_args(argv)

    doc = Path("data/output") / args.document
    if not doc.is_dir():
        raise SystemExit("no such document: %s" % doc)
    records = load_corpus(doc)
    in_scope = [r for r in records if int(r["page"]) <= GT_LAST_PAGE]
    changed, buckets, n_vault = restore_corpus(records, doc, args.apply)

    print("vault tashkeel fill (%s)" % ("APPLIED" if args.apply else "DRY RUN"))
    print("  vault diacritized lines:        %d" % n_vault)
    print("  OCR lines scanned (GT scope):    %d" % len(in_scope))
    print("  lines changed:                  %d" % buckets.get("lines_changed", 0))
    print("  tokens kept (already diacritic):%d" % buckets.get("kept_ocr_diacritics", 0))
    print("  gaps filled from vault:         %d" % buckets.get("filled_gap", 0))
    print("  no vault line matched:          %d" % buckets.get("no_vault_line", 0))
    print("  vault line has no form:         %d" % buckets.get("vault_has_no_form", 0))
    if args.apply:
        print("  written to %s/vault_tashkeel_text/" % doc)

    rd = Path(args.report_dir)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "fill_report.json").write_text(
        json.dumps(
            {
                "document": args.document,
                "vault_lines": n_vault,
                "lines_scanned": len(in_scope),
                "buckets": dict(buckets),
                "applied": args.apply,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
