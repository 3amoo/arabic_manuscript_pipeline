# CHANGELOG

سجل مختصر لكل تعديل بيتعمل في الكود عبر الجلسات المختلفة. الهدف: تحط الملف ده في أول أي محادثة جديدة ويبقى فاهم إيه اللي اتعمل واللي لسه لأ، من غير ما تعيد شرح كل حاجة من الصفر.

كل سطر: **الملف** — إيه اللي اتغيّر (إضافة/تعديل/حذف) وليه، باختصار شديد.

---

## 2026-09-01

- **review_manuscript.py** — إصلاح باگ: كان بيدور على `config/settings.yaml` و `config/prompts.yaml` و بيحط `src/` في `sys.path`، لكن المشروع flat layout (مفيش `config/` ولا `src/` — كل حاجة في الروت جنب `main.py`). النتيجة كانت إن السكربت شغال على `settings` فاضي دايمًا (`enabled=False` حتى لو الإعدادات الحقيقية `true`) وكان بيعمل `sys.exit(1)` فورًا من غير ما يقرا أي حاجة حقيقية. اتصلح بتصحيح المسارات لـ `settings.yaml` / `prompts.yaml` في الروت، وشيل سطر `sys.path.insert` خالص.

- **pdf_text_extractor.py (ملف جديد)** — أول بند من الـ Backlog: فحص لكل صفحة PDF على حدة هل فيها text layer مضمّن قابل للاستخراج مباشرة (`extract_direct_text()`)، بدل ما كل صفحة تتحول لصورة وتاخد OCR كامل حتى لو النص جاهز أصلاً. الفحص متحفظ عمدًا (شرطين لازم يعدّوا سوا): (1) عدد حروف كافي (`MIN_TEXT_CHARS=20`)، (2) على الأقل 85% من الحروف عربي أو لاتيني حقيقي (مش رموز/PUA/`U+FFFD` الناتجة عن ToUnicode CMap عاطل — المشكلة اللي إنت وصفتها في ملاحظاتك بالظبط). لو أي شرط فشل، بترجع `None` والصفحة بتاخد مسار الـ OCR العادي زي ما هو من غير أي تغيير. الفحص per-page مش per-file، يعني كتاب فيه مقدمة نصية رقمية + متن ممسوح ضوئيًا هيستفيد من الاختصار في صفحات المقدمة بس.
- **input_handler.py** — `InputHandler.__init__` بقى ياخد `enable_direct_text_extraction` (افتراضي `True`). `_load_pdf()` بينادي `extract_direct_text()` لكل صفحة قبل الـ render، وبيضيف مفتاح `direct_text` لكل `page_data` (بيبقى `None` لو الصفحة عادية أو لو دي صورة مش PDF أصلاً - `_load_image()` اتعدلت برضو عشان تضيف نفس المفتاح بـ `None` ثابت، عشان الـ shape يفضل موحّد). بيسجل في اللوج كام صفحة استفادت من الاختصار.
- **main.py** — `process_document()` بقى يشوف `page_data.get('direct_text')` الأول قبل أي حاجة تانية؛ لو موجود، بيتخطى `preprocess_page()` و `process_page_image()` بالكامل (يعني لا deskew ولا CLAHE ولا layout detection ولا PaddleOCR ولا vision fallback) ويحفظ النص المستخرج مباشرة بـ `ocr_method: direct_extraction` و `structure: direct_text`. بيسجل في نهاية كل مستند كام صفحة من الإجمالي استخدمت الاختصار ده.
- **settings.yaml** — إضافة `input.direct_text_extraction.enabled` (افتراضي `true`) للتحكم في تفعيل/تعطيل الميزة بالكامل من غير تعديل كود.

- **ocr_engine.py** — بند التاني من الـ Backlog: إضافة `OCREngine.extract_segments_batch()` — نسخة مجمّعة (batched) من `extract_segment()`، بتاخد قائمة كاملة من الـ line crops وتبعتهم لـ `rec_only.predict()` في مجموعات (chunks) بدل نداء منفصل لكل سطر. فيه معالجة دفاعية (defensive) لو `predict()` رجّع عدد نتائج أقل من المتوقع، عشان النتايج التالية متتزحلقش على أسطر غلط. مفتاح إعداد جديد `ocr.segment_batch_size` (افتراضي 16، محافظ عشان الـ GTX 1650 4GB بتاعتك).
- **main.py** — `extract_poetry_region()` و `extract_prose_region()` اتعملهم إعادة هيكلة لمرحلتين: **Pass 1** بيصنّف كل سطر ويقصّه (right/left للشعر، أو سطر كامل للنثر) من غير OCR، **نداء batch واحد** لكل الأسطر مع بعض، ثم **Pass 2** بيجمع النص النهائي ويطبّق منطق الـ vision-fallback escalation والـ noise filtering **بالظبط زي ما كان قبل كده** (من غير أي تغيير في السلوك، بس اتغيّر مصدر نتيجة الـ OCR بس). النتيجة: نداء OCR واحد لكل صفحة/منطقة بدل نداء لكل سطر (وكانت اتنين للسطر الشعري: يمين + شمال).
- **settings.yaml** — إضافة `ocr.segment_batch_size` (افتراضي 16).

