# Quickstart: Ground-Truth Alignment & CER/WER Measurement

**Branch**: `006-ground-truth-alignment-cer` | **Date**: 2026-09-17

> دليل التحقق من أن الميزة تعمل من البداية للنهاية. لا يحتوي على كود تنفيذ — التنفيذ في `tasks.md`.

---

## المتطلبات المسبقة

1. البيئة: `myenv/bin/python` (Python 3.11.16) — ممنوع Python النظام (§9).
2. `jiwer 4.0.0` مثبت في venv المشروع (موجود).
3. المدخلات موجودة:
   - `data/output/عمود النسب نسخة 2/raw_text/` (113 صفحة).
   - `data/ground_truth/عمود النسب/عمود_النسب.clean.md` (620 بيت).
4. **لا GPU، لا شبكة مطلوبة** — هذا spec قياس فقط (REVIEW_ONLY).

---

## الخطوة 1 — تشغيل المواءمة

```bash
myenv/bin/python -m src.pipeline.evaluation.align_ground_truth \
    --document "عمود النسب نسخة 2" \
    --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md"
```

**النتيجة المتوقعة:**
- Exit code: `0` (أو `2` مع تحذير أن GT لا تغطي كل الصفحات — **متوقع وصحيح**).
- STDOUT: سطر لكل صفحة بحالتها وثقتها.
- يُنتَج: `data/evaluation_reports/006/alignment.json`.

**التحقق:**
```bash
# ص23 يجب أن تبدأ عند GT#1
myenv/bin/python -c "
import json
a = json.load(open('data/evaluation_reports/006/alignment.json'))
for e in a:
    if e['page'] == 23:
        print('ص23:', e['status'], 'gt_start =', e['gt_start'])
        assert e['gt_start'] == 1, 'فشل: ص23 يجب أن تبدأ عند GT#1'
        print('✔ SC-001 منطقي')
"
```

**النتيجة المتوقعة**: `ص23: matched gt_start = 1` ثم `✔ SC-001 منطقي`.

---

## الخطوة 2 — القياس الكامل

```bash
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer \
    --document "عمود النسب نسخة 2" \
    --alignment "data/evaluation_reports/006/alignment.json" \
    --diacritics-metrics \
    --heatmap
```

**النتيجة المتوقعة:**
- Exit code: `2` (تحذير: 90 صفحة خارج نطاق GT — **متوقع وصحيح**، أنظر research.md R2).
- يُنتَج:
  - `quality_report.json` (CorpusReport كامل).
  - `quality_report.txt` (مقروء).
  - `heatmap.txt` (ASCII).

**التحقق من الأرقام (المرجع الرقمي الأول):**
```bash
myenv/bin/python -c "
import json
r = json.load(open('data/evaluation_reports/006/quality_report.json'))
print('صفحات قِيست:', r['pages_evaluated'])
print('CER المرجَّح: %.1f%%' % (r['weighted_cer'] * 100))
print('WER المرجَّح: %.1f%%' % (r['weighted_wer'] * 100))
print('تشكيل صحيح: %.1f%%' % (r['diacritics_total']['accuracy'] * 100))
print('أبيات هلوسة:', r['hallucination_total'])
# النطاق الصحيح (research.md R5):
assert 8 < r['weighted_cer']*100 < 25, 'CER خارج النطاق المتوقع'
assert r['pages_evaluated'] == 13, 'يجب قياس 13 صفحة (ص23-35)'
print('✔ الأرقام في النطاق المتوقع')
"
```

**النتيجة المتوقعة** (من research.md R5):
- `pages_evaluated: 13`
- `weighted_cer` بين 8% و 25% (القياس الأولي على ص23-26 كان 13-18%).
- `weighted_wer` بين 40% و 60%.
- `diacritics accuracy` بين 75% و 90% (~17% فقد).
- `hallucination_total: 3` (ص27).

---

## الخطوة 3 — التحقق من عدم المساس (Safety)

هذا **أهم** تحقق — يثبت Constitution IV (Raw Evidence Immutability).

```bash
# سجل البصمات قبل/بعد (يجب أن تتطابق)
before=$(find data/output data/ground_truth -name '*.txt' -exec sha256sum {} \; | sort | sha256sum)
# (أعد تشغيل الخطوتين 1-2)
after=$(find data/output data/ground_truth -name '*.txt' -exec sha256sum {} \; | sort | sha256sum)
test "$before" = "$after" && echo "✔ SC-005: raw_text/ و ground_truth/ لم يُمَسَّا" || echo "✗ فشل: تم التعديل!"
```

أو ببساطة:
```bash
git status --short data/output data/ground_truth
# يجب أن لا يظهر أي تعديل
```

---

## الخطوة 4 — الاختبارات

```bash
# الاختبارات الجديدة
myenv/bin/python -m unittest tests.test_gt_alignment -v
myenv/bin/python -m unittest tests.test_diacritic_metrics -v

# الانحدار (لا يجب أن تتأثر)
myenv/bin/python -m unittest tests.test_cer_normalization tests.test_escalation_policy tests.test_output_generator -v

# py_compile
myenv/bin/python -m py_compile src/pipeline/evaluation/align_ground_truth.py \
    src/pipeline/evaluation/evaluate_cer.py \
    tests/test_gt_alignment.py tests/test_diacritic_metrics.py
```

**النتيجة المتوقعة**: كلها OK. `test_cer_normalization` **يجب** أن يمر دون أي تعديل (FR-008: التطبيع الموحَّد).

---

## الخطوة 5 — تصحيح AGENTS.md (SC-008)

بعد الحصول على الأرقام، تُحدَّث AGENTS.md:

```bash
# تحقق من تصحيح §8
grep -c "GT ناقصة" docs/AGENTS.md    # يجب = 0
grep -c "620 بيت" docs/AGENTS.md      # يجب ≥ 1
```

---

## سيناريوهات التحقق (Acceptance)

| السيناريو | الأمر | النتيجة |
|---|---|---|
| SC-001: مواءمة ص24 | شغّل الخطوة 1 | `ص24: gt_start=13` |
| SC-002: CER كامل | الخطوة 2 | رقم واحد قابل لإعادة الإنتاج |
| SC-003: التوزيع | `heatmap.txt` | تصنيف كل صفحة |
| SC-004: التشكيل | الخطوة 2 | ~81% accuracy |
| SC-005: عدم المساس | الخطوة 3 | sha256 متطابق |
| SC-006: الانحدار | الخطوة 4 | 55+ اختبار OK |
| SC-008: الميموري | الخطوة 5 | 0 عبارة "ناقصة" |
