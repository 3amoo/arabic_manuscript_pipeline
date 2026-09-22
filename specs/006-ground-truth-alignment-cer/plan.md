# Implementation Plan: Ground-Truth Alignment & Full-Corpus CER/WER Measurement

**Branch**: `006-ground-truth-alignment-cer` | **Date**: 2026-09-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-ground-truth-alignment-cer/spec.md`

## Summary

مشكلة جوهرية: المشروع كله يمشي **بدون بوصلة رقمية** — GT كامل (620 بيت) موجود لكن غير موائم لترقيم الصفحات، وآلة القياس `evaluate_cer.py` تتوقع `ground_truth/<doc>/page_NNN.txt` (ملف لكل صفحة) بينما الـ GT الفعلي **ملف واحد بترقيم أبيات ١..٦٢٠**. هذا الـ spec يردم الفجوة: (1) أداة مواءمة تنتج ملف تعيين `{page → [أبيات GT]}` بمطابقة تسلسلية محافظة + نسبة ثقة، (2) توسيع آلة القياس لتقبل هذا التعيين فتحسب CER/WER لكل الصفحات + قياس تشكيل منفصل (missing/wrong/correct)، (3) تقرير + خريطة حرارية + تصحيح للميموري.

النهج الفني (من research.md): المواءمة بـ **نافذة انزلاقية + مسافة ليفنشتاين** على مستوى البيت (وحدة المعنى الأساسية)، مع قيد التسلسل (البيت N لا يقابل صفحة بعد التي يقابلها N+1) — لا حاجة لـ DTW معقد. قياس التشكيل **لا** يستخدم jiwer (الذي يعالج الحركات كحروف) بل مقارنة موضعية مباشرة: لكل حرف أساسي، هل الحركة التالية موجودة ومطابقة. هذا يفرّق missing (مفقودة) عن wrong (خاطئة) — تمييز يستحيل على CER العادي.

## Technical Context

**Language/Version**: Python 3.11.16 (يفسِّر المشروع `myenv/bin/python` — ممنوع Python النظام 3.14.7، AGENTS.md §9).

**Primary Dependencies**: `jiwer 4.0.0` (مثبت، لـ CER/WER)، stdlib فقط لخوارزمية المواءمة (لا تبعيات جديدة — مبدأ Local-First VII).

**Storage**: ملفات JSON + نصي فقط. `alignment.json` (التعيين)، `quality_report.json` + `.txt` (التقرير)، `heatmap.txt` — كلها في **طبقة جديدة** `data/evaluation_reports/006/` (قاعدة §6: لا كتابة فوق `raw_text/`/`ground_truth/`).

**Testing**: stdlib `unittest` (نمط المشروع — `tests/test_cer_normalization.py` مثلًا). اختبارات وحدة جديدة في `tests/test_gt_alignment.py` + `tests/test_diacritic_metrics.py`.

**Target Platform**: Void Linux x86_64، CLI فقط (constitution: Interface Policy — CLI هو الواجهة المدعومة).

**Project Type**: أداة CLI للقياس (REVIEW_ONLY — لا تلمس ممر الإنتاج).

**Performance Goals**: مهمة وضعية: المواءمة على 620 بيت × 113 صفحة × ليفنشتاين O(n·m) — يجب أن تنتهي في **أقل من دقيقة** (620² سطرًا × 113 صفحة في حدود مئات الألاف من العمليات). القياس نفسه لحظي (jiwer على 113 ملف).

**Constraints**: 
- لا كتابة فوق `raw_text/` ولا `ground_truth/` ولا `corrected_text/` (قاعدة §6 / Constitution IV).
- لا فتح `.env` (§10).
- لا لمس كاش OCR (§4.8).
- **REVIEW_ONLY**: لا تعديل لـ `main.py` ولا لمراحل المعالجة.

**Scale/Scope**: مخطوط واحد (عمود النسب نسخة 2، 113 صفحة) + GT 620 بيت. التعميم لمخطوطات أخرى خارج النطاق (spec 006 §Outside Scope) — لكن الأكواد **يجب ألا تُصاغ بطريقة تجعل المخطوط الحالي ثابتًا كونيًا (Constitution VIII)**: الترتيب/الأرقام تأتي من معطيات الـ input، لا hardcoded.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| المبدأ | الحكم | التبرير |
|---|---|---|
| **I. Reverse-Engineering-First** | ✅ غير مطبَّق | هذا spec قياس — لا يمس ترتيب الاستخراج. لا خطر. |
| **II. Evolutionary Implementation** | ✅ يُحترم | سنعمل على **توسيع** `evaluate_cer.py` + `bootstrap_ground_truth.py` الموجودين (قرأناهما بالكامل)، لا إنشاء آلة قياس من الصفر. أنظر "Existing-code check" أدناه. |
| **III. Faithful Reconstruction** | ✅ غير مطبَّق | لا تصعيد رؤية ولا استبدال ناتج OCR. القياس يقرأ الإخراج الموجود فقط. |
| **IV. Raw Evidence Immutability** | ✅ يُحترم | كل المخرجات في طبقة `data/evaluation_reports/006/` منفصلة. سنثبت ذلك بفحص sha256 قبل/بعد (SC-005). |
| **V. Diacritic Preservation** | ✅ يُحترم | هذا الـ spec **يخدم** المبدأ: أول قياس حقيقي للتشكيل. لا تصحيح، قياس فقط. |
| **VI. Measurement-Driven** | ✅ **هذا هو المبدأ نفسه** | spec 006 يجعل المبدأ قابل للتطبيق — حاليًا مستحيل لأن GT غير موائم. |
| **VII. Resource-Constrained Local-First** | ✅ يُحترم | stdlib + jiwer فقط، لا GPU، لا شبكة، لا تبعيات جديدة. |
| **VIII. Generalized Scope** | ✅ يُحترم | المواءمة تعمل على أي ملف GT مرقم + أي عدد صفحات. لا hardcoded لـ 113/620 — كلها ديناميكية. |

**Gate verdict: PASS** — لا انتهاكات، لا حاجة لجدول Complexity Tracking.

### Existing-code check (Principle II)

| الملف الجديد/المُعدَّل | يبني على | الحالة |
|---|---|---|
| `align_ground_truth.py` (جديد) | لا يوجد مكافئ — المواءمة غير موجودة في الكود | مبرر: لا أداة تعيين موجودة. `bootstrap_ground_truth.py` **يجهز صورًا** ولا يعالج الترقيم. |
| `evaluate_cer.py` (تعديل) | موجود بالكامل، قرأنا واجهته | يُوسَّع: إضافة `--alignment` mode + `--diacritics-metrics` — لا إعادة كتابة. |
| `tests/test_gt_alignment.py` (جديد) | نمط `tests/test_cer_normalization.py` | يُتبع نمط المشروع (stdlib unittest). |
| AGENTS.md (تصحيح) | موجود | تصحيح §8/§12 فقط. |

## Project Structure

### Documentation (this feature)

```text
specs/006-ground-truth-alignment-cer/
├── plan.md              # هذا الملف
├── research.md          # Phase 0 — قرارات المواءمة وقياس التشكيل
├── data-model.md        # Phase 1 — AlignmentEntry / PageQuality / CorpusReport
├── quickstart.md        # Phase 1 — كيف تشغل القياس
├── contracts/
│   └── cli.md           # Phase 1 — واجهة CLI الكاملة
└── tasks.md             # Phase 2 (تُنشئها /speckit.tasks)
```

### Source Code (repository root)

```text
src/pipeline/evaluation/
├── evaluate_cer.py          # تعديل: + alignment mode + diacritic metrics
├── align_ground_truth.py    # جديد: أداة المواءمة (alignment.json)
├── bootstrap_ground_truth.py # موجود (يُقرأ فقط — لا يُلمس)
├── benchmark_cer_wer.py      # موجود (يُقرأ فقط)
└── clean_ground_truth.py    # موجود (يُقرأ فقط)

tests/
├── test_gt_alignment.py     # جديد: المواءمة (sequence, confidence, edge cases)
├── test_diacritic_metrics.py # جديد: correct/missing/wrong
└── test_cer_normalization.py # موجود (يُمرر — FR-008: تطبيع موحَّد)

data/evaluation_reports/006/  # طبقة جديدة بالكامل (قاعدة §6)
├── alignment.json
├── quality_report.json
├── quality_report.txt
└── heatmap.txt
```

**Structure Decision**: بنية مشروع واحد (Option 1) متوافقة مع `src/pipeline/` الموجودة. الأكواد الجديدة في `evaluation/` المنطقي (القياس يعيش هناك مع `evaluate_cer.py`). **لا `src/` جديد**، لا إعادة هيكلة — أقل تغيير ممكن (مبدأ II).

## Complexity Tracking

> لا انتهاكات في Constitution Check — هذا القسم فارغ عمدًا.

*(لا توجد انتهاكات تحتاج تبريرًا)*