اتعمل اختبار وظيفي فعلي (مش syntax check بس) بمحاكاة PaddleOCR، أكّد إن: (1) نداء الـ batch بيتعمل مرة واحدة بالظبط لكل منطقة بدل نداء لكل سطر، (2) ترتيب النتايج بيتحط في مكانه الصح في النص النهائي (بيت الشعر بالشطرين + السطر الكامل)، (3) الـ vision-fallback escalation لسه بيشتغل صح على كل نتيجة من الـ batch.

- **ocr_cache.py (ملف جديد)** — بند التالت من الـ Backlog: `OCRCache` class، بتخزن نتيجة الـ OCR لكل line crop في قاعدة SQLite محلية (`output/.cache/ocr_cache.sqlite3` افتراضيًا)، مفتاح التخزين (hash) بيتكون من bytes الصورة + shape + dtype + **اسم موديل الـ recognition نفسه**. النقطة الأخيرة دي مهمة: لو غيّرت `text_recognition_model_name` في المستقبل (مثلاً لموديل مدرّب خصيصًا كما في الـ Backlog)، الـ cache القديم بيبقى تلقائيًا "مش موجود" بدل ما يرجّعلك نتايج موديل قديم، من غير أي كود تحقق إضافي. كل كتابة بتتعمل commit فورًا (autocommit) عشان لو الـ run وقعت في النص، الصفحات اللي اتعملت قبل الكراش يفضل الـ cache بتاعها موجود. **مش بتكاش vision_fallback ولا text_correction** — دول ليهم منطق مختلف وممكن يكونوا غير حتميين (non-deterministic)، فالـ caching اتعمل للـ OCR العادي بس اللي هو حتمي (deterministic) 100%.
- **ocr_engine.py** — `extract_segments_batch()` بقى بيدوّر على الـ cache الأول لكل صورة قبل ما يستخدم PaddleOCR؛ الصور اللي مش موجودة (cache miss) بس هي اللي بتتبعت للـ batch الفعلي (اتفصلت لدالة داخلية جديدة `_run_paddle_batch()`)، والنتايج الجديدة بتتخزن في الـ cache على طول. `extract_segment()` (النسخة القديمة لصورة واحدة) بقت مجرد wrapper بينادي `extract_segments_batch()` بصورة واحدة، فبتستفيد من نفس الـ caching تلقائيًا. مفتاح إعداد جديد `ocr.caching.enabled` (افتراضي `true`) و `ocr.caching.db_path`.
- **main.py** — في نهاية التشغيلة، بيطبع تقرير `ocr_engine.cache.summary()` (كام سطر كان cache hit وكام سطر فعليًا اتعمله OCR)، بنفس أسلوب تقارير `vision_engine.summary()` الموجودة.
- **settings.yaml** — إضافة `ocr.caching.enabled` و `ocr.caching.db_path`.

اتعمل اختبار وظيفي شامل (مش syntax check) بمحاكاة PaddleOCR، أكّد: (1) أول مرة تشوف صورة = cache miss وبتتعمل OCR، (2) تاني مرة لنفس الصورة بالظبط = cache hit وصفر نداءات لـ PaddleOCR، (3) الـ cache بيفضل موجود لو عملت `OCREngine` **جديد تمامًا** بنفس ملف الـ DB (يعني محاكاة تشغيلة جديدة كاملة بعد إعادة تشغيل) — صفر نداءات PaddleOCR من أول instance، (4) تغيير اسم الموديل بيخلي نفس الصورة تترجع cache miss تلقائيًا (الحماية من النتايج القديمة)، (5) تعطيل الـ caching (`enabled: false`) بيخلي كل نداء يروح لـ PaddleOCR عادي زي الأول.

---

## 2026-09-02

