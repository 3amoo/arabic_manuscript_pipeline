# Tasks — spec 007

- [x] T001 — فرض FR-003: `grep -rn "ocr_prompts\|review_prompts" --include="*.py" src/ main.py tests/` (يجب = فارغ)
- [x] T002 — فرض FR-002: حذف `ocr_prompts` + `review_prompts` من `config/prompts.yaml` (إبقاء `analysis_prompts` + تعليقاتها)
- [x] T003 — تحقق: `myenv/bin/python -c "import ruamel.yaml ..."` يحمّل `analysis_prompts.text_correction` بنجاح
- [x] T004 — فرض FR-001: إعادة كتابة `docs/CLAUDE.md` وفق R8
- [x] T005 — فرض SC-001: grep CLAUDE.md للعبارات المحظورة → صفر
- [x] T006 — فرض FR-004: تصحيح ملاحظة AGENTS.md §5 (analysis_prompts.text_correction مستخدم)
- [x] T007 — فرض FR-005: `find . -name __pycache__ -not -path "./myenv/*" -exec rm -rf {} +`
- [x] T008 — فرض SC-003: `find . -name __pycache__ -not -path "./myenv/*"` = فارغ + git status نظيف
- [x] T009 — فرض FR-006: إضافة قرارات التأجيل الثلاثة + وثائق symlink في AGENTS.md
- [x] T010 — فرض FR-007: كتابة `audit.md` (جدول ادعاءات: المصدر ← الواقع ← مطابق)
- [x] T011 — فرض FR-008: تحديث `docs/CHANGELOG.md`
- [x] T012 — فرض FR-010: py_compile لكل الملفات المُعدَّلة
- [x] T013 — فرض FR-010: ركض كل الاختبارات (129+) → OK
- [x] T014 — فرض FR-009: main.py `--start 24 --end 26` exit 0
- [x] T015 — فرض FR-009: sha256 raw_text + ground_truth = 91b3f61101170b233619 + cache سليم
- [x] T016 — فرض FR-009: فحص الأسرار في كل مخرج جديد
- [x] T017 — تعليم كل مهام tasks.md مكتملة + تحديث checklist
