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

## حاجات معروفة لسه محتاجة شغل (Backlog)

دي مش تم عملها، بس اتكتبت هنا عشان متتنساش وتبقى معروفة كسياق:

- ~~Direct text extraction للـ PDF النصي~~ — **تم (2026-09-01)**، شوف فوق.
- ~~Batch OCR للـ line crops~~ — **تم (2026-09-01)**، شوف فوق.
- ~~Caching (SQLite/hash-based)~~ — **تم (2026-09-01)**، شوف فوق.
- **اكتشاف النص الملون (العناوين الحمراء عبر HSV)**: مش موجود، كل حاجة بتتعمللها binarize مباشرة.
- **Token-level verification بمحلل صرفي (CamelTools/Farasa) + قاموس بدائل**: البديل الحالي escalation سطر كامل لموديل رؤية، مش كلمة واحدة مشكوك فيها + قاموس.
- **CER/WER benchmarking (jiwer) على ground truth حقيقي**: لسه مفيش. الجزء اللي عمله كلود من الكتاب **مقرر عمدًا إنه ميتستخدمش كـ ground truth آلي** — استخدامه محصور في مراجعة بشرية/spot-check يدوي بس، لحد ما يتعمل dataset حقيقي (~50 صفحة) بـ ground truth يدوي فعلي.

---

### طريقة الاستخدام
لما تبدأ محادثة جديدة، اعمل attach للملف ده (+ الكود لو محتاج) وقول للموديل يقرا الـ Backlog والتاريخ الأخير الأول قبل ما يقترح حاجة جديدة، عشان ميقترحش حاجة مكررة أو يتجاهل قرار اتاخد قبل كده (زي موضوع الـ ground truth بتاع كلود).