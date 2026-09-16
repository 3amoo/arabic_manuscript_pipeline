# AGENTS.md — عقد تشغيل خطّ إنتاج المخطوطات العربية

> هذا الملف **عقد تشغيل للوكيل** وليس مجرد توثيق. يُميّز بوضوح بين: ما هو **مطبَّق الآن**، وما هو **ممنوع**، وما هو **مطلوب عند المهمة فقط**، وما هو **خارطة مستقبلية**.
> اقرأ `baseline/BASELINE.md` مرة واحدة قبل أي تعديل — هو اللقطة المرجعية للجودة الحالية وأساس أي مقارنة لاحقة.

---

## 1) Project Identity — من هو المشروع

- يحوّل هذا المشروع **PDF المخطوطات العربية المشكولة** إلى نص رقمي مهيكل (شعر/نثر/عناوين) مع **الحفاظ على التشكيل قدر الإمكان**.
- المفهوم المحوري: تحويل PDF→نص هو **Reverse Engineering**. الـ PDF مشفَّر للعرض مثل كتاب. إذا كانت خريطة `ToUnicode` سليمة فُكّ التشفير مباشرة (أسرع وأصح من أي OCR)؛ أما صفحات الصور فيجب رسمها ثم معالجتها ثم تحليلها ثم قراءتها.
- الخطأ الأشهر في المشاريع التقليدية: **القفز من الاستلام مباشرة إلى OCR** متجاهلًا Layout Analysis والـ Preprocessing التكيفي — الناتج «حساء حروف». هذا المشروع لا يفعل ذلك، ولا يُسمح لأي تعديل أن يجعله يفعل.
- **المبدأ الحاكم: OCR ≠ Editing.** النظام يستعيد ما *في الصفحة*، لا ما يعتقد أنه «صحيح».

---

## 2) Source of Truth — مصادر الحقيقة

| المصدر | نوعه | الاستخدام |
|---|---|---|
| `AGENTS.md` + **الكود الفعلي** + `settings.yaml` + `prompts.yaml` | **الحقيقة الحالية** | أي مهمة/قرار/تنفيذ يُبنى عليه |
| `CHANGELOG.md` | **سرد تاريخي** | قد يحتوي أشياء لم تعد صحيحة بعد التعديلات — لا يُعامل كحالة حالية |
| `baseline/` | **دليل ثابت (immutable evidence)** | للمقارنة فقط — **لا يُعدَّل ولا يُحذف** |

قاعدة تشغيلية: إذا تعارض «ما يقوله CHANGELOG» مع الكود الفعلي → **الكود هو الحقيقة**، وأبلغ عن الانحراف.

---

## 3) Current State — الحالة الحالية

القيم المسموحة لـ STATUS:

```
implemented  = مطبَّق ويعمل الآن — اقرأ الكود لفهم التفاصيل
partial      = مطبَّق لكن بقيوده المعروفة الموثّقة في الملاحظة
planned      = مرجع خطة — لا يُنفَّذ إلا بمهمة صريحة تطلب التطوير
blocked      = متوقّف حتى يتحقق شرط (تثبيت تبعية أو موافقة)
prohibited   = ممنوع تنفيذه مهما كانت المهمة
```

