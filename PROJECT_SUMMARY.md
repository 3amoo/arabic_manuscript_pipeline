# خلاصة المشروع المفصّلة — مراجعة عميقة للمرجعية والبيانات (2026-09-06)

> **الغرض**: مراجعة **تفصيلية** لكل وحدات المشروع (`myenv`-قابل للتشغيل، مسطّح)، مدعومة بالأدلة من الكود والمخرجات الفعلية والـ Baseline، وتلخيصها في وثيقة واحدة.
> **المصادر**: قراءة كاملة لأعضاء الخط الرئيسي + أدوات المرحلة الثانية + `settings.yaml`/`prompts.yaml`/`CHANGELOG.md` + عينات مخرجات (صفحات 1–4، 24–26، 107، 113) + `baseline/metrics/output_metrics_24_26.txt`.
> **الحكّام**: `AGENTS.md` (الحقيقة)، `baseline/BASELINE.md` (لقطة ثابتة)، `CHANGELOG.md` (سرد تاريخي — قد يخالف الكود).
> **تحقق**: `myenv/bin/python -m py_compile` على كل الملفات العشرين → سليم (`PY_COMPILE_OK`).

---

## 0) ملاحظة منهجية (اقرأ أولًا)

- **لا تطابقٍ بين `baseline/BASELINE.md` §4 والكود الحالي**: BASELINE.md لقطة مجمّدة بتاريخ 2026-09-05 تصف بنية **قبل** إزالة `src/` (كان يعرض شجرة `src/` + `sys.path.insert` + استيرادات هجينة). بعد الإزالة صارت البنية **مسطّحة تمامًا**. BASELINE.md **لا يُعدَّل** (immutable) — وثيقته المرجعية الحالية `AGENTS.md` §5.
- **دليل الترتيب الزمني**: `CHANGELOG.md` يصف تغييرات تصل لـ 2026-09-05؛ تسلسل التغييرات بعد baseline هو: Dedup (`src/`→جذر) ← إعادة كتابة `AGENTS.md` ← يتبع ذلك إصلاحات وُثّقت في الكود نفسه.
- **المركزي**: الكود الفعلي > أي وصف (انظر §1–§7 أدناه تلتزم بالكود كما هو الآن).

---

## 1) نبذة المعمارية الحالية (بالتفصيل)

الخط (من `main.py`):

```
input/عمود النسب نسخة 2.pdf (113 صفحة، بلا نصياً)
  │  input_handler._load_pdf() — لكل صفحة:
  │    • extract_direct_text(page) → فحص نصي تحفظي (pdf_text_extractor.py)
  │    • render 200 DPI → BGR numpy + metadata (rotation/rect)
  │  main.process_document():
  │    • لو direct_text صالح → save_page بـ ocr_method=direct_extraction (يتجاوز كل شيء)
  │    • وإلا: preprocess_page() = deskew → CLAHE → denoise_light
  │  process_page_image() = layout:
  │    • layout.binarize Otsu → dilate_text → find_components
  │    • remove_border_components + remove_page_footer_components
  │    • compute_content_bbox → find_footnote_boundary (3 إشارات + تسجيل)
  │  extract_poetry_region() / extract_prose_region():
  │    • rowseg.binarize (Otsu، عقد 0/1) → remove_edge_frame_lines
  │    • detect_gutter (شعر) / classify_line → verse_row | full_width | rule
  │    • _detect_line_bands ← Surya (اختياري/غير مثبت) أو row-projection klassike
  │    • split_oversized_lines (شبكة أمان للأسطر الملتصقة)
  │  PASS 1: قصّ كل الأسطر → PASS 2: extract_segments_batch (دفعة واحدة)
  │    • OCRCache (SQLite، blake2b بصورة+shape+dtype+اسم الموديل)
  │    • _run_paddle_batch: rec_only.predict() دفعات segment_batch_size=16
  │    • vision_fallback (اختياري): escalation للثقة < 0.55 + rotation عبر backends
  │    • فلتر noise (_is_noise_line) + إعادة compute بعد التصعيد
  └─ output_generator.save_page() → raw_text/page_NNN.txt + إعادة بناء full_manuscript.txt من raw_text على القرص (2026-09-09)
```