- **vision_fallback.py / text_correction_engine.py** — إصلاح باگ "ILLEG"
  الحقيقي (اتأكد من `escalations.jsonl` فعلي على رن صفحات 23-26: صفحة 26
  اتكتب فيها "ILLEG" كنص منقول في full_manuscript.txt). السبب:
  `_looks_like_plausible_arabic()` كانت بترجع `True` تلقائيًا لأي رد أقل
  من `MIN_ARABIC_LETTER_RATIO_MIN_LETTERS` (6 حروف) من غير ما تتأكد إن
  فيه ولو حرف عربي واحد فيه - فرد إنجليزي قصير زي "ILLEG" (نسخة مقطوعة
  من "ILLEGIBLE" رجّعها groq) عدّى كأنه ترجمة صحيحة. الإصلاح: لو الرد
  قصير، بنتجاوز نسبة الـ 50% بس لازم يفضل شرط "فيه حرف عربي واحد على
  الأقل" (`arabic_letters > 0`) - نفس الإصلاح في الملفين لأنهم نسخة
  مطابقة من نفس الدالة.
- **vision_fallback.py** — إضافة كاشف "نص متكرر حرفيًا" (`repeated_verbatim`):
  لوحظ في `escalations.jsonl` (صفحات 24-26) إن نفس الجملة تقريبًا
  ("وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...") بترجع من backends مختلفة على قصاصات
  paddle_text بتاعها رموز عشوائية (`w`, `ww`, `ـــ`) - على صفحات محتواها
  كتير أصلًا (مش فاضية)، وده إشارة هلوسة قوية. `VisionFallbackEngine`
  دلوقتي بيتتبع كل نص escalated اترجع في التشغيلة، ولو نفس النص اترجع
  تاني بالظبط، بيتحط `repeated_verbatim: true` في `escalations.jsonl` +
  تحذير في اللوج + عداد في `summary()`. مجرد جرس إنذار للمراجعة البشرية -
  مفيش أي تغيير في النص النهائي المكتوب في full_manuscript.txt.
- **main.py** — الـ 3 نقاط اللي بتسجل escalation جوه `extract_poetry_region()`
  (verse_right, verse_left, full_width) بقوا بيسجلوا `repeated_verbatim`
  من الـ dict الراجع من `vision_engine.transcribe()`.
- **تأكيد بصري للهلوسة (بالمقارنة مع صور حقيقية من الكتاب):** السطر
  الأول في `page_025.txt` الناتج ("وَمَا لِلْعَيْنِ مِنْ دَمْعٍ إِذَا")
  **غير موجود في الصفحة الحقيقية خالص** - اختراع كامل من `openrouter`
  على قصاصة paddle_text='ـــ'. في المقابل، escalation تاني في نفس
  الصفحة ("[ مقدمة ]" من gemini) طلع **صحيح فعلًا** - الصفحة فيها عنوان
  "مقدمة" حقيقي. هذا يؤكد أن `repeated_verbatim` (تكرار حرفي عبر
  قصاصات/صفحات مختلفة) هو المعيار الصح للتمييز، مش مجرد "قصاصة فاضية = ارفض".
- **أوفست ترقيم الصفحات موثّق:** رقم الصفحة المطبوع في الكتاب = رقم
  صفحة الـ PDF (اللي بيستخدمه main.py/--start/--end) − 3.

## 2026-09-03

- **morphological_verifier.py (ملف جديد)** — أول لبنة من بند "Token-level
  verification" في الـ Backlog: `MorphologicalVerifier` بيستخدم محلل
  CAMeL Tools المدمج (`calima-msa-r13`) للحكم هل كلمة عربية معينة عندها
  تحليل صرفي صحيح ولا لأ (بعد تشيل التشكيل - بما فيها الألف الخنجرية
  U+0670 - للبحث بس، مفيش تعديل على الكلمة الأصلية). لو مشكوك فيها،
  `generate_candidates()` بيولّد بدائل بتبديل حرف واحد من جدول تشابه
  شكلي حقيقي (بحد -> بعد بتبديل ح/ع، إلخ)، ومنسيبش غير البدائل اللي هي
  نفسها كلمات صحيحة. اتعمل اختبار فعلي (مش mock، بالداتابيز الحقيقية)
  على كلمات من `page_023.txt` الحقيقي: أمسك "مممدا" (0 تحليلات، بدون
  بدائل - معطوبة أكتر من حرف واحد)، "أَغْظمِها" -> بديل صحيح "أَعْظمِها"،
  "عِماذُ" -> بديل صحيح "عِمادُ". حدود موثقة في الـ docstring اتأكدت
  بالتجربة الفعلية: "خزاعة" (اسم قبيلة حقيقي) بيرجع 0 تحليلات
  (False Positive - مش في قاموس MSA الحديث)، و"بَحْدُ" (تلخبط OCR من
  "بَعْدُ") بيرجع صحيح صدفة (False Negative).
