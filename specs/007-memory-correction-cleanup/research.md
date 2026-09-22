# Research — spec 007 (تصحيح الميموري وتنظيف البقايا)

> كل سطر R\* أدناه **مُقاس/مُتحقَّق مباشرةً** (ليس افتراضًا). الأوامر في الأسفل قابلة لإعادة التشغيل.

## R1 — CLAUDE.md يحمل تعليمات نشاط مضادة للهيكل الحالي

**الفحص**: قراءة `docs/CLAUDE.md` سطر 7:

> "The project is FLAT layout: ALL modules live at the project root beside main.py ... The src/ directory was deleted ... Do NOT recreate src/ or re-add sys.path hacks."

**الواقع** (commit `2587731` «Refactor: reorganize flat project into src/pipeline/ package structure»):
```
src/pipeline/ingestion/{input_handler,pdf_text_extractor}.py
src/pipeline/preprocessing/{preprocessing,page_layout_detector,segment_text_rows}.py
src/pipeline/ocr/{ocr_engine,vision_fallback,surya_line_detector,...}.py
src/pipeline/output/{output_generator,review_manuscript}.py
src/pipeline/correction/{text_correction_engine,morphological_verifier}.py
src/pipeline/evaluation/{align_ground_truth,evaluate_cer}.py
```
`main.py` يستورد `from src.pipeline.ingestion.input_handler import ...` (تأكد §5 في AGENTS.md).

**الأثر**: أي وكيل جديد يقرأ CLAUDE.md **يُنهى عن الهيكل الصحي**. هذا تناقض نشط مع AGENTS.md §5 الذي يقول صراحةً «ممنوع إعادة `sys.path.insert`» (هذا الجزء سليم) لكن CLAUDE.md يوسّعه إلى «لا تُعد إنشاء src/» (خطأ).

**الاستنتاج**: CLAUDE.md ليس متقادمًا فقط — هو **مضلِّل نشط**. الأولوية القصوى.

## R2 — جرد تناقضات CLAUDE.md الكاملة

| السطر في CLAUDE.md | الادعاء | الواقع | الخطر |
|---|---|---|---|
| 7 | "FLAT layout... src/ deleted" | `src/pipeline/` موجود وفعّال | **عالي** — يمنع الهيكل الصحيح |
| 7 | "config/ is gone" | `config/settings.yaml` + `config/prompts.yaml` موجودان | **عالي** — يضلل مسارات الإعداد |
| 11 | "baseline/ — immutable quality snapshot ... output_as_was/" | `baseline/` **غير موجود إطلاقًا** | متوسط — مرجع وهمي |
| 11, 45, 54 | "baseline/ is immutable evidence" | غير موجود | متوسط |
| 30 | "the manual ground-truth dataset is EMPTY" | 620 بيت كاملة في `عمود_النسب.clean.md` (spec 006) | **عالي** — ينفي وجود القياس |
| 34 | "Pages 24-26 currently rendered+placeholder-only" | GT كاملة 620 بيت على مستوى الوثيقة | متوسط |
| 20 | "1-5 vision escalations per run" | صحيح تقريبًا (0 في آخر ركض cache-hit) | منخفض |
| 26 | "There is no formal test suite configured" | 129+ اختبار stdlib unittest يعمل | متوسط |
| 41 | "Layout is FLAT... never re-introduce src/" | مضاد للواقع | **عالي** |
| 45, 54 | "baseline/ is immutable evidence" | غير موجود | متوسط |
| 53 | "Config: settings.yaml, prompts.yaml at the project root (config/ deleted)" | في `config/` | متوسط |

**العدد**: 5 ادعاءات **عالية الخطورة**، 5 متوسطة، 2 منخفضة.

## R3 — prompts.yaml: مفتاحان ميتان، واحد حي

**الفحص الميكانيكي**:
```
$ grep -rn "ocr_prompts\|review_prompts" --include="*.py" src/ main.py tests/ | grep -v __pycache__
(فارغ — لا شيء)
$ grep -rn "analysis_prompts" --include="*.py" src/ main.py tests/ | grep -v __pycache__
src/pipeline/output/review_manuscript.py:141:        prompts.get("analysis_prompts", {}).get("text_correction")
```

**مفاتيح prompts.yaml العليا** (ruamel): `ocr_prompts`, `analysis_prompts`, `review_prompts`.

**الاستنتاج**: `ocr_prompts` + `review_prompts` = **ميتة تمامًا**. `analysis_prompts.text_correction` = الوحيد الحي. لا تحميل ديناميكي بالسلسلة المحسوبة ظاهر (الاسم حرفي في `.get()`).

**ملاحظة على AGENTS.md §5**: تقول «أنماط `analysis.*`/`review.*` غير مسكونة من الكود» — **نصفها خطأ**: `analysis_prompts.text_correction` مسكون. تُصحَّح في FR-004.

## R4 — __pycache__ الجذر = بقايا حقبة المسطّح

