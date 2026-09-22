# Feature Specification: تصحيح الميموري وتنظيف البقايا المتقادمة (Memory Correction & Stale-Artifact Cleanup)

**Feature Branch**: `007-memory-correction-cleanup`

**Created**: 2026-09-18

**Status**: Draft

**Input**: المرحلة 2 من خطة الجودة: بعد spec 006 أصبح لدينا مرجع رقمي حقيقي (CER 25.0% / WER 59.9%)، لكن طبقة الميموري لا تزال تحمل معلومات متقادمة بشكل **ضار**، وبقايا كودية/تهيئة ميتة تعيق الفهم. هذا الـ spec يصحّح الميموري ويحذف الميت، بلا أي تأثير على ممر الإنتاج.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - تصحيح CLAUDE.md الضار (Priority: P1)

`docs/CLAUDE.md` يحمل **تعليمات نشطة مضادة للهيكل الحالي**: «المشروع مسطّح (FLAT)... تم حذف src/... لا تُعِد إنشاء src/ أو إعادة sys.path hacks» — بينما المشروع أُعيد هيكلته إلى حزمة `src/pipeline/` (commit `2587731`) و`main.py` يستورد `src.pipeline.*`. كما يقول إن `config/` محذوف (موجود)، و`baseline/` لقطة ثابتة (غير موجود)، وأرضية GT **فارغة** (620 بيت كاملة موجودة). أي وكيل جديد يقرأ هذا الملف سيُمنع من الهيكل الصحيح.

**Why this priority**: هذا خطأ **نشط في التوجيه**، ليس مجرد إزعاج — يتناقض مباشرةً مع AGENTS.md §5 ومع الكود الفعلي. يبدأ به لأنه الأكثر قدرة على تضليل التنفيذ اللاحق (specs 008+).

**Independent Test**: يُقرأ `CLAUDE.md` وحده ويتطابق كل ادعاء معماري/حالة فيه مع الكود الفعلي و AGENTS.md — بلا تناقض واحد.

**Acceptance Scenarios**:

1. **Given** قراءة `CLAUDE.md`، **When** التحقق من كل ادعاء بنية (layout/config/imports)، **Then** لا يوجد ادعاء يقول «مسطّح» أو «لا تُعد إنشاء src/» أو «config/ محذوف».
2. **Given** قراءة `CLAUDE.md`، **When** البحث عن أرقام الجودة، **Then** المرجع الرقمي الأول موجود (CER 25.0% / WER 59.9% / تشكيل 82.0%) مع وسم «مسافة إلى benchmark عمل».
3. **Given** تعارض محتمل بين CLAUDE.md و AGENTS.md، **When** قراءة الملفين، **Then** CLAUDE.md يحيل صراحةً إلى AGENTS.md كالعقد الحاكم (لا يكرر تفاصيل قابلة للانحراف).
4. **Given** ملف CLAUDE.md الجديد، **When** تشغيل `main.py --start 24 --end 26`، **Then** exit 0 و`raw_text/` غير ملموس (REVIEW_ONLY).

---

### User Story 2 - حذف التهيئة الميتة في prompts.yaml (Priority: P2)

`config/prompts.yaml` يحوي 3 مفاتيح عليا: `ocr_prompts` و`analysis_prompts` و`review_prompts`. فحص مباشر: **لا سطر كود واحد** في `src/` أو `main.py` أو `tests/` يقرأ `ocr_prompts` أو `review_prompts`. الوحيد المستخدم = `analysis_prompts.text_correction` (في `src/pipeline/output/review_manuscript.py:141`). ملاحظة AGENTS.md §5 تقول إن «`analysis.*`/`review.*` غير مسكونة» — وهي **نفسها غير دقيقة** (analysis_prompts.text_correction مستخدم).

**Why this priority**: تهيئة ميتة تُكلف قراءةً وفهمًا، وتُوهِم وجود سلوك (prompts للـ OCR والمراجعة) غير موجود. أولوية متوسطة لأنها لا تضلّل نشطًا كالـ US1.

