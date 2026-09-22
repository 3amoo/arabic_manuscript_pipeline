# AGENTS.md — عقد تشغيل خطّ إنتاج المخطوطات العربية

> هذا الملف **عقد تشغيل للوكيل** وليس مجرد توثيق. يُميّز بوضوح بين: ما هو **مطبَّق الآن**، وما هو **ممنوع**، وما هو **مطلوب عند المهمة فقط**، وما هو **خارطة مستقبلية**.
> **تحديث 2026-09-18 (spec 008)**: المواءمة صُحِّحت — الصفحات غير المطابقة لم تعد **تُجمِّد مؤشر GT** (كانت تتسبب في أن تُقاس الصفحة التالية ضد نافذة متأخرة صفحة كاملة). **المرجع الحالي: CER 25.9% / WER 60.2% / تشكيل 82.1% (45 صفحة)** — المرجع السابق (spec 006): **CER 25.0% (43 صفحة)**. كلاهما قابل لإعادة الإنتاج (`align_ground_truth.py` + `evaluate_cer.py --alignment`)، والفرق = **صدق وليس تراجعًا** (§12).`baseline/` **غير موجود** (تحقق مباشر) — كل إشاراته أدناه **بالية**.

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
| `data/evaluation_reports/006/` | **دليل القياس (spec 006)** | تقارير CER/WER + المواءمة — القراءة فقط على `raw_text/`/`ground_truth/` |

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
| 300 DPI افتراضي / حرف ≥30px | **measured, rejected** | **القياس دحض الفرضية**: عند 200 DPI الحالي المتوسط ارتفاع الحرف **32px** (الصفحة large-format 3188×4423px) — شرط ≥30px **متحقق بالفعل**. A/B على 45 صفحة: CER موزون 26.8% → **25.3%** (−1.5pp؛ 25 تحسَّنَت / 15 تدهورت) — **لكن غير معتبر إحصائيًا**: paired t=1.44 (p≈0.16) و95% bootstrap CI **[−0.10,+3.43]pp يعبر الصفر**. يكلِّف 2× runtime و2.25× بكسلات. **القرار: إبقاء 200 DPI**. **الثوابت صارت DPI-aware** (`set_dpi_scale()` في الموديلين، scale=1.0 = byte-identical) — هذا هو الإنجاز الدائم؛ تغيير الـ DPI لاحقًا سطر واحد آمن. التفاصيل: `specs/010-dpi-and-diacritics` |
| `PageQualityAnalyzer` (لون/كثافة تشكيل/إطارات) | **planned** | غير موجود |
| `detect_pdf_type` على مستوى الملف (TEXT/IMAGE/HYBRID) | **implemented** | `pdf_text_extractor.detect_pdf_type` يجمع أحكام الصفحات الفردية ويُعلِن صنف الملف (TEXT/IMAGE/HYBRID/UNKNOWN) في `_load_pdf` — HYBRID يُبلَّغ بصريح WARNING (§4.5)، والتوجيه الفعلي يبقى صفحة-بصفحة |
| Adaptive Binarization | **planned** | مرهونة بمهمة صريحة + قياس CER (§4.2) |
| Surya Layout / LayoutAnalyzer + Spatial reading-order | **measured, not active** | `surya-ocr` **مثبَّت الآن** (0.22.1 بـ `--no-deps`، spec 009 — لا أضرار: `openai` 3.3.1 و`pillow` 12.3.0 و`opencv-python-headless` 5.0.0.93 سليمة). **الـ fp16 all-NaN bug مُصلَح** في `surya_line_detector.py` (`DetectionPredictor.local(dtype=torch.float32)` بدل server-backed predictor الذي يُرجِع 0 سطر بصمت بـ HTTP 200). **لكن النتيجة سلبية**: A/B على 45 صفحة → CER موزون 27.0% → 26.5% (−0.6pp ضوضاء؛ 24 صفحة تحسَّنَت / 17 تدهورت / 4 ثابتة؛ صفحات جيدة تدهورت مثل ص55 10.4%→23.3%). Oracle pick-per-page يعطي 23.9% لكنه يحتاج GT (غير قابل للنشر). **الخلاصة: تقسيم الأسطر ليس عنق الزجاجة** (يتطابق مع ميزانية أخطاء spec 008: 66% أخطاء حروف مقابل 13% أبيات ساقطة) → **surya يبقى مُعطَّلًا** والـ spec القادم يستهدف أخطاء الحروف + التشكيل. الإعداد في `settings.yaml` معطَّل (commented) مع التوثيق الكامل |
| إخفاء الزخارف/الإطارات بقناع قبل OCR | **planned** | غير موجود |
| حلقة ثقة صفحة <50% → إعادة معالجة | **implemented** | `process_page_image` يعيد المعالجة مرة واحدة بإعدادات Binarization أدق (block=31/c=5) عند صفحة ثقتها < 50% (§4.10) — الخيار في `ocr.page_confidence_reprocess` |
| `normalize_arabic_unicode` / `repair_arabic_spacing` | **planned** | غير موجود |
| CamelTools Token-verification | **blocked** | `camel-tools` **غير مثبَّت حاليًا** (`MorphologicalVerifier().available = False`، «No module named 'camel_tools'» — تحقق مباشر spec 007). **بيانات القاعدة الصرفية لا تزال موجودة** في `~/.camel_tools/data/morphology_db/calima-msa-r13` (تُنزَّل 2026-09-06)، فإعادة تثبيت الحزمة تكفي لإعادة التفعيل دون إعادة تنزيل. كان يعمل (89/394 كلمة على 24–26). **أداة مراجعة فقط** — الدمج داخل main.py planned (§4.6) = **spec لاحق** (أُخر عن spec 011) |
| Ensemble محلي Paddle vs Surya | **measured, rejected** | A/B spec 009 على 45 صفحة: 27.0% → 26.5% (−0.6pp ضوضاء). oracle pick-per-page 23.9% يحتاج GT. انظر §3 (Surya) |
| Diacritic-preserving preprocessing (فقد 17.9% من التشكيل) | **measured: recognition ceiling** | **الفرضية دُحضت**: التشكيل **يبقى بكسلًا** عبر كل مراحل الـ preprocessing (probe: p23 259→401، p31 210→352 مكوّن صغير؛ حبر النطاق العلوي 8-12k vs الجسم 79-81k في القصاصات النهائية). الموديل **يُصدر تشكيلًا** (4-10 علامات/سطر) لكنه **يضعها على حروف خطأ**. **لا يوجد بديل أفضل**: PaddleOCR 3.7 لديه موديلان عربيان فقط؛ `arabic_PP-OCRv5_server_rec` لا يُحمَّل («No engine bindings registered»)؛ `PP-OCRv6_medium_rec` يُصدر **صفر** تشكيل. **A/B كامل (45 ص)**: v3 أسوأ بـ **+3.9pp CER** (27.0%→30.9%) واسترجاع التشكيل **82.4%→8.6%** (34/45 صفحة أسوأ). **الخلاصة: الفقد = سقف الـ recognizer**، ليس عيب preprocessing/DPI/اختيار موديل. الرافعة المتبقية = **fine-tuning** (Phase 4). التفاصيل `specs/011-diacritics-preservation` |
| Non-Paddle recognizer (Qari-OCR VLM) | **measured, rejected** | **السقف ليس خاصًا بـ Paddle**. `NAMAA-Space/Qari-OCR-0.2.2.1-VL-2B-Instruct` (Qwen2-VL-2B + LoRA، 4-bit nf4 — الوحيد القابل للتشغيل على GTX 1650 3.6GB) قِيس على نفس GT slices الخاصة بـ Paddle (spec-008 alignment): p24 CER **75.5%** (أفضل من Paddle 138.1%) **لكن شطب التشكيل** (11 علامة vs 203 = recall 5.3%)؛ p31 (أفضل صفحة Paddle) = **19 حرف garbage إحداثي** `(101,101),(888,807)` = فشل كامل؛ p23 recall 83.5% **لكن على نص مُهلوس** (يقرأ الحواشي المُشكَّلة ويُفسد الأبيات). **خلاصة**: معماريته مختلفة تمامًا (VLM vs CNN+CTC) وكلاهما يفقد التشكيل → المشكلة في **جودة طباعة المخطوط vs الموديلات المتاحة**. **القرار: لا تبديل/ensemble**؛ fine-tuning = **الرافعة الوحيدة المتبقية**. التفاصيل `specs/012-non-paddle-ocr-evaluation` |
| Fine-tuning الـ recognizer (بوابة جدوى) | **gate passed للحروف، not للتشكيل** | **fine-tuning يعمل وينقل الفائدة لصفحات غير مرئية** — تم بناء dataset من **نفس crops الـ pipeline** (346 train / 58 val، 26 صفحة `matched`، labels = شطري الأبيات من GT، التحقق من الاقتران بـ OCR) وتدريب v5 على GTX 1650 (batch 4، 384px — السقف 3.6GB). **النتيجة على صفحات لم تُرَ قط (63-67)**: CER **28.6%→26.8%**، win/loss/tie **14/5/39**؛ **لكن استرجاع التشكيل 85.2%→83.9%** (12/14 = ثبات تقريبًا). 80 epoch أحدثت overfit (norm_edit_dis 0.49→0.59) → 346 عينة تتشبَّع. **خلاصة**: التقنية مثبتة وتُحسِّن الحروف، لكن cross-entropy العادي على 346 شطرًا **لا يحرِّك التشكيل** — يحتاج loss يهتم *بأي حرف* يحمل العلامة. **3 مصائد صامتة** سُجِّلت (R4): تصغير charset يُعِيد تهيئة head، `-o Global.pretrained_model` يُتجاهل، `max_text_length` أقل من أطول label → recursion لا نهائي. التفاصيل `specs/013-finetuning-feasibility-gate` |
| Diacritic-aware fine-tune (السقف) | **measured, ceiling ACCEPTED** | **المحاولة الأخيرة فشلت على الجانبين**. (1) **Corوس موسَّع**: استرجاع 19 صفحة غير-`matched` عبر **sequence alignment** (DP على نصوص الـ OCR vs أبيات GT، قبول الزوج عند CER<0.6) → **688 train / 148 val** (~2×). النتيجة: CER **33.1%→32.4%**، استرجاع التشكيل **85.5%→84.0%** (23/15/110 letters، 26/30 diacritics) — المكسب في الحروف *تقلَّص* (−0.7pp بعد −1.8pp في 013). (2) **Diacritic-weighted CTC loss**: وزن كل عينة `(1 + عدد التشكيلات)` من الـ encoded indices — **النتيجة مطابقة تمامًا** لِلْ_plain (32.4% / 84.0%، نفس W/L/T). **التشخيص**: الموديل **يُصدر** تشكيلًا بكثرة لكنه **يضعه على حروف خطأ** (`عَمْرَر` لـ `عَمْرٌ`)؛ وزن العينة لا يحمل أي معلومة عن **موضع** العلامة = مشكلة position/association وليست weighting. **القرار: قبول السقف** — الـ fine-tuning line مُغلقة (stop condition binding)، 17.9% = جودة المسح vs المُتعرِّفات المتاحة. **البرنامج ينتقل لمرحلة المراجعة** (post-OCR correction). التفاصيل `specs/014-diacritic-finetune` |
| Review-stage morphological verification | **measured: gate/fixer rejected; diacritic-repair signal real** | **المُتحقق كان ساكنًا** (camel_tools غير مُثبَّت → كل فحص يُرجع `None` صامتًا). بعد التثبيت (camel-tools 1.6.0، DB موجود): **flag rate 24.4%** (1,240/5,084) بدقة **99.9%** أنها أخطاء فعلية — لكن **كبواب**: أقل معدل لكل صفحة 11.3% → **0 من 45 صفحة قابلة للتخطي**؛ **كثقة**: Spearman rho(flag-rate, CER) = **−0.112** (علاقة صفرية)؛ **كمُصلح**: 0.5% فقط (6/1,239) لها الشكل الصحيح بين المرشحين (الأخطاء merged words/inserted letters وليست confusion لحرف واحد). **الإشارة الحقيقية (R4)**: **226 token** بحروف صحيحة وتشكيل خاطئ لكلمة موجودة فعلًا = بالضبط خطأ spec 011؛ المُحلل يقدم التشكيل الصحيح لـ **58 منها (25.7%)** (`بنو`→`بَنُو`، `عِلم`→`عِلْمُ`). **القرار: لا نشر كبوابة/مُصلح**؛ تبقى review-only flagger. التفاصيل `specs/015-review-stage-verification` |
| Diacritic-repair pass (تحليل التشكيل) | **REJECTED — net-negative in every variant** | **الإشارة (58/226 = 25.7%) غير قابلة للحصاد بدون GT**. أربع سياسات قِيسَت: (1) **unique-analysis form**: فقط **25/226 (11.1%)** لها شكل واحد، ودقته **24.0%** (6/25)؛ (2) **MLEDisambiguator** (LM ranker): yield **52/225 = 23.1%** لكنه **يكسر 97/131 = 74.0%** من الـ tokens الصحيحة؛ (3) **conservative** (فقط عندما يكون شكل الـ OCR نفسه غير صالح تحليليًا + حفظ الحروف): **262 applied → 47 fixed / 97 broke / 118 still wrong = net −50**. **السبب الجذري**: **style mismatch وليست مشكلة disambiguation** — الناسخ يترك أدوات الربط بدون تشكيل (`في`،`إذ`،`هم`،`مَا`،`حتْى`) بينما `calima-msa-r13` يُشكِّلها كاملةً؛ هذه التصادمات **unique+certain+wrong** = لا يصلحها أي confidence threshold. إضافةً: الـ pool غالبًا يفتقد شكل GT أصلًا (118/262 هبطت على شكل خاطئ). **القرار: غلق السطر** (3 إخفاقات = stop condition)، حتى review-only مرفوض (74% false-edit ستُغرق المراجع). **لا كود/لا config/لا بيانات** — sha256 ثابت `91b3f61101170b233619`. التفاصيل `specs/016-diacritic-repair` |
| Vision-fallback escalation review | **measured: WORKS when backends alive — quota is the blocker (spec 018)** | **الـ escalation path لا يفعل شيئًا في المُنتَج الحالي**. قياس مُزاوج (vision on vs off، نفس القصاصات، 15 صفحة: أسوأ 5 + عيّنة 10): **+0.00pp، byte-identical، 0 escalations اشتعلت** — ثقة السطور المُتخallah 0.60 مقابل threshold 0.55. **السبب الجذري للقياس الخاطئ**: سجل المراجعة كان **245 مدخلًا من ≥10 شغلات** (smoke tests على صفحات 24–33)، **0/245** نصها موجود في المُنتَج → القياس السطحي ("80.9% تحسّن!"، "35/36 رفض خطأ!") كان يقيس **حالات مُلغاة**؛ بالمعيار المطلق (CER≤0.35): **0/245** نص قابل للاستخدام. **الـ 26 رفضًا للإيقاع المهيكل** (`وَمَا لِلْعَيْنِ` في ص 24–27) كانت **صحيحة** — الإيقاع غير موجود في GT تلك الصفحات. **العيب الحقيقي (تم إصلاحه)**: `save_escalations()` كان يفتح السجل append دائمًا → يدمر فائدة المراجعة؛ الآن **rotation لكل شغلة** (`escalations.prev.jsonl`). **الـ backends كلها ميتة الآن** (gemini quota، openrouter 402، groq 404). التفاصيل `specs/017-escalation-review` |
| Atria text-correction backend (`Atria-Dawn-Preview`) | **planned** | `src/pipeline/correction/text_correction_engine.py` — **نصي فقط (text-only)**؛ انظر §4.13.1 و spec 005. **غير فعّال حاليًا على صفحات حقيقية**: `reasoning_content` يتمدَّد لملء `max_tokens` فيُخفِق كل صفحة ويسقط على `raw` (research §R2.2) — يبقى آخرَ في `rotation_order` حتى يُقاس حلٌ |
| Bench CER/WER (`jiwer`) + Ground Truth | **implemented** | **spec 006** + **spec 008 (تصحيح المواءمة)**: أرضية GT **كاملة** (620 بيت، `عمود_النسب.clean.md`، ص23..ص67) + مواءمة تلقائية + قياس شامل. **المرجع الحالي (spec 008، 2026-09-18): CER 25.9% / WER 60.2% / تشكيل 82.1%** عبر **45 صفحة مُقيِّسة** — **المرجع السابق (spec 006): CER 25.0% / 43 صفحة** (الفرق = صدق: ص59/ص67 كانا مُقصاتَين وهما سيئتان فعلًا — §12). — §8 |
| GPU/CPU fallback (ONNX/تشغيل متعدد) | **blocked** | `paddlepaddle-gpu` فقط |

