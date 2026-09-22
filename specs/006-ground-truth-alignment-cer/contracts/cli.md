# CLI Contract: Ground-Truth Alignment & CER/WER Measurement

**Branch**: `006-ground-truth-alignment-cer` | **Date**: 2026-09-17

> الواجهة المدعومة هي CLI فقط (Constitution: Interface Policy). جميع الأوامر تعمل من جذر المشروع عبر `myenv/bin/python` (Python 3.11.16).

---

## 1. أداة المواءمة — `align_ground_truth.py`

تنتج ملف التعيين `{page → [أبيات GT]}`.

### الاستدعاء

```bash
myenv/bin/python -m src.pipeline.evaluation.align_ground_truth \
    --document "عمود النسب نسخة 2" \
    --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md" \
    --output "data/evaluation_reports/006/alignment.json"
```

### المعطيات (Arguments)

| المعطى | مطلوب | افتراضي | الوصف |
|---|---|---|---|
| `--document` | نعم | — | اسم الوثيقة (مجلد `data/output/<document>/`) |
| `--gt-file` | نعم | — | المسار لملف GT النظيف (`.clean.md`) |
| `--output` | لا | `data/evaluation_reports/006/alignment.json` | ملف الإخراج JSON |
| `--window` | لا | `40` | عرض نافذة البحث في GT حول الـ cursor |
| `--hallucination-threshold` | لا | `20` | مسافة ليفنشتاين فوقها يُعتبر البيت هلوسة |
| `--start-page` / `--end-page` | لا | الكل | تقييد النطاق (للتجارب السريعة) |

### الإخراج

**STDOUT**: سجل تقدم مقروء (صفحة → حالة + confidence). **Exit 0** عند النجاح.

**ملف JSON**: `list[AlignmentEntry]` (شكل data-model.md). كل صفحة (1..N) لها مدخل، حتى لو `out_of_gt_scope` — **لا تُسقَط صفحة صامتة** (FR-003).

### الأخطاء (Exit codes)

| الكود | المعنى |
|---|---|
| `0` | نجاح — كل الصفحات لها مدخل |
| `1` | خطأ في المعطيات (ملف GT غير موجود / document مجهول) |
| `2` | تحذير: GT لا يغطي كل الصفحات — البيانات الجزئية كُتبت، لكن `pages_out_of_scope > 0` (ليس فشلًا — معلوم من R2) |

---

## 2. توسيع آلة القياس — `evaluate_cer.py`

**تعديل** (مش إعادة كتابة — Constitution II) على الآلة الموجودة. تضاف أوضاع جديدة، وتُحفظ القديمة كما هي.

### الاستدعاءات

**الطريقة الحالية (محفوظة بالكامل):**
```bash
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer \
    --document "عمود النسب نسخة 2" --pages 24-26
```

**الطريقة الجديدة — مواءمة (FR-001..007):**
```bash
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer \
    --document "عمود النسب نسخة 2" \
    --alignment "data/evaluation_reports/006/alignment.json"
```

**قياس التشكيل (FR-005):**
```bash
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer \
    --document "عمود النسب نسخة 2" \
    --alignment "data/evaluation_reports/006/alignment.json" \
    --diacritics-metrics
```

### المعطيات الجديدة (مضافة للقديمة)

| المعطى | افتراضي | الوصف |
|---|---|---|
| `--alignment` | غير مفعّل | مسار `alignment.json` — يحول الوضع من per-page GT إلى المواءمة |
| `--diacritics-metrics` | `false` | يضيف قياس correct/missing/wrong/extra للتشكيل |
| `--report-dir` | `data/evaluation_reports/006` | مجلد إخراج التقارير |
| `--heatmap` | `false` | ينتج `heatmap.txt` (ASCII) |

### السلوكيات (Contracts)

**`--alignment` المفعَّل:**
- يقرأ `alignment.json` ويطبّق `AlignmentEntry.status`:
  - `matched` / `low_confidence` → حساب CER/WER على `gt[gt_start..gt_end]` مقارنةً بأبيات ` ... ` في الصفحة (بعد استثناء `hallucination_verses`).
  - `prose_only` / `out_of_gt_scope` / `unmatched` / `empty_page` → لا حساب، تسجيل في التقرير فقط.
- **الإخراج**: `quality_report.json` + `quality_report.txt` (شكل CorpusReport).

**`--diacritics-metrics` المفعَّل (يتطلب `--alignment`):**
- يطبّق منطق DiacriticStats على **النص الخام** (مع الحركات) — **لا** يستخدم `normalize_text` (الذي يجرّد الحركات).
- يضيف حقل `diacritics` لكل `PageQuality`.

**`--heatmap` المفعَّل:**
- ينتج خريطة ASCII: 113 خلية، كل خلية حرف واحد حسب CER:
  ```
  . = لم تُقس     _ = prose     # = CER < 5%     o = 5-15%    O = 15-30%
  X = 30-60%      ! = > 60%     ? = low_confidence
  ```
- عنوان لكل 10 صفحات (1, 10, 20, ...).

### Exit codes (محفوظة + مضافة)

| الكود | المعنى |
|---|---|
| `0` | حساب + طباعة ناجحة |
| `1` | خطأ في المعطيات |
| `2` | تحذير: صفحات لم تُقس (placeholder/out-of-scope) — البيانات الجزئية صحيحة |

**ملاحظة مهمة**: exit 2 **ليس فشلًا** — هو الطريقة الأمينة للقول "لا يمكن قياس البعض". سلوك محفوظ من الآلة الأصلية.

---

## 3. الثوابت (لا تُغيَّر)

- `TATWEEL`، `TASHKEEL` regex، `normalize_text()` — **تُستورد من `evaluate_cer.py`**، لا تنسخ (FR-008).
- فاصل الشعر ` ... ` — نفس المعتمد في §4.9.
- `--diacritics` القديم (strip/keep) يبقى كما هو — التوافق مع الماضي.

---

## 4. أمثلة الإخراج

### `quality_report.txt` (نصي مقروء)

```
=== تقرير جودة المخطوط: عمود النسب نسخة 2 ===
Generated: 2026-09-17T...

المرجع: data/ground_truth/عمود النسب/عمود_النسب.clean.md (620 بيت)
ملاحظة: الأرقام = مسافة إلى benchmark عمل (Constitution §VI)، مش حقيقة مطلقة.

الصفحات: 113 | قِيست: 13 | خارج نطاق GT: 90 | نثرية: 22

CER المرجَّح: 14.2%
WER المرجَّح: 52.8%

التشكيل: 251/308 صحيح (81.5%) | missing 41 | wrong 12 | extra 8

أبيات الهلوسة المستثناة: 3 (في ص27)

أسوأ 5 صفحات:
  ص27: CER 10.3% WER 42.5% [3 أبيات هلوسة]
  ...
```

### `heatmap.txt` (ASCII)

```
توزيع CER عبر الصفحات (113):
        1         2         3         4         5         6
        0123456789012345678901234567890123456789012345678901
   1-10:_______________.oOOO____________________________
  11-20:_______________________________________.oO_____
  21-30:_____.ooOOOOO!__O____________________________o__
  ...
المفتاح: . = لم تُقس  _ = prose  # = <5%  o = 5-15%  O = 15-30%  X = 30-60%  ! = >60%  ? = low_conf
```
