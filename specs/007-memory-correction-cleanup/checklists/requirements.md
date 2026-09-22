# Requirements Checklist — spec 007

> كل مطلب = سطر قابل للفحص الآلي/البصري. علامة ✓ تُوضع بعد التحقق فقط.

## FR — Functional Requirements

- [x] FR-001: CLAUDE.md مُعاد كتابته (أ: لا «FLAT»/«src/ deleted»، ب: يصف src/pipeline/ + config/، ج: إحالة إلى AGENTS.md، د: المرجع الرقمي الأول + وسم «مسافة إلى benchmark عمل»)
- [x] FR-002: prompts.yaml = analysis_prompts فقط
- [x] FR-003: grep الميكانيكي للتأكيد قبل الحذف (نتيجة فارغة)
- [x] FR-004: AGENTS.md §5 ملاحظة الأنماط مصحَّحة
- [x] FR-005: كل __pycache__/ خارج myenv محذوفة
- [x] FR-006: AGENTS.md يحوي قرارات: data/archive/ + config/opencode.json + PROJECT_SUMMARY + symlink
- [x] FR-007: audit.md موجود وكل ادعاءاته «مطابق»
- [x] FR-008: CHANGELOG محدَّث
- [x] FR-009: sha256 raw_text/ + ground_truth/ = 91b3f61101170b233619؛ cache سليم؛ main.py exit 0
- [x] FR-010: 129+ اختبار OK + py_compile سليم

## NFR — Non-Functional

- [x] NFR-001: REVIEW_ONLY/INFRASTRUCTURE — لا مسّ لـ OCR/preprocessing/الكاش
- [x] NFR-002: قابلية الاسترجاع (git / regeneration)
- [x] NFR-003: حتمية — لا تغيير في مخرج إنتاجي

## SC — Success Criteria

- [x] SC-001: CLAUDE.md خالٍ من العبارات المحظورة
- [x] SC-002: prompts.yaml = analysis_prompts فقط
- [x] SC-003: لا __pycache__ خارج myenv
- [x] SC-004: AGENTS.md = 3 قرارات تأجيل + §5 مصحَّحة
- [x] SC-005: audit.md كلها «مطابق»
- [x] SC-006: اختبارات + py_compile + main.py + sha256
- [x] SC-007: CHANGELOG محدَّث