---

## 4) Non-Negotiable Rules — القواعد غير القابلة للنقاش

> الأرقام أدناه مطابقة لتنفيذ الكود الحالي — لا تُغيَّر دلالاتها إلا بمهمة صريحة ومقاسة.

### 4.1 المعالجة المبالغ فيها تدمر النص العربي
لا تُستخدم عمليات Morphology (`erosion`/`dilation`) **افتراضيًا** على النص العربي، خصوصًا قبل OCR، لأنها تدمج نقاط الثاء/الشين بجسم الحرف وتطمس الكسرة.
**استثناء مسموح فقط عند الحاجة الانتقائية على أهداف غير مباشرة النص** (إزالة إطار خارجي، تنظيف بقع، فصل عناصر layout، صنع masks) — بشرط تجربة تثبت تحسّنًا في CER/WER دون ضرر على التشكيل. أي إدخال morphology بعده: سجّل CER/WER قبل/بعد.

### 4.2 حماية التشكيل عند الثنائية
- **مطبَّق الآن**: `preprocessing.adaptive_binarize` / `adaptive_binarize_gray` (adaptiveThreshold كتلة 51، `ADAPTIVE_THRESH_GAUSSIAN_C`) موحَّدة في موضع واحد، وتستخدمها `page_layout_detector.binarize_to_255()` و`segment_text_rows.binarize_to_mask()` و`preprocessing._estimate_skew_angle` — تلغي نسخ Otsu الثلاث.
- انتبه: `layout.binarize_to_255()` تُرجع 0/255، بينما `rowseg.binarize_to_mask()` تُرجع 0/1 — لا تخلط بينهما.
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

### 4.13.1 سياسة A1/A2/E1 — قبول/فشل ناتج أي backend تصحيحي

> **الأصل**: سياستا A1/A2/E1 متفق عليها من جلسة سابقة (مؤرشفة). لم تُعرَّف في أي ملف بالـ repo أو git history أو `.specify/memory/` — أُعيد بناؤها هنا من مفردات بوابات §4.13 نفسها (research.md §R7). إن اختلف الأصل، هذا هو المكان الوحيد للتصحيح.

ناتج أي backend للتصحيح (`text_correction_engine.py`، مرحلة `review_manuscript` الانفصلة) يُحكم عليه بواحدة من ثلاث:

