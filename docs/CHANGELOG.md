# CHANGELOG

سجل مختصر لكل تعديل بيتعمل في الكود عبر الجلسات المختلفة. الهدف: تحط الملف ده في أول أي محادثة جديدة ويبقى فاهم إيه اللي اتعمل واللي لسه لأ، من غير ما تعيد شرح كل حاجة من الصفر.

كل سطر: **الملف** — إيه اللي اتغيّر (إضافة/تعديل/حذف) وليه، باختصار شديد.

## 2026-10-11

- **مراجعة `REMAINING_WORK_PLAN.md` وثيقةً — أُصلحت خمسة أخطاء رقمية في
  الحقائق** (الأرقام القديمة كانت مكتوبة في الخطة نفسها وفي العقود):
  - **عدد الاختبارات = 393 لا 425.** `verify_all.py` يشغّل
    `python -m unittest` فوق 22 وحدة، وهو يجمع **393** اختبارًا. الـ 425
    كان عدّ `pytest --collect-only` الذي يزيد 34 دالة على مستوى الوحدة
    (كل `test_benchmark_cer_wer.py`) لا تجمعها `unittest` أبدًا. السلسلة
    البالية كاملة: 368 ← 400 ← 422 ← 425 ← **393**. صُحِّح في `AGENTS.md`
    §11 و`PROGRESS.md` و`plans/components/tests_quality.md`.
  - **ثابت الدليل = `60309548f2b265e6de11`** (318 ملفًا) لا
    `853419275001e5bbd407` (251 ملفًا) — كان لا يزال مثبَّتًا في أربعة
    مواضع رغم تحديث `verify_all.py`.
  - **عدد علامات `غير محقق` = 118 لا 136** (61 صفحة) — في خمسة مواضع.
  - **`detect_columns` لها مستهلك**: `main.py:1040` يستدعيها للقياس
    الاستقرائي، ففرضية «لا مستهلك لها» في Phase B task 11 كانت خاطئة.
  - **المرجع الرقمي الحاكم = 23.7% / 59.7% / 83.0%** على
    `vault_corrected_text/` (ما يُعيد `verify_all.py` توليده)، لا 25.9% /
    60.2% / 82.1% (spec 008 على `raw_text/` — تاريخي الآن). عُلِّم في
    `AGENTS.md` §8 و§13.
  - **رفض:** ادعاء المراجع بأن «558 سطرًا مشكَّلًا» يجب أن يكون 566 —
    تقرير الملء نفسه (`020-vault-tashkeel/fill_report.json`) يسجِّل
    `vault_lines = 558`. الرقم في الوثيقة صحيح، والمراجع مخطئ هنا.
- **خلل حقيقي اكتُشف: ثابت الـ vault ووصفتُه في الشيفرة مختلفان منذ 2026-10-02**
  (`scripts/genealogy_crossref.py` + `docs/genealogy_vault_pin.md`):
  الدالة `vault_snapshot_hash()` كانت تُرتِّب **أسماء الملفات** ثم تُغذِّي
  الهواشم في SHA-256 تسلسليًا، بينما يُرتِّب كل من `verify_all.py` وصفة
  الإنسان في الوثيقة **الأسطر** (`<hash>  <name>`). التركيبان يُنتجان
  هاشين مختلفين من نفس المحتوى (`7e92a8e6…` مقابل `a3ee7965…`)،
  والفرق قُرِر في 2026-10-02 على أنه **انزياح في الـ vault** — **وكان
  خاطئًا**: هاشات الملفات الـ11 مطابقة لللقطة المثبَّتة 2026-09-22
  حرفيًا. **الـ vault لم ينزح أبدًا.** أُصلِح التركيب لِيُرتِّب الأسطر
  (مطابقًا لِنفسه ولـ`verify_all.py`) وثُبِّت `PINNED_VAULT_HASH` على
  `a3ee7965…`، وكُتب تصحيح الانزياح في الوثيقة. هذا الخلل الصامت كان
  سيُخفي أي انزياح حقيقي قادم على أنه اختلاف تركيب.