| المكوّن | STATUS | الحالة الفعلية الآن |
|---|---|---|
| Direct Text Extraction (فحص ToUnicode والـ garbage) | **implemented** | `pdf_text_extractor.py` — النسبة الدقيقة في §4.4 |
| توجيه صفحة-بصفحة «نصي/صوري» | **implemented** | `input_handler._load_pdf` لكل صفحة على حدة |
| Deskew → CLAHE → Denoise خفيف | **implemented** | `preprocessing.py` (نواة 3، خفيف عمدًا) |
| Binarization متعلِّم للتشكيل | **implemented** | `preprocessing.adaptive_binarize` (adaptiveThreshold كتلة 51) — يلغي نسختي Otsu المتعارضتين (§4.2) |
| OCR دفعاتي + Cache SQLite | **implemented** | `extract_segments_batch`، batch=16 لـ4GB، cache في `output/.cache` |
| تصعيد رؤية لأسطر الثقة المنخفضة | **implemented** | `vision_fallback.py` — **غير حتمي**؛ انظر سياسة الـ Vision §4.13 |
| `repeated_verbatim` دائم (SQLite عبر الركضات) | **implemented** | `repeated_verbatim_tracker.py` → `output/.cache/repeated_verbatim.sqlite3` |
| بنية الشعر ثنائي الشطر `يمين ... يسار` | **implemented** | حافظ على هذا التنسيق |
| 300 DPI افتراضي / حرف ≥30px | **planned** | التصيير الافتراضي الحالي دون 300 DPI |
| `PageQualityAnalyzer` (لون/كثافة تشكيل/إطارات) | **planned** | غير موجود |
| `detect_pdf_type` على مستوى الملف (TEXT/IMAGE/HYBRID) | **implemented** | `pdf_text_extractor.detect_pdf_type` يجمع أحكام الصفحات الفردية ويُعلِن صنف الملف (TEXT/IMAGE/HYBRID/UNKNOWN) في `_load_pdf` — HYBRID يُبلَّغ بصريح WARNING (§4.5)، والتوجيه الفعلي يبقى صفحة-بصفحة |
| Adaptive Binarization | **planned** | مرهونة بمهمة صريحة + قياس CER (§4.2) |
| Surya Layout / LayoutAnalyzer + Spatial reading-order | **planned** | مُثبَّت `surya-ocr 0.22.1` لكن **غير مفعَّل** (§13 Phase 2 — القياس §4.12)؛ `surya_line_detector.py` يستخدم `DetectionPredictor` فقط (لا VLM LayoutPredictor الذي يحتاج server)، ومفعّله صار جاهزًا (`available=True`، 20 bands على ص 24) عبر فلَبة `layout_detection.line_detector` في `settings.yaml` |
| إخفاء الزخارف/الإطارات بقناع قبل OCR | **planned** | غير موجود |
| حلقة ثقة صفحة <50% → إعادة معالجة | **implemented** | `process_page_image` يعيد المعالجة مرة واحدة بإعدادات Binarization أدق (block=31/c=5) عند صفحة ثقتها < 50% (§4.10) — الخيار في `ocr.page_confidence_reprocess` |
| `normalize_arabic_unicode` / `repair_arabic_spacing` | **planned** | غير موجود |
| CamelTools Token-verification | **partial** | `camel-tools 1.6.0` مثبَّت + `morphology-db-msa-r13` مثبَّت والتول يعمل فعلًا (`MorphologicalVerifier.available=True`؛ فحص: `عليكم` سليم ✔، `شسسسسش` مرفوض ✔؛ 89/394 كلمة على 24–26 → `review/suspicious_words.jsonl` — §8). **أداة مراجعة فقط** — الدمج داخل main.py (درس صورة-كلمة + مرشحين → نموذج رؤية) ما زال planned (§4.6) |
| Ensemble محلي Paddle vs Surya | **planned** | — |
| Bench CER/WER (`jiwer`) + Ground Truth | **partial** | الآلة جاهزة وتتحقق ميكانيكيًا (`evaluate_cer.py`)؛ الأرضية (GT) ناقصة — تتطلّب نسخًا يدويًا/نموذج رؤية (§8) |
| GPU/CPU fallback (ONNX/تشغيل متعدد) | **blocked** | `paddlepaddle-gpu` فقط |

---

## 4) Non-Negotiable Rules — القواعد غير القابلة للنقاش

> الأرقام أدناه مطابقة لتنفيذ الكود الحالي — لا تُغيَّر دلالاتها إلا بمهمة صريحة ومقاسة.

### 4.1 المعالجة المبالغ فيها تدمر النص العربي
لا تُستخدم عمليات Morphology (`erosion`/`dilation`) **افتراضيًا** على النص العربي، خصوصًا قبل OCR، لأنها تدمج نقاط الثاء/الشين بجسم الحرف وتطمس الكسرة.
**استثناء مسموح فقط عند الحاجة الانتقائية على أهداف غير مباشرة النص** (إزالة إطار خارجي، تنظيف بقع، فصل عناصر layout، صنع masks) — بشرط تجربة تثبت تحسّنًا في CER/WER دون ضرر على التشكيل. أي إدخال morphology بعده: سجّل CER/WER قبل/بعد.

### 4.2 حماية التشكيل عند الثنائية
- **مطبَّق الآن**: `preprocessing.adaptive_binarize` / `adaptive_binarize_gray` (adaptiveThreshold كتلة 51، `ADAPTIVE_THRESH_GAUSSIAN_C`) موحَّدة في موضع واحد، وتستخدمها `page_layout_detector.binarize()` و`segment_text_rows.binarize()` و`preprocessing._estimate_skew_angle` — تلغي نسخ Otsu الثلاث.
- انتبه: `layout.binarize()` تُرجع 0/255، بينما `rowseg.binarize()` تُرجع 0/1 — لا تخلط بينهما.
- ذراع إعداد: `block_size`/`c` افتراضيان (51/10)؛ أي ضبط لهما يلزمه قياس CER قبل/بعد (§4.12).

### 4.3 Deskew إجباري
قبل أي OCR. موجود: `deskew_page` (إسقاطي) في `preprocessing.py`. لا تُفحص أي صفحة بدون ميلان مُصحَّح.

### 4.4 النصي قبل الصوري (قاعدة الـ 85% — تعريف دقيق)
لكل صفحة على حدة، يجرب `pdf_text_extractor.py` أولًا. التعريف الدقيق للفحص (مطابق للكود):

```
usable-char        = حرف عربي أو لاتيني أو رقم أو علامة مقبولة
usable_char_ratio  = count(usable-char) / count(كل الأحرف غير whitespace)
```

