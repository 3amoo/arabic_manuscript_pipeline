# Feature Specification: CER/WER Benchmarking Harness

**Feature Branch**: `[002-cer-wer-benchmark]`

**Created**: 2026-09-07

**Status**: Draft

**Input**: User description: "بناء ميزة 'CER/WER Benchmarking Harness' لمشروع خط إنتاج استخراج نص المخطوطات العربية.

## السياق
يمتلك المشروع الآن (بعد إنجاز ميزة 'Ground Truth Corpus Cleanup' السابقة) ملف مرجعي نظيف
(`عمود_النسب.clean.md`) يحتوي على 620 بيتًا شعريًا، كل بيت في صيغة سطر واحد (شطر أيمن + فاصل
' ... ' + شطر أيسر)، مفصولة عن بعضها بسطر فارغ. كما يمتلك المشروع خط إنتاج (pipeline) قائم
(`main.py`) ينتج مخرجات الفعلية في `output/<document>/raw_text/page_NNN.txt` (ملف نصي مستقل لكل
صفحة) و`output/<document>/full_manuscript.txt` (كل الصفحات مجمّعة في ملف واحد).

المطلوب الآن: أداة تقارن هذين المصدرين وتحسب معدلات الخطأ الحرفي (CER) والكلمي (WER) باستخدام
مكتبة `jiwer`، لتوفير أول قياس رقمي موضوعي لجودة خط الإنتاج - وهو شرط غير قابل للتفاوض في دستور
المشروع (مبدأ 'Measurement-Driven Improvement') لم يكن متاحًا فعليًا حتى الآن بسبب غياب مرجع نظيف.

## القرار المعتمد لطريقة المقارنة (غير قابل للتفاوض في هذه الميزة)
لا يوجد حاليًا أي ربط أو جدول مطابقة بين 'رقم البيت' في الملف المرجعي و'رقم الصفحة' في مخرجات خط
الإنتاج (قيد موثّق صراحة في ميزة Ground Truth Cleanup السابقة، ولم يُحَل هناك عمدًا). بدلاً من محاولة
حل هذا الربط، تعتمد هذه الميزة **مقارنة الكتاب كاملاً كنص متصل واحد**: يُجمَّع الملف المرجعي النظيف
بالكامل كنص واحد، وتُجمَّع كل صفحات خط الإنتاج (`full_manuscript.txt` أو ما يعادله) بالكامل كنص واحد،
ويُحسب CER/WER على مستوى الكتاب ككل - وليس صفحة بصفحة أو بيت ببيت. هذا يعني أن الأداة **لا تحتاج** إلى
حل مشكلة 'أي بيت يقابل أي صفحة' لتعمل.

## قرار حاسم بخصوص التطبيع (Normalization) - يجب توثيقه بوضوح شديد
المقارنة يجب أن تكون **حرفية بالكامل (character-for-character)، بدون أي تطبيع أو تبسيط للنص قبل
المقارنة** - لا إزالة تشكيل، لا توحيد أشكال الألف/الهمزة/التاء المربوطة، لا إزالة علامات ترقيم، لا
تجاهل حالة الأحرف (لا ينطبق أصلاً على العربية لكن للتوضيح). السبب: مبدأ الدستور 'OCR ≠ Editing' -
أي تطبيع يُدخِل قرارًا تفسيريًا في عملية القياس نفسها، ويُخفي أخطاء حقيقية (مثل فقدان تشكيل أو تبديل
حرف مشابه شكليًا) كان يجب أن تظهر في الرقم النهائي. الاستثناء الوحيد المسموح به صراحة: التعامل مع
الفروق التنسيقية غير الجوهرية الناتجة عن بنية الملفين المختلفة (مثل الأسطر الفارغة الفاصلة بين
الأبيات في الملف المرجعي، أو فواصل الصفحات/العناوين في مخرجات خط الإنتاج مثل '--- نهاية الصفحة ---')
- هذه ليست 'تطبيعًا لغويًا' بل إزالة لعناصر بنيوية (structural) لا علاقة لها بالمحتوى النصي نفسه ولا
تنتمي لأي من الملفين أصلاً كمحتوى حقيقي.

## المطلوب من الأداة
1. قراءة الملف المرجعي النظيف وتجميع محتواه كنص متصل واحد (مع إزالة العناصر البنيوية غير النصية
   مثل الأسطر الفارغة الفاصلة وعناوين '## البيت N' نفسها - المحتوى فقط هو المقارَن).
2. قراءة مخرجات خط الإنتاج (على مستوى الكتاب كامل) وتجميعها كنص متصل واحد (مع إزالة العناصر البنيوية
   الخاصة بها مثل فواصل نهاية الصفحة).
