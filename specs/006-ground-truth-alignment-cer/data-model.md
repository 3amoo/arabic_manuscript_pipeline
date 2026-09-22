# Data Model: Ground-Truth Alignment & CER/WER Measurement

**Branch**: `006-ground-truth-alignment-cer` | **Date**: 2026-09-17

---

## Key Entities

### AlignmentEntry
تمثيل تعيين صفحة واحدة بأبيات GT المقابلة لها.

| الحقل | النوع | الوصف | القيود |
|---|---|---|---|
| `page` | `int` | رقم صفحة الإخراج (1..N) | ≥ 1 |
| `gt_start` | `int \| null` | أول رقم بيت GT مطابق | 1-based؛ `null` لو unmatched |
| `gt_end` | `int \| null` | آخر رقم بيت GT مطابق | ≥ gt_start |
| `status` | `enum` | نتيجة المواءمة | أحد القيم أدناه |
| `confidence` | `float` | نسبة ثقة التعيين | 0.0 - 1.0 |
| `out_verses_count` | `int` | عدد أبيات ` ... ` في الإخراج | ≥ 0 |
| `gt_verses_count` | `int` | عدد أبيات GT المستخدمة | = gt_end - gt_start + 1 |
| `skipped_gt` | `int` | أبيات GT تم تخطيها (gap) | ≥ 0 |
| `hallucination_verses` | `list[int]` | أرقام أبيات الإخراج ذات d>20 | قائمة 1-based |
| `anchor_distance` | `float` | مسافة البيت المرجعي (الأوسط) | ≥ 0 |

**قيم `status`:**

| القيمة | المعنى | متى |
|---|---|---|
| `matched` | تعيين ناجح وموثوق | confidence ≥ 0.7 |
| `low_confidence` | تعيين ضعيف | 0.3 ≤ confidence < 0.7 |
| `prose_only` | صفحة نثرية صرفة (0 أبيات) | out_verses_count == 0 |
| `out_of_gt_scope` | خارج نطاق GT (ص1-22 أو 36+) | gt_start == null |
| `empty_page` | صفحة فارغة | لا أسطر نصية |
| `count_mismatch` | عدد الأبيات غير متطابق | abs(out-gt) > 2 |

**حالة خاصة — `hallucination_verses`:**
لا تُحذف من الإخراج (قاعدة §6). تُسجل أرقامها فقط، وتُستثنى من حساب CER في PageQuality، لكنها **تبقى في `raw_text/`** ويُفصل عدّها في التقرير.

---

### PageQuality
نتيجة قياس جودة صفحة واحدة.

| الحقل | النوع | الوصف |
|---|---|---|
| `page` | `int` | رقم الصفحة |
| `status` | `string` | موروث من AlignmentEntry |
| `cer` | `float \| null` | Character Error Rate (0-1) — null لو غير قابل للقياس |
| `wer` | `float \| null` | Word Error Rate (0-1) |
| `diacritics` | `DiacriticStats \| null` | قياس التشكيل المنفصل |
| `gt_verses_count` | `int` | أبيات GT المقارنة |
| `out_verses_count` | `int` | أبيات الإخراج |
| `evaluated_verses_count` | `int` | الأبيات الفعلية المستخدمة (بعد استثناء الهلوسة) |
| `hallucination_count` | `int` | عدد أبيات الهلوسة المستثناة |

---

### DiacriticStats
قياس التشكيل — تصنيف كل حركة.

| الحقل | النوع | الوصف |
|---|---|---|
| `correct` | `int` | حركة موجودة في GT ومطابقة في الإخراج |
| `missing` | `int` | حركة موجودة في GT، مفقودة في الإخراج |
| `wrong` | `int` | حركة موجودة لكن خاطئة (فتحة بدل ضمة) |
| `extra` | `int` | حركة في الإخراج ليس لها مقابل في GT |
| `total_gt` | `int` | إجمالي حركات GT = correct+missing+wrong |
| `accuracy` | `float` | correct / total_gt (مقاييس الحركات فقط) |

**المنطق (يقرأ الحروف الأساسية وما يتبعها من combining marks):**