- **تُرفض الطبقة النصية** (وتُسقَط الصفحة لمسار OCR) إذا تحقق أي مما يلي:
  - `length(stripped text) < 20` حرفًا، **أو**
  - `ratio < 0.85` (أي «garbage» يتجاوز 15% — معاملتها تحفظية لصالح OCR)، **أو**
  - `U+FFFD ratio > 0.02` (رموز الاستبدال = إشارة ToUnicode مكسور).
- صفحة بنسبة 84%؟ → تُسقَط لـ OCR. لا يوجد «قبول تقريبي».
- لا يتغير الـ implementation إلا بمهمة صريحة، ودائمًا مع قياس CER.

### 4.5 الهجين — تعريف رسمي
أصناف الـ PDF:

```
TEXT   → طبقة نصية قابلة للاستخدام → Direct Extraction
IMAGE  → صور بلا طبقة وحيمة → Render → تحليل → OCR
HYBRID → نص قابل للاستخدام + صور → لا يُوجَّه إنتاجيًا الآن
```

- **HYBRID**: غير مدعوم للتوجيه الإنتاجي؛ **لا يَسقط بصمت إلى OCR**، ويُبلَّغ عنه صراحةً (log واضح، لا صمت). الفحص الحالي تحفظي لصالح هذا.
- **التصنيف على مستوى الملف (مطبَّق)**: `pdf_text_extractor.detect_pdf_type` يجمع أحكام الصفحات الفردية إلى صنف واحد (TEXT إذا كل الصفحات نصوص قابلة للاستخدام / IMAGE إذا ولا صفحة / HYBRID إذا مختلط / UNKNOWN للفارغ) ويسجّله في `_load_pdf` بعد التحميل — **سطر دائم لكل ملف**، وعن HYBRID يأتي WARNING صريح (§4.5)، وتوجيه التشغيل الفعلي يبقى **لكل صفحة** وليس للملف.
- قرار «نصي/صوري» **لكل صفحة** وليس لملف كامل.

### 4.6 الحفاظ الأمين على النص (Faithful Reconstruction) — حجر الأساس
**الممنوع صراحةً على مستوى الفقرة/البيت**: إعادة كتابة بواسطة LLM لـ:
- تصحيح إملائي (spelling normalization) بمن في ذلك الإملاء التاريخي،
- إضافة/حذف علامات ترقيم،
- تعديل جماليّ/أسلوبي (stylistic correction)،
- توحيد الهمزات/التاء المربوطة من داخل النص،
- دمج أو تقسيم جمل،
- «اختراع» تشكيل غير ظاهر في الصورة،
- حذف تكرار يبدو «ظاهرًا».

**البديل المسموح فقط — Token-level**: كلمة مشكوك الثقة → محلل صرفي/قواميس → **صورة الكلمة + مرشحين** → سؤال نموذج رؤية: «اكتب الكلمة المطابقة للصورة فقط، بلا إضافات».
- ملاحظة توتر: `text_correction_engine.py` (مرحلة `review_manuscript`) يعيد كتابة نصوص؛ هي مرحلة **اختيارية منفصلة معطّلة افتراضيًا** ولا تدخل في الممر الأساسي.

### 4.7 القراءة كُتلًا لا كلمة-كلمة
بثّ الـ crops في دفعات (الهدف 32–64؛ الحالي 16 بسبب 4GB VRAM). لا تُمرَّر كلمة بكلمة. لا تُرفَع الـ batch بلا تجربة VRAM.

### 4.8 Cache إلزامية
كاش SQLite مفهرس بـ Hash لصورة الـ crop (`ocr_cache.py` → `output/.cache/ocr_cache.sqlite3`). **لا تُلغِ/لا تُغيِّر المفتاح**؛ العودة للصفحات المحسوبة مسبقًا مكسب كبير.

### 4.9 الشعر
اكتشاف الـ Gutter (فراغ عمودي) → فصل الشطر الأيمن والأيسر صورتين مستقلتين → OCR لكل شطر وحده → إعادة التركيب بالترتيب (يمين→يسار، أعلى→أسفل) بفاصل ` ... `. المخرج الحالي: `الشطر الأيمن ... الشطر الأيسر` — حافظ.

### 4.10 سياسة الثقة (منضبطة رقميًا)
- **مصدر الثقة**: عدد الحروف/الثقة القادمة من PaddleOCR (لكل كلمة/سطر/منطقة) **ومتوسطات النظام المحسوبة** — لا تخلط بينهما عند المقارنة.
- النطاقات (word/line):
  - `≥ 85` → **قبول** مباشر.
  - `65 – 84.99` → **مرشح للتصعيد/المراجعة**.
  - `< 65` → **تصعيد عالي الخطورة** (مطلوب دليل إضافي).
