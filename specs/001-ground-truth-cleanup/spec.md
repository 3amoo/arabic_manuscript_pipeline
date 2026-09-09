# Feature Specification: Ground Truth Corpus Cleanup

**Feature Branch**: `001-ground-truth-cleanup`

**Created**: 2026-09-06

**Status**: Draft

**Input**: User description: "بناء ميزة 'Ground Truth Corpus Cleanup' لمشروع خط إنتاج استخراج نص المخطوطات العربية. يوجد ملف مرجعي (Ground Truth) بصيغة Markdown لكتاب الاختبار الأساسي (شعر عربي مشكول)، تم إنتاجه سابقًا بواسطة نموذج LLM (Claude) قرأ صور صفحات الكتاب ونسخها، ويحتوي حاليًا على محتوى إضافي غير مرغوب فيه (شروحات معاني الكلمات والفوائد التفسيرية) يجب حذفه، مع دمج الشطرين الشعريين في سطر واحد بنفس تنسيق مخرجات خط الإنتاج الحالي، بطريقة قابلة لإعادة الاستخدام على ملفات مرجعية أخرى مستقبلية بنفس البنية."

## Clarifications

### Session 2026-09-06

- Q: When the cleanup process encounters an annotation callout block whose label doesn't match either of the two currently known types ("معاني الكلمات" or "الفوائد"), should it still strip that block automatically, or treat it as a structural anomaly to report? → A: Strip any callout matching the general structural pattern (a `> [!type]- ...` block on its own line), regardless of its specific label text — no per-label configuration or allowlist needed.
- Q: When the cleanup process finds a structurally malformed verse block (e.g. missing a hemistich, or a duplicate verse number), should it stop the entire run immediately, or continue processing the remaining verses and report all anomalies together at the end? → A: Continue processing every verse block regardless of earlier anomalies; exclude only the malformed verse itself from the cleaned output, and emit one complete anomaly report at the end covering the whole file in a single pass.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce a clean, comparable reference file from the annotated Ground Truth (Priority: P1)

As the person preparing quality benchmarks for the manuscript pipeline, I need a version of the
existing Ground Truth file that contains only the verse numbering and the verse text itself (both
hemistichs merged into the pipeline's own output format), with all explanatory annotations removed,
so that this file can later be used as an official CER/WER reference without the annotations
inflating the character/word error rate against something the pipeline was never meant to produce.

**Why this priority**: This is the entire point of the feature. Without a clean reference file, no
CER/WER benchmarking effort (a separate, non-negotiable requirement in the project constitution) can
proceed at all. Every other behavior in this spec exists to make this single output trustworthy.

**Independent Test**: Can be fully tested by running the cleanup process against the existing
annotated Ground Truth file and confirming the output file contains exactly one line per verse
(right hemistich + separator + left hemistich), in verse order, with zero remaining explanatory
content — deliverable and verifiable entirely on its own, without needing the future CER/WER tool to
exist yet.

**Acceptance Scenarios**:

1. **Given** the existing annotated Ground Truth Markdown file for the primary test manuscript,
   **When** the cleanup process is run against it, **Then** a new output file is produced containing
   one entry per verse, each with its verse number and a single merged line of the two hemistichs,
   and no `[!info]-` or `[!question]-` callouts or their contents anywhere in the output.
2. **Given** a verse block in the source file that contains only hemistichs and no annotation
   callouts at all (already "clean"), **When** the cleanup process runs, **Then** that verse is
   still included in the output, unchanged in content, merged into the single-line format like every
   other verse.
3. **Given** the cleanup process has finished, **When** the original annotated source file is
   inspected afterward, **Then** it is byte-for-byte identical to its state before the process ran
   (no in-place modification, no deletion).
4. **Given** the cleaned output file, **When** the number and order of verses in it is compared to
   the number and order of verses in the original source file, **Then** they match exactly — no
   verse is missing, duplicated, or reordered.

---

### User Story 2 - Reuse the cleanup process on a different, differently-structured reference file (Priority: P2)

As the person who will eventually add more manuscripts to this project, I need the same cleanup
process to work on another Ground Truth file that follows the same general repeating pattern (verse
heading, two hemistichs, optional annotation callouts) — without having to write a new one-off
script for every new manuscript's reference file.

**Why this priority**: The project constitution requires the tool to generalize beyond a single
book. If the cleanup process only works on the one file it was built against, it becomes throwaway
tooling rather than a reusable part of the project's quality-measurement capability. This is
important but secondary to first proving the cleanup works correctly at all (User Story 1).

**Independent Test**: Can be tested by pointing the same cleanup process at a second, structurally
similar sample file (verse blocks with the same heading/hemistich/callout pattern, but different
verse count, different annotation content, and some verses missing one or both callout types) and
confirming it produces a correctly cleaned output without any code changes specific to that second
file.

**Acceptance Scenarios**:

1. **Given** a second reference file following the same repeating verse structure but with
   different verse numbers, wording, and a different mix of present/absent annotation sections,
   **When** the same cleanup process is run against it, **Then** it produces a correctly cleaned
   output file following the same rules as User Story 1, with no manual per-file adjustment.
2. **Given** a reference file whose verse numbering does not start at 1 or is not perfectly
   sequential, **When** the cleanup process runs, **Then** the output preserves each verse's
   original number as-is (no renumbering), in the same order as the source.

---

### User Story 3 - Detect and surface structural anomalies instead of silently producing a wrong result (Priority: P3)

As the person relying on the cleaned output for quality measurement, I need to be warned if a verse
block in the source file doesn't match the expected repeating pattern (e.g., missing hemistichs, an
unrecognized section type, a verse number that repeats), rather than the process silently dropping
content, merging things incorrectly, or producing a corrupted reference without any indication.