3. حساب CER وWER باستخدام مكتبة `jiwer` بين النصين.
4. إنتاج تقرير واضح يتضمن: الرقمين (CER، WER)، وعدد الأحرف/الكلمات في كل من المرجع والمخرجات،
   وأي ملاحظة حول فروق طول واضحة بين النصين قد تشير لمشكلة في المحاذاة (مثل غياب صفحات كاملة من
   مخرجات خط الإنتاج، وهو أمر معروف الحدوث - راجع ملاحظات AGENTS.md عن صفحات 'blank_or_unclear').
5. الأداة يجب أن تكون **قابلة لإعادة الاستخدام على أي مستند مستقبلي آخر**، لا مكتوبة خصيصًا لكتاب
   'عمود النسب' - تأخذ مسار الملف المرجعي ومسار مخرجات خط الإنتاج كمدخلات (arguments)، وليس كقيم
   ثابتة (hardcoded) في الكود.

## قيد معروف يجب توثيقه صراحة كخارج النطاق الحالي
هذه الميزة لا تحاول حل مشكلة محاذاة على مستوى الصفحة أو البيت - النتيجة رقم واحد على مستوى الكتاب كاملاً، وليس صفحة بصفحة أو بيت ببيت."

## Clarifications

### Session 2026-09-07

- Q: Should verse numbers (Arabic numerals) be included in the text comparison for CER/WER calculation? → A: No, verse numbers must be excluded from comparison text as they are structural metadata not present in pipeline output, to avoid introducing artificial errors.
- Q: What should be the variance tolerance for repeated CER/WER calculations on identical inputs? → A: 0% variance (exact match) as string comparison is deterministic.
- Q: Should the benchmarking tool modify input files? → A: No, tool must be read-only for input files to maintain raw evidence immutability principle.

### User Story 1 - Benchmark Current Pipeline Accuracy (Priority: P1)

As a pipeline developer, I want to measure the Character Error Rate (CER) and Word Error Rate (WER) of the current OCR pipeline against a clean ground truth reference, so I can establish a baseline measurement for future improvements as required by the project constitution's "Measurement-Driven Improvement" principle.

**Why this priority**: This is the foundation for all future optimization work. Without accurate CER/WER measurements, no change to the OCR pipeline can be validated as an improvement.

**Independent Test**: Can be fully tested by running the benchmark tool against the existing clean reference (`عمود_النسب.clean.md`) and pipeline output (`output/عمود النسب نسخة 2/full_manuscript.txt`) and verifying that it produces CER and WER percentages, character counts, and word counts.

**Acceptance Scenarios**:

1. **Given** a clean ground truth file with 620 poetic verses and a pipeline output file containing OCR-extracted text, **When** the benchmarking tool is executed with these two files as inputs, **Then** the tool should calculate and display CER and WER percentages, along with character and word counts for both files.
2. **Given** structural elements in both files (empty lines between verses in ground truth, page separators in pipeline output), **When** the benchmarking tool processes the files, **Then** it should remove these structural elements while preserving all textual content including diacritics, punctuation, and Arabic letter forms exactly as written.
3. **Given** a significant length difference between ground truth and pipeline output (indicating missing pages or content), **When** the benchmarking tool compares the files, **Then** it should flag the length discrepancy in its report as a potential alignment issue.

---

### User Story 2 - Reusable Benchmark for Future Documents (Priority: P1)

As a pipeline maintainer, I want a benchmarking tool that can be reused on any future document with its own ground truth, not just the specific test manuscript, so I can maintain the project's "Generalized Scope - Not Book-Specific" principle.

**Why this priority**: The tool must be generalizable to support the project's stated goal of handling Arabic manuscripts in general, not just one specific book.

**Independent Test**: Can be fully tested by creating a test reference file and test pipeline output for a different (mock) document, running the tool with these inputs, and verifying it produces correct CER/WER measurements without hardcoded assumptions about verse structure or content.

**Acceptance Scenarios**:

1. **Given** a different manuscript with its own clean reference file and pipeline output, **When** the benchmarking tool is executed with these new files as command-line arguments, **Then** it should work correctly without modification or configuration changes.
2. **Given** the benchmarking tool executable, **When** run with `--help` or without arguments, **Then** it should display usage instructions explaining how to provide ground truth and pipeline output file paths as arguments.

---

### Edge Cases