```
$ ls __pycache__/
benchmark_cer_wer.cpython-311.pyc     ocr_cache.cpython-311.pyc
clean_ground_truth.cpython-311.pyc    ocr_engine.cpython-311.pyc
evaluate_cer.cpython-311.pyc          output_generator.cpython-311.pyc
input_handler.cpython-311.pyc         page_layout_detector.cpython-311.pyc
main.cpython-311.pyc                  pdf_text_extractor.cpython-311.pyc
```
كل هذه الوحدات **لا وجود لها في الجذر الآن** (انتقلت إلى `src/pipeline/*/`). هي bytecode متقادم لا يُستورد (Python لا يحمّل pyc من `__pycache__` إلا لو طابق مسار المصدر).

**التحقق من العزل**: `.gitignore` سطر 13 = `__pycache__/` → **غير متتبَّعة**، حذفها لا يُنتج تغييرًا في git. آمن تمامًا. `myenv/` يُعزَل في أمر الحذف (يحوي venv كامل).

## R5 — .claude/skills/clean-code-guard هو symlink وليس تكرارًا

```
$ ls -la .claude/skills/clean-code-guard
lrwxrwxrwx clean-code-guard -> ../../.agents/skills/clean-code-guard
$ diff -rq .agents/skills/clean-code-guard .claude/skills/clean-code-guard
(فارغ)
```
**الاستنتاج**: تثبيت skill موحَّد عبر symlink. **لا حذف** — كان مشتبهًا كتكرار في جرد سابق، والصحيح أنه symlink مقصود. يُوثَّب لمنع إعادة الاكتشاف (EC-005).

## R6 — data/archive/ و config/opencode.json: قرار التأجيل

- `data/archive/debug_page107_resolved.zip` (1020K): أرشيف تصحيح صفحة 107 (مرحلة ink-density gate). اسمه ينص على **resolved**. حذفه لا يفيد الجودة؛ إبقاؤه كدليل تاريخي = الخيار الآمن. **يُبقى + يُوثَّق**.
- `config/opencode.json` يظهر ` D` في git status: محذوف من شجرة العمل، آخر تعديله commit `2587731`. هذا جزء من **هجرة opencode** إلى `~/.config/opencode/opencode.jsonc` + `.opencode/` (موثَّق في AGENTS.md §12 آخر بند). **شأن opencode، خارج ممر المشروع — يُترك كما هو**. لا يُسترجع ولا يُلتزم (AGENTS.md §10: التزام/دفع يحتاج طلبًا صريحًا).

## R7 — PROJECT_SUMMARY.md: الوسم يكفي

`docs/PROJECT_SUMMARY.md` = مراجعة موسوعية بتاريخ 2026-09-06 (بنية، بيانات، كل وحدة). spec 006 أضاف وسم «لقطة تاريخية... راجعها بحذر» في رأسها. **إعادة كتابتها بالكامل** = إعادة إنتاج كامل لوثيقة موسوعية (ساعات) مقابل قيمة منخفضة: الميموري الحاكم الآن AGENTS.md، والوسم صادق. **القرار: الوسم يكفي** (موثَّق في FR-006).

## R8 — مبدأ تصميم CLAUDE.md: DRY على مستوى الميموري

**التوتر**: CLAUDE.md مُصمَّم كملف «الصقني في جلسة Claude جديدة» (self-contained)، لكن كل تفصيل يُكرَّر = سطح انحراف إضافي (هذا ما حدث بالضبط: AGENTS.md تحديث وCLAUDE.md لا).

**الحل المعتمد**: CLAUDE.md الجديد يحوي **فقط**:
1. هوية المشروع + الغاية (3 أسطر).
2. **الأرقام المفتاحية** (المرجع الرقمي الأول + سطر «مسافة إلى benchmark عمل»).
3. **القواعد الصلبة الخمس** (Faithful Reconstruction، raw_text لا يُكتب فوقه، 85% rule، Vision-not-authoritative، القياس إجباري) — كلاسيكية قصيرة.
4. **البنية الحالية الصحيحة** (src/pipeline/ + config/) — فقرة واحدة لا جدولًا قابلًا للانحراف.
5. **إحالة صريحة**: «AGENTS.md هو العقد الحاكم — اقرأه. هذا الملف يحمل الأرقام والقواعد الصلبة فقط.»

النتيجة: ~40 سطر بدل 55، وصفر تكرار للتفاصيل المتقلبة (STATUS markers، roadmap،Hardware details — هذه في AGENTS.md).

## R9 — تصنيف التغيير (AGENTS.md §11)

كل تغييرات هذا الـ spec = **INFRASTRUCTURE** (py_compile + smoke على الاستيرادات) + **REVIEW_ONLY** (الوثائق). **لا OCR_BEHAVIOR / PREPROCESSING / OUTPUT_FORMAT** — لا يلزم قياس CER إضافي هنا (القياس الافتراضي لم يتغير: CER 25.0%).

## R10 — نقطة الأمان الأساسية

كل التعديلات تمس **الوثائق + التهيئة الميتة + bytecode غير متتبَّع**. لا واحدة تمس:
- `raw_text/` أو `ground_truth/` (sha256 مرجعي `91b3f61101170b233619` يجب أن يثبت).
- منطق OCR / preprocessing / الكاش.
- `main.py` أو أي وحدة إنتاج.

**التحقق الإجباري**: main.py exit 0 + 129+ اختبار + sha256 + لا أسرار (FR-009، FR-010).