- صفحة: `page_confidence < 50` → **إعادة معالجة** بإعدادات Binarization مختلفة، ثم محاولة ثانية.
- **تعريف صفحة-الثقة (مطبَّق)**: متوسط مرجَّح بعدد الحروف لثقة الأسطر المُبقاة فقط (المستبعدة بـ noise filter لا تُحسب) عبر منطقتي الشعر/النثر معًا. تُكتب كنسبة مئوية في ترويسة الصفحة (`# Page Confidence`) مع `# Binarization Attempt` (1 أو 2).
- ذراع إعادة المعالجة: `preprocessing.set_binarize_params(block_size=31, c=5)` عبر `ocr.page_confidence_reprocess` في `settings.yaml` — يُستدعى قبل المحاولة الثانية ويُعاد ضبطه بعدها. عند تعادل أو تدهور النتيجة الثانية تُحتفظ الأولى ويُتجاهل سجل تصعيدها.

### 4.11 ترتيب القراءة والتخطيط
حلِّل Layout قبل OCR. الهدف: وحدة Layout مستقلة تُصنّف (عنوان/فقرة/حاشية/شعر/زخرفة/إطار)، وتُخفي الزخارف/الإطارات بقناع قبل OCR كي لا تُقرأ «حروفًا». ترتيب القراءة: يمين→يسار، أعلى→أسفل.

### 4.12 القياس إجباري
أي تحسين يمس OCR/المعالجة المسبقة يلزمه CER/WER (`jiwer`) ضد أرضية صحيحة (Ground Truth) لصفحات مرجعية + Layout Accuracy. «شكلي أفضل» بلا أرقام **لا يُقبل دليلًا**.

### 4.13 سياسة الـ Vision (المصعد الاحتياطي)
- **ناتج الـ Vision ليس سلطةً بذاته، أبدًا.**
- التسلسل المعتمد: نتيجة OCR → نتيجة Vision → مقارنة/دليل/ثقة → **قبول token-level فقط**.
- لا يُستبدَل ناتج OCR بنص Vision لمجرد أنه «يبدو أفضل». هدف المشروع **النسخ الأمين**، لا «أحسن نص عربي».
- **بوابات القبول الإلزامية قبل أي استبدال بنص Vision (مطبَّقة في `main.py` — القرار النقي في `_evaluate_escalation()`, والغلاف المتكامل في `_maybe_escalate_line()` + `_should_escalate_line`):**
  1. **لا تصعيد لخط ضجيج**: أي سطر قرأته PaddleOCR كضجيج فقط (بلا حرف عربي حقيقي: `..wmmw.`، `ww`، `ـــ`، صفحة فارغة) **لا يُرفَع للـ Vision أبدًا** — كان هذا ناقل الهلوسة الموثّق حيث يعيد النموذج بيتًا بلاغيًا مشهورًا كاملًا مقابل crop شبه فارغ (مطلع معلّقة امرئ القيس على صفحات 20–27).
  2. **رفض `repeated_verbatim` العابر للـ crops**: نص Vision أصبح علامة تكرار حرفي عبر الـ SQLite (`repeated_verbatim_tracker.py`، أي عاد بحرفه لـ crop آخر أو ركضة سابقة) هو **تخمين أنيق** وليس قراءة لهذا الـ crop بدقة — **لا يُستبدَل به نص OCR**، بقي نص OCR كما هو، لكنه **يُسجَّل في escalations للمراجعة** كي يراها المراجع (`reason: repeated_verbatim_cross_crop`).
  3. **رفض صدى OCR (echo)**: نص Vision عاد حرفيًا (modulo whitespace) بنفس نص OCR الخاطئ — «تصعيد» بلا أية معلومة = فشل فعلي للـ backend — يُرفض ولا يُسجَّل كتحسين (`reason: echoed_ocr`).
  - **نجاح الـ Vision الحقيقي** (غير مكرر وغير صدى) يُقبَل ويُهجّر نص OCR في المخطوط — كل المحاولات الحقيقية للـ Vision (مقبولة ومرفوضة) تُسجَّل في `escalations.jsonl` بحقلَي `accepted` و`reason`؛ وحدة الاختبارات `tests/test_escalation_policy.py` (stdlib unittest) تغطّي كل البوابات.
- معلومة قائمة: الـ Vision **غير حتمي** بين الركضات، ومعرَّض لـ 429 وrefusals، وقابل للهلوسة — لكن الهلوسة المستهدفة أعلاه أصبحت مرفوضة من الإخراج (لا تظهر في نصوص الصفحات) مع بقائها مرئية في `escalations.jsonl`.

---

## 5) Architecture — المعمارية الحالية (Flat)

> المشروع **مسطّح**: كل الوحدات في الجذر جنب `main.py`. مجلد `src/` أُزيل (كان تكرارًا مطابقًا). **ممنوع** إعادة إنشائه و**ممنوع** إعادة `sys.path.insert`.