```
لكل حرف أساسي في GT:  [حرف][حركة?]
لكل حرف أساسي في الإخراج: [حرف][حركة?]

التطابق يتم على مستوى الحرف الأساسي:
  - حركة GT + حركة إخراج متطابقة   → correct
  - حركة GT + لا حركة              → missing
  - حركة GT + حركة مختلفة          → wrong
  - لا حركة GT + حركة إخراج        → extra
```

**الترتيب مهم**: `accuracy` = correct/total_gt يقيس **استرجاع التشكيل** (recall)، وليس الدقة الكاملة — لأن الحركات الزائدة (extra) تُشوّش لكنها لا تقلل accuracy. هذا مقصود: الهدف الأول هو **الحفاظ على تشكيل GT**.

---

### CorpusReport
التقرير الإجمالي للمخطوط.

| الحقل | النوع | الوصف |
|---|---|---|
| `document` | `string` | اسم الوثيقة |
| `generated_at` | `string` | ISO timestamp |
| `gt_source` | `string` | المسار للـ GT المستخدم |
| `pages_total` | `int` | إجمالي الصفحات (113) |
| `pages_evaluated` | `int` | الصفحات ذات قياس فعلي |
| `pages_out_of_scope` | `int` | خارج GT |
| `pages_prose_only` | `int` | نثرية |
| `verses_total` | `int` | إجمالي أبيات الإخراج |
| `verses_evaluated` | `int` | أبيات بعد استثناء الهلوسة |
| `weighted_cer` | `float` | CER المرجَّح بالحروف لكامل المنطقة المقيسة |
| `weighted_wer` | `float` | WER المرجَّح |
| `diacritics_total` | `DiacriticStats` | إجمالي التشكيل |
| `hallucination_total` | `int` | إجمالي أبيات الهلوسة |
| `worst_pages` | `list[PageQuality]` | أسوأ 10 صفحات |
| `best_pages` | `list[PageQuality]` | أفضل 5 (للأ参考) |
| `confidence_distribution` | `dict` | {matched, low_confidence, ...} |

---

## Validation Rules

1. **FR-002 (التسلسل)**: لأي صفحتين i < j بـ status=matched: `entry[i].gt_end < entry[j].gt_start`. يُفحص في اختبارات الوحدة.
2. **FR-009 (القراءة فقط)**: بعد كل تشغيل، sha256 لكل ملفات `raw_text/` و`ground_truth/` يجب أن تتطابق مع ما قبل التشغيل.
3. **FR-013 (إعادة الإنتاج)**: نفس المدخلات → نفس الأرقام. المواءمة خالية من العشوائية (no RNG، no dict ordering dependence — التكرار على list مرتبة).
4. **FR-008 (التطبيع)**: `normalize_text()` المستخدم **هو نفسه** في `evaluate_cer.py` الموجود (نفس الدالة، استيراد مباشر) — لا نسخة ثانية.

---

## State Transitions

```
[صفحة إخراج]
    │
    ├─ لا أبيات (' ... ')?  ──نعم──→ prose_only (أو empty_page لو لا أسطر)
    │                              │
    ├─ خارج نطاق GT (ص<23 أو >35)  ──→ out_of_gt_scope
    │                              │
    └─ مواءمة (نافذة + anchor أوسط)
            │
            ├─ confidence ≥ 0.7 ──→ matched ──→ PageQuality (CER+WER+تشكيل)
            ├─ 0.3 ≤ conf < 0.7 ─→ low_confidence ──→ PageQuality (مع تحذير)
            └─ conf < 0.3 ──────→ unmatched ──→ PageQuality(cer=null)
```

---

## Output Artifacts (الطبقة الجديدة)

| الملف | المحتوى | القاعدة |
|---|---|---|
| `data/evaluation_reports/006/alignment.json` | `list[AlignmentEntry]` | جديد — لا يلمس شيء |
| `data/evaluation_reports/006/quality_report.json` | `CorpusReport` | جديد |
| `data/evaluation_reports/006/quality_report.txt` | تقرير نصي مقروء | جديد |
| `data/evaluation_reports/006/heatmap.txt` | ASCII heatmap لتوزيع CER | جديد |

**كل المسارات في طبقة منفصلة** (Constitution IV — Raw Evidence Immutability). لا كتابة فوق `raw_text/` أو `ground_truth/` أو `corrected_text/`.