**Why this priority**: A silently wrong Ground Truth file is worse than no Ground Truth file — it
would produce misleading CER/WER numbers that look authoritative. This is important for
trustworthiness but is a safety net around the core behavior (User Stories 1–2), not the primary
value driver.

**Independent Test**: Can be tested by feeding the cleanup process a deliberately malformed sample
verse block (e.g., only one hemistich line, a duplicated verse number, an unrecognized callout type)
and confirming the process reports the specific anomaly (which verse, what was wrong) rather than
completing silently with a corrupted or incomplete output.

**Acceptance Scenarios**:

1. **Given** a verse block missing one of its two expected hemistich lines, **When** the cleanup
   process runs, **Then** it reports that specific verse number and the nature of the problem, and
   does not silently emit a malformed or guessed line in its place.
2. **Given** two verse blocks sharing the same verse number, **When** the cleanup process runs,
   **Then** it reports the duplicate verse number rather than silently keeping only one or merging
   them.
3. **Given** a fully well-formed source file, **When** the cleanup process runs, **Then** zero
   anomalies are reported and the process completes normally.
4. **Given** a source file containing several unrelated malformed verse blocks (e.g. one missing a
   hemistich, another with a duplicate verse number), **When** the cleanup process runs, **Then** it
   does not stop at the first anomaly — it continues processing every remaining verse block, excludes
   only the malformed verses themselves from the cleaned output, and produces a single consolidated
   anomaly report at the end listing every anomaly found across the whole file in one pass.

### Edge Cases

- What happens when a verse block has annotation callouts in reverse order (e.g. "الفوائد" appearing
  before "معاني الكلمات") or repeated more than once within the same verse block? The cleanup MUST
  still remove all such callout content regardless of order or repetition, keeping only the verse
  heading and the two hemistich lines.
- What happens when a hemistich line itself happens to contain a bracket-like character or the
  literal substrings used to mark callouts (e.g. as part of quoted poetry text)? The cleanup MUST
  distinguish structural callout markers (which appear on their own line, as the source file's fixed
  pattern dictates) from incidental characters inside hemistich text, and must not corrupt hemistich
  content while removing callouts.
- What happens when the source file has trailing/leading decorative content outside any verse block
  (e.g. a title page, an introduction, section-divider lines like "نسب فلان" between verses, as
  observed in the current reference file)? This non-verse content is not part of any numbered verse
  and MUST be excluded from the cleaned output; only numbered verse blocks are extracted.
