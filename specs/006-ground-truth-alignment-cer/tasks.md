---

description: "Task list for Ground-Truth Alignment & CER/WER Measurement (spec 006)"
---

# Tasks: Ground-Truth Alignment & Full-Corpus CER/WER Measurement

**Input**: Design documents from `/specs/006-ground-truth-alignment-cer/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: مطلوبة (spec 006 §11 DoD — كل ميزة قياس تحتاج اختبارات لأن الأرقام themselves يجب أن تكون موثوقة). اختبارات تُكتب FIRST وتفشل قبل التنفيذ (TDD) لأنها **أرقام مرجعية**.

**Organization**: Tasks grouped by user story (US1=مواءمة, US2=قياس CER/WER, US3=تشكيل, US4=تصحيح ميموري).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: إنشاء البنية الأساسية لهذا spec فقط (لا تلمس ممر الإنتاج).

- [x] T001 إنشاء طبقة الإخراج المنفصلة `data/evaluation_reports/006/` (dir + `.gitkeep`) — تثبت Constitution IV
- [x] T002 [P] قراءة + توثيق واجهة `src/pipeline/evaluation/evaluate_cer.py` الحالية كاملةً (الدوال: `normalize_text`, `score_page`, `parse_page_spec`, `has_usable_gt_content`) — تُستورد، لا تُنسخ
- [x] T003 [P] التحقق من أن `data/ground_truth/عمود النسب/عمود_النسب.clean.md` = 620 بيت مرقم (١..٦٢٠) — تأكيد فرضية research.md R2

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: الأدوات المشتركة التي يحتاجها كل user story.

**⚠️ CRITICAL**: لا يمكن بدء أي story قبل اكتمال هذه المرحلة.

- [x] T004 [P] تنفيذ `levenshtein(a, b)` في `src/pipeline/evaluation/align_ground_truth.py` — خوارزمية مسافة ليفنشتاين (stdlib، لا تبعيات)
- [x] T005 [P] تنفيذ `extract_gt_verses(gt_file) -> list[str]` في `src/pipeline/evaluation/align_ground_truth.py` — قراءة `.clean.md`، إزالة الترقيم (١٢٣..)، تطبيع `normalize_text` (مستوردة من evaluate_cer)
- [x] T006 [P] تنفيذ `extract_page_verses(page_path) -> list[str]` في `src/pipeline/evaluation/align_ground_truth.py` — قراءة صفحة raw_text، إزالة الهيدر (`#`)، الاحتفاظ فقط بأسطر ` ... ` (فاصل §4.9)
- [x] T007 تنفيذ `detect_page_type(page_path) -> enum` في `src/pipeline/evaluation/align_ground_truth.py` — تصنيف: `poetry` (كل الأسطر ` ... `) / `prose` (لا ` ... `) / `mixed` / `empty` (بحث: R1)

**Checkpoint**: الأدوات الأساسية جاهزة — يمكن بدء US1.

---

## Phase 3: User Story 1 - مواءمة GT مع ترقيم الصفحات (Priority: P1) 🎯 MVP

**Goal**: إنتاج `alignment.json` يربط كل صفحة بأبيات GT المقابلة + نسبة ثقة.

**Independent Test**: تشغيل على ص23-26 → ص23@gStart=1, ص24=13, ص25=29, ص26=42 (research.md R2/R5).

### Tests for User Story 1 (TDD — تكتب أولاً وتفشل)

- [x] T008 [P] [US1] اختبار `levenshtein` في `tests/test_gt_alignment.py`: حالات الأساس (ident=0, one-sub=1, one-ins=1, one-del=1, empty) + نص عربي مشكول
- [x] T009 [P] [US1] اختبار `extract_gt_verses` في `tests/test_gt_alignment.py`: يقرأ 620 بيت، الترقيم مزال، لا أسطر فارغة
- [x] T010 [P] [US1] اختبار `detect_page_type` في `tests/test_gt_alignment.py`: poetry/prose/mixed/empty على fixtures حقيقية (ص24=poetry, ص1=prose, ص113=empty)
- [x] T011 [P] [US1] اختبار الحفاظ على التسلسل (FR-002): لأي صفحتين i<j matched: `gt_end[i] < gt_start[j]`
- [x] T012 [P] [US1] اختبار حالة `hallucination_verses`: بيت d>20 يُعلَّم ولا يُسقَط (قاعدة §6)
- [x] T013 [P] [US1] اختبار edge cases: صفحة فارغة → `empty_page`؛ نثرية → `prose_only`؛ خارج GT → `out_of_gt_scope` (لا silent drop — FR-003)