**Independent Test**: بعد الحذف: `review_manuscript.py` يستخرج prompt التصحيح بنجاح (استدعاء مباشر)، وكل الاختبارات تمر، والمفاتيح الميتة اختفت.

**Acceptance Scenarios**:

1. **Given** `grep -rn "ocr_prompts\|review_prompts" src/ main.py tests/`، **When** تنفيذه، **Then** النتيجة فارغة (تأكيد نهائي قبل الحذف).
2. **Given** حذف المفتاحين، **When** قراءة `config/prompts.yaml`، **Then** تبقى `analysis_prompts` فقط وبها `text_correction`.
3. **Given** الكود، **When** تشغيل `review_manuscript.py` حتى نقطة تحميل الـ prompt، **Then** `analysis_prompts.text_correction` يُحمَّل بنجاح بلا استثناء.
4. **Given** AGENTS.md §5، **When** قراءة ملاحظة «الأنماط غير المسكونة»، **Then** صُحِّحت لتقول بدقة: `ocr_prompts`/`review_prompts` محذوفة، والوحيد المستخدم `analysis_prompts.text_correction`.

---

### User Story 3 - تنظيف البقايا الكودية المتقادمة (Priority: P2)

`__pycache__/` في جذر المشروع يحتوي `.pyc` لـ **وحدات لم تعد موجودة في الجذر** (`input_handler`, `ocr_engine`, `output_generator`, `page_layout_detector`, `pdf_text_extractor`, `evaluate_cer`, `benchmark_cer_wer`, `clean_ground_truth`, `main`...) — بقايا حقبة المسطّح قبل إعادة الهيكلة. ملوّثة ومضللة (محاولة استيرادها تفشل/تتوهم). `__pycache__/` مُدرَج أصلًا في `.gitignore` (سطر 13) فهي غير متتبَّعة.

**Why this priority**: نظافة مساحة العمل؛ منخفضة المخاطر لأنها ملفات غير متتبَّعة (gitignored) قابلة لإعادة التوليد آليًا.

**Independent Test**: بعد الحذف: `find . -name __pycache__ -not -path "./myenv/*"` فارغ، والاختبارات تمر (تُعاد توليدها في tests/__pycache__ فورًا — وهذا متوقع وصحيح).

**Acceptance Scenarios**:

1. **Given** الجذر، **When** `ls __pycache__/`، **Then** لا يوجد (قبل الحذف) → فارغ (بعده).
2. **Given** الحذف، **When** تشغيل الاختبارات، **Then** تمر كلها (تُعاد توليد pycache جديدة بشكل طبيعي وصحيح).
3. **Given** `git status`، **When** فحصه، **Then** لا يظهر أي `__pycache__` كتغيير (مؤكد أنه gitignored).

---

### User Story 4 - توثيق قرارات التأجيل (Priority: P3)

ثلاثة عناصر اكتُشفت وبقيت **بدون قرار موثَّق**:
- `data/archive/debug_page107_resolved.zip` (1MB) — أرشيف تصحيح صفحة 107 من مرحلة ink-density.
- `config/opencode.json` يظهر محذوفًا في `git status` (هجرة opencode إلى `~/.config/opencode/` + `.opencode/`).
- `docs/PROJECT_SUMMARY.md` — لقطة 2026-09-06 موسومة الآن كـ«تاريخية» (spec 006)، لكن هل يكفي الوسم أم تستوجب إعادة كتابة؟

**Why this priority**: قرار توثيقي صرف — يمنع إعادة اكتشاف هذه العناصر في كل جلسة. القرار الموصى به (quality-first + آمن): **تأجيل الكل مع توثيق صريح** في AGENTS.md: الأرشيف يُبقى (دليل تاريخي، حذفه لا يفيد)، `config/opencode.json` شأن opencode خارج ممر المشروع (يُترك كما هو)، PROJECT_SUMMARY يكفيه وسم «تاريخية» (إعادة كتابة لقطة موسوعية = جهد كبير مقابل قيمة منخفضة، والميموري الحاكم الآن AGENTS.md).