ممر الإنتاج الأساسي (`main.py`):
1. `input_handler.py` — اكتشاف ملفات `input/`، لكل صفحة: `direct_text` اختياري + صورة مرسومة (BGR) + metadata (rotation/rect).
2. `pdf_text_extractor.py` — فحص الطبقة النصية لكل صفحة (تعريف §4.4).
3. `preprocessing.py` — `deskew_page` → `apply_clahe` → `denoise_light`.
4. `page_layout_detector.py` — بنية verse/prose/full_width + مناطق الشعر/النثر.
5. `segment_text_rows.py` — تقسيم الأسطر.
6. `ocr_engine.py` — `extract_segments_batch`: كاش SQLite → دفعات PaddleOCR (16) → كتابة إلى الكاش.
7. `vision_fallback.py` — تصعيد أسطر الثقة المنخفضة عبر الـ backends (Claude/Gemini/Groq/OpenRouter/Cohere/GitHub Models + sovereign/sovereign_2) بحد 3000 نداء مشترك.
8. `output_generator.py` — حفظ تدريجي + `full_manuscript.txt` + `review/escalations.jsonl`.

مرحلة ثانية منفصلة (لا تعمل ضمن `main.py`):
- `review_manuscript.py` + `text_correction_engine.py` — مراجعة/تصحيح (اختياري، معطّل افتراضيًا).
- `morphological_verifier.py` + `flag_suspicious_words.py` — فحص صرفي (يعمل الآن: camel-tools 1.6.0 + r13 مثبَّتان — §3، §8).
- `surya_line_detector.py` — بديل تقسيم أسطر (**مثبَّت لكن معطّل افتراضيًا**: `layout_detection.line_detector` غير موجود في `settings.yaml` — تفعيله ينتظر قياس CER §4.12).
- `sync_vision_backends.py` — مزامنة الـ backends (افتراضياته كانت تشير إلى `config/settings.yaml` المحذوف).

الإعداد: `settings.yaml` + `prompts.yaml` في **الجذر فقط** (`config/` محذوف — لا تُعِد إنشاءه). ملاحظة: أنماط `analysis.*`/`review.*` غير مسكونة من الكود.

---

## 6) Data Flow & Lineage — تدفق البيانات وخط النسب

```
source image / text layer
        ↓
  raw OCR  (خط الطبقة الأصل)
        ↓
  fallback OCR (Vision، عند الثقة المنخفضة)
        ↓
  candidate
        ↓
  verified token
        ↓
  reviewed text  (مرحلة اختيارية منفصلة)
```

**قاعدة صريحة — Never overwrite raw OCR evidence:**
- `raw_text/page_NNN.txt` هي **طبقة الدليل الأصل** القابلة للقراءة الآلية.
- لا تُستبدَل هذه الطبقة بنتائج أي مرحلة لاحقة (تصعيد، تصحيح، تطبيع، إعادة OCR).
- أي إخراج محسَّن يُكتب في **طبقة منفصلة** (`corrected_text/` ونحوها)، مع بقاء المرجع الأصلي كما هو.

---

## 7) Output Contract — عقد المخرجات

| المخرج | المسار | الحكم |
|---|---|---|
| الصفحات الخام | `output/<وثيقة>/raw_text/page_NNN.txt` | **دليل لا يُكتب فوقه** (§6) |
| المستند الكامل | `output/<وثيقة>/full_manuscript.txt` | يُعاد بناؤه من الصفحات الخام |
| سجل التصعيد | `output/<وثيقة>/review/escalations.jsonl` | append-only |
| طبقات محسّنة | `corrected_text/` ونحوها | مفصولة دائمًا عن الخام |

- تنسيق الشعر: `الشطر الأيمن ... الشطر الأيسر` (لا تُغيّره بلا طلب صريح).
- **لا تُكتب secrets في أي مخرج** (راجع §10).

---

## 8) Quality & Metrics — القياس

- CER/WER عبر `jiwer` ضد أرضية صحيحة يدوية (Ground Truth) لصفحات مرجعية — **الآلة جاهزة**: `evaluate_cer.py` (متحقق عليها ميكانيكيًا بـ `verify_cer_harness.py` + `tests/test_cer_normalization.py`)، والواجهة المُساعدة لإنتاج الأرضية جاهزة: `bootstrap_ground_truth.py` (يرسم الصفحة 300 DPI + يضع placeholder `# GT-PENDING` — الترجمة نفسها تتطلب نسخًا يدويًا/نموذج رؤية، والأرضية نفسها **ناقصة**: `ground_truth/<doc>/page_NNN.txt` للصفحات 24–26 ضمن `ground_truth/README.md`). عند إضافة GT: `myenv/bin/python evaluate_cer.py --document "عمود النسب نسخة 2" --pages 24-26`.
- Layout Accuracy: نسبة تمييز المتن/الحاشية/الشعر/العناوين.
- المرجع الرقمي الحالي: `baseline/metrics/output_metrics_24_26.txt` ومنهج التقييم في `baseline/BASELINE.md` §7.
- أي ادعاء «تحسّن» بلا قياس = مرفوض (انظر §4.12).