- **A1 — Accept (قبول)**: الرد يجتاز `clean_and_validate_correction()` (عربي معقول، ليس رفضًا، أُزيلت reasoning blocks). يُستخدم النص المصحح ويُسجَّل `source` = اسم الـ backend — نظير `reason: "accepted"` في §4.13.
- **A2 — Accept-but-record (قبول غير حاكم)**: النص المصحح يُكتب في طبقة **منفصلة** `corrected_text/` مع ترويسة `# Correction source:` — **لا يُكتب فوق `raw_text/` أبدًا** (§6). تصحيح LLM ليس سلطةً دليلية كنص OCR الخام؛ هو طبقة تسهيل يمكن إعادة تشغيلها أو حذفها — نظير قاعدة §4.13 «ناتج الـ Vision ليس سلطةً بذاته».
- **E1 — Escalate-or-fail (فشل آمن)**: عند فشل التحقق، استنفاد الكوتة، أو موت كل الـ backends، **تبقى الصفحة على نص OCR الخام** (`source: "raw"`) وتُسجَّل في عدّادات المصادر per-page — لا تُسقَط صفحة ولا تُكتَب بصمت. الفشل مرئي في `engine.summary()` و`review_manuscript.py`.

**القاعدة الإضافية الوحيدة (Atria تحديدًا)**: **429 هو E1 فقط بعد استنفاد محاولة Retry-After**، لا عند أول ظهور — لأن كوتة Atria المشتركة (RPM) عابرة بطبيعتها، فالقفز إلى E1 مباشرةً يُنتج فشلًا من شرط عابر ويسقط الـ backend الوحيد المُهيَّأ. انفيذ: FR-007 في spec 005.

---

## 5) Architecture — المعمارية الحالية

> **تحديث 2026-09-17 (بعد إعادة الهيكلة commit `2587731`)**: المشروع أعاد هيكلته إلى **حزمة `src/pipeline/`** (`main.py` يستورد `src.pipeline.*`) — الفقرة السابقة التي تقول «مسطّح، ممنوع إعادة `src/`» **بالية**، والكود هو الحقيقة (§2). الباقي أدناه محدَّث ليعكس المسارات الفعلية. **ممنوع** إعادة `sys.path.insert` (ما زال ساريًا).

ممر الإنتاج الأساسي (`main.py`):
1. `src/pipeline/ingestion/input_handler.py` — اكتشاف ملفات `input/`، لكل صفحة: `direct_text` اختياري + صورة مرسومة (BGR) + metadata (rotation/rect).
2. `src/pipeline/ingestion/pdf_text_extractor.py` — فحص الطبقة النصية لكل صفحة (تعريف §4.4).
3. `src/pipeline/preprocessing/preprocessing.py` — `deskew_page` → `apply_clahe` → `denoise_light`.
4. `src/pipeline/preprocessing/page_layout_detector.py` — بنية verse/prose/full_width + مناطق الشعر/النثر.
5. `src/pipeline/preprocessing/segment_text_rows.py` — تقسيم الأسطر.
6. `src/pipeline/ocr/ocr_engine.py` — `extract_segments_batch`: كاش SQLite → دفعات PaddleOCR (16) → كتابة إلى الكاش.
7. `src/pipeline/ocr/vision_fallback.py` — تصعيد أسطر الثقة المنخفضة عبر الـ backends (Gemini/Cohere/Sovereign/OpenRouter + qwen_vl المحلي) بحد 3000 نداء مشترك. **أي backend يدور = نتيجة اختبار تحكّم الصورة الفارغة (blank-image control)، لا تخمين** — Groq/GitHub Models/Cohere كلها أزيلت بعدما أثبت التحكّم أنها تعيد عربية فصيحة على صورة بيضاء (انظر `docs/backend_health_table.md` + `check_vision_health.py --cheap`).
8. `scripts/measure_der.py` — DER (معدل خطأ التشكيل) **منفصل** عن CER. CER يعتبر الحركة المفقودة كالحرف المفقود، فيُخفي المشكلة. المقاس: base-CER 19.6% لكن DER 34.9%.
9. `scripts/fallback_report.py` + `logs/fallback_events.jsonl` — تيليمتري معدل التصعيد. المقاس: 4.9% من السطور فقط هي اللي بتتصعّد → أزمة تعدد الـ backends نطاقها صغير. `--review-queue` بتبني `logs/manual_review_queue.md`.
10. `classify_band()` في `segment_text_rows.py` — الهامش (marginalia): سطر حبره شبه كله على جنب واحد من الـ gutter يُفصل على قناة `--- الهامش ---` بدل ما يتداخل مع البيت.
11. **العلامة الـ inline** (`UNRESOLVED_MARKER` في `output_generator.py`) — السطر اللي اتصعّد وما ردش backend يفضل نصه (أفضل دليل متاح، لا يُحذف) لكن بعلامة `# ⟦⚠ غير محقق: فشل التصعيد البصري⟧` + سجل `no_backend_responded` صريح. **العلامة تبدأ بـ `#`** فمستبعدة من قياس CER (الرقم ما يتأثرش). الثابت `d91e54f71ece5757bed6`.
8. `src/pipeline/output/output_generator.py` — حفظ تدريجي + `full_manuscript.txt` + `review/escalations.jsonl`.

مرحلة ثانية منفصلة (لا تعمل ضمن `main.py`):
- `src/pipeline/output/review_manuscript.py` + `src/pipeline/correction/text_correction_engine.py` — مراجعة/تصحيح (مرحلة اختيارية، تكتب `corrected_text/` فقط — §4.6، §6). **Atria backend (spec 005) هنا**.
- `src/pipeline/correction/morphological_verifier.py` + `flag_suspicious_words.py` — فحص صرفي (**camel-tools 1.6.0 مُثبَّت — spec 015**؛ لكن **المُتحقق يبقى REVIEW-ONLY** — قِيسَ كبوابة/مُصلح ورُفِض، §3/§12).
- `src/pipeline/ocr/surya_line_detector.py` — بديل تقسيم أسطر (**surya-ocr 0.22.1 مُثبَّت لكن معطَّل** — قِيسَ سلبيًا في spec 009، §3/§12؛ يتدهور للكاشف الكلاسيكي بأمان، الإعداد commented في `settings.yaml`).
- `src/pipeline/ocr/sync_vision_backends.py` — مزامنة الـ backends.

الإعداد: `config/settings.yaml` + `config/prompts.yaml` (انتبه: المسار **`config/`** — مجلد الإعداد الحالي، وليس جذر المشروع؛ الفقرة السابقة قالت إن `config/` محذوف وهذا **لم يعد صحيحًا**). **تنبيه spec 007**: `config/prompts.yaml` يُحذف منها كل ما هو غير مسكون — `ocr_prompts` و`review_prompts` و`analysis_prompts.{word_explanation,summarization,entity_extraction}` (0 مراجع في الكود، تحقق grep مباشر). **يتبقى فقط `analysis_prompts.text_correction`** (يقرأه `review_manuscript.py:141`).

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

- CER/WER عبر `jiwer` ضد أرضية صحيحة (Ground Truth) لصفحات مرجعية — **القياس يعمل الآن (spec 006)**: الأرضية = 620 بيت في `data/ground_truth/عمود النسب/عمود_النسب.clean.md` (تغطي ص23..ص67). المواءمة: `myenv/bin/python -m src.pipeline.evaluation.align_ground_truth --document "عمود النسب نسخة 2" --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md"`. القياس: `myenv/bin/python -m src.pipeline.evaluation.evaluate_cer --document "عمود النسب نسخة 2" --alignment "data/evaluation_reports/008/alignment.json" --report-dir "data/evaluation_reports/008" --diacritics-metrics --heatmap`. **المرجع الحالي (spec 008، 2026-09-18): CER 25.9% / WER 60.2% / تشكيل 82.1% (45 صفحة مُقيِّسة: 26 نظيفة + 17 ضعيفة + 2 مستعادة)** — كلها **قابلة لإعادة الإنتاج** (deterministic) و**= مسافة إلى benchmark عمل** (Constitution §VI). **المرجع السابق (spec 006): CER 25.0% / 43 صفحة** محفوظ في `data/evaluation_reports/006/` كخط أساس للفرق.
  - **التقرير النهائي (الإغلاق، 2026-09-18): `data/evaluation_reports/017-final/quality_report.{txt,json}`** — أُعيد توليد المرجع بالكامل بعد انتهاء البرنامج: **نفس الأرقام بالضبط** (CER 25.9% / WER 60.2% / تشكيل 82.1%)، تأكيدًا أن المُنتَج الحالي مستقر ولا يوجد انحراف غير مُكتشَف. هذا = **المرجع الرقمي الحاكم** لأي مقارنة مستقبلية.
- `baseline/` **غير موجود** رغم إشارات §2/§11/§14 إليه. لا تُبنَ عليه قرارات (spec 006 اكتشف ذلك). المرجع الرقمي الحالي = القياس أعلاه.
- Layout Accuracy: نسبة تمييز المتن/الحاشية/الشعر/العناوين.
- المرجع الرقمي الحالي: تقارير `data/evaluation_reports/006/` (spec 006) + منهج التقييم في `spec 006/research.md` §R5.
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