### Implementation for User Story 1

- [x] T014 [US1] تنفيذ `align_page(...)` في `src/pipeline/evaluation/align_ground_truth.py`: نافذة `[cursor, cursor+window]`، البيت المرجعي = **الأوسط** (مقاومة الهلوسة، R3)، skip مسموح، إرجاع AlignmentEntry
- [x] T015 [US1] تنفيذ حساب `confidence`: نسبة أبيات الإخراج ذات d<hallucination_threshold ضمن النافذة المختارة (R3)
- [x] T016 [US1] تنفيذ `align_corpus(...) -> list[AlignmentEntry]` في نفس الملف: الحلقة الرئيسية عبر الصفحات بالترتيب + cursor محفوظ
- [x] T017 [US1] تنفيذ CLI `main()` في نفس الملف: argparse (`--document`, `--gt-file`, `--output`, `--window`, `--hallucination-threshold`, `--start-page`, `--end-page`) + كتابة JSON + exit codes (0/1/2 حسب contracts/cli.md)
- [x] T018 [US1] تشغيل فعلي على المخطوط الكامل + التحقق من SC-001 (ص24=GT#13)

**Checkpoint**: `alignment.json` مُنتَج وقابل للتحقق المستقل.

---

## Phase 4: User Story 2 - قياس CER/WER شامل (Priority: P1)

**Goal**: تقرير جودة رقمي لكامل المخطوط + أسوأ الصفحات + كشف الأسطر المفقودة.

**Independent Test**: `weighted_cer` بين 8-25%، `pages_evaluated=13` (research.md R5).

### Tests for User Story 2 (TDD)

- [x] T019 [P] [US2] اختبار `score_aligned_page` في `tests/test_gt_alignment.py` (أو `tests/test_cer_alignment.py`): على صفحة 24 → CER≈15.6% WER≈55% (الرقم المرجعي)
- [x] T020 [P] [US2] اختبار FR-009: بعد التشغيل، sha256 لـ `raw_text/` + `ground_truth/` متطابق (safety)
- [x] T021 [P] [US2] اختبار FR-013: تكرار التشغيل → نفس الأرقام (no RNG)
- [x] T022 [P] [US2] اختبار `count_mismatch`: صفحة 15 بيت vs GT 16 → status صحيح + no crash

### Implementation for User Story 2

- [x] T023 [US2] تعديل `src/pipeline/evaluation/evaluate_cer.py`: إضافة `--alignment` arg + `score_aligned_page()` (يستخدم `normalize_text` الموجود — FR-008، يحترم `hallucination_verses` بالاستبعاد + التسجيل)
- [x] T024 [US2] تنفيذ `build_corpus_report(...) -> CorpusReport` في `evaluate_cer.py`: weighted CER/WER، أسوأ/أفضل صفحات، توزيع الثقة (data-model.md)
- [x] T025 [US2] تنفيذ `--heatmap`: ASCII heatmap في `data/evaluation_reports/006/heatmap.txt` (مفتاح . _ # o O X ! ?)
- [x] T026 [US2] تنفيذ تقرير `quality_report.txt` (نصي مقروء، شكل contracts/cli.md §4) + `quality_report.json`
- [x] T027 [US2] تشغيل كامل + التحقق من SC-002/SC-003/SC-007 (أرقام في النطاق، baseline/ غير ملموس)

**Checkpoint**: أرقام CER/WER مُنتَة + قابلة لإعادة الإنتاج.

---

## Phase 5: User Story 3 - قياس التشكيل (Priority: P2)

**Goal**: نسب correct/missing/wrong/extra للحركات لكل صفحة + إجمالي.

**Independent Test**: accuracy بين 75-90% (research.md R5: ~17% فقد).

### Tests for User Story 3 (TDD)

- [x] T028 [P] [US3] اختبار منطق DiacriticStats في `tests/test_diacritic_metrics.py`: `عَبْدُ` vs `عَبدُ` → correct=2, missing=1 (case بحث R6)
- [x] T029 [P] [US3] اختبار wrong vs missing: `بَ` vs `بُ` → wrong=1 (ليس missing)
- [x] T030 [P] [US3] اختبار extra: `بْ` vs `بَبْ` → extra=1
- [x] T031 [P] [US3] اختبار النص المتطابق حروفًا: 0% CER لكن تشكيل ناقص (case acceptance scenario 4)

### Implementation for User Story 3

- [x] T032 [US3] تنفيذ `analyze_diacritics(gt_text, out_text) -> DiacriticStats` في `evaluate_cer.py` (أو وحدة مساعدة): مقارنة موضعية للحروف الأساسية + combining marks (منطق data-model.md)
- [x] T033 [US3] إضافة `--diacritics-metrics` arg (يتطلب `--alignment`) + دمج `diacritics` في PageQuality + CorpusReport
- [x] T034 [US3] تشغيل + التحقق من SC-004 (accuracy ~81%)

**Checkpoint**: قياس التشكيل يعمل بشكل مستقل.

---

## Phase 6: User Story 4 - تصحيح الذاكرة (Priority: P2)

**Goal**: توثيق يعكس الواقع: GT كامل (مش ناقص)، baseline/ مفقود، أرقام مسجلة.

**Independent Test**: `grep -c "GT ناقضة" docs/AGENTS.md` = 0 (SC-008).

- [x] T035 [US4] تصحيح `docs/AGENTS.md` §8: حذف «الـ GT ناقصة» → كتابة «620 بيت كامل، نطاق ص23-35» + طريقة المواءمة
- [x] T036 [US4] تصحيح `docs/AGENTS.md` §2/§8/§11/§14: إشارات `baseline/` — توثيق وضعه الفعلي (مفقود) أو حذفها
- [x] T037 [US4] تسجيل **المرجع الرقمي الأول** في §8: CER 14-18% / WER 42-58% / تشكيل ~81% / هلوسة 18% في ص27 + تسمية إلزامية «مسافة إلى benchmark عمل» (Constitution §VI)
- [x] T038 [P] [US4] تحديث `docs/CHANGELOG.md` بقصة spec 006 (الاكتشافات: GT كامل، baseline/ مفقود، هلوسة في raw_text)
- [x] T039 [P] [US4] تعليم `docs/PROJECT_SUMMARY.md` + `docs/CLAUDE.md` كـ **باردة/تاريخية** (أو تصحيح) — يحتويان بنية مسطحة + camel-tools غير مثبت (كلاهما خطأ)

**Checkpoint**: الميموري تطابق الواقع.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: التحقق النهائي + الانحدار + التوثيق.

- [x] T040 [P] تشغيل كامل quickstart.md (الخطوات 1-5) + التحقق من كل acceptance scenarios
- [x] T041 [P] تشغيل كل الاختبارات: `tests.test_gt_alignment`, `tests.test_diacritic_metrics` + الانحدار (`test_cer_normalization`, `test_escalation_policy`, `test_output_generator`, `test_atria_text_backend`, `test_cer_normalization`) — يجب أن تمر كلها (SC-006)
- [x] T042 [P] `py_compile` على كل الملفات المتأثرة (DoD #1)
- [x] T043 [P] ركض `main.py --start 24 --end 26` — يجب exit 0 بدون تغيير (هذا spec قياس فقط، لا تأثير على الإنتاج)
- [x] T044 [P] فحص أمني: لا مفاتيح في أي مخرج (DoD #6)
- [x] T045 [P] تأكيد `baseline/` (إن وُجد) و`raw_text/` و`ground_truth/` و`corrected_text/` و`output/.cache/` — بصمات متطابقة (DoD #4/#5)
- [x] T046 [P] توثيق: تحديث `docs/AGENTS.md` §11 بأوامر القياس الجديدة (quickstart §1-2)
- [x] T047 [P] تنظيف: حذف `.pytest_cache/` + `data/logs/` + `data/temp/` كتنظيف عام (قرار plan §"الحاجات المش مهمة")

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: لا اعتمادات — يبدأ فورًا
- **Foundational (Phase 2)**: يعتمد على T001 (طبقة الإخراج)
- **US1 (Phase 3)**: يعتمد على Phase 2 كاملة (T004-T007) — **blocks US2**
- **US2 (Phase 4)**: يعتمد على US1 (يحتاج `alignment.json` + AlignmentEntry)
- **US3 (Phase 5)**: يعتمد على US2 (يحتاج PageQuality structure)
- **US4 (Phase 6)**: يعتمد على US2+US3 (يحتاج الأرقام النهائية)
- **Polish (Phase 7)**: يعتمد على كل ما سبق

### User Story Dependencies

- **US1 (P1)**: بعد Foundational. لا اعتماد على stories أخرى. **MVP**
- **US2 (P1)**: بعد US1 (يستهلك alignment.json)
- **US3 (P2)**: بعد US2 (يضيف طبقة على PageQuality)
- **US4 (P2)**: بعد US2+US3 (يحتاج الأرقام)

### Within Each User Story

- الاختبارات تُكتب FIRST وتفشل (TDD) — أرقام مرجعية يجب أن تكون موثوقة
- الأدوات قبل الحلقة الرئيسية
- CLI قبل التشغيل الفعلي
- كل story تنتهي بـ Independent Test + Checkpoint

### Parallel Opportunities

- Phase 1: T002, T003 متوازية
- Phase 2: T004-T007 كلها متوازية (ملفات/دوال مختلفة)
- US1 tests: T008-T013 كلها متوازية
- US2 tests: T019-T022 متوازية
- US3 tests: T028-T031 متوازية
- US4: T038, T039 متوازية
- Polish: T040-T047 كلها متوازية

---

## Parallel Example: User Story 1

```bash
# كل اختبارات US1 معًا (TDD — يجب أن تفشل أولًا):
Task: "اختبار levenshtein في tests/test_gt_alignment.py"
Task: "اختبار extract_gt_verses في tests/test_gt_alignment.py"
Task: "اختبار detect_page_type في tests/test_gt_alignment.py"

# أدوات Foundational معًا:
Task: "levenshtein في align_ground_truth.py"
Task: "extract_gt_verses في align_ground_truth.py"
Task: "extract_page_verses في align_ground_truth.py"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1: Setup (طبقة إخراج + قراءة evaluate_cer.py)
2. Phase 2: Foundational (levenshtein + extractors)
3. Phase 3: US1 (المواءمة + tests)
4. **STOP + VALIDATE**: ص23=GT#1, ص24=GT#13, ص25=GT#29, ص26=GT#42
5. عندها يصبح قياس CER ممكنًا → US2

### Incremental Delivery

1. US1 → alignment.json (المواءمة)
2. US2 → quality_report (CER/WER الكامل)
3. US3 → diacritics (قياس التشكيل)
4. US4 → تصحيح الميموري (AGENTS.md/CHANGELOG)
5. Polish → التحقق النهائي + الانحدار

---

## Notes

- **هذا spec قياس فقط (REVIEW_ONLY)**: لا تعديل لـ `main.py`، لا إعادة OCR، لا تفعيل Surya. كل ما يلمس الإنتاج = لا شيء.
- **الرقم المرجعي الأول سيفيد spec 008+**: كل تحسين لاحق يُقاس ضده (Constitution VI).
- **لا حذف صامت لأي بيانات**: أبيات الهلوسة تُسجَّل ولا تُحذف (قاعدة §6).
- التزام صارم بـ FR-009 (عدم الكتابة فوق raw_text/ground_truth) — يُفحص بـ sha256 (SC-005).