**تفاصيل صحيحة تستحق الحفظ (من الكود):**

1. **Deskew إجباري وأول** (`preprocessing.py:13-16`): وثيقة سبب — كل الكاشفين السفليين يفترضون أسطرًا أفقية.
2. **حدود الإطار/السفلي تُزَال قبل content_bbox**: ثلاث حالات متميزة اتُّخذت من خلال debug حقيقي في `page_layout_detector.py`:
   - إطار مكسور (مقطع 650px من 1769px) → `is_edge_border_strip` (متعلق بالحافة + نسبة أبعاد عالية + طول أدنى)،
   - blob محتوى طويل/ضخم (وصل 94%×91% من الصفحة بسبب dilation) → `_touches_all_four_edges` (لاستبعاد الحدود الزائفة)،
   - رقم صفحة أسفل (`is_page_footer_component`) → لمنع تسرب فهرس إلى `content_bbox` (كان هذا خلط footnote boundary في صفحة حقيقية).
3. **تمييز footnote = 3 إشارات مرتبطة بالتسامح**: فجوة أفقية + خط فاصل (مورفولوجيا + محيط) + نص أصغر أدناه؛ **تسجيل درجة ≥2** مطلوب للقص، وربط تعادل يُوصَل لصالح الأسفل (حفظ المزيد من المحتوى).
4. **القراءة RTL صحيحة**: `_reorder_rtl` في `ocr_engine.py:124-185` يعيد ترتيب baked boxes يمين→يسار ضمن الصف، باستخدام **وسيط ارتفاع المنطقة** (وليس ارتفاع box) كتسامح للقسيمة — أُصلح مشكلة `-` المنقسم في صف منفصل.
5. **قصّ التصрыв per-line داخل prose** (`main.py:314-327`): قصة حقيقية مثبتة — قصّ عريض/قصير جدًا في `extract()` (طول قصير يُمطّ حتّى 960) → هلوسة كاملة؛ القصّ per-line يمنع ذلك.
6. **batch عازلة مع Padding دفاعي** (`ocr_engine.py:415-425`): إذا رجع predict أقل عددًا للنتائج، يُملَّأ الناقص بفارغ بعدّم ألا يزحف اصطفاف النتائج.
7. **إعادة حساب noise بعد التصعيد** (`main.py:221-224`): إعادة `likely_noise` على نصvision — إذن النص الهلاوسي المكرر قد يُفلتر صوتيًا، ولم يمرّ (flagged فقط).
8. **منطقة فارغة → لا OCR إطلاقًا** (`main.py:396-407`): blank_or_unclear تُحتسب صفحة فارغة وعلامة للإنسان (كان OCR يهلِّج ضجيجًا من شريط زخرفي).

---

## 2) مراجعة الوحدات (تفصيلية — نقاط قوة/عيوب/مخاطر)