- **flag_suspicious_words.py (ملف جديد)** — سكريبت مراجعة منفصل، نفس
  شكل `review_manuscript.py` بالظبط (`--document --start --end`)، بيشغل
  المحلل على `raw_text/` بعد ما `main.py` يخلص، وبيقرا إعداداته
  (`db_name`, `max_candidates`) من `settings.yaml`'s `token_verification`
  section (باگ اتصلح: أول نسخة كانت بتتجاهل الإعدادات دي بالكامل)، ويكتب
  `output/{doc}/review/suspicious_words.jsonl` - بدون أي تعديل على
  `raw_text` أو `full_manuscript.txt`، مجرد قائمة مراجعة. اتعمل اختبار
  end-to-end فعلي (اسم مستند فيه عربي ومسافات، فلترة `--start/--end`،
  التحقق من صحة كل سطر JSON برمجيًا) وطلع كله سليم.
- **settings.yaml** — إضافة `token_verification.db_name` و
  `token_verification.max_candidates`.

## حاجات معروفة لسه محتاجة شغل (Backlog)

دي مش تم عملها، بس اتكتبت هنا عشان متتنساش وتبقى معروفة كسياق:

- ~~Direct text extraction للـ PDF النصي~~ — **تم (2026-09-01)**، شوف فوق.
- ~~Batch OCR للـ line crops~~ — **تم (2026-09-01)**، شوف فوق.
- ~~Caching (SQLite/hash-based)~~ — **تم (2026-09-01)**، شوف فوق.
- **اكتشاف النص الملون (العناوين الحمراء عبر HSV)**: مش موجود، كل حاجة بتتعمللها binarize مباشرة.
- **Token-level verification بمحلل صرفي (CamelTools/Farasa) + قاموس بدائل**:
  ~~المرحلة الأولى (المحلل الصرفي + توليد البدائل، `morphological_verifier.py`
  + `flag_suspicious_words.py`) تمت (2026-09-03)~~، شوف فوق. **باقي**:
  ربط `generate_candidates()` بمرحلة تحقق بالصورة فعلية (تمرير كروب
  الكلمة + قائمة البدائل لموديل رؤية والسؤال "أي دول يطابق الصورة
  بالظبط؟") - محتاج الأول تعديل أعمق في `segment_text_rows.py`/
  `ocr_engine.py` عشان نقدر نقص كروب كلمة واحدة لوحدها من صورة السطر
  (حاليًا الثقة والـ crops على مستوى السطر كامل بس، مش الكلمة).
- **CER/WER benchmarking (jiwer) على ground truth حقيقي**: لسه مفيش. الجزء اللي عمله كلود من الكتاب **مقرر عمدًا إنه ميتستخدمش كـ ground truth آلي** — استخدامه محصور في مراجعة بشرية/spot-check يدوي بس، لحد ما يتعمل dataset حقيقي (~50 صفحة) بـ ground truth يدوي فعلي.

---

### طريقة الاستخدام
لما تبدأ محادثة جديدة، اعمل attach للملف ده (+ الكود لو محتاج) وقول للموديل يقرا الـ Backlog والتاريخ الأخير الأول قبل ما يقترح حاجة جديدة، عشان ميقترحش حاجة مكررة أو يتجاهل قرار اتاخد قبل كده (زي موضوع الـ ground truth بتاع كلود).

## 2026-09-05

- **تأكيد إنتاجي لـ `repeated_verbatim`:** أول رن حقيقي بعد الإصلاح (صفحات
  24-26) أظهر إشارتين صحيحتين فعليًا - نفس جملة "وَمَا لِلْعَيْنِ مِنْ
  دَمْعٍ..." اتكررت حرفيًا مرتين داخل الرن نفسه (صفحة 25 وصفحة 26) واتحطلها
  `repeated_verbatim: true` بالظبط زي المتوقع.
- **قيد معروف في الكاشف الحالي:** `_seen_escalated_texts` بيتصفّر كل
  تشغيلة (in-memory، instance-level) - فمش قادر يكتشف إن نفس الجملة
  اتكررت عبر رنّات/جلسات مختلفة (زي ما هو موثّق فعليًا في
  vision_escalations.txt: نفس الجملة ظهرت على صفحات 20، 21، 24-27 عبر
  أيام مختلفة). الخطوة الجاية: نقل العداد لجدول SQLite دائم (نفس فلسفة
  ocr_cache.py) عشان يمسك التكرار عبر كل تاريخ التشغيل، مش رن واحد بس.
- **ملاحظة صيانة:** تحذير Deprecation حقيقي من `google.generativeai` -
  "All support... has ended", والبديل الرسمي `google.genai`. لسه شغالة
  دلوقتي، بند Backlog للانتقال قبل ما تتعطل فجأة.
- **ملاحظة:** Groq رجّع صفر escalations ناجحة في هذا الرن رغم 4 استجابات
  200 OK - كل رد فشل الـ validation (على الأرجح النموذج بيرفض التخمين
  على قصاصات غامضة، سلوك آمن مش باگ، لكن يستاهل متابعة لو استمر).

## الخطوة القادمة
- إضافة Sovereign (`claude-sonnet-5` عن طريق backend.sovereigneg.com)
  فعليًا لـ settings.yaml وتجربته على نفس صفحات 24-26 - الرن ده لسه
  من غير Sovereign خالص (rotating across: gemini, groq, openrouter بس).
- نقل تتبع `repeated_verbatim` لـ SQLite دائم بدل الذاكرة المؤقتة.



## 2026-09-05 (تكملة)

- **vision_fallback.py** — تسجيل `SovereignVisionBackend` تحت اسمين في
  `BACKEND_REGISTRY` (`sovereign` و`sovereign_2`) لدعم حسابين منفصلين
  عندك على نفس المنصة (رصيد EGP محدود بشهر واحد لكل حساب) - كل اسم في
  `rotation_order` بياخد سلوت مستقل بمفتاحه الخاص، فالدوران بيوزّع
  النداءات على الحسابين تلقائيًا بدل ما يحرق واحد بس.
- **ملاحظة:** كتابة نفس مفتاح YAML (`sovereign`) مرتين تحت `backends:`
  خطأ صامت - الـ parser بياخد آخر قيمة بس ويتجاهل الأولى من غير أي
  تحذير. الحل الصح: اسم مختلف لكل حساب.



  ## 2026-09-05 (تكملة 2)

- **باگ حقيقي:** بعد ما اتغيّرت أسماء متغيرات .env لـ GEMINI_API_KEY1/2،
  GROQ_API_KEY1/2 (بدل الاسم القديم من غير رقم)، `text_correction`
  section في settings.yaml فضلت بتأشّر على الاسم القديم (`GEMINI_API_KEY`,
  `GROQ_API_KEY`) اللي بقى مش موجود خالص - فهتتكسر أول ما يتشغّل
  review_manuscript.py. اتصلح بتحديث api_key_env لـ GEMINI_API_KEY1/
  GROQ_API_KEY1.
- **vision_fallback.py** — إضافة `groq_2` (نفس GroqVisionBackend) في
  BACKEND_REGISTRY - كان اتضاف `gemini_2`/`sovereign_2` قبل كده بس
  `groq_2` كانت ناقصة.
- **settings.yaml** — تحديث كل `api_key_env` في vision_fallback.backends
  للأسماء الحقيقية الجديدة في .env (بدون underscore قبل الرقم:
  GEMINI_API_KEY1/2، GROQ_API_KEY1/2، SOVEREIGN_API_KEY1/2).


  ## 2026-09-05 (تكملة 3)

- **تأكيد: Sovereign (claude-sonnet-5) شغال ونتيجته ممتازة.** أول
  escalation حقيقي عن طريقه أعطى "مقدمة" - نفس العنوان الحقيقي المؤكد
  بصريًا من صورة الصفحة، وبدون الأقواس الزائدة اللي كان يضيفها gemini
  في نفس الموضع بالظبط في رنّات سابقة. أنظف نتيجة على القصاصة دي حتى الآن.
- **اكتشاف معماري مهم:** نظام الـ round-robin الحالي بيوقف عند أول رد
  ينجح الـ validation، مش أول رد صحيح. بما إن openrouter تقريبًا
  مايرفضش خالص (بيخمّن دايمًا) بينما gemini/groq/sovereign بيرفضوا
  بأمانة على القصاصات الغامضة، فـ openrouter بيسرق الفوز من backends
  أدق كل ما دوره ييجي قبلهم في السايكل - زيادة عدد الـ backends وحدها
  متكفيش، الترتيب في rotation_order بيفرق فعليًا في الدقة النهائية.
  الحل: نقل openrouter لآخر rotation_order (ملاذ أخير بس، مش أولوية).
- **ملاحظة متكررة:** repeated_verbatim لسه per-run (in-memory) - نفس
  القيد اللي اتسجل قبل كده، لسه محتاج نقله لـ SQLite دائم.

## الخطوة القادمة
- بعد تعديل الترتيب، شغّل --start 24 --end 26 تاني وقارن: هل sovereign
  دلوقتي بياخد فرصة أكتر (وبالتالي نتايج أنضف) بدل ما openrouter يسبقه؟


  