- What happens when the cleanup process is run twice on the same source file? It MUST produce the
  same output both times (the process does not depend on or mutate any state between runs) and MUST
  NOT append to or duplicate content in an existing output file — it overwrites/produces a fresh
  output deterministically.
- What happens when the source file uses Arabic-Indic numerals for verse numbers (as the current
  reference file does, e.g. "١"، "٢") versus Western numerals? The cleanup MUST preserve the verse
  number exactly as written in the source, in the output, without converting numeral systems.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The cleanup process MUST accept a source Ground Truth Markdown file as input and
  identify every verse block within it, where a verse block begins at a verse-number heading and
  extends up to (but not including) the next verse-number heading or the end of the file.
- **FR-002**: For each identified verse block, the cleanup process MUST extract exactly two elements:
  the verse number (preserved exactly as written in the source, including its numeral system) and
  the two hemistich lines that immediately follow the heading.
- **FR-003**: The cleanup process MUST remove all explanatory/annotation content within a verse
  block by recognizing the general structural callout pattern (a block introduced by its own line
  matching `> [!<type>]- ...`, e.g. the currently-known "word meanings" and "benefits/commentary"
  callouts, plus everything nested under it up to the next such callout, the next verse heading, or
  a section divider). This removal MUST apply to any callout matching that structural pattern
  regardless of its specific label text, order, repetition, or whether it is a type seen before —
  no hardcoded label list or per-manuscript configuration is required to recognize and strip a new
  annotation type.