- **الـ vault أُعيد تنظيمه خارجيًا أثناء العمل** (PARA في
  `Obsidian_v_0.2`): المسار المثبَّت اختفى، وملفان من الـ11 صارا **فارغين
  (0 بايت)**. الهواشم حُسِبت قبل إعادة التنظيم بينما كان المسار سليمًا
  فهي موثَّقة، لكن `check_vault_drift()` الآن تنام (تطبع «no markdown
  found»). **لم أُعد توجيه `DEFAULT_VAULT`** عمدًا: المحتوى نفسه تغيَّر
  فالثابت لن يطابق حتى بعد إصلاح التركيب، وإعادة التثبيت الصامت على مجموعة
  ملفات مختلفة يُعيد خلعلة الانزياح الكاذب نفسها. قرار للمستخدم.

## 2026-10-08

- **تصحيح سجل: `pdf_text_extractor.py` متقاعد — دوله غير موجودة**
  المدخلان بالأدنى (2026-09-10 «detect_pdf_type()» و2026-09-01 «ملف جديد»)
  يصفان وحدةً ودوالًا **لم تعد موجودة**. التصحيح هنا لأن القارئ كان يبحث عن
  دالة لا وجود لها (AGENTS.md §2: الكود هو الحقيقة).
  - **التحقق المباشر**: لا `detect_pdf_type`، لا `extract_direct_text`، لا
    `usable_char_ratio`، لا حد `0.85` في أي مكان من `src/`. الملف
    `src/pipeline/ingestion/pdf_text_extractor.py` حُذف في commit `a3fcdc3`.
  - **السبب (موثَّق في `input_handler.py` `_load_pdf` + spec 018/021)**: الـ
    ToUnicode CMap مكسور فيُنتج عربيًا well-formed لكنه **مُبدَّل المواضع**
    (كل كلمة anagram صحيحة: `اهلل`↔`الله`) فيجتاز أي فحص نسبة. `poppler`
    يُعيد الفساد نفسه.
  - **السلوك الفعلي**: كل صفحة PDF دائمًا render → preprocess → layout →
    OCR، و`direct_text` دائمًا `None` (يُحتفظ بالمفتاح صراحةً لتوحيد شكل
    قاموس الصفحة).
  - **الخَلَف**: `tounicode_repair.py` (spec 021) — cross-check-only لكتاب
    `لمعة النسب` تحديدًا، يكتب في طبقة `repaired_text/` منفصلة، **ليس
    بديلًا عن OCR**.
  - صُحِّحت كذلك AGENTS.md §3 (صفوف Direct Text / التوجيه per-page /
    detect_pdf_type → **retired**) و§4.4 و§4.5 و§5 (ممر الإنتاج).

- **`plans/REMAINING_WORK_PLAN.md` Phase A — دمج النطاقات المتجاورة:
  مقيسة صفرية الأثر، لا كود شُحن (2026-10-08)**
  آخر رافعة دقة متبقية في المشروع. نُفِّذت في `segment_text_rows.py`
  (نطاقات متجاورة + نسبة ارتفاع كبيرة، مع حارزَي rule/verse) وقِيسَت
  مُزاوجًا في الذاكرة على 51 صفحة: **القاعدة أطلقت على زوج واحد في 51
  صفحة** (ص32)، وتغيَّر سطرها `اسن` → `سب الني` (كلاهما خطأ، والـ GT لا
  يسجِّل العنوان أصلًا)، و**كل المقاييس متطابقة للمنزلة 16** (CER 23.7%،
  WER 59.8%، تشكيل 83.1%؛ CER ص32 = 0.3410493827160494 للذراعين). باقي
  الصفوف الموثّقة (ص6/ص21/ص111) ليست شظايا متجاورة بنسبة كبيرة فلا تصلها
  القاعدة ببنائها. **القرار: غلق كباقي السطور المقيسة سلبًا — لا كود شُحن**
  (رُدَّ `main.py`/`segment_text_rows.py`)، والتسجيل الكامل في
  `plans/REMAINING_WORK_PLAN.md` Phase A و`docs/binarization_experiment.md`.
  **القياس بحد ذاته هو المُنجَز**: ذراع التحكّم أعاد الـ corpus حرفيًا على
  الـ 51 صفحة، وصفة القياس (front-end في الذاكرة + نسخة cache في /tmp +
  `evaluate_cer --output-root`) قابلة لإعادة الاستخدام لأي رافعة تقسيم لاحقة.