- What happens when the ground truth file contains no content (empty file)?
- How does system handle missing pipeline output files or invalid paths?
- What happens when the pipeline output contains no textual content (only structural separators)?
- How does the tool handle very large files (multiple MB of text)?
- What happens when the character sets differ significantly between files (e.g., mixed encodings)?
- How does the tool handle the case where pipeline output is much shorter than ground truth (indicating missing pages)?
- How does the tool handle the case where pipeline output is much longer than ground truth (indicating extraneous content or duplication)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read a clean ground truth file and extract its textual content as a single continuous string, removing structural elements (empty lines between verses, verse numbers as Arabic numerals or any similar numeric prefixes) while preserving all linguistic content of the poetic verses (right hemistich, separator "...", left hemistich) including diacritics, punctuation, and Arabic letter forms exactly as written.
- **FR-002**: System MUST read a pipeline output file (either `full_manuscript.txt` or equivalent aggregated output) and extract its textual content as a single continuous string, removing structural elements (page separators like "--- نهاية الصفحة ---") while preserving all OCR-extracted text including errors. Note: Page headers exist only in raw_text/page_NNN.txt files and are not present in the aggregated full_manuscript.txt.
- **FR-003**: System MUST calculate Character Error Rate (CER) using the `jiwer` library or equivalent standard metric, comparing the extracted ground truth text against the extracted pipeline output text.
- **FR-004**: System MUST calculate Word Error Rate (WER) using the `jiwer` library or equivalent standard metric, comparing the extracted ground truth text against the extracted pipeline output text.
- **FR-005**: System MUST count and report the number of characters in both the ground truth and pipeline output texts.
- **FR-006**: System MUST count and report the number of words in both the ground truth and pipeline output texts.
- **FR-007**: System MUST detect and flag significant length discrepancies between ground truth and pipeline output (e.g., when one is more than 20% shorter/longer than the other) as potential alignment issues.
- **FR-008**: System MUST accept file paths for ground truth and pipeline output as command-line arguments, not as hardcoded values.
- **FR-009**: System MUST display a clear, human-readable report including: CER percentage, WER percentage, character counts for both files, word counts for both files, and any length discrepancy warnings.
- **FR-010**: System MUST NOT perform any linguistic normalization (diacritic removal, hamza unification, taa marbouta conversion, punctuation removal, case normalization) on either text before comparison.
- **FR-011**: System MUST handle Arabic text encoding correctly (UTF-8).
- **FR-012**: System MUST be executable as a standalone command-line tool with appropriate error handling for missing files, invalid paths, and empty content.
- **FR-013**: System MUST NOT modify or overwrite any input files (ground truth or pipeline output) - read-only access only, in accordance with Principle IV (Raw Evidence Immutability) of the project constitution.

- **Ground Truth File**: A clean reference text file containing the correct transcription of a manuscript, typically with structural elements like verse separators or section markers that need to be removed before comparison.
- **Pipeline Output File**: The OCR pipeline's extracted text output, typically containing structural elements like page separators or headers that need to be removed before comparison.
- **CER (Character Error Rate)**: Percentage of characters that differ between ground truth and pipeline output, calculated as (substitutions + insertions + deletions) / total characters in ground truth.
- **WER (Word Error Rate)**: Percentage of words that differ between ground truth and pipeline output, calculated as (substitutions + insertions + deletions) / total words in ground truth.
- **Structural Elements**: Non-content markers in files that should be removed before comparison (empty lines, verse numbers as Arabic numerals, page separators, headers) but NOT linguistic elements (diacritics, punctuation, letter forms).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pipeline developers can obtain CER and WER measurements for any OCR pipeline run against its corresponding ground truth reference in under 5 minutes of tool execution time.
- **SC-002**: The benchmarking tool produces identical, reproducible measurements when run multiple times on the same inputs (measurement variance = 0%).
- **SC-003**: The tool correctly identifies and reports length discrepancies when pipeline output is missing significant portions of content (detects when one text is >20% shorter than the other).
- **SC-004**: The tool's output report is clear enough that non-technical stakeholders can understand the basic accuracy metrics (CER/WER percentages and what they mean for pipeline quality).
- **SC-005**: The tool handles at least 100,000 characters of text without performance degradation or memory issues.
- **SC-006**: The tool can be successfully run on at least 3 different manuscript/ground-truth pairs without modification, demonstrating generalization beyond the initial test manuscript.

## Assumptions

- The `jiwer` Python library is available and can be installed via pip if not already present in the project dependencies.
- Ground truth files follow the established format of `عمود_النسب.clean.md`: verse numbers as Arabic numerals on the same line as verse text (to be removed as structural elements), with empty lines between verses.
- Pipeline output files contain page separators in the format "--- نهاية الصفحة ---" or similar recognizable markers.
- Both ground truth and pipeline output files are encoded in UTF-8 and contain valid Arabic text.
- The benchmarking tool will be run in a Python environment (3.8+) with standard library access.
- No page-by-page or verse-by-verse alignment is required for this tool to provide value - whole-document comparison is acceptable as a baseline measurement.
- Length discrepancies between files will be interpreted as potential alignment/coverage issues rather than errors to be corrected by the tool.
- The tool does not need to handle PDF files directly - it works with already-extracted text files.