- **FR-004**: The cleanup process MUST merge the two extracted hemistich lines of each verse into a
  single line, joined with the exact same separator format the manuscript pipeline itself already
  uses to join right and left hemistichs in its own output ("right hemistich" + " ... " + "left
  hemistich"), so that a cleaned Ground Truth verse line and a pipeline-produced verse line are
  structurally comparable.
- **FR-005**: The cleanup process MUST preserve verse order and verse numbering exactly as they
  appear in the source file — it MUST NOT renumber, reorder, deduplicate-by-merging, or reinterpret
  verse numbers.
- **FR-006**: The cleanup process MUST exclude any content in the source file that falls outside a
  numbered verse block (front matter, titles, section-divider lines between verses, etc.) from the
  cleaned output.
- **FR-007**: The cleanup process MUST NOT modify, move, or delete the original source Ground Truth
  file in any way; the original remains available, unchanged, after the process runs, at its
  existing location.
- **FR-008**: The cleanup process MUST write its cleaned result to a distinct output location whose
  name/path clearly differentiates it from the original source file (e.g. a `-clean` / `-cleaned`
  suffix, or an equivalent clearly-labeled path), and MUST NOT be written to the same path as the
  source.
- **FR-009**: The cleanup process MUST be reusable, unmodified, against any other source file that
  follows the same general repeating structure (verse heading → two hemistich lines → zero or more
  annotation callout sections), without requiring changes specific to the particular book/content of
  a given source file.
- **FR-010**: When the cleanup process encounters a verse block that does not conform to the
  expected structure (e.g. a heading not followed by two hemistich lines, or a verse number that
  duplicates one already seen earlier in the same file), it MUST report the specific verse number and
  the nature of the anomaly, and MUST NOT silently emit a guessed, blank, or corrupted line for that
  verse in the cleaned output in its place.
- **FR-011**: The cleanup process MUST support being run repeatedly against the same source file and
  produce identical output each time (deterministic, no accumulation/append behavior across runs).
- **FR-012**: The cleanup process MUST NOT abort the entire run upon encountering the first
  structural anomaly. It MUST continue processing every remaining verse block in the source file,
  excluding only the specific malformed verse(s) from the cleaned output, and MUST produce one
  consolidated anomaly report at the end of the run covering every anomaly found across the whole
  file in a single pass.

### Key Entities

- **Ground Truth Source File**: the original, unmodified reference document (Markdown) for a given
  manuscript, produced by a prior LLM-assisted transcription pass. Contains a sequence of verse
  blocks, each with a verse number, two hemistich lines, and optional annotation callouts. Treated as
  read-only input.
- **Verse Block**: one repeating unit within a source file — identified by its verse-number heading,
  its two hemistich lines, and zero or more annotation callout sections (any block matching the
  general `> [!<type>]- ...` structural pattern, regardless of specific label text) that follow, up
  to the next verse block or end of file.
- **Cleaned Ground Truth File**: the output artifact — one entry per verse, each holding only the
  verse number and the single merged hemistich line, in the same order and numbering as the source,
  with all annotation content removed. Verses excluded due to a structural anomaly (FR-010, FR-012)
  are omitted from this file, not included in a corrupted form. This is the artifact intended for
  later use as a CER/WER benchmarking reference (per the project constitution's Ground Truth policy —
  an aspirational quality ceiling, not an infallible truth source).
- **Structural Anomaly Report**: the consolidated set of warnings/errors produced once per run,
  covering every verse block across the whole source file that did not match the expected repeating
  pattern, each entry identifying its verse number and what specifically was unexpected. Processing
  continues past each anomaly rather than stopping the run (FR-012).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the cleanup process against the existing primary test manuscript's Ground
  Truth file produces a cleaned output containing exactly as many verse entries as the source file
  has numbered verses (620 verses in the current reference file), with no gaps or duplicates in
  verse numbering.
- **SC-002**: A manual inspection of any 20 randomly sampled verse entries in the cleaned output
  finds zero occurrences of annotation-related content (word-meaning explanations or
  benefits/commentary text) and exactly one merged hemistich line per verse.
- **SC-003**: The original Ground Truth source file's checksum/content is unchanged before and after
  running the cleanup process, on 100% of runs.
- **SC-004**: The cleanup process, when pointed at a second sample file with the same general
  repeating structure but different content, produces a correctly cleaned output without any code or
  configuration change specific to that second file's content.
- **SC-005**: When deliberately given a structurally malformed verse block, the process surfaces a
  clear, specific anomaly report (identifying the verse number and issue) in 100% of tested malformed
  cases, rather than completing with a silently corrupted or incomplete result.

## Assumptions

- The source Ground Truth file's repeating structure (verse-number heading, followed immediately by
  exactly two hemistich lines, followed by zero or more annotation callout sections of the two known
  types) is stable and consistent across the entire file, as verified against the current primary
  test manuscript's reference file. Future reference files reused with this process are expected to
  follow the same general shape, though specific decorative or section-divider content between
  verses may differ and must simply be excluded (per FR-006).
- "Two hemistich lines" is a structural assumption grounded in the current test manuscript's poetic
  form (a poem written in balanced two-hemistich verses, as reflected in the pipeline's own
  verse-joining output format). This is treated as a documented structural assumption of this
  process, not a permanent restriction on the whole project's scope — a future reference file that is
  entirely prose, or built from single-line verses, would be an explicitly out-of-scope input for the
  process described here.
- There is currently no established correspondence between "verse number" (used in this Ground Truth
  file) and "page number" (used in the manuscript pipeline's own output files, e.g.
  `output/<document>/raw_text/page_NNN.txt`). This feature deliberately does NOT attempt to establish
  or resolve that correspondence. Producing a clean, verse-numbered reference file is this feature's
  entire responsibility; mapping verses to pages (or finding an alternative comparison approach that
  does not require such a mapping, such as comparing the whole book as one continuous text) is
  explicitly out of scope here and is deferred to a separate, future CER/WER measurement-tooling
  feature.
- The cleaned output's merged-hemistich-line format is expected to structurally match whatever the
  manuscript pipeline's own poetry-path output produces for a single verse line, so that a future
  comparison tool can align them without additional reformatting. If the pipeline's own separator
  format changes in the future, this cleanup process's output format is expected to be updated to
  match it again — this dependency is treated as a known coupling, not hidden or accidental.
- This feature produces the cleaned reference artifact; it does not itself compute or report any
  CER/WER metric. That measurement capability is separate, future work per the project constitution.