- **توثيق: عقود الطبقات والـ knobs غير النشطة (REMAINING_WORK_PLAN Phase C 13–16، 2026-10-08)**
  - `output_generator.py` docstring: عقد الطبقات — `raw_text/` طبقة دليل
    و`save_page()` هو كاتبها الوحيد، وأي مرحلة أحدث تكتب في طبقة منفصلة
    (`corrected_text/`، `repaired_text/`، `vote_corrected_text/`،
    `vault_corrected_text/`) بدل الكتابة فوق الخام (AGENTS §6/§7).
  - `config/settings.yaml`: `token_verification` — التوثيق يشرح أن البلوك
    مُعطَّل عمدًا وأن `flag_suspicious_words.py` يعمل على الافتراضات
    (`calima-msa-r13`، `max_candidates=5`) عندما يكون غائبًا، وأدواره كلها
    قِيسَت ورُفِضَت (specs 015/016). `ocr.min_confidence` — لا يقرؤه إلا
    `OCREngine.extract()` (whole-page) الذي لا يستدعيه `main.py` أبدًا.
  - `scripts/vote_correct_names.py` docstring: النقطة العمياء البنيوية —
    التجميع بالـ skeleton لا يرى أخطاء الحرف الأساسي أصلًا (حرفان مختلفان =
    skeleton مختلفان لا يلتقيان في cluster أبدًا)، وهو لماذا يوجد
    `genealogy_crossref.py`/`vault_vote_correct_names.py` كإشارة من مصدر
    مختلف تمامًا؛ الآليتان متكاملتان لا مكررتان.

## 2026-09-10

- **new: ink-density gate (spec 004) — pre-API-call filter قبل وضع الـ Vision**
  بوابة كثافة الحبر في `_maybe_escalate_line()` في `main.py` + اختبارات في
  `tests/test_escalation_policy.py` (23 اختبارًا جديدًا: InkDensityGate /
  InkDensityGateIntegration / InkDensityGateConfig + قسما التكامل) +
  `settings.yaml` (`vision_fallback.ink_density_threshold`، افتراضي 0.02).
  - الفكرة: قبل أي نداء Vision لسطر منخفض الثقة، تُقاس نسبة بكسلات الحبر
    (binarization → ink=255/bg=0) على الـ crop؛ إن كانت أقل من الحد تُحجب
    المحاولة ويُسجَّل قيد تدقيق (`source: ink_density_gate`،
    `escalated_text: null`، `ink_ratio`، `reason` من ثلاثة رموز) — Fail-closed
    عند صورة مفقودة/غير قابلة للثنائية. لا تُغيَّر `result["text"]` (§FR-007)
    ولا أي سلوك للبوابات القائمة (§FR-010) ولا مفتاح الكاش.
  - **نتيجة المعايرة (صادقة، ليست تسويقية)**: قُيست 3,629 crop على كل الـ 113
    صفحة (`specs/004-ink-density-gate/calibrate_ink_density.py`).
    الـ 9 crops الوحيدة المرشحة للتصعيد (ثقة <0.55) كلها فوق 0.02
    (حبر 0.054–0.357) ⇒ **البوابة تحجب 0 من 9** ولا تُقلِّل نداءات Vision
    فعليًا على هذا المخطوط. الغرض الحقيقي دفاعي: حجب الصفحات الفارغة/المفقودة
    (أخطاء مسح، صفحات ناقصة) في مخطوطات قادمة، وليست معالجة لنمط ضجيج هذا
    المخطوط (علامات مائية/تطويل — حبر مرتفع بلا نص مقروء). بقي الحد 0.02
    كما هو، والنتيجة موثقة في تعليق `settings.yaml`.
  - الأداء: ~0.16 ms/crop (هدف <50 ms، هامش ~300×). القياس الكامل في
    `specs/004-ink-density-gate/research.md` §Performance.
  - ملاحظة نزاهة: `SC-003` (تخفيض ≥10% في نداءات transcribe على صفحات
    24–26) **غير متحقَّق** — المعايرة فندت افتراضها (لا توجد crops فارغة
    تستحق الحجب)، ونموذج `InkDensityGateStub` المذكور في quickstart V7 لم
    يُبنَ قط. يُوثَّق هذا صراحةً في quickstart/research ولا يُدَّعى أنه
    حاصل.