---

## 9) Hardware Constraints — قيود الأجهزة

| البند | القيمة | الأثر العملي |
|---|---|---|
| الجهاز | Dell G15 5510 | — |
| نظام | Void Linux x86_64 / KDE Plasma 6.7.4 / Kernel 6.12.41_1 | إدارة حزم عبر `xbps` (ليست apt)؛ لا تفترض pip خارج الـ venv |
| CPU | i5-10200H (8 خيوط) @ حتى 4.10GHz | التعدد يصل ~8 عمليات |
| GPU | **GTX 1650 Mobile/Max-Q — 4GB VRAM فقط** | `segment_batch_size = 16` افتراضيًا في `settings.yaml`؛ لا ترفعه بلا تجربة VRAM |
| GPU2 | Intel UHD 610 (مدمجة) | لا تُستخدم لـ OCR |
| RAM | 15.4 GB | حد أقصى معقول |
| Python | `myenv/bin/python` = **3.11.16** | **ممنوع** Python النظام (3.14.7) |

التبعيات المعتمدة: `paddleocr 3.7.0` + `paddlepaddle-gpu 3.2.0` (GPU فقط) + `paddlex 3.7.2` + `pymupdf 1.28.2` + `opencv` + `google-generativeai 0.8.6` + `groq` + `openai 2.54.0` (نُزِّلت من 3.3.1 عند تثبيت surya — متوافقة مع كل استخدامات `chat.completions`) + `anthropic` + `cohere` + `ruamel.yaml` + `torch 2.13.0` + `jiwer 4.0.0` (قياس CER/WER، §8) + `surya-ocr 0.22.1` (مثبَّت، غير مفعَّل — §3) + `camel-tools 1.6.0` + `morphology-db-msa-r13` (مثبَّتان — §13 Phase 4).
قاعدة تثبيت بيانات camel: `myenv/bin/camel_data -i morphology-db-msa-r13`.

**تحذير pip**: كان `myenv/bin/pip` يشير إلى venv شقيق خاطئ
(`/home/omar/Desktop/arabic_manuscript_pipeline/myenv`) فتُثبَّت التبعيات في
المكان الغلط — **أُصلح 2026-09-06** (صارت تشير إلى venv المشروع). الصيغة
الموثوقة للتثبيت: **`myenv/bin/python -m pip install ...`** (ليست
`myenv/bin/pip install ...`). لاحظ أيضًا أن `myenv/pyvenv.cfg` وراثة غريبة
(تنص على `python3.14`) رغم أن المفسِّر الفعلي `myenv/bin/python` = 3.11.16 —
المشروع يعمل على 3.11 ولا تغيير.

---

## 10) Security — الأمان

- `.env` يحتوي **مفاتيح API حقيقية** (Gemini/Groq/OpenRouter/GitHub PAT/Cohere/Sovereign). **ممنوع**: طباعته، قراءته، عرضه في diff، أو تضمينه في أي مخرَج. هو في `.gitignore` ولا توجد له نسخة في الـ remote (تحقق أمني مؤكد).
- عند الحاجة للمفاتيح استقرئها من `settings.yaml`/`sync_vision_backends.py` ونص الاختبار فقط — **لا تفتح `.env`**.
- لا تُلتزِم/لا تدفع/لا تعمل PR إلا بطلب صريح.

---

## 11) Validation — التحقق و Definition of Done

أوامر التشغيل (من جذر المشروع):
```bash
myenv/bin/python main.py                                # كامل input/
myenv/bin/python main.py --start 24 --end 26            # نطاق صفحات للتجارب
myenv/bin/python -m unittest tests.test_escalation_policy -v   # سياسة الـ Vision (§4.13)
myenv/bin/python -m unittest tests.test_cer_normalization -v   # تطبيع قياس CER/WER (§8)
myenv/bin/python verify_cer_harness.py                  # فحص ميكانيكي لآلة القياس (§8)
myenv/bin/python evaluate_cer.py --document "عمود النسب نسخة 2" --pages 24-26   # بعد إضافة GT (§8) — exit 2 طالما الـ GT placeholder فقط
myenv/bin/python bootstrap_ground_truth.py --document "عمود النسب نسخة 2" --pages 24-26   # يجهّز صور 300 DPI + placeholders للـ GT (§8)
myenv/bin/python review_manuscript.py --document "عمود النسب نسخة 2"
myenv/bin/python flag_suspicious_words.py --document "عمود النسب نسخة 2"   # يعمل الآن (REVIEW_ONLY)
myenv/bin/python sync_vision_backends.py
```