| الملف | الدور | نقاط قوة | عيوب/مخاطر (بملف:سطر) |
|---|---|---|---|
| `main.py` | Orchestrator | توجيه per-page؛ batching مرحلتين؛ حفظ تدريجي؛ نطاق `--start/--end` | `extract()` لا يُستدعى — `confidence=100.0` ثابت (فخ كامن)؛ `structure='verse'` حتى لو كل الأسطر noise |
| `input_handler.py` | تحميل + فحص نصي + render | `direct_text` لكل صفحة؛ تصاريح لصفحة بدون نصية (`direct_text: None` منسّق) | `find_all_files()` يبحث uppercase/lowercase؛ لا معالجة `page_count` بالأيقونة |
| `pdf_text_extractor.py` | فحص ToUnicode/الصفحة | تعريف دقيق (20 حرف، نسبة ≥0.85، U+FFFD ≤2%); متحفظ عمدًا؛ الفحص per-page | لا يستخرج مسافات/أسطر (يعمل بالنص المجرّد `.strip()`) |
| `preprocessing.py` | Deskew→CLAHE→Denoise | deskew إسقاطي (خلو 0.05° تجنب blur)؛ denoise خفيف kernel=3 | — thresholding/sharpening غير منفذ عمدًا |
| `page_layout_detector.py` | Layout (شعر/نثر/عنوان) | 3 إشارات footnote + تسجيل؛ إزالة إطارات بطيئة | `binarize()` = Otsu عادي (ص:187) — يطمس حركات؛ docstring header قديم (`src/01_extract/...`)؛ أنماط دالة render/`open_pdf`/`validate_page_range` dead لكن قابلة للاستيراد |
| `segment_text_rows.py` | تقسيم أسطر + gutter | gutter هندسي؛ classify_line؛ split_oversized_lines | `binarize()` = Otsu عائد 0/1 (ص:74) — **عقد مختلف عن layout**؛ ثوابت/خطوات مضبوطة على 200 DPI |
| `ocr_engine.py` | OCR دفعاتي + كاش | batch 16؛ padding defensive؛ `rec_only` منفصل لمنع تشويه aspect ratio | كود DEBUG يكتب `debug/` (ص:253-265)؛ `extract().confidence=100.0`؛ لا `min_confidence` في مسار batch؛ نص `+0.4` غير مستخدم فعليًا في main |
| `ocr_cache.py` | كاش SQLite | blake2b + shape/dtype/model؛ autocommit؛ INSERT OR IGNORE | لا TLS/rotation؛ فرصة نمو قاعدة هائلة على كتب كبيرة (لا pruning) |
| `vision_fallback.py` | تصعيد الرؤية | rotation+dead-repo؛ budget shared؛ null-safe openai؛ validation (refusal/arabic/ILLEGIBLE) | `repeated_verbatim` **in-memory` فقط**؛ FutureWarning من `google.generativeai` (ص:384)؛ لا بوابة ink/before-escalation؛ خطأ: المؤشر `rotation_order` يتقدم يوم الرد |
| `output_generator.py` | حفظ + سجل | تدريجي؛ `escalations.jsonl` append-only | `full_manuscript` يُبنى من `_page_texts` الذاكرة → **re-run جزئي ينهار الملف إلى النطاق فقط** (مثال فعل: 3/113 صفحة الآن)؛ `save()` يحذف filename تلقائيًا |
| `review_manuscript.py` | مرحلة ثانية | فصل `corrected_text/`؛ يفحص per-page; fallback raw | يتطلب `prompts.yaml.analysis_prompts.text_correction` — آخر خطأ: `config/` references مُصلَحة؛ لا نطاق في `full_manuscript_corrected` عند نطاق جزئي |
| `text_correction_engine.py` | تصحيح نصي | نفس البنية الأمنية؛ per-page | **`settings.yaml` yarn يشير إلى `llama-3.3-70b-versatile` (decommissioned)** → أول تشغيل review سيعلّم groq dead (مصدر: `text_correction_engine.py:243-251` + settings.yaml:177) |
| `surya_line_detector.py` | بديل خط Surya (blocked) | None-return fallback؛ merge y-overlaps | غير مثبت؛ لا LayoutPredictor (VLM يحتاج server) |
| `sync_vision_backends.py` | صيانة backends | token-based keywords (يُصلح "mini" في gemini)؛ ruamel round-trip؛ exclusion embeddings | `DEFAULT_SETTINGS_PATH="config/settings.yaml"` (غياب)؛ لا معرفة بـ `sovereign/sovereign_2`؛ smoke test لا يختبّر نداء فعلي |
| `morphological_verifier.py`/`flag_suspicious_words.py` | فحص صرفي (blocked) | camel-tools أول لبنة token-verification | camel-tools غير مثبت → exit 1 مؤكد (تجربة مع documented)؛ خزاعة→0 تحليلات (FP) |
| `settings.yaml` | إعداد | موثق بالتفصيل | أقسام `analysis.*`/**`review.*`** غير مسكونة؛ `text_correction.enabled: true` مقابل استئناف إعداد؟ (settings يفعّل، لكن review_manuscript default ليس مفعّلًا في main)؛ `text_det_limit_side_len=1536` غير ذي أثر على batch |
| `prompts.yaml` | قوالب | `text_correction` المستخدم | `ocr_prompts.*` و`review_prompts.*` **غير مستخدمة من الكود** — قوالب vision actuale في `vision_fallback.PROMPT` |

---

## 3) الجودة المرصودة (الأدلة الفعلية)

من `baseline/metrics/output_metrics_24_26.txt` (فرمات `raw_text` بدون header):

| ص | أحرف | أسطر | أزواج شعر | كلمات | عربية | تشكيل/حرف | أخطاء ضجيج متسربة |
|---|---|---|---|---|---|---|---|
| 24 | 1017 | 17 | 17 | 161 | 139 | 0.203 | `..wmmw.` `w..ww.` |
| 25 | 834 | 15 | 13 | 120 | 107 | 0.240 | `ـــ` |
| 26 | 780 | 14 | 14 | 120 | 105 | 0.190 | `wmw` |

**يعمل جيدًا (بالاستناد الفعلي):**
- البنية الشعرية: كل بيت `يمين ... يسار` بترتيب RTL صحيح — في كل الصفحات الثلاث (17/13/14 شطرًا).
- العنوان «مقدمة» على صفحة 25 يُصعد مرتبًا عبر `sovereign` (السطر `""` → `مقدمة`) — **صحيح**.
- التشكيل حقيقي: 0.19–0.24 علامة/حرف.

**يعمل معطوبًا (أمثلة من الملفات):**
- صفحة 24 سطر 1: `..wmmw. ... w..ww.` — **مرّ بدون فلتر**. السبب الجذري (التحليل أدناه §4).
- صفحة 25 سطر 1: `ـــ` غير مفلتر؛ سطر 4 `وَمَا لِلْعَيْنِ مِنْ دَمْعٍ إِذَا` = **هلوسة في المخطوط نفسه** («إذَا» مقطوعة من المشهور).
- صفحة 26 سطر 1: `wmw ... وَمَا لِلْعَيْنِ مِنْ دَمْعٍ إِلَّا وَ` (شطر عليها ضجيج + شطر هلاوسي).
- أخطاء قراءة فادحة: `شينث الوَّصيي`، `بباليىي`، `لحخَرْم`، `كبْرتِم`، `قواعد اليتِوإسْمَاعيلُ`، `عَصََْبَ` (تراص شدة+سكون+فتحة خاطئ).
- صفحة 4 prose: `فان ه قده خل ادم من ين` (نصف الجملة مضمحل) — النثر/الحواشي ممزوج بغِبش.
- صفحة 107: confidences منخفضة (أُوثق في BASELINE بأن النطاق 0.50-0.77) → كل الأسطر تقريبًا «مرشح» — النص هشّ.

---

## 4) التحليل الجذري للمشاكل المرصودة (الأهم)

### 4.1 لماذا تمرّ أسطر الضجيج (حاجز الحقيقة)
`_is_noise_line` (ocr_engine.py:232-247) يحسب `tokens = text.split()` ويصطفّ كـ noise فقط إذا:
```
len(tokens) >= 3 AND ratio(single_char_tokens) > 0.55
```
لكن `..wmmw.` **رمز واحد مفرد** (كلمة واحدة من 7 رموز) → `len(tokens)=1` → الشرط `< 3` يفشل → `likely_noise=False` → يمرّ. `wmw` مثلها، `ـــ` مثلها. **الفلتر لا يستطيع الإمساك بضجيج أحادي الرمز إطلاقًا.** الإصلاح الطبيعي: تجاهل أي سطر بلا حرف عربي واحد (الموجود الآن عند ثقة 0) — بشرط CER قياس.

### 4.2 هلوسة الرؤية على قصاصات شبه فارغة — مثبتة بالسجل
`escalations.jsonl` (final, 39 سطرًا عبر رنّات):
- الجملة المشهورة «وَمَا لِلْعَيْنِ مِنْ دَمْعٍ إِلَّا / إِذَا / إِلَّا وَ ...» عادت **verbatim مكررة** على قصاصات paddle_text = `..wmmw.`، `w..ww.`، `wmw`، `""`, `ـــ` — كلها من `openrouter` (qwen2.5-vl-72b) عبر الصفحات 24-26. وقد حُدّد `repeated_verbatim: true` على عدد منها.
- في المقابل `sovereign` أعاد «مقدمة» الصحيحة، و`gemini` أعاد «مقدمة» أيضًا.
- **الدرس**: لا بوابة تقيس «هل القص ملوّن أصلًا؟» قبل إرسالها للرؤية. أي قصّة تقريبًا فارغة (صورة بيضاء/كشيدة) تذهب للرؤية وتفتح باب هلوسة. المقترح: حساب `ink_ratio` للقص (نسبة عدم-البياض) وعتبة صفرية — تعطيل الرؤية صفر قبل إنفاق حصة.

### 4.3 الانهيار في `full_manuscript.txt` عند إعادة رن جزئي — **Resolved (2026-09-09)**
~~`save_page` يعيد بناء `full_manuscript` من `_page_texts` (ذاكرة العملية فقط)~~ — **أُصلح**: `_rewrite_full_manuscript()` الآن يقرأ ملفات `raw_text/page_NNN.txt` من القرص ويدمجها مع صفحات العملية الحالية (العملية الحالية تنتصر عند التداخل). `full_manuscript.txt` يعكس دائمًا كل صفحة محفوظة على القرص. كما استُبدلت الملفة المؤقتة الثابتة (`full_manuscript.txt.tmp`) بـ `tempfile.mkstemp()` لتوليد ملف فريد — آمن لعمليات إعادة البناء المتزامنة.

### 4.4 binarize المزدوجة (عقود مختلفة)
- `layout.binarize()` → 0/255 (Otsu) — `page_layout_detector.py:177-188`.
- `rowseg.binarize()` → 0/1 (Otsu) — `segment_text_rows.py:67-77`.
- نفس العملية تُطبق مرتين على نفس الصفحة بأشكال متعارضة في التدفق العادي؛ أي خلط صامت يدمّر الكشف (متجاب في `main.py` docstring). الهدف المعلن في `AGENTS.md §4.2` هو توحيدها في **adaptiveThreshold** عند مهمة صريحة + قياس CER.

### 4.5 اللا-حتمية + الحصص الخارجية
- نفس صفحة 24 بين رنّات: سطر أول مختلف تمامًا (هلاوسي مُصعَّد ↔ ضجيج خام). والـ run من baseline اعتمد 100% على cache (0 نداء paddle جديد) و32/3000 نداء vision — لكن الرؤية نفسها non-deterministic بين جلسات/حسابات (429/retry).
- **أساس أي مقارنة**: أسطر الكاش الحتمي (مخرجات PaddleOCR المخزّنة) فقط؛ مقارنة أسطر الـ Vision عبر رنّات محظورة في AGENTS §11.

### 4.6 لا قياس تلقائي (جذر المشكلة الكبرى)
- لا GT، لا jiwer، لا camel-tools. عبارة «تحسّن» بلا أرقام = رأي (AGENTS §4.12). بدون ذلك، **لا يمكننا إثبات أن أي تحسين لاحق نجح أو أخفق** — كل ما لدينا ملاحظة ولو الغير قابل للنشر.

### 4.7 hygiene-refs معطوبة
- `sync_vision_backends.py` DEFAULT → `config/settings.yaml` (لا يوجد).
- `BASELINE.md §4` يعرض شجرة `src/` قديمة (immutable، مقصود).
- `debug/` يحتوي `page_fed_to_ocr.png` + `page_107_*` وصور segmentes — تلوث من DEBUG في `ocr_engine.py` (تنظيف عند الطلب فقط، AGENTS §12).
- `analysis.*`/`review.*` في settings + `ocr_prompts.*`/`review_prompts.*` في prompts غير مسكونة → مربكة.

---

## 5) نقاط قوة يجب الحفاظ عليها (قائمة المعطيات)

1. **فحص النصي التحفظي per-page** (تعريف §4.4) — صحيح عمرانيًا؛ PDF هجين يستفيد بدون إعداد يدوي.
2. **Deskew إجباري وأول + CLAHE/denoise خفيف** — لا إفراط على التشكيل.
3. **كشف الإطارات/ترقيم الصفحات بثلاث حالات** — تفكير معماري دفاعي (القص الخاطئ أسوأ من ترك كل شيء كما هو).
4. **ميّز footnote 3-إشارة مع تسجيل** — إشارة gap+separator+smaller-text لا يمكنها التدخل.
5. **Batching+Cache**: batch 16 لـ 4GB؛ كاش بمعرّف model؛ إعادة تشغيل رخيصة.
6. **المساواة RTL** و**ترتيب القراءة** يمين→يسار أعلى→أسفل.
7. **`raw_text/` لا يُكتب فوقه** (§6 AGENTS) و`escalations.jsonl` append-only.
8. **انضباط التوثيق**: `AGENTS.md` عقد، `baseline/` ثابتة، `CLAUDE.md` ذاكرة.
9. **فلترة noise في مسار الشعر** (الآن تُطبّق على كل شطر على حدة، وتُعاد بعد تصعيد vision).

---

## 6) المقترحات (مرتّبة أثر/جهد، مع قياس مطلوب — انظر AGENTS §11)

### FAST WINS (ساعات)
1. **بوابة ink قبل الرؤية** (`vision_fallback.should_escalate` أو `main.py`): قصّ بكثافة حب غير بيضاء تحت عتبة → لا تصعيد + وسم `blank_low_info`. — يقضي على السبب الجذري للهلوسة §4.2 دون لمس OCR. **القياس**: عدد تصعيدات على crops فارغة قبل/بعد.
2. **فلتر سطر بلا حرف عربي** — يقتل §4.1. **القياس**: أسطر الضجيج المتسربة قبل/بعد.
3. **توحيد binarize** في `adaptiveThreshold` كتلة كبيرة موحّدة (AGENTS §4.2) — تلغي نسختين متعارفتين. **القياس**: CER + فحص التشكيل.
4. **~~إصلاح `full_manuscript` buildup من القرص~~** — **مُنجز (2026-09-09)**: يقرأ من `raw_text/` على القرص + atomic write فريد. **القياس**: عدد الصفحات في الملف = عدد `raw_text/` بعد re-run.
5. **عزل `debug/` + إزالة DEBUG code** + ملف `.env.example`.
6. **إصلاح `sync_vision_backends`** (جذر + sovereign + cohere 422 clearance).

### MID (يوم–يومان)
7. **كاش رؤية حتمي** (hash crop + prompt-version + model) → غير إنفاق الحصص وزاد الاستنساخ.
8. **`repeated_verbatim` دائم** (جدول SQLite) → منع تكرار الهلوسة عبر الجلسات (AGENTS roadmap Phase 2).
9. **صحة backends عبر run**: التوقف عن انتظار backends معروفة dead (وفر ~30s/رنّ من أصل ~120s).
10. **شجرة segments قياسية** `review/segments_NNN.json` (bbox, text, confidence, source, method) — أساس GT/Layout/poetry.
11. **قِياس CER/WER harness** (`eval_ocr.py` + GT يدوي لصفحات مرجعية: 4/24/25/26/107) — يُعمل أولًا **قبل أي تحسين** ليسجل خط الأساس الجديد.

### PHASE 2+ (أسابيع، بنود خارطة AGENTS)
12. Surya Layout (بعد تثبيت) بديل اكتشاف الأسطر الإسقاطي للبنى المعقدة؛ Paddle يبقى للقراءة.
13. كشف Gutter هندسيًا على BBoxes + Mask للزخارف/الإطارات قبل OCR.
14. DPI 300 مع تجربة CER المقارنة قبل الالتزام.
15. Confidence كلمة→سطر→صفحة + حلقة إعادة معالجة للصفحات <50%.
16. Ensemble محلي Paddle vs Surya + Qwen-VL محلي كـ backend حتمي مجاني.
17. CamelTools token-verification مع قصّ كلمة + مرشّحي رؤية (مسار §4.6 المُصرَّح به).

---

## 7) ما أوافق عليه من مقترحات سابقة / ما أتحفظ عليه

**أؤيد**: Surya للتخطيط فقط (لا قراءة)؛ الحفاظ الأمين على النص (Token-level فقط، لا rewrite)؛ قواعد «baseline ثابتة»؛ كاش بمفتاح model؛ أداء del 3000 budget vision؛ DoD + تصنيفات تغيير.

**أتحفظ/أعترض:**
1. **«HYBRID لا يُوجَّه إنتاجيًا»** (AGENTS §4.5) — أتفهم؛ لكن الفحص الصفحة-بصفحة الحالي (تعريف §4.4) يكفي عمليًا، والتخلي عنه رفضًا كاملًا للصفحة يضيع الفحص النصي الرقمي. ابقِ الوضع الحالي (رفض silent، log صريح).
2. **الاعتماد على فتوى التصعيد** في `repeated_verbatim` وحده — انظر §4.2: الاستخدام المتكرر لـ openrouter (بدون بوابة ink) هو المشكلة الأولية؛ `repeated_verbatim` جرس إنذار **بعد** الأنفاق لا **قبل** العتبة. بوابة ink هي المهمة رقم واحد عندي.
3. **رفع batch >16 بلا تجربة VRAM** — مرفوض حتى تجربة مع رصد `max_memory_allocated`.
4. **A fine-tuning Paddle في القريب** — يؤيّد التأجيل (لا GT، لا قياس).
5. **تثبيت `analysis.*`/`review.*` غير مسكونة** — إما توثيق أو حذف؛ لا إعداد «وهمي» في الإعداد.

---

## 8) أفكار استكشافية (لم تنضج — مرجع)

- **verify-mode**: عند نسبة كاش hit ~100% ويقل رندر — مسار قراءة سريعة (render+layout فقط) دون إعادة OCR لكل رن.
- **مسارات الحواشي كطبقة منفصلة**: عند توفر كتب فقه/نحو — فصل «المتن/الحاشية» كطبقتين (هي بالفعل منطقة prose منفصلة؛ يمكن رقمنة كاملة).
- **HSV/فصل الألوان للعناوين الحمراء**: فقط إذا ظهرت كتب ملونة.
- **sorting متعدد لمقارنة الطبقات**: مقارنة/ترتيب في `corrected_text/` فقط — على مبدأ الطبقات.
- **تتبع الكشيدة/الشدة** كبيانات بنائية (لا تجريف).

---

## 9) Safety Rails (تُحدَّث — تجاوزها ممنوع)

1. لا تعدّل/لا تحذف `baseline/`؛ لا تفتح/تطبع/تلتزم `.env`.
2. لا تكتب فوق `raw_text/` بنتائج مراحل لاحقة (إخراج محسّن → `corrected_text/`).
3. لا تُلغِ/لا تغيّر مفتاح كاش OCR (`output/.cache/ocr_cache.sqlite3`).
4. لا تعيد إنشاء `src/` أو `config/` أو سطر `sys.path.insert`.
5. أي تغيير OCR/معالجة → CER/WER قبل/بعد وإلا رفض (AGENTS §4.12، §11).
6. لا تُقارن أسطر الـ Vision بين رنّات (غير حتمية) — الكاش الحتمي فقط.
7. ~~**لا يُعدّ `full_manuscript.txt` مرجعًا كاملاً إلا إذ كان رن كامل** — انتبه لمخاطر §4.3 في حال partial re-run.~~ **Resolved (2026-09-09)**: `full_manuscript.txt` يُعاد بناؤه من `raw_text/` على القرص — أي رنّ جزئي يُكمل الملف بدل حذفه. Atomic write فريد يمنع التلوث في حال التشغيل المتزامن.
8. **لا تُرسِل قصاصات شبه فارغة للرؤية** بعد تفعيل بوابة ink (مستقبلي).

---

## 10) خريطة تنفيذ مقترحة (بعد مراجعة المستخدم)

```
الآن:       1,2,3,4,5,6 من §6  (بعد موافقة صريحة + قياس CER حيث يلزم)
بعدها:      7,8,9,10,11
أسابيع:     12,13,14,15  (Phase 2 AGENTS)
مستقبلي:    16,17 (Phase 3/4)
```

---

## 11) خريطة الملفات (مرجع في جلسة جديدة)

| الملف | الدور القيمة | ملاحظات |
|---|---|---|
| `main.py` | توجيه + نطاقات + حفظ تدريجي | لا `sys.path` — flat |
| `input_handler.py` | تحميل PDF/صور + فحص النصي + render 200 DPI | `direct_text` per-page |
| `pdf_text_extractor.py` | فحص ToUnicode/الصلاحية (تعريف §4.4) | متحفظ 20/0.85/0.02 |
| `preprocessing.py` | deskew→CLAHE→denoise | no morphology افتراضيًا |
| `page_layout_detector.py` | layout شعر/نثر/عنوان + footnote | binarize=Otsu (0/255) عيب معروف |
| `segment_text_rows.py` | أسطر + gutter + verse/full | binarize=Otsu (0/1) عيب معروف |
| `ocr_engine.py` | batch 16 + كاش + rec_only | DEBUG code موجود |
| `ocr_cache.py` | SQLite blake2b + model | autocommit |
| `vision_fallback.py` | rotation + dead + repeated_verbatim | **لا بوابة ink**؛ google.generativeai deprecated |
| `output_generator.py` | raw_text + full + escalations | **full manuscript يُعاد بناؤه من raw_text على القرص** — partial re-run لا يُفقد الصفحات السابقة (Resolved 2026-09-09: atomic write عبر tempfile.mkstemp unique) |
| `review_manuscript.py` / `text_correction_engine.py` | مرحلة اختيارية منفصلة (اختيارية) | groq model stale في settings |
| `surya_line_detector.py` | Surya خط (blocked) | غير مثبت |
| `sync_vision_backends.py` | صيانة backends | defaults مكسورة؛ no sovereign |
| `morphological_verifier.py` / `flag_suspicious_words.py` | صرفي (blocked) | camel-tools غير مثبت |
| `settings.yaml` / `prompts.yaml` | إعداد + قوالب | أقسام غير مسكونة |
| `AGENTS.md` | عقد تشغيل | **قراءة إلزامية قبل تعديل** |
| `CLAUDE.md` | ذاكرة الجلسات | |
| `baseline/` | لقطة ثابتة + BASELINE.md | للإثبات فقط |

---

*نهاية الملخص التفصيلي — جُمع بعد قراءة كاملة للملفات الستة عشر + الإعداد + القوالب + السجل التاريخي، فحص `py_compile`، مراجعة مخرجات حقيقية (صفحات 1–4، 24–26، 107) وسجل التصعيد، وتثبيت الأرقام على `baseline/metrics/output_metrics_24_26.txt`.*