- **new: bootstrap_ground_truth.py + evaluate_cer.py (بوابة GT) + tests/** —
  واجهة إنتاج أرضية GT (Phase 4 §8، رفع الحاجز المتبقي أمام §4.12):
  - `bootstrap_ground_truth.py` — `--document`/`--pages`/`--dpi` (300 افتراضي):
    يبحث عن الـ PDF في `input/`، يرسم كل صفحة إلى
    `ground_truth/<doc>/rendered/page_NNN.png`، وبيضع placeholder
    `# GT-PENDING` فارغ (سطور تعليقات فقط: document/page/source image/
    reviewer/status + تذكير بصيغة hemistich) إلى جانبها — **لا يُنشئ
    نسخًا من مخرجات OCR أبدًا** (ممنوع §4.12)، ولا يلمس GT موجود فعلًا
    (تحقق فوري: عند `--doc X --pages 24` يعيد الرسم ولا يكتب فوق GT).
  - `evaluate_cer.py` — بوابة نزاهة جديدة `has_usable_gt_content()`: ملف GT
    اللي يحتوي على مجرد ترويسات # فقط (مثل ملفات `# GT-PENDING`) يُعد «غير
    جاهز للقياس» حتى يملؤه إنسان أو نموذج — ويخرج `exit 2` بخطأ واضح يمنع
    قراءات CER/WER كاذبة صفرًا (قياس صادق أو لا قياس، الـ Baseline الحالي
    يُطبّقه).
  - `tests/test_cer_normalization.py` — اختبار تشغيل مع `jiwer 4.0.0` (في
    venv)، مقاييس CER/WER تعمل في الإطار. اختبارات تطبيع `evaluate_cer.py`
    (إسقاط علامات #، tatweel، tashkeel أو عدمه، ضم الأسطر).

- **review_manuscript.py / output_generator.py — صيانة: مزامنة ترتيب الـ page_confidence & binarization_attempt**
  صف البنود في ترويسة الصفحة بنفس الترتيب (Page Confidence أول، Binarization Attempt
  لاحقًا) حتى يتميز الاثنان ولا يتغير في المراجعة اللاحقة. الـ confidence يظهر
  كنسبة مئوية (الرسم البياني: ثقة الصفحة 70٪ = `# Page Confidence: 70%`).
  Binarization attempt = 1 أو 2 (الـ reprocess أعلاه 50٪ يحاول مرة أخرى).

- **pdf_text_extractor.py — إضافة: detect_pdf_type()**
  يجمع الأحكام المصدرة من `extract_direct_text()` لكل الصفحات لتعلن صنف ملف
  كامل: `TEXT` (كل الصفحات نصوص)، `IMAGE` (جميعها صور)، `HYBRID` (مزيج —
  يظهر WARNING صريح، توجيه التشغيل page-per-page مثل ما هو). يُعرض بصيغة:
  `TXT/T/I/H/U` + النسبة `(usable/N_total)`. مثال مقتضب: `TYPE: TEXT (0/3)`،
  `TYPE: IMAGE (3/3)`.
  - **⚠ تصحيح 2026-10-08: هذا غير موجود.** الوحدة حُذفت في commit `a3fcdc3`
    مع تقاعد مسار الطبقة النصية — لا `detect_pdf_type` ولا سطر `TYPE:` في
    `_load_pdf`. انظر قسم 2026-10-08 أعلاه و AGENTS.md §4.4/§4.5.

- **AGENTS.md — تحديث واسع (مُدمَج الآن في هذا المشروع)**
  سرد الحالة السائدة كاملاً: الحالة الحالية §3 (implemented/partial/planned/
  blocked/prohibited) لكل مكون، القواعد غير القابلة للنقاش §4، والعقود على
  المعمارية/الإخراج/القياس. أصبح المرجع الأول قبل أي تعديل.

- **ocr_engine.py — صيانة: إزالة كود DEBUG/plotting وتنظيف debug/**
  حُذفت وظائف الـ plotting والمخططات من الدالة العامة (كانت تستخدم
  `cv2.imwrite` ومجلد `debug/` من داخل الـ batch). المجلد شُطب خوفًا من
  انسكاب الصور العارض للمساحة — التشخيص يرجع `logging.debug` في
  التطوير الموضعي فقط، كل التحليل المرئي (plots) يطالب بتنفيذ منفصل.

- **surya_line_detector.py — تثبيت surya-ocr وجعله جاهز**
  تثبيت `surya-ocr 0.22.1` مع حِزَمه المتوقعة (torch، opencv، onnxruntime،
  sentencepiece — الـ venv تتحمّلها). اختبر `SuryaLineDetector.available = True`
  وربط حزمه (20 band تقريبًا على صورة ص 24). إضاءة التبديل موجودة عبر
  مفتاح `layout_detection.line_detector` في `settings.yaml` — **غير مفعّلة**
  الآن (مطالبة بـ CER/WER أولاً).

- **إعادة توثيق: `opencode.json` (سوفرن الميزات)، تحديث `opencode.jsonc` في مشاريع أخرى، قواعد استخدام الـ Models من دون خرق للروابط**.

- **vision_fallback.py — صيانة: تصحيح الإعداد عند فشل الـ backends واستجابة الـ 429**
  - إصلاح تسرب الكائن المثيل (instance) بعد 429: كان يبقى مثيل الـ backend ويمنع
    التبديل إلى البديل — الآن يُنشأ مرة واحدة ويتم إعادة إنشائه فقط حال 429.
  - زيادة صمود الإعداد (retry_config): زيادة محاولات الارتباط من 2 إلى 5،
    تحمّل ميزي في الـ timeout (15 ثانية → 30)، تعطيل SSL-verification الصارم
    المؤقت لبعض الخوادم المتعسرة.
  - التغلب على مقطع `max_calls` عند تعاقب الـ 429: الرقم العام (3000) صحيح
    محسوب (الأسطر المطلوبة) ولا يُخفض لمجرد تعثر خادم معين. إعادة استخدام
    الفرد الفاشل = 0 من مجمل الحد.

- **AGENTS.md — إضافة: §9 (العتاد)، §11 (التأكد، Definition of Done)، §12 (المعوقات المعروفة، vision-hallucination & repeated_verbatim)**
  - §9: Dell G15 5510، أنظمة التشغيل، GTX 1650 4GB VRAM (batch=16) — تحد
    واقعي، ليس افتراض نظري يمكن تجاهله.
  - §11: قائمة Definition of Done المطلوبة قبل أن يُعتبر التعديل مكتملاً —
    ترسيم "ما الذي يعد جاهزًا" صراحة بدلًا من التعيين الانتقائي. 
  - §12: القيود التي لا تحتاج لتعب الاستكشاف من 0 في كل محادثة — مثل
    ground truth غير الموجود، surya المُثبَّت والمُعطّل، vision غير الحتمي،
    الضجيج الشعري على الصفحات 20–27.

- **project_constitution.md — خطة للمستقبل (غير مطلوبة حالياً مع AGENTS.md القوية)**
  خارطة طريق دستورية لترتيب الأولويات وربطها بالمبادئ الثابتة، مرشحة لأن
  تصبح `baseline/CONSTITUTION.md` بعد النضج.

- **main.py / AGENTS.md — إغلاق فجوة الوثائق: سياسة التصعيد في Vision، حماية التشكيل، القياس الإجباري، ممنوعيات صارمة**
  ترسيخ سياسة Vision الجديدة: بوابات `_evaluate_escalation`، `_should_escalate_line`،
  `_maybe_escalate_line`. تكريس "OCR ≠ Editing" كرئيس غير قابل للتفاوض، والتركيز
  على الـ CER/WER قبل أي ادعاء تحسين (الميزة الحقيقية التي فُعلت قبل 24-26:
  `flag_suspicious_words.py` جاهزة، لكن غياب GT يجعل الـ §4.12 مضمون الفشل).

- **new: repeated_verbatim_tracker.py (SQLite) + settings.yaml**
  قاعدة بيانات مستدامة عبر الركضات لمعالجة هلوسات Vision المتكررة:
  - الإصدار القديم في الذاكرة (`_seen_escalated_texts`) فقد تمامًا ظاهرة
    التعقيب الحرفي عبر الجلسات (صفحات 20–27 كانت ترسل نفس 
    «وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...» في سلسلة ركضات منفصلة —
    لا شاهد عليها أبدًا إذ كانت كل جلسة تبدأ بـ dict فارغ).
  - الجديد: `repeated_verbatim_db` في `output/.cache/repeated_verbatim.sqlite3`
    يحفظ كل نص Vision (مع تطبيع خفيف: حذف التشكيل) وعدّاد تكراره.
    التطبيع: U+064B–U+0652 وU+0670 فقط (يستوعب اختلافات الضبط بين
    النداءات لنفس العبارة). لا يخزن نص OCR أو صور — مجرد عداد.
  - التسجيل: `repeated_verbatim_tracker.register(text)` تزيد العداد
    وتُرجع `True` إذا سبق أن سجلت العبارة (ضمن هذه الجلسة أو أي جلسة سابقة).
    إذا كان `True` في `vision_fallback.py`، يُسجل الخطأ في `escalations.jsonl`
    ولكن ناتج OCR الأصلي يبقى مخرجًا نهائيًا — لا استبدال بـ Vision.
  - التتبع: `settings.yaml` `vision_fallback.repeated_verbatim_db`.

- **AGENTS.md — إضافات من سجلات التشغيل: status table §3، حماية التشكيل §4.2، الثقة §4.10، Vision §4.13**
  - §3: عرض تفصيلي لكل مُكوّن (من Direct Text إلى Bench CER/WER).
  - §4.2: توحيد `adaptive_binarize[_gray]` (كتلة 51 Gaussian) موصلة من
    `preprocessing.py` عبر `layout.binarize()` و`rowseg.binarize()`
    (كل منهما يرجع صيغة ثنائية مختلفة — 0/255 مقابل 0/1 — لا تتداخل).
  - §4.10: `ocr.page_confidence_reprocess` — إعادة معالجة الصفحات الأقل
    من 50% بإعدادات Binarization أدق (block=31/c=5) قبل محاولة OCR ثانية.
  - §4.13: بوابات تصعيد Vision الثلاث الصريحة — "لا تصعيد لخط ضجيج"،
    "رفض repeated_verbatim"، "رفض صدى OCR echoed_ocr" (بنية تكرار حرفي
    غير مرتبطة بالصورة = تخمين فاشل، يُرصد في إسكالشنز للتدقيق ولكن لا
    يُطبق في المخطوط).

- **camel-tools + morphology-db-msa-r13 — تثبيت وفحص**
  - camel-tools 1.6.0 (`myenv/bin/python -m pip install camel-tools`)
    ومرفقها morphology-db-msa-r13
    (`myenv/bin/camel_data -i morphology-db-msa-r13`) مثبتتان وتم التحقق.
  - تحقق من الشغل: رمى `flag_suspicious_words.py` لصفحات 24–26 ورجع
    89 كلمة من 394 مشكوكًا فيها — كلها منطقية: تشمل `شسسسسش` (رفض صحيح)
    وكلمات غامضة في الخط (رغم صحتها في العربية — الـ flagger يحقق
    شكلاً، ليس صحة).
  - الجاهز الآن: `morphological_verifier.py` + `flag_suspicious_words.py`
    يعملان ولو كأداة مراجعة خارجية. يبقى الباقي: مَوضَعة التحقق الصرفي
    في الـ pipeline نفسها (بعد الحصول على صورة الكلمة + مُرشّحين من
    القواميس → الطلب «أي من هذه المرشحين تطابق الصورة؟»).

## 2026-09-01

- **review_manuscript.py** — إصلاح باگ: كان بيدور على `config/settings.yaml` و `config/prompts.yaml` و بيحط `src/` في `sys.path`، لكن المشروع flat layout (مفيش `config/` ولا `src/` — كل حاجة في الروت جنب `main.py`). النتيجة كانت إن السكربت شغال على `settings` فاضي دايمًا (`enabled=False` حتى لو الإعدادات الحقيقية `true`) وكان بيعمل `sys.exit(1)` فورًا من غير ما يقرا أي حاجة حقيقية. اتصلح بتصحيح المسارات لـ `settings.yaml` / `prompts.yaml` في الروت، وشيل سطر `sys.path.insert` خالص.

- **pdf_text_extractor.py (ملف جديد)** — أول بند من الـ Backlog: فحص لكل صفحة PDF على حدة هل فيها text layer مضمّن قابل للاستخراج مباشرة (`extract_direct_text()`)، بدل ما كل صفحة تتحول لصورة وتاخد OCR كامل حتى لو النص جاهز أصلاً. الفحص متحفظ عمدًا (شرطين لازم يعدّوا سوا): (1) عدد حروف كافي (`MIN_TEXT_CHARS=20`)، (2) على الأقل 85% من الحروف عربي أو لاتيني حقيقي (مش رموز/PUA/`U+FFFD` الناتجة عن ToUnicode CMap عاطل — المشكلة اللي إنت وصفتها في ملاحظاتك بالظبط). لو أي شرط فشل، بترجع `None` والصفحة بتاخد مسار الـ OCR العادي زي ما هو من غير أي تغيير.   الفحص per-page مش per-file، يعني كتاب فيه مقدمة نصية رقمية + متن ممسوح ضوئيًا هيستفيد من الاختصار في صفحات المقدمة بس.
  - **⚠ تصحيح 2026-10-08: الملف حُذف** (commit `a3fcdc3`) مع تقاعد مسار
    الطبقة النصية — لا `extract_direct_text` في `src/`. السبب والسلوك الفعلي
    في قسم 2026-10-08 أعلاه. المدخلان التاليان (`input_handler.py` و
    `settings.yaml`) يصفان أيضًا تفعيلًا لم يعد موجودًا: `enable_direct_text_extraction`
    و`input.direct_text_extraction.enabled` رُفعا؛ `_load_pdf` لا يستدعي شيئًا
    قبل الـ render.
- **input_handler.py** — `InputHandler.__init__` بقى ياخد `enable_direct_text_extraction` (افتراضي `True`). `_load_pdf()` بينادي `extract_direct_text()` لكل صفحة قبل الـ render، وبيضيف مفتاح `direct_text` لكل `page_data` (بيبقى `None` لو الصفحة عادية أو لو دي صورة مش PDF أصلاً - `_load_image()` اتعدلت برضو عشان تضيف نفس المفتاح بـ `None` ثابت، عشان الـ shape يفضل موحّد). بيسجل في اللوج كام صفحة استفادت من الاختصار.
- **main.py** — `process_document()` بقى يشوف `page_data.get('direct_text')` الأول قبل أي حاجة تانية؛ لو موجود، بيتخطى `preprocess_page()` و `process_page_image()` بالكامل (يعني لا deskew ولا CLAHE ولا layout detection ولا PaddleOCR ولا vision fallback) ويحفظ النص المستخرج مباشرة بـ `ocr_method: direct_extraction` و `structure: direct_text`. بيسجل في نهاية كل مستند كام صفحة من الإجمالي استخدمت الاختصار ده.
- **settings.yaml** — إضافة `input.direct_text_extraction.enabled` (افتراضي `true`) للتحكم في تفعيل/تعطيل الميزة بالكامل من غير تعديل كود.

- **ocr_engine.py** — بند التاني من الـ Backlog: إضافة `OCREngine.extract_segments_batch()` — نسخة مجمّعة (batched) من `extract_segment()`، بتاخد قائمة كاملة من الـ line crops وتبعتهم لـ `rec_only.predict()` في مجموعات (chunks) بدل نداء منفصل لكل سطر. فيه معالجة دفاعية (defensive) لو `predict()` رجّع عدد نتائج أقل من المتوقع، عشان النتايج التالية متتزحلقش على أسطر غلط. مفتاح إعداد جديد `ocr.segment_batch_size` (افتراضي 16، محافظ عشان الـ GTX 1650 4GB بتاعتك).
- **main.py** — `extract_poetry_region()` و `extract_prose_region()` اتعملهم إعادة هيكلة لمرحلتين: **Pass 1** بيصنّف كل سطر ويقصّه (right/left للشعر، أو سطر كامل للنثر) من غير OCR، **نداء batch واحد** لكل الأسطر مع بعض، ثم **Pass 2** بيجمع النص النهائي ويطبّق منطق الـ vision-fallback escalation والـ noise filtering **بالظبط زي ما كان قبل كده** (من غير أي تغيير في السلوك، بس اتغيّر مصدر نتيجة الـ OCR بس). النتيجة: نداء OCR واحد لكل صفحة/منطقة بدل نداء لكل سطر (وكانت اتنين للسطر الشعري: يمين + شمال).
- **settings.yaml** — إضافة `ocr.segment_batch_size` (افتراضي 16).