**Independent Test**: يوجد موضع واحد في AGENTS.md يفصل هذه القرارات الثلاثة بصراحة، فلا تُعاد اكتشافها.

**Acceptance Scenarios**:

1. **Given** AGENTS.md، **When** البحث عن «data/archive»، **Then** يوجد سطر قرار واضح (يُبقى/تاريخي).
2. **Given** AGENTS.md، **When** البحث عن «config/opencode.json»، **Then** يوجد سطر قرار (خارج النطاق/شأن opencode).
3. **Given** AGENTS.md، **When** البحث عن «PROJECT_SUMMARY»، **Then** يوجد سطر قرار (تاريخية + الميموري الحاكم).

---

### User Story 5 - تدقيق الاتساق النهائي + التحقق الكامل (Priority: P1)

بعد كل التصحيحات: تدقيق شامل لكل ادعاء معماري/حالة في الميموري (AGENTS.md + CLAUDE.md) مقابل الكود الفعلي، ثم التحقق الكامل: py_compile، كل الاختبارات، ركض `main.py`، ثبات sha256 للأدلة، لا أسرار.

**Why this priority**: بدونها لا يُعتمد شيء مما سبق — هذا هو التعريف بـ«انتهى» لهذا الـ spec.

**Independent Test**: تقرير تدقيق منظم (كل سطر = ادعاء ← مصدره ← مطابق/لا) + الاختبارات الكاملة تمر.

**Acceptance Scenarios**:

1. **Given** تدقيق الاتساق، **When** تنفيذه، **Then** ينتج جدول ادعاءات كلها «مطابق» (أي انحراف يُصحَّح في نفس الـ spec).
2. **Given** التغييرات كلها، **When** `py_compile` + الاختبارات (129+)، **Then** كلها OK.
3. **Given** ممر الإنتاج، **When** `main.py --start 24 --end 26`، **Then** exit 0.
4. **Given** الأدلة، **When** sha256 لـ `raw_text/` + `ground_truth/`، **Then** مطابق للقيمة المرجعية (91b3f61101170b233619).
5. **Given** المخرجات الجديدة، **When** فحص الأسرار، **Then** لا توجد مفاتيح.

---

## Requirements *(mandatory)*

### Functional Requirements

**FR-001**: CLAUDE.md يُعاد كتابته بحيث: (أ) لا يحوي أي ادعاء «مسطّح/لا تُعد إنشاء src/»، (ب) يصف `src/pipeline/` و`config/` كما هما، (ج) يحيل إلى AGENTS.md كعقد حاكم، (د) يحمل المرجع الرقمي الأول مع وسم «مسافة إلى benchmark عمل».

**FR-002**: `config/prompts.yaml` يُحذف منه كل مفتاح ميت: `ocr_prompts` و`review_prompts` (مفاتيح عليا) + `analysis_prompts.{word_explanation,summarization,entity_extraction}` (0 مراجع). يبقى **`analysis_prompts.text_correction` فقط**.

**FR-003**: قبل الحذف: `grep -rn "ocr_prompts\|review_prompts" --include="*.py" src/ main.py tests/` يعطي نتيجة فارغة (تأكيد ميكانيكي، لا افتراض).

**FR-004**: AGENTS.md §5 تُصحَّح ملاحظة الأنماط غير المستخدمة لتعكس الواقع بدقة.

**FR-005**: كل `__pycache__/` خارج `myenv/` تُحذف.

**FR-006**: AGENTS.md يُضاف إليه موضع قرار واحد موثَّد لكل من: `data/archive/`، `config/opencode.json`، `docs/PROJECT_SUMMARY.md`.

**FR-007**: تقرير تدقيق الاتساق (audit.md) يُنتج ويُحفظ داخل الـ spec directory.

