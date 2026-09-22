# Plan — spec 007 (تصحيح الميموري وتنظيف البقايا)

**Constitution Check (PASS)** — هذا الـ spec يخدم مباشرةً:
- **§VI (Distance to a working benchmark)**: يحمي المرجع الرقمي First (CER 25.0%) من التشويش بوثائق منافسة تحمل أرقامًا/ادعاءات متقادمة.
- **§IV (Evidence over claims)**: كل تصحيح مبني على فحص ميكانيكي مباشر (R1–R10)، وكل قرار مُوثَّم بقابلية إعادة الفحص.
- **§VIII (Memory as code)**: الميموري (AGENTS.md/CLAUDE.md) جزء من المنتج — انحرافها = عيب. هذا الـ spec يعالج 5 ادعاءات عالية الخطورة (R2).
- **§I (Faithful Reconstruction)**: غير ممسوس — لا تغيير على نص الإخراج.
- **§II (Safety)**: لا تأثير على `raw_text/`/`ground_truth/`/الكاش (FR-009).

**النطاق**: REVIEW_ONLY + INFRASTRUCTURE فقط (R9). لا قياس CER جديد مطلوب (لم يتغير سلوك OCR).

---

## Phases

### Phase 1 — CLAUDE.md (US1) — P1
1. إعادة كتابة `docs/CLAUDE.md` كاملًا وفق R8 (هوية + أرقام + قواعد صلبة + بنية صحيحة + إحالة).
2. تحقق SC-001: grep للكلمات المحظورة → صفر.

### Phase 2 — التهيئة الميتة (US2) — P2
3. FR-003: تأكيد ميكانيكي نهائي أن `ocr_prompts`/`review_prompts` غير مستخدمين.
4. FR-002: حذف المفتاحين من `config/prompts.yaml` (مع الحفاظ على `analysis_prompts`).
5. FR-004: تصحيح ملاحظة §5 في AGENTS.md.
6. SC-002 + scenario 3: تحميل `analysis_prompts.text_correction` ناجح.

### Phase 3 — البقايا الكودية (US3) — P2
7. FR-005: حذف كل `__pycache__/` خارج myenv.
8. SC-003 + git status نظيف.

### Phase 4 — قرارات التأجيل (US4) — P3
9. FR-006: إضافة موضع القرارات الثلاثة في AGENTS.md (archive/opencode.json/PROJECT_SUMMARY + symlink R5).

### Phase 5 — التدقيق والتحقق (US5) — P1
10. FR-007: audit.md — جدول ادعاءات (المصدر ← الواقع ← مطابق).
11. FR-008: CHANGELOG.
12. FR-009 + FR-010 + SC-006: py_compile + 129+ اختبار + main.py exit 0 + sha256 + لا أسرار.

---

## Risk Assessment

| الخطر | الاحتمال | الأثر | التخفيف |
|---|---|---|---|
| استخدام ديناميكي غير مرئي لـ prompts الميتة | منخفض | متوسط | FR-003 grep ميكانيكي + smoke استيراد review_manuscript |
| حذف __pycache__ أثناء ركض | منخفض | منخفض | تنفذ قبل التحقق |
| CLAUDE.md يفقد سياقًا ضروريًا | متوسط | متوسط | R8: self-contained + سيناريو 1 يفحص كل ادعاء |
| انحراف جديد في AGENTS.md أثناء التصحيح | منخفض | متوسط | audit.md النهائي يفحص الميموري كلها |

**Reversibility**: كل الحذوفات قابلة للاسترجاع (git / regeneration) — NFR-002.
