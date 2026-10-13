#!/usr/bin/env python3
"""Convert Shamela (.bok) library books to plain text.

A .bok file is a Microsoft Access (Jet) database used by the Shamela library
(مكتبة الشاملة). The book body lives in a table named ``b<book_id>`` whose
``nass`` column holds the text encoded with the Windows-1256 (cp1256) code
page. Tashkeel (diacritics) are stored as real marks inside that text.

This tool extracts the body in reading order and writes two UTF-8 text files
that are identical except for the diacritics:

  * ``<name>_with_tashkeel.txt``    - normalized text, tashkeel preserved
  * ``<name>_without_tashkeel.txt`` - the same text with all diacritics stripped

Both files get the same light normalization: in-record ``\r`` separators become
newlines, trailing spaces are dropped, and runs of 3+ blank lines collapse to
one blank line.

Requirements: the ``mdbtools`` command line tools (``mdb-export`` /
``mdb-tables``) must be installed. On Debian/Ubuntu: ``sudo apt install mdbtools``.

Usage:
    python3 bok_to_text.py <file.bok> [file2.bok ...] [-o OUTPUT_DIR]
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
import sys

# Arabic diacritics (tashkeel) + closely related combining marks.
#   U+064B-U+065F : tanween, fatha/damma/kasra, shadda, sukun, hamza marks ...
#   U+0670        : superscript alef
#   U+06D6-U+06ED : Quranic annotation signs. The class skips U+06DD/U+06DE/
#                  U+06E9 on purpose: they are format/symbol characters, not
#                  combining marks, so they are not tashkeel.
# U+0640 (tatweel) is deliberately *not* removed: it is a spacing letter, not
# a diacritic, and is part of the spelling.
TASHKEEL_RE = re.compile(
    "[\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]"
)

# Strip trailing spaces on each line and collapse 3+ consecutive line breaks
# into a single blank line.
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def die(msg: str) -> None:
    sys.stderr.write(f"error: {msg}\n")
    raise SystemExit(1)


def need_mdbtools() -> None:
    """Ensure the mdbtools binaries are available."""
    missing = [t for t in ("mdb-export", "mdb-tables") if shutil.which(t) is None]
    if missing:
        die(
            "the mdbtools utilities are required but were not found: "
            + ", ".join(missing)
            + "\n       install them with e.g. `sudo apt install mdbtools`."
        )


def list_tables(path: str) -> list[str]:
    out = subprocess.run(
        ["mdb-tables", path], capture_output=True, check=True
    ).stdout.decode("utf-8", "replace")
    return out.split()


def export_table(path: str, table: str) -> tuple[list[str], list[list[str]]]:
    """Export a table as CSV, returning (header, rows).

    Raises RuntimeError if the table cannot be read.
    """
    proc = subprocess.run(["mdb-export", path, table], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"could not read table '{table}' from {path}")
    text = proc.stdout.decode("utf-8", "replace")
    if "\ufffd" in text:
        sys.stderr.write(
            f"warning: replacement characters while reading '{table}'; "
            "the text may not have been decoded as expected.\n"
        )
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RuntimeError(f"table '{table}' in {path} is empty or unreadable")
    return rows[0], rows[1:]


def find_content_table(path: str, tables: list[str]) -> str:
    """Locate the table holding the book body.

    Shamela names it ``b<book_id>``; it always has a ``nass`` (text) column.
    We prefer that, then fall back to any table exposing ``nass`` with data.
    Unreadable/empty candidate tables are skipped rather than fatal.
    """
    def probe(tbl: str) -> tuple[list[str], list[list[str]]] | None:
        try:
            return export_table(path, tbl)
        except RuntimeError:
            return None

    for tbl in (t for t in tables if re.fullmatch(r"b\d+", t)):
        got = probe(tbl)
        if got and "nass" in got[0] and got[1]:
            return tbl
    # Fallback: any table with a non-empty nass column.
    for tbl in tables:
        got = probe(tbl)
        if got and "nass" in got[0] and got[1]:
            return tbl
    die(f"no content table (b<id> with a 'nass' column) found in {path}")


def extract_body(path: str) -> str:
    """Return the full book text in reading order, tashkeel preserved."""
    content_tbl = find_content_table(path, list_tables(path))
    header, rows = export_table(path, content_tbl)

    nass_idx = header.index("nass")
    id_idx = header.index("id") if "id" in header else None

    # Sort by numeric id (Shamela's reading order). Fall back to row order.
    if id_idx is not None:
        def id_key(row: list[str]) -> tuple[int, int]:
            try:
                return (0, int(row[id_idx]))
            except (ValueError, IndexError):
                return (1, 0)
        rows.sort(key=id_key)

    chunks: list[str] = []
    for row in rows:
        if nass_idx >= len(row):
            continue
        text = row[nass_idx]
        if not text:
            continue
        # Shamela uses \r as the in-record line/paragraph separator.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks.append(text.strip())

    body = "\n".join(chunks)
    body = _TRAILING_WS_RE.sub("\n", body + "\n")
    body = _BLANK_LINES_RE.sub("\n\n", body)
    return body.strip() + "\n"


def strip_tashkeel(text: str) -> str:
    """Remove all Arabic diacritics.

    Diacritics are combining marks attached to the preceding letter, so
    removing them never changes spacing - the result therefore differs from
    the input *only* by the marks themselves.
    """
    return TASHKEEL_RE.sub("", text)


def process(path: str, out_dir: str) -> tuple[str, str]:
    """Convert one .bok file; return (with_path, without_path)."""
    if not os.path.isfile(path):
        die(f"no such file: {path}")

    body = extract_body(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(out_dir, exist_ok=True)

    with_path = os.path.join(out_dir, f"{stem}_with_tashkeel.txt")
    without_path = os.path.join(out_dir, f"{stem}_without_tashkeel.txt")

    with open(with_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    with open(without_path, "w", encoding="utf-8") as fh:
        fh.write(strip_tashkeel(body))

    return with_path, without_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Shamela .bok books to text with and without tashkeel."
    )
    parser.add_argument("files", nargs="+", help="one or more .bok files")
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help="directory for the output .txt files (default: beside each input)",
    )
    args = parser.parse_args(argv)

    need_mdbtools()

    for path in args.files:
        out_dir = args.output_dir or os.path.dirname(os.path.abspath(path))
        with_path, without_path = process(path, out_dir)
        body = open(with_path, encoding="utf-8").read()
        n_lines = body.count("\n") + 1
        print(f"converted: {path}")
        print(f"  with tashkeel    -> {with_path} ({n_lines} lines)")
        print(f"  without tashkeel -> {without_path} ({n_lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