التبعيات المعتمدة: `paddleocr 3.7.0` + `paddlepaddle-gpu 3.2.0` (GPU فقط) + `paddlex 3.7.2` + `pymupdf 1.28.2` + `opencv` + `google-generativeai 0.8.6` + `groq` + `openai` (النسخة **المثبَّتة فعلًا 3.3.1** — §9 القديم كان يقول 2.54.0 وصار **صيته قديمًا**؛ صُحِّح بعد التحقق المباشر `openai.__version__`. كل الاستخدامات `chat.completions`، وواجهة `RateLimitError.response.headers` المستخدمة في spec 005 متوفرة في openai ≥1) + `anthropic` + `cohere` + `ruamel.yaml` + `torch 2.13.0` + `jiwer 4.0.0` (قياس CER/WER، §8) + **`surya-ocr 0.22.1` مثبَّت بـ `--no-deps` (spec 009 — لكنه معطَّل بعد قياس سلبي، §3/§12)** + **`camel-tools 1.6.0` مُثبَّت (spec 015 — REVIEW-ONLY، §3/§12)** + **`scikit-image` + `albumentations` + `lmdb` + `scipy` (spec 013 — training-only، لا تُستورد في الـ inference path)**؛ بيانات `calima-msa-r13` موجودة في `~/.camel_tools/`.
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
myenv/bin/python verify_all.py                       # الإغلاق: كل الفحوص الأربعة دفعة واحدة (أنظر الأسفل)
myenv/bin/python main.py                                # كامل input/
myenv/bin/python main.py --start 24 --end 26            # نطاق صفحات للتجارب
myenv/bin/python -m unittest tests.test_escalation_policy -v   # سياسة الـ Vision (§4.13)
myenv/bin/python -m unittest tests.test_cer_normalization -v   # تطبيع قياس CER/WER (§8)
myenv/bin/python -m src.pipeline.evaluation.verify_cer_harness   # فحص ميكانيكي لآلة القياس (§8)
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer --document "عمود النسب نسخة 2" --pages 24-26   # الوضع القديم (per-page GT)
myenv/bin/python -m src.pipeline.evaluation.align_ground_truth --document "عمود النسب نسخة 2" --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md"   # spec 006: المواءمة
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer --document "عمود النسب نسخة 2" --alignment "data/evaluation_reports/006/alignment.json" --diacritics-metrics --heatmap   # spec 006: القياس الكامل
myenv/bin/python review_manuscript.py --document "عمود النسب نسخة 2"
myenv/bin/python flag_suspicious_words.py --document "عمود النسب نسخة 2"   # يعمل الآن (REVIEW_ONLY)
myenv/bin/python sync_vision_backends.py
```

**`verify_all.py` (أداة الإغلاق — spec 017)**: تنفِّذ الفحوص الأربعة التي أنهت كل جلسة، دفعةً واحدة، وتُرجع 0 فقط إذا نجحت كلها:
1. **ثابت الدليل** — sha256 لكل `.txt` تحت `data/output` + `data/ground_truth` = `853419275001e5bbd407` (نفس بناء `find … -exec sha256sum … | sort | sha256sum` تمامًا). **الثابت يتحرك عمدًا** عند كل تطبيق/تراجع للتصحيحات (انظر تحديثات `verify_all.py`): القيمة في `verify_all.py` نفسها هي المرجع، هذه السطر ملخّص فقط.
2. **الاختبارات** — كل الوحدات (متوقع: 368 OK، skipped=2).
3. **Smoke** — `main.py --start 24 --end 26` exit 0 (الكتابة byte-identical وهذا جزء مما يؤكده الثابت).
4. **إعادة توليد الـ benchmark** — التقرير النهائي يجب أن يعيد **23.7% / 59.7% / 83.0%** بالضبط. **المرجع يُقاس الآن على `vault_corrected_text/` وليس `raw_text/`** (Phase 1 Task 6، 2026-09-22): البقاء على `raw_text/` يُبقي أخطاء OCR المُثبَت خطؤها؛ `raw_text/` يبقى قابلاً للقياس عبر `evaluate_cer --layer raw_text` (23.7% / 59.8% / 83.1%).
القراءة فقط بالنسبة لطبقات الدليل (لا تكتب فوق `raw_text/`/`ground_truth/` إطلاقًا). علم `--skip-smoke` لتجاوز ركض الصفحات (~2د).

### Definition of Done — التعديل لا يُعَد «منتهيًا» إلا إذا:
1. الملفات المتأثرة تمر `myenv/bin/python -m py_compile`.
2. ركض نطاق فعلي صغير (`--start 24 --end 26`) نجاحًا بـ `exit 0`.
3. المخرجات وُلِّدت في مكانها الصحيح.
4. **لا تغيير في `raw_text/`/`ground_truth/`** (immutable evidence — §6)؛ `baseline/` نفسه **غير موجود** (spec 006).
5. سلوك الكاش محفوظ (لم يُلغَ / لم يتغير مفتاحه).
6. **لا تسريب أسرار** في أي مخرج/سجل.
7. `CHANGELOG.md` حُدِّث عند تغيير سلوك مرصود.
8. **قياس CER/WER** أُنجز لكل تغيير يمس OCR/المعالجة المسبقة.
9. عند أي فارق بصري: قورنت أسطر PaddleOCR الخام مع القياس (spec 006) — أسطر تصعيد الرؤية (Vision) غير حتمية بين الركضات، فيُقارَن فقط ناتج الكاش الحتمي.

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

- القياس (§8): **آلة CER/WER جاهزة وتُستخدم الآن فعلًا** (spec 006 + spec 008). **المرجع الحالي (مُقاس 2026-09-18، spec 008): CER 25.9% / WER 60.2%** عبر **45 صفحة مُقيِّسة** (26 نظيفة / 17 ضعيفة الثقة / **2 مستعادة**)، **استرجاع التشكيل 82.1%** (فقد 17.9%)، **117 بيت هلوسة مشتبهة (تشخيصي)**. **المرجع السابق (spec 006): CER 25.0% / WER 59.9% / تشكيل 82.0% / 43 صفحة** — والفرق **صدق وليس تراجعًا**: ص59 وص67 كانتا **مُقصاتَين من القياس** (status=unmatched → CER 0.0%) بينما محتواهما الحقيقي سيئ (CER 64.9% / 47.3%)، وص60 كان مُضخَّمًا 71.2% → 54.1% بعد تصحيح نافذتها. **سبب ارتفاع CER قليلًا = دخول صفحات سيئة فعلًا للقياس** — وهذا هو الصحيح. كل الأرقام = **مسافة إلى benchmark عمل** (Constitution §VI). **أرضية GT كاملة** = 620 بيت — **تغطي ص23..ص67 فقط** (أول 22 صفحة نثرية خارجها، وكذلك ص68+).
- **spec 008 — عيب تصحيح المواءمة (منع إعادة الاكتشاف)**: `align_corpus` كان يُقدِّم المؤشر فقط عندما `gt_end is not None`؛ والصفحة `unmatched` كانت تُعيد `gt_start=gt_end=None` → **يتجمَّد المؤشر** → الصفحة التالية تُبحث في نافذة متأخرة صفحة كاملة → CER مُضخَّم. **التصحيح**: الصفحة unmatched الآن تستهلك نافذة تقديرية (**advance-by-count** من المؤشر — وليس anchor ضعيف: القياس أظهر أن anchor صفحة 59 وضعها 494 بينما الحقيقة 487) + امتصاص الآيات المتخطاة للصفحات غير المطابقة (GT 578–583). **النتيجة**: تغطية GT **كاملة 1..620**، ص59/ص67 مُقاستَان فعلًا، ص60 71.2%→54.1%. الصفحات matched الـ26 **لم تتغير** (تحقق byte-identical).
- **`camel-tools` 1.6.0 مُثبَّت (spec 015)** والمُتحقق يعمل: `MorphologicalVerifier().available = True`. **لكن كل أدوارها قِيسَت ورُفِضَت** (spec 015: بوابة 0/45 صفحة قابلة للتخطي، rho=−0.112 كثقة، 0.5% كـ fixer؛ spec 016: إصلاح التشكيل net-negative في كل تنويع). **تبقى REVIEW-ONLY** (`flag_suspicious_words.py` — راجع §3).
- **spec 011 — فقد التشكيل = سقف الـ recognizer وليس عيب pipeline (2026-09-18)**: سلسلة القياسات أثبتت أن التشكيل **يبقى بكسلًا** عبر preprocessing (probe لكل مرحلة: p23 259→401، p31 210→352 مكوّن؛ حبر النطاق العلوي 8-12k مقابل 79-81k للجسم في القصاصات النهائية) وأن الموديل **يُصدره** (4-10 علامات/سطر) لكنه **يضعه على حروف خطأ** (`وللسَليموللاسِْسْقاء`). **لا يوجد بديل**: PaddleOCR 3.7 بها موديلان عربيان فقط؛ `arabic_PP-OCRv5_server_rec` يفشل («No engine bindings registered») و`PP-OCRv6_medium_rec` يُصدر **صفر** تشكيل. **A/B كامل (45 صفحة)**: v3 → CER **+3.9pp أسوأ** (27.0%→30.9%) واسترجاع تشكيل **82.4%→8.6%** (34/45 أسوأ). **القرار: إبقاء v5** (الموديل الحالي صحيح). **لا تغيير في الكود شُحن** — الإنجاز = القياس + جعل `text_recognition_model_name` knob صريح في `settings.yaml` (كان default مُشفَّر في `ocr_engine.py`). **الخلاصة**: رافعات preprocessing/DPI/اختيار-موديل استُنفدت؛ الرافعة الوحيدة المتبقية لـ 66% أخطاء الحروف = **fine-tuning الـ recognizer** (Phase 4). التفاصيل `specs/011-diacritics-preservation`.
- **spec 012 — تقييم non-Paddle recognizer: السقف ليس خاصًا بـ Paddle (2026-09-18)**: إجابةً على توصية spec 011 (هل السقف خاص بـ Paddle أم بالمخطوط؟). **القيود Hardware أولاً**: GTX 1650 (3.63GB) لا تُشغِّل surya-recognition (docker spawn يفشل: «unknown or invalid runtime name: nvidia»؛ vLLM محلي OOM في vision tower رغم `cpu_offload_gb=2`) ولا أي VLM 7B. **الوحيد القابل للتشغيل**: `Qari-OCR-0.2.2.1-VL-2B-Instruct` = Qwen2-VL-2B + LoRA r=16 بـ **4-bit nf4** (1.55B params). **القياس على نفس GT slices** (p24 13..28، p31 107..118، p23 1..12): p24 CER **75.5%** (vs Paddle 138.1%) **لكن شطب التشكيل تمامًا** (11 علامة vs 203 = recall 5.3%)؛ p31 (أفضل صفحة Paddle 98.2%) = **19 حرف garbage إحداثي** `(101,101),(888,807)` = فشل recognition كامل (0%)؛ p23 recall 83.5% **لكن على نص مُهلوس** (يقرأ الحواشي المُشكَّلة ويُفسد الأبيات: `فَدَخَلْوا بِيْمَيْهِمْ في رَزِمْ`). **الخلاصة**: معماريتان مختلفتان تمامًا (VLM شمولي vs CNN+CTC لكل حرف) كلاهما يفقد التشكيل → **الصعوبة في جودة طباعة المخطوط**، ليس في Paddle. **القرار: لا تبديل ولا ensemble** (عدم استقرار per-page يُفصل أيضًا أي pipeline حتمي). **لا كود/لا config/لا بيانات تغيَّرت** — sha256 `91b3f61101170b233619` ثابت؛ **الخريطة الكاملة لخيارات OCR-side أُغلقت**: preprocessing (بريء) + DPI (غير معتبر) + surya (ضوضاء) + v3 (أسوأ) + non-Paddle (مرفوض) ← **fine-tuning = الرافعة الوحيدة المتبقية** (Phase 4). التفاصيل `specs/012-non-paddle-ocr-evaluation`.
- **spec 013 — بوابة جدوى fine-tuning: التقنية تعمل، التشكيل لم يتحرك (2026-09-18)**: الإجابة على توصية spec 012 (هل fine-tune سريع يحرِّك التشكيل؟). **بناء dataset من نفس crops الـ pipeline** (`build_ft_dataset.py` يعيد استخدام `input_handler`/`preprocessing`/`segment_text_rows` حرفيًا — ليست إعادة كتابة) مع labels = شطري الأبيات من GT عبر spec-008 alignment، صفحات `matched` فقط (band count == verse count)، التحقق من صحة الاقتران بـ OCR عشوائي. **346 train / 58 val** (الصفحات 63-67 محجوزة بالكامل — لا تسريب بين شطري البيت). **تفعيل مسار training** كان يتطلب إصلاح 4 فجوات (R1): training YAML غير موجود في الـ wheel (سحب من GitHub)، training registry لا يُستورد مع `import paddlex`، `PADDLE_PDX_PADDLEOCR_PATH` يجب أن يُضبط **قبل** استيراد الـ API package (وإلا `runner_root_path=None`)، و3 deps ناقصة (`scikit-image`/`albumentations`/`lmdb` — مُضافة لـ myenv، لا يستوردها main.py). **القيود Hardware**: batch 4، 384px width هي سقف 3.6GB (512px يُحدث OOM)؛ الافتراضي 320px **يُسطِّح** crop بنسبة 8:1 (4.4× ضغط) فيصبح غير مقروء؛ eval batch الافتراضي 128 يُحدث OOM وحده. **النتيجة (30 epoch، lr 1e-4)**: CER **28.6%→26.8%** على val، win/loss/tie **14/5/39**؛ **استرجاع التشكيل 85.2%→83.9%** (12/14) = **لم يتحرك**. 80 epoch → overfit (norm_edit_dis 0.49→0.59) = 346 عينة تتشبَّع. **3 مصائد صامتة** (R4) أنتجت garbage بثقة قبل تشخيصها: (1) تصغير charset إلى 57 حرفًا **أعاد تهيئة head** (log: `[120,60] not matched [120,749]`) فتُركت الأوزان المُدرَّبة؛ (2) `-o Global.pretrained_model` **يُتجاهل صامتًا** (log: `train from scratch`) — يجب وضعه في الـ YAML؛ (3) `max_text_length: 25` < أقصر label (26) → **recursion لا نهائي** في `MultiScaleDataSet.__getitem__` يظهر كـ `RecursionError` داخل `deepcopy`. **القرار**: fine-tuning **مُثبَت كتقنية** وينقل الفائدة لصفحات غير مرئية، لكن cross-entropy العادي **لا يُحسِّن التشكيل** → المرحلة التالية تحتاج loss واعٍ بالتشكيل أو قبول السقف. **لا كود/لا config/لا بيانات** — sha256 `91b3f61101170b233619` ثابت. التفاصيل `specs/013-finetuning-feasibility-gate`.
- **spec 014 — diacritic-aware fine-tune: السقف مُقبَل، البرنامج ينتقل لمرحلة المراجعة (2026-09-18)**: المحاولة الأخيرة على الجانبين مع stop condition binding. (1) **Corpus موسَّع**: 19 صفحة غير-`matched` كانت مُستبعدة كـ band-detection artifact (معظمها +1..+4 نطاقات ضوضاء، 4 منها متساوية أصلًا و`low_confidence` فقط) → **استرجعتها عبر sequence alignment** (DP على نصوص الـ OCR لكل نطاق vs أبيات GT، normalized-CER cost matrix، قبول الزوج عند **CER<0.6**، عقوبة تخطي 0.8) → **688 train / 148 val** (~2× 013)، الاقتران مُتحقَّق على p030. **النتيجة**: CER **33.1%→32.4%** (مكسب **تقلَّص** من −1.8pp إلى −0.7pp) و**الاسترجاع 85.5%→84.0%** (letters 23/15/110، diacritics 26/30). (2) **Diacritic-weighted CTC loss**: patch في `CTCLoss` (flag `dia_weight`، وزن العينة `1+عدد التشكيلات` محسوب من **encoded label indices** ضد charset الموديل — لا strings عبر batch) — **النتيجة مطابقة تمامًا** لِلْplain (32.4% / 84.0% / نفس W/L/T) رغم أن الـ flag كان نشطًا (CTCLoss 419→49 vs 419→50). **التشخيص (R3)**: الموديل **يُصدر** تشكيلًا بكثرة لكنه **يضعه على حروف خطأ** (`عَمْرَر أبُو عَبْدِ الإلَهِ` لـ `عَمْرٌ أَبُو عَبْدِ الإِلَه`) — مشكلة **position/association**، ووزن العينة scalar لا يحمل معلومة عن الموضع. **القرار: قبول السقف** — 17.9% = جودة المسح vs المُتعرِّفات المتاحة؛ **الـ fine-tuning line مُغلقة** (نفيان = stop condition binding)؛ **الـ 66% أخطاء حروف تُعالَج downstream** (post-OCR correction). **لا كود/لا config/لا بيانات** — sha256 `91b3f61101170b233619` ثابت، patch الـ loss في شجرة training **خارج** myenv (لا يؤثر على inference). التفاصيل `specs/014-diacritic-finetune`.
- **spec 015 — review-stage verification: البوابة/المُصلح مرفوضان، إشارة إصلاح التشكيل حقيقية (2026-09-18)**: المرحلة الأولى كانت **تشخيصًا**: `morphological_verifier.py` + `flag_suspicious_words.py` مكتوبان منذ زمن لكن **`camel_tools` لم يُثبَّت قط** → كل فحص يُرجع `None` صامتًا (التقرير فارغ دائمًا). التثبيت (`camel-tools 1.6.0`، DB `calima-msa-r13` موجود) → `available=True`. **القياسات الأربع على 45 صفحة**: (1) **flag rate 24.4%** (1,240/5,084) بدقة **99.9%** أن المُعلَّم خطأ فعلًا؛ (2) **كبوابة لتخطي LLM correction**: أقل معدل 11.3% لكل صفحة → **0 من 45 صفحة قابلة للتخطي** = مرفوض؛ (3) **كثقة (confidence proxy)**: Spearman rho(flag-rate, CER) = **−0.112** = **علاقة صفرية** = مرفوض؛ (4) **كمُصلح**: **0.5% فقط** (6/1,239) لها الشكل الصحيح بين المرشحين — الأخطاء **merged words** (`بِنسنبَتَة`=بِنْسِبَتِه) و**inserted letters** (`فُذدَخلوا`=فَدَخَلُوا)، وليست confusion لحرف واحد. **الإشارة الحقيقية (R4)**: **226 token** الحروف فيها صحيحة لكن التشكيل خاطئ لكلمة حقيقية = **بالضبط خطأ spec 011** ("يُصدر التشكيل ويضعه على حروف خطأ")؛ المُحلل يقدم التشكيل الصحيح لـ **58 منها (25.7%)** (`بنو`→`بَنُو`، `عِلم`→`عِلْمُ`، `كان`→`كانَ`). **القرار: لا نشر كبوابة أو مُصلح** — تبقى review-only flagger (الآن تعمل فعلًا). **الخطوة التالية (spec 016)**: بناء **diacritic-repair pass** على إشارة الـ 58 — disambiguation بدون GT + شرط تطبيق محافظ + كتابة لـ `review/` أولًا. **الحد الأقصى (honest)**: 25.7% تُقاس **بالـ GT**؛ المُنفَّذ يختار بدون GT فستقل الدقة. **لا كود/لا config** — sha256 `91b3f61101170b233619` ثابت؛ `camel-tools` مُضافة لـ myenv (additive، الـ OCR path لا يستوردها). التفاصيل `specs/015-review-stage-verification`.
- **spec 016 — diacritic-repair pass: مرفوض net-negative في كل تنويع (2026-09-18)**: **الإشارة (58/226 = 25.7%) غير قابلة للحصاد بدون GT.** أربع سياسات قِيسَت على نفس 45 صفحة: (1) **unique-analysis form**: **201/226 (89%)** لها تحليلات متعددة أو لا تحليل → فقط **25 (11.1%)** لها شكل واحد، ودقته **24.0%** (6 صحيح / 19 خاطئ)؛ (2) **MLEDisambiguator** (LM ranker من camel_tools): yield **52/225 = 23.1%** لكنه **يكسر 97/131 = 74.0%** من الـ tokens الصحيحة — أي net-negative 2:1؛ (3) **conservative** (طبِّق فقط عندما يكون شكل الـ OCR نفسه غير صالح تحليليًا + حفظ الحروف): **262 applied → 47 fixed / 97 broke / 118 still wrong = net −50**؛ الـ 118 تثبت أن **شكل GT غالبًا غير موجود في الـ pool أصلًا**. **السبب الجذري (R2)**: **style mismatch وليست مشكلة disambiguation** — الناسخ يترك أدوات الربط بدون تشكيل (`في`،`إذ`،`هم`،`مَا`،`حتْى`) بينما `calima-msa-r13` (MSA) يُشكِّلها كاملةً؛ هذه التصادمات **unique+certain+wrong** (`فِي` لـ `في`) = لا يصلحها أي confidence threshold أو reranker. **القرار: غلق السطر** (3 إخفاقات = stop condition binding) — حتى review-only مرفوض (74% false-edit ستُغرق المراجع البشري). **الـ 25.7% تُسجَّل كـ upper bound غير قابل للتحقيق**. الأفكار غير المُجرَّبة (meter/rhyme rerank، analyzer خاص بالمخطوط) out of scope: الربح ~1% من الـ tokens مقابل مشروع بحثي. **لا كود/لا config/لا بيانات/لا myenv changes** — sha256 `91b3f61101170b233619` ثابت، 142 اختبار OK. **التالي (spec 017)**: **vision-fallback escalation review** — آخر مكوّن في الـ pipeline يتخذ قرار جودة غير مُقاس (spec 012 قاست الـ VLM منعزلاً، لكن أحدًا لم يقِس ما يفعله مسار الـ escalation بمخرجه). التفاصيل `specs/016-diacritic-repair`.
- **spec 017 — vision-fallback escalation review: الـ escalation path مُقيَّس و**ساكن** (+0.00pp)؛ عيب rotation السجل تم إصلاحه (2026-09-18)**: الهدف كان قياس آخر قرار جودة غير مُقاس في الـ pipeline. **النتيجة المُزاوجة**: `_run_page_once()` بـ vision on vs off على نفس القصاصات (15 صفحة: أسوأ 5 بـ CER + عيّنة 10 طبقات) → **+0.00pp، byte-identical، 0 escalations اشتعلت**. السبب: ثقة السطور المُتخلَّفة mean 0.60 مقابل threshold 0.55 (107 سطر قِيسَت). **القياس السطحي الأول كان خاطئًا**: سجل `escalations.jsonl` كان **245 مدخلًا من ≥10 شغلات** (page-order resets عند 9 حدود؛ smoke tests على ص 24–33)، **0/245** نصها موجود في المُنتَج النهائي → "80.9% تحسّن" و"35/36 رفض خاطئ" كانت تقيس **حالات مُلغاة**؛ بالمعيار المطلق (CER≤0.35) **0/245** قابل للاستخدام. **الـ 26 رفضًا للإيقاع المهيكل** (`وَمَا لِلْعَيْنِ مِنْ دَمْعٍ` في ص 24–27) **صحيحة** — الإيقاع غير موجود في GT تلك الصفحات أصلاً. **العيب الحقيقي (أُصلح)**: `save_escalations()` فتحت السجل append دائمًا → سجل مراجعة يصف نصوصًا غير موجودة = أسوأ من لا شيء؛ الآن **rotation لكل شغلة** (أرشفة إلى `escalations.prev.jsonl`، guard against re-rotation). **الـ backends كلها ميتة حاليًا** (gemini free-tier quota 20/يوم، openrouter HTTP 402 no credits، groq HTTP 404 model retired، sovereign لا credentials) — القياس المباشر blocked تشغيليًا. **القرار: لا تغيير في policy** (لا فشل مُقاس لإصلاحه). **تغيير واحد**: `src/pipeline/output/output_generator.py`. sha256 `91b3f61101170b233619` ثابت، 142 اختبار OK، smoke exit 0. **البرنامج وصل لنقطة أن أي تحسين دقة آخر blocked على credentials خارجية**. التفاصيل `specs/017-escalation-review`.

- **spec 018 — تصحيح spec 017: الـ escalation ليس ساكنًا، الحصة هي العائق (2026-09-19)**
- **spec 019 — لا يوجد مسار escalation مجاني بديل (قياس سالب، 2026-09-19)**
- **spec 020 — جولة الحصة الثانية: 25.9% → 25.0% (2026-09-20)**
- **spec 021 — تشخيص فساد ToUnicode في لمعة + وحدة إصلاح (2026-09-20)**: بدلاً من النسخ اليدوي للـ GT، شخَّصتُ سبب تقاعد `direct_text`: كل كلمة فاسدة **أناگرام** صحيحة (`اهلل`↔`الله`، `احلمد`↔`الحمد`) — الـ CMap يُصدِر مكوّنات ligature اللام-ألف بترتيب خطأ (أحرف zero-width تتشارك x). **poppler يُعيد نفس الفساد** → في الـ PDF نفسه. **الفرز الهندسي العام رُفِض** (يُصلح النثر 0.207→0.053 لكنه **يكسر** الأنساب 0.400→0.457). **المُنفَّذ**: `tounicode_repair.py` = 83 تصحيحًا مُتحقَّقًا + guarded adjacent-swap (آمن صارم: **8 صفحات أفضل، 0 أسوأ**). **النثر أصبح مقروءًا** (`data/output/لمعة النسب/repaired_text/`). **تنبيه منهجي (صُحِّح في 021b)**: نطاق الفساد قِيسَ أولًا بمعيار فاصل ` ... ` الذي **لا تملكه لمعة** فبدا محصورًا في النثر — القياس الصحيح يُظهره **شاملاً ~30% على كل الصفحات**. مع ذلك **لا يُلغي تقاعد direct_text** (الطبقة ليست مرجعًا موثوقًا) (cross-check لا بديل). **GT لـ لمعة تعذَّر**: ليست نصًا مرجعيًا رقميًا (439هـ)، أبيات غير مرقَّمة، وتتطلب قراءة الصور — **مفتوح للمستخدم**.: انقلاب الحصة اليومية أتاح جولة ثانية. **p59 0.652→0.365**، **p65 0.735→0.429**، **p67 0.472→0.437** (تحسُّن صافٍ). **p28/p38/p43 تدهورت +0.02 لكل منها** من escalations لم تُصب أسطرها الأساسية — **رُدَّت** (القاعدة: يُقبل التحسُّن فقط). النتيجة: **CER 25.0% / WER 59.9% / تشكيل 81.3%** (الثابت `8c04e8ca624cafecc5ea`، تقرير `019-escalation-pass`). **حقيقة مهمة**: p67 تحسَّنت **بدون أي escalation مقبولة** — PaddleOCR stochastic، فإعادة التشغيل وحدها أحيانًا تُحسِّن (مجاني ولكن غير حتمي). **الحصة تنفد بعد ~10 نداءات/يوم** → ~3–6 صفحات يوميًا؛ إنهاء 457 سطر قابل للتصعيد = **عدة أسابيع** على المجاني، أو **جولة واحدة بمفتاح مدفوع**.: فحصت كل backend ميت علّه يُحيي المسار دون مفاتيح مدفوعة. **Groq**: 13 موديل متاح، **صفر VLM** (Groq أوقف كل موديلات الرؤية؛ البديل النصّي `qwen3.8-27b` لا يُجيد الصور). **OpenRouter**: فيه VLM مجاني واحد (`inclusionai/ling-3.0-flash-vl:free`، cost=0 فعلًا) — اختبرته end-to-end على 18 سطر حقيقي من ص29 بنفس طريقة الـ pipeline (surya line crops). **النتيجة: أسوأ من PaddleOCR** (per-verse CER **0.323 vs 0.216**؛ و0.255 vs 0.228 بعد حذف فشل 429). **السبب الجوهري: hallucination لا قراءة** — يُصدِر عربية مُشكَّلة معقولة المظهر بدل قراءة الحروف فعليًا (`أتحف`→`أقعد`، `وغمسوا`→`وغفروا`). يفوز فقط على أسوأ 4 أسطر ولا يعوِّض الباقي. **القرار: الرَّفض — لا بديل مجاني**. الـ lever الوحيد المُثبَت = **gemini (مدفوع)**.: أُعيد القياس بعد عودة gemini (quota reset يومي). إعادة p27–p30 أشعلت **8 escalations مقبولة** وحسَّنت CER فعلًا: **p27 0.309→0.279**، **p29 0.307→0.254** (p28 بلا تغيير). النصوص المُصعَّدة صحيحة (`وواخَوا أث مِّىالحُمرإذا` ← `واخْتَلَفُوا أَنْ سِوَى الخُمس ⁽٤⁾ إِذَا`). السطح: **457 سطر** تحت 0.55 + 1,337 في 0.55–0.65. **لكن gemini free tier = 20 نداء/يوم**، ماتت في منتصف تجربة 10 صفحات. **القرار المُعدَّل: المسار يعمل لكنه مقيد بالحصة — لا يُتوسَّع بلا مفاتيح مدفوعة**؛ وصف spec 017 بـ«inert» كان مضلِّلًا لظرفه. **إعادة اعتماد**: `018-rebaseline` = **CER 25.9% / WER 60.4% / تشكيل 81.5%** (الثابت `9c8e1caeba3deb3a31ee`)؛ 82.1% غير قابلة للتكرار مع تقاعد direct_text. أيضًا: **«21% extra lines» من spec 008 لا تتكوَّن** — net **−5 أسطر/620 بيت**؛ الأخطاء within-line.
- **spec 010 — ثوابت الـ layout صارت DPI-aware + قياس 300 DPI سلبي إحصائيًا** (2026-09-18): الفرضية كانت «الحروف أصغر من 30px عند 200 DPI» — **دُحضت بالقياس المباشر** (المتوسط 32px عند 200 DPI). **12 ثابت pixel-based** في `page_layout_detector.py`/`segment_text_rows.py` صارت تُشتَق من الـ DPI (`set_dpi_scale(dpi)` تعيد ربطها بمعامل dpi/200، كل ثوابت النسبة ratio لم تُمَس). **A/B على 45 صفحة بنفس GT windows**: CER موزون 26.8% → 25.3% (−1.5pp، 25 تحسَّنَت/15 تدهورت/5 ثابتة)، **لكن paired t=1.44 (p≈0.16) و95% CI [−0.10,+3.43]pp يعبر الصفر → غير معتبر إحصائيًا** (spec 009 علَّمنا: لا تُشحن تقديرًا نقطة favorable ليس معتبرًا). تكلفة 2× runtime (411.7s) و2.25× بكسلات. **القرار (بموافقة المستخدم): إبقاء 200 DPI** — **لكن فك الارتباط شُحن** (scale=1.0 = byte-identical، sha256 `91b3f61101170b233619` مُتحقق). **تشنخيص إضافي**: 40/41 صفحة متغيرة حافظت على عدد الأسطر المتطابق → الـ scaling سليم والفرق حقيقي في نص الـ OCR وليس عيب scaling. **الخلاصة الاستراتيجية**: رافعات جودة الصورة العامة استُنفدت (surya −0.6pp، 300 DPI −1.5pp غير معتبر) → الـ spec القادم **يستهدف التشكيل تحديدًا** (17.9% من الحركات مفقودة) بدل شراء دقة للصفحة كاملة.
- **`surya-ocr` مثبَّت + مُعطَّل بعد قياس سلبي** (spec 009، 2026-09-18): `surya-ocr 0.22.1` مُثبَّت بـ `--no-deps` (صفر أضرار: `openai` 3.3.1 و`pillow` 12.3.0 و`opencv-python-headless` 5.0.0.93 سليمة؛ الـ deps الناقصة فقط أُضيفت: `beautifulsoup4`/`filetype`/`platformdirs`). **عُثر على السبب الجذري لـ«0 سطر»**: `DetectionPredictor()` الافتراضي in surya 0.22.1 هو **server-backed** — يُطلِق subprocess خادم يحمِّل النموذج على `settings.MODEL_DTYPE` = **fp16 على CUDA**، وEfficientViT (`text_detection/2025_05_07`) يُنتج **heatmap كله NaN** (تحقق مباشر: fp16 nan=60000/max=nan؛ fp32 nan=0/max=0.957) → NaN ينجو من cast إلى uint8 كصفر → الخادم يُرجِع «0 text lines» مع **HTTP 200** (فشل صامت). **الإصلاح**: `DetectionPredictor.local(dtype=torch.float32)` في `surya_line_detector.py`. **القياس (45 صفحة، A/B متطابق)**: CER موزون 27.0% → **26.5%** (−0.6pp = ضوضاء؛ 24 تحسَّنَت / 17 تدهورت / 4 ثابتة؛ ص59 −26.4pp لكن ص55 10.4%→23.3%)؛ oracle pick-per-page 23.9% **يحتاج GT** (غير قابل للنشر)؛ قاعدة اختيار بسيطة (count-agreement) تعطي 26.4%. **القرار: surya يبقى معطَّلًا** — تقسيم الأسطر **ليس عنق الزجاجة** (يتطابق مع ميزانية أخطاء spec 008: 66% أخطاء حروف / 21% أسطر زائدة / 13% أبيات ساقطة). الإعداد commented في `settings.yaml` مع التوثيق الكامل لإعادة التفعيل لاحقًا.
- تصعيد الرؤية **غير حتمي** + حصص 429 خارجية؛ `repeated_verbatim` **دائم الآن** عبر `repeated_verbatim_tracker.py` (SQLite في `output/.cache/`).
- `paddlepaddle-gpu` فقط (لا نسخة CPU) — المشروع يحتاج GPU لتشغيل OCR.
- جودة الصفحات الخام ضعيفة (أمثلة موثقة في `spec 006/research.md` §R5 + تقارير القياس)؛ أسطر الضجيج (مثل `..wmmw.`، `ـــ`) تُفلتر الآن عبر `_is_noise_line()` (بلا حرف عربي حقيقي) + `_is_repetitive_garble()` (بنية تكرار الحرف الواحد: `شسسسسش` → صحيح عربيًا لكنه جمعيًا حرف/حرفان مكرران — لا يُقرأ). أُعيد فحص السلة على كامل الـ corpus الحالي: إصابة واحدة (`شسسسسش` ص 20) وصفر نتائج إيجابية كاذبة؛ يجب تكرار هذا الفحص عند أي توسيع للقاعدة.
- هلوسة الـ Vision الشهيرة (`وَمَا لِلْعَيْنِ مِنْ دَمْعٍ...` على صفحات 20–27) **مُعالَجة**: لا تصعيد لخطوط الضجيج، ولا قبول لـ `repeated_verbatim` (§4.13). لا تزال الهلوسات غير المتكررة على كروبات ضعيفة وسيلة خطورة قائمة — تُسجَّل في escalations للمراجعة ولا تُكتشف آليًا بعد.
- **Atria-Dawn-Preview كـ backend تصحيح (spec 005) — قيود أصلية في الموديل نفسه**، تختلف عن قيود الأداة (السطر السابق):
  - **نصي فقط**: واجهة `correct(prompt: str)` لا تستقبل صورًا أصلًا، فالقيد مُرضى بنيويًا (ليس بفحص وقت تشغيل). لا يجوز استخدام هذا الـ backend في مسار `vision_fallback` (يتطلب `transcribe(image)`).
  - **معرّف الموديل حساس للحالة**: يجب أن يطابق `Atria-Dawn-Preview` **حرفًا بحرف** في `settings.yaml` وفي ثابت الصنف؛ أي تغيير حالة = خطأ not-found يُزيل الـ backend من الدوران بعد أول محاولة (يصنِّفه `_looks_like_permanent_error` دائم).
  - **الكوتة RPM مشتركة**: 429 من Atria **عابر بطبيعته**، لذا يُعالَج داخل الـ backend (احترام `Retry-After` + محاولة واحدة) قبل أن يصل لتصنيف المحرك الذي يعتبر أي 429 دائمًا — التفاصيل في §4.13.1 و FR-007.
  - **`reasoning_content` يستهلك من `max_tokens`**: الموديل يُصدر reasoning في حقل منفصل **يُحتسب من سقف المخرجات**؛ عند سقف صغير يُرجِع أحيانًا `finish_reason='length'` و`content=None` لنفس الـ prompt ثم ينجح عند الإعادة (**عابر**، صُنِّف كذلك عمدًا لئلا يُقتل الـ backend ظلمًا لباقي الركضة). **لكن على صفحة حقيقية كاملة**: الـ reasoning **يتمدَّد لملء أي سقف** ويتجاوز 8000 → كل صفحة تفشل وترجع `raw`، والسقف الكافي (≥16k) **يعلِّق النداء >200s** (research §R2.2). يعني: الموديل لا يصلح حاليًا لتصحيح صفحة كاملة بشكل الـ prompt الحالي — **قيد شكل/موديل لا كود**؛ الكود يسقط بأمان على `raw` دائمًا.
  - **لا يُعرف بعد كيف تؤثر مرحلة التصحيح على CER/WER** — المرحلة REVIEW_ONLY (§4.6 ملاحظة التوتر) ولا يمكن قياسها قبل وجود أرضية GT (§8).
- **أداة opencode + نموذج Atria (TEXT-ONLY) — ضمان تجريبي الجزء منه:** فرض أن Atria-Dawn-Preview لا يستقبل صورًا/PDF يعتمد جزئيًا على **API إضافي تجريبي** في opencode. الطبقة الأساسية والدائمة هي إعلان `modalities.input: ["text"]` في `~/.config/opencode/opencode.jsonc` (ميدان config مستقر وموثَّق في schema) الذي ينفِّذه opencode في مسار الإرسال الأساسي عبر `unsupportedParts()` في `provider/transform.ts`. أما الطبقة الثانوية فهي خطّاف `experimental.chat.messages.transform` في plugin `~/.config/opencode/plugins/atria-text-only-guard.js` الذي ينتزع أجزاء image/PDF قبل التسلسل. **الخطّاف التجريبي قد يتغيَّر أو يتعطَّل بين إصدارات opencode بلا إشعار** — إن طُوِّر opencode وتوقَّف منع الصور/PDF فجأة، **افحص هذا الخطّاف أولًا** مقابل توثيق/تواصفات plugin الحالية (`@opencode-ai/plugin`) قبل تصحيح أي شيء آخر؛ الإعلان في config يظل ساريًا ويفصل الحماية وحده حتى لو اختفى الخطّاف بالكامل.

---

## 13) Roadmap — خارطة الطريق (ليست قائمة تنفيذ)

> **The roadmap is not an execution queue.** لا تُنفَّذ بنود الخارطة إلا إذا كانت المهمة الحالية تطلبها **صراحةً**. كل بند فيها STATUS=planned/blocked حتى تُكلف به.

**Phase 1 — أثر عالٍ / تكلفة قليلة:**
- ~~دالة ثنائية تحمي التشكيل~~ (**مُنجَزة**) — `adaptive_binarize` في `preprocessing.py` / `adaptive_binarize_gray`، موحَّدة في موضع واحد (تلغي نسخ Otsu الثلاث). باقي: قياس CER (§4.12).
- ~~فلتر أسطر الضجيج~~ (**مُنجَز**) — `_is_noise_line()` يستبعد الآن أي سطر بلا حرف عربي حقيقي (رفض التطويل/الحركات/الأرقام/اللاتيني).
- ~~إزالة كود DEBUG في `ocr_engine.py` + تنظيف `debug/`~~ (**مُنجَز**) — حُذف، وشُطب مجلد `debug/`.

**Phase 2 — بنية وسيط (ترقية):**
- ~~تثبيت `surya-ocr` + التفعيل + قياس CER~~ (**مُنجَز بنتيجة سلبية — spec 009، 2026-09-18**): 0.22.1 مُثبَّت بـ `--no-deps`؛ عُثر على **fp16 all-NaN bug** في server-backed `DetectionPredictor` وصُلِح (`DetectionPredictor.local(dtype=torch.float32)`)؛ A/B على 45 صفحة → CER موزون 27.0% → **26.5%** (−0.6pp ضوضاء؛ oracle 23.9% يحتاج GT). **القرار: معطَّل** — تقسيم الأسطر ليس عنق الزجاجة (66% أخطاء حروف في ميزانية spec 008). الإعداد commented في `settings.yaml` مع التوثيق.
- كشف Gutter هندسيًا على الـ Bounding Boxes، وعزل الزخارف/الإطارات بقناع قبل OCR. — **مُغلق بالقياس (spec 022): الزخارف معزولة أصلًا (is_edge_border_strip)؛ 0 أسطر ضجيج؛ فاصل 96.4%**
- رفع DPI الافتراضي إلى 300 وفك الثوابت المرتبطة بـ 200 — **فك الارتباط مُنجَز (شُحن)**؛ **قياس 300 DPI رُفِض**: −1.5pp لكن paired t=1.44 (p≈0.16) و95% CI يعبر الصفر (spec 010). الإبقاء على 200؛ التفاصيل §12.
- ~~جعل `repeated_verbatim` دائمًا~~ (**مُنجَز**) — `repeated_verbatim_tracker.py` (SQLite بدل ذاكرة الجلسة)، متصل بـ `vision_fallback.py` عبر `repeated_verbatim_db` في `settings.yaml`.

**Phase 3 — نظام الثقة/التوسّع:**
- ~~Confidence كلمة→سطر→صفحة مع حلقة إعادة معالجة للصفحات <50%.~~ (**مُنجَز**) — `_aggregate_page_confidence` (متوسط مرجَّح بعدد الحروف للأسطر المُبقاة) + إعادة معالجة مرة واحدة عبر `set_binarize_params` عند `page_confidence < ocr.page_confidence_reprocess.threshold` (§4.10).
- Ensemble محلي Paddle vs Surya على عينة، واعتماد الأفضل — **قِيسَ (spec 009) ورُفِض**: 27.0%→26.5% (−0.6pp ضوضاء)؛ oracle 23.9% يحتاج GT. انظر §3 و§12.
- ~~إضافة Qwen-VL-Chat محلي/مجاني كـ backend آخر.~~ (**مُنجَز**) — `QwenVLBackend` في `vision_fallback.py` (Ollama OpenAI-compatible، موديل افتراضي `qwen2.5vl:7b`، بلا مفتاح API). **غير مُفعَّل افتراضيًا** — سطر `- qwen_vl` في `rotation_order` معلّق في `settings.yaml`؛ آمن حتى على آلة بلا Ollama (فشل سريع ثم خروج من الدوران).

**Phase 4 — اللغة والقياس (مستقبلي):**
- ~~تثبيت `camel-tools` + القاعدة الصرفية~~ (**مُنجَز — spec 015**): 1.6.0 + `calima-msa-r13`، `available=True`. **لكن كل أدوارها قِيسَت ورُفِضَت** (بوابة/ثقة/fixer في 015، إصلاح التشكيل في 016) — تبقى **REVIEW-ONLY** (`flag_suspicious_words.py`). التفاصيل في **Phase 5** بالأسفل و§12.
- `normalize_arabic_unicode` و`repair_arabic_spacing`. — **مُغلق بالقياس (spec 022): CER +0.0000 على أسوأ 4 صفحات — أخطاء recognition لا تنسيق**
- Dataset أرضية صحيحة (50 صفحة صعبة: شعر/عناوين/حواشٍ) + سكربت `jiwer` (CER/WER) + Layout Accuracy — **مُغلق بالقياس (spec 022): البنية التحتية موجودة (alignment.json + quality_report.json عبر 45 صفحة)** — يُعمل بعد كل تعديل.
- - **(طموح) Fine-tuning لـ PaddleOCR على الخطوط التراثية — مغلق: السقف مُقبَل (spec 014)**. 013 أثبتت أن التقنية تعمل (CER 28.6%→26.8%) لكن التشكيل لا يتحرك؛ **014 جربت الجانبين وفشلت**: corpus موسَّع (688/148 عبر sequence alignment) → CER 33.1%→32.4% فقط و**الاسترجاع 85.5%→84.0%**؛ diacritic-weighted CTC loss → **نتيجة مطابقة تمامًا**. التشخيص: الموديل يُصدر التشكيل ويُخطئ في **موضعه** (`عَمْرَر` لـ `عَمْرٌ`)، وزن العينة لا يحل مشكلة position. **stop condition binding: لا مزيد من متغيرات fine-tuning**. الـ 66% أخطاء حروف = جودة المسح vs المتعرِّفات.

**Phase 5 — مرحلة المراجعة (مُنجَزة بالكامل، 015–017):**
- ~~تثبيت `camel-tools` + القاعدة الصرفية~~ (**مُنجَز — spec 015**): 1.6.0 + `calima-msa-r13`. **كل أدوار المُتحقق قِيسَت ورُفِضَت**: كبوابة لتخطي LLM correction → **0/45 صفحة قابلة للتخطي** (أقل معدل 11.3%)؛ كـ confidence proxy → **rho(flag-rate, CER) = −0.112** (علاقة صفرية)؛ كـ fixer بالـ confusion groups → **0.5%** (الأخطاء merged words/inserted letters). **الإشارة الوحيدة الحقيقية**: 226 token بحروف صحيحة وتشكيل خاطئ، المُحلل يقدم الصحيح لـ **58 (25.7%)** — لكن **بدون GT** (spec 016).
- ~~إصلاح التشكيل بالتحليل الصرفي~~ (**مغلق: net-negative — spec 016**): 4 سياسات قِيسَت — unique-analysis (24.0% دقة، يكسر 50% من الصحيح)؛ MLEDisambiguator (yield 23.1%، **يكسر 74.0%**)؛ conservative (net **−50**). **السبب الجذري: style mismatch** — الناسخ يترك أدوات الربط بدون تشكيل بينما الـ MSA analyzer يُشكِّلها كاملةً (`فِي` لـ `في`) = تصادمات unique+certain+wrong لا يصلحها reranker. **الـ 25.7% تُسجَّل كـ upper bound غير قابل للتحقيق.**
- ~~مراجعة مسار الـ vision escalation~~ (**مُنجَز — spec 017**): قياس مُزاوج (vision on/off، 15 صفحة) = **+0.00pp، 0 escalations** (ثقة السطور mean 0.60 vs threshold 0.55). **اكتُشف عيب حقيقي وأُصلح**: سجل `escalations.jsonl` كان يراكم عبر الشغلات (245 مدخلًا من ≥10 شغلات، **0/245 في المُنتَج**) → صار rotation لكل شغلة. **الـ backends كلها ميتة الآن** (gemini quota / openrouter 402 / groq 404 / sovereign لا credentials).

**حالة البرنامج (الإغلاق، 2026-09-18):** كل مكوّن في الـ pipeline قِيس. **CER 25.9% / WER 60.2% / تشكيل 82.1%** (التقرير النهائي `data/evaluation_reports/017-final/`). الخط الجانبي للأخطاء (66% حروف) محصور بين **جودة المسح** (17.9% تشكيل مفقود) و**المُتعرِّفات المتاحة** (Paddle هو الأفضل؛ VLMs تَخلع التشكيل؛ fine-tuning لا يحرِّكه). **كل البنود الهندسية أُغلقِت بالقياس (spec 022)** — **مهمة الـ escalation بـ gemini أُلغِيت نهائيًا (2026-09-20): لن تُدفع مفاتيح**؛ المسار نفسه ثبت أنه يعمل (spec 018: 8 escalations حسَّنت p27/p29 بـ −3.0pp/−5.4pp) لكنه مقفول خلف حصة مجانية ~20 نداء/يوم. **لا يتبقَّى سوى GT لـ لمعة (تحتاج قارئًا بشريًا للصور).**

---

## 14) CHANGELOG Policy — سياسة السجل

- `CHANGELOG.md` = **سرد تاريخي** للسلوك المرصود (بالعربية، بنمط المستند) — ليس «الحالة الحالية» (انظر §2).
- سجّل فيه عند تغيير سلوك مرصود أو عند طلب صريح.
- `baseline/` **غير موجود** (spec 006) — لا تُبنَ عليه قرارات.
- عند بدء مهمة تحسين: شغِّل القياس (`align_ground_truth.py` ثم `evaluate_cer.py --alignment`) لـ«قبل»، نفِّذ، ثم أعد القياس لـ«بعد». الفرق هو الدليل الوحيد المقبول (§4.12).

### 14.1) قرارات مؤجَّلة (spec 007) — لا تُعِد اكتشافها

| العنصر | القرار | السبب |
|---|---|---|
| `data/archive/debug_page107_resolved.zip` (1MB) | **يُبقى** | دليل تاريخي لتصحيح ص107 (مرحلة ink-density) — حذفه لا يفيد الجودة |
| `config/opencode.json` (يظهر محذوفًا في `git status`) | **يُترك كما هو** | شأن هجرة opencode إلى `~/.config/opencode/` + `.opencode/` — **خارج ممر المشروع**؛ لا يُسترجع ولا يُلتزم (§10) |
| `docs/PROJECT_SUMMARY.md` | **يكتفي بوسم «تاريخية»** | لقطة موسوعية بتاريخ 2026-09-06 تصف البنية المسطّحة القديمة؛ إعادة كتابتها = جهد كبير مقابل قيمة منخفضة — الميموري الحاكم = هذا الملف |
| `.claude/skills/clean-code-guard` | **symlink مقصود** — لا يُحذف | يشير إلى `../../.agents/skills/clean-code-guard` (تحقق مباشر) — تثبيت skill موحَّد، **ليس تكرارًا** |
| `docs/CLAUDE.md` | **ميموري مُصغَّر (spec 007)** | يحمل الهوية + الأرقام + القواعد الصلبة فقط، ويُحيل لهذا الملف كالعقد الحاكم — لتقليل سطح الانحراف |