### Definition of Done — التعديل لا يُعَد «منتهيًا» إلا إذا:
1. الملفات المتأثرة تمر `myenv/bin/python -m py_compile`.
2. ركض نطاق فعلي صغير (`--start 24 --end 26`) نجاحًا بـ `exit 0`.
3. المخرجات وُلِّدت في مكانها الصحيح.
4. **لا تغيير في `baseline/`** (immutable).
5. سلوك الكاش محفوظ (لم يُلغَ / لم يتغير مفتاحه).
6. **لا تسريب أسرار** في أي مخرج/سجل.
7. `CHANGELOG.md` حُدِّث عند تغيير سلوك مرصود.
8. **قياس CER/WER** أُنجز لكل تغيير يمس OCR/المعالجة المسبقة.
9. عند أي فارق بصري: قورنت أسطر PaddleOCR الخام مع `baseline/execution/output_24_26/` — مع تنبيه أن أسطر تصعيد الرؤية (Vision) غير حتمية بين الركضات، فيُقارَن فقط ناتج الكاش الحتمي.

### Change Classification — ما الاختبارات المطلوبة لكل نوع تغيير

| نوع التغيير | الاختبار المطلوب |
|---|---|
| `OCR_BEHAVIOR` | ركض عيّنة OCR + CER/WER |
| `LAYOUT` | ركض عيّنة + فحص البنية (verse/prose/full_width) |
| `PREPROCESSING` | ركض عيّنة + CER/WER + فحص التشكيل |
| `OUTPUT_FORMAT` | مقارنة لقطة (snapshot) قبل/بعد |
| `PERFORMANCE` | قياس runtime + VRAM |
| `INFRASTRUCTURE` | `py_compile` + smoke على الاستيرادات |
| `REVIEW_ONLY` | مراجعة/فحص مخرجات فقط — بلا ركض واجب |

---

## 12) Known Issues — قيود معروفة (لا تُعاد اكتشافها)

- القياس (§8): آلة CER/WER جاهزة (`evaluate_cer.py` + `jiwer 4.0.0` مثبت في venv المشروع) لكن **أرضية GT صحيحة غير موجودة بعد** — إنتاجها يتطلب نسخًا يدويًا أو نموذج رؤية (نماذج الجلسات الحالية بلا مدخل صور).
- `camel-tools 1.6.0` + `morphology-db-msa-r13` **مثبَّتان ويعملان** (§3، §13 Phase 4): `flag_suspicious_words.py` يُنتج `review/suspicious_words.jsonl` فعلًا (REVIEW_ONLY — لا يدخل في ممر الـ OCR). دمج الـ Token-verification داخل main.py (العقد §4.6) ما زال planned.
- `surya-ocr 0.22.1` **مثبَّت ومفعّله جاهز** (`SuryaLineDetector.available=True`، 20 bands على ص 24 — §13)، لكن `layout_detection.line_detector` غير موجود في `settings.yaml` → مجرى التفكير الكلاسيكي يعمل كما هو. تثبيت surya خفَّض `pillow` (12.3.0→10.4.0) و`opencv-python-headless` (5.0.0.93→4.11.0.86) و`openai` (3.3.1→2.54.0) — كل الاستخدامات المتأثرة فُحصت سليمًا (GPT: `chat.completions` لكل backends) وركض `--start 24 --end 26` exit 0 بنفس النتائج. تفعيل surya يغيّر سلوك OCR → يلزمه قياس CER (§4.12).
- تصعيد الرؤية **غير حتمي** + حصص 429 خارجية؛ `repeated_verbatim` **دائم الآن** عبر `repeated_verbatim_tracker.py` (SQLite في `output/.cache/`).
- `paddlepaddle-gpu` فقط (لا نسخة CPU) — المشروع يحتاج GPU لتشغيل OCR.
- جودة الصفحات الخام ضعيفة (أمثلة موثقة في `baseline/BASELINE.md` §3)؛ أسطر الضجيج (مثل `..wmmw.`، `ـــ`) تُفلتر الآن عبر `_is_noise_line()` (بلا حرف عربي حقيقي) + `_is_repetitive_garble()` (بنية تكرار الحرف الواحد: `شسسسسش` → صحيح عربيًا لكنه جمعيًا حرف/حرفان مكرران — لا يُقرأ). أُعيد فحص السلة على كامل الـ corpus الحالي: إصابة واحدة (`شسسسسش` ص 20) وصفر نتائج إيجابية كاذبة؛ يجب تكرار هذا الفحص عند أي توسيع للقاعدة.
- هلوسة الـ Vision الشهيرة (`وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...` على صفحات 20–27) **مُعالَجة**: لا تصعيد لخطوط الضجيج، ولا قبول لـ `repeated_verbatim` (§4.13). لا تزال الهلوسات غير المتكررة على كروبات ضعيفة وسيلة خطورة قائمة — تُسجَّل في escalations للمراجعة ولا تُكتشف آليًا بعد.

---

## 13) Roadmap — خارطة الطريق (ليست قائمة تنفيذ)