**FR-008**: CHANGELOG.md يُحدَّث بدخول هذا الـ spec.

**FR-009**: الثبات: `raw_text/` + `ground_truth/` sha256 unchanged؛ كاش OCR سليم؛ `main.py` exit 0.

**FR-010**: كل الاختبارات (129+) تمر + py_compile سليم لكل الملفات المُعدَّلة.

### Non-Functional Requirements

**NFR-001 (Safety)**: كل تغييرات هذا الـ spec **REVIEW_ONLY / INFRASTRUCTURE** — لا تمس OCR أو المعالجة أو سلوك الكاش. (تصنيف التغيير حسب AGENTS.md §11.)

**NFR-002 (Reversibility)**: حذف `__pycache__` قابل لإعادة التوليد آليًا (لا فقدان معلومات). حذف مفاتيح prompts.yaml موثَّق في CHANGELOG وقابل للاسترجاع من git.

**NFR-003 (Determinism)**: لا تغيير في أي مخرج إنتاجي — نفس المدخلات تعطي نفس النتائج.

---

## Technical Design

- **CLAUDE.md**: إعادة كتابة كاملة موجزة — «السياق الأساسي + الأرقام المفتاحية + إحالة صريحة»، لا تكرار لتفاصيل AGENTS.md القابلة للانحراف. الغرض: تقليل سطح الانحراف المستقبلي (DRY على مستوى الميموري).
- **prompts.yaml**: حذف مفتاحين بـ ruamel.yaml (يحافظ على التعليقات والتنسيق)، أو حذف يدوي دقيق.
- **__pycache__**: `find . -name __pycache__ -not -path "./myenv/*" -exec rm -rf {} +` — آمن لأن myenv معزول.
- **التدقيق**: سكربت مقارنة آلي قدر الإمكان + جدول ادعاءات.

## Edge Cases

- **EC-001**: ماذا لو كان `ocr_prompts`/`review_prompts` مستخدمَين عبر تحميل ديناميكي (مثل `prompts.get(name)` بسلسلة محسوبة)؟ — فحصنا grep للاسمين الحرفيين وسمات التحميل؛ إن ظهر استخدام ديناميكي غير معروف، FR-003 يرفض الحذف.
- **EC-002**: `review_manuscript.py` قد يتعطل إن انعدم `text_correction` — لن نحذفه (نحذف المفتاحين الآخرين فقط)؛ FR-002 يضمن بقاءه.
- **EC-003**: حذف `__pycache__` أثناء تشغيل اختبارات قد يسبب تعارضًا — يُنفَّذ قبل التحقق، لا أثنائه.
- **EC-004**: CLAUDE.md مطلوب كملف "لصق في جلسات Claude" — يجب أن يبقى قائمًا بذاته (self-contained) كفاية لجلسة جديدة بلا AGENTS.md. التوتر بين "self-contained" و"لا تكرار" يُحل: الأرقام + القواعد الصلبة فقط + إحالة.
- **EC-005**: `.claude/skills/clean-code-guard` هو **symlink** إلى `../../.agents/skills/clean-code-guard` (تحقق مباشر) — **ليس تكرارًا**، لا يُحذف. يُوثَّق لمنع إعادة الاكتشاف.

---

## Success Criteria

- **SC-001**: CLAUDE.md خالٍ من «FLAT»/«لا تُعد إنشاء src/»/«config/ deleted»/«GT EMPTY» — وكلها تظهر كـ«غير صحيح» إن فُرضت.
- **SC-002**: `config/prompts.yaml` = `analysis_prompts` فقط.
- **SC-003**: لا `__pycache__` خارج myenv.
- **SC-004**: AGENTS.md يحوي قرارات التأجيل الثلاثة + ملاحظة §5 المصحَّحة.
- **SC-005**: audit.md موجود وكل ادعاءاته «مطابق».
- **SC-006**: 129+ اختبار OK + py_compile + main.py exit 0 + sha256 ثابت.
- **SC-007**: CHANGELOG محدَّث.