> **The roadmap is not an execution queue.** لا تُنفَّذ بنود الخارطة إلا إذا كانت المهمة الحالية تطلبها **صراحةً**. كل بند فيها STATUS=planned/blocked حتى تُكلف به.

**Phase 1 — أثر عالٍ / تكلفة قليلة:**
- ~~دالة ثنائية تحمي التشكيل~~ (**مُنجَزة**) — `adaptive_binarize` في `preprocessing.py` / `adaptive_binarize_gray`، موحَّدة في موضع واحد (تلغي نسخ Otsu الثلاث). باقي: قياس CER (§4.12).
- ~~فلتر أسطر الضجيج~~ (**مُنجَز**) — `_is_noise_line()` يستبعد الآن أي سطر بلا حرف عربي حقيقي (رفض التطويل/الحركات/الأرقام/اللاتيني).
- ~~إزالة كود DEBUG في `ocr_engine.py` + تنظيف `debug/`~~ (**مُنجَز**) — حُذف، وشُطب مجلد `debug/`.

**Phase 2 — بنية وسيط (ترقية):**
- ~~تثبيت `surya-ocr`~~ (**مُنجَز 2026-09-06**) — مثبَّت (0.22.1) + `SuryaLineDetector` جاهز (`available=True`)، ومفتاح التفعيل `layout_detection.line_detector: "surya"` موثّق في `settings.yaml` لكنه **غير مفعَّل**؛ يبقى كذلك حتى قياس CER (§4.12). عند التفعيل: اكتشاف الأسطر عبر `DetectionPredictor` للبنى المعقدة/الأعمدة مع إبقاء Paddle للقراءة.
- كشف Gutter هندسيًا على الـ Bounding Boxes، وعزل الزخارف/الإطارات بقناع قبل OCR.
- رفع DPI الافتراضي إلى 300 وفك الثوابت المرتبطة بـ 200.
- ~~جعل `repeated_verbatim` دائمًا~~ (**مُنجَز**) — `repeated_verbatim_tracker.py` (SQLite بدل ذاكرة الجلسة)، متصل بـ `vision_fallback.py` عبر `repeated_verbatim_db` في `settings.yaml`.

**Phase 3 — نظام الثقة/التوسّع:**
- ~~Confidence كلمة→سطر→صفحة مع حلقة إعادة معالجة للصفحات <50%.~~ (**مُنجَز**) — `_aggregate_page_confidence` (متوسط مرجَّح بعدد الحروف للأسطر المُبقاة) + إعادة معالجة مرة واحدة عبر `set_binarize_params` عند `page_confidence < ocr.page_confidence_reprocess.threshold` (§4.10).
- Ensemble محلي Paddle vs Surya على عينة، واعتماد الأفضل.
- ~~إضافة Qwen-VL-Chat محلي/مجاني كـ backend آخر.~~ (**مُنجَز**) — `QwenVLBackend` في `vision_fallback.py` (Ollama OpenAI-compatible، موديل افتراضي `qwen2.5vl:7b`، بلا مفتاح API). **غير مُفعَّل افتراضيًا** — سطر `- qwen_vl` في `rotation_order` معلّق في `settings.yaml`؛ آمن حتى على آلة بلا Ollama (فشل سريع ثم خروج من الدوران).

**Phase 4 — اللغة والقياس (مستقبلي):**
- ~~تثبيت `camel-tools` + القاعدة الصرفية~~ (**مُنجَز 2026-09-06**) — 1.6.0 + `morphology-db-msa-r13` مثبَّتان (`myenv/bin/camel_data -i morphology-db-msa-r13`) و`flag_suspicious_words.py` يعمل (REVIEW_ONLY — §3، §8). المتبقي: تفعيل Token-verification داخل main.py (درس صورة-كلمة + مرشحين → نموذج رؤية، العقد §4.6).
- `normalize_arabic_unicode` و`repair_arabic_spacing`.
- Dataset أرضية صحيحة (50 صفحة صعبة: شعر/عناوين/حواشٍ) + سكربت `jiwer` (CER/WER) + Layout Accuracy — يُعمل بعد كل تعديل.
- (طموح) Fine-tuning لـ PaddleOCR على الخطوط التراثية.

---

## 14) CHANGELOG Policy — سياسة السجل

- `CHANGELOG.md` = **سرد تاريخي** للسلوك المرصود (بالعربية، بنمط المستند) — ليس «الحالة الحالية» (انظر §2).
- سجّل فيه عند تغيير سلوك مرصود أو عند طلب صريح.
- `baseline/` = **دليل ثابت**: لا يُعدَّل ولا يُستخدم كمرجع للحالة الحالية، بل للمقارنة فقط.
- عند بدء مهمة تحسين: اقرأ أولًا `baseline/BASELINE.md` §6 (فرص) و§7 (منهج التقييم)، ثم نفّذ بقياس CER/WER قبل وبعد.