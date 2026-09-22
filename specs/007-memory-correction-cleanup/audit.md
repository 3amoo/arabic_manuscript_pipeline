# Audit — spec 007 (تدقيق اتساق الميموري)

> كل سطر = ادعاء في الميموري ← مصدره ← **مطابق/لا**. كل فحص **ميكانيكي مباشر** (الأوامر قابلة لإعادة التشغيل).
> تاريخ التدقيق: 2026-09-18. أي انحراف صُحِّح **ضمن هذا الـ spec** (US5).

## A. الاكتشافات الكبرى (صُحِّحت)

### A1 — ❌→✅ ادعاء تثبيت surya-ocr و camel-tools (الاكتشاف الأكبر)

| ما كانت الميموري تقول | الواقع (مُتحقَّق) |
|---|---|
| §3: «`surya-ocr 0.22.1` مُثبَّت... مفعّله صار جاهزًا (`available=True`، 20 bands)» | `SuryaLineDetector().available = **False**` — «No module named 'surya'» |
| §3: «`camel-tools 1.6.0` + `morphology-db-msa-r13` مثبَّتان والتول يعمل فعلًا (`available=True`)» | `MorphologicalVerifier().available = **False**` — «No module named 'camel_tools'» |
| §9: القائمة كلاهما «مثبَّت» | `pip list` = لا سورة ولا camel |
| §12, §13: «مُنجَز 2026-09-06» | الحزمتان **غير موجودتين**؛ **بيانات `calima-msa-r13` موجودة** في `~/.camel_tools/data/morphology_db/` |

**فحص الأوامر**:
```
$ myenv/bin/python -m pip list | grep -iE "jiwer|surya|camel|openai|paddle"
jiwer 4.0.0 / openai 3.3.1 / openai-harmony 0.0.8 / paddleocr 3.7.0 / paddlepaddle-gpu 3.2.0 / paddlex 3.7.2
$ myenv/bin/python -c "from src.pipeline.ocr.surya_line_detector import SuryaLineDetector as S; print(S().available)"
False  (Surya line detector could not be initialized (No module named 'surya')...)
$ myenv/bin/python -c "from src.pipeline.correction.morphological_verifier import MorphologicalVerifier as M; print(M().available)"
False  (Morphological verifier could not be initialized (No module named 'camel_tools')...)
```

**الأثر**: هذا ادعاء **حاسم (load-bearing)** — spec 009 (تفعيل Surya) و spec 011 (camel token-verification) مبنيَّان على وجودهما. التدهور آمن (كلا الصنفين يسقط للكاشف الكلاسيكي / skip)، لكن الخطط كانت ستفشل عند البدء.

**التصحيح**: §3 (Surya + CamelTools → `blocked`)، §9، §12 (سطران)، §13 (Phase 2 + Phase 4 → «أُلغي التثبيت») + §5 (سطرا morphological_verifier/surya_line_detector).

### A2 — ❌→✅ CLAUDE.md يحمل تعليمات معمارية معكوسة

5 ادعاءات **عالية الخطورة** (R2): «FLAT layout / src/ deleted / Do NOT recreate src/» + «config/ is gone» + «GT dataset EMPTY» + «baseline/ immutable snapshot». كلها عكس الواقع مباشرةً. → **أُعيدت كتابة CLAUDE.md كاملًا** (R8: هوية + أرقام + قواعد صلبة + بنية صحيحة + إحالة).

### A3 — ❌→✅ prompts.yaml: 5 مفاتيح ميتة

`ocr_prompts` + `review_prompts` (عليان) + `analysis_prompts.{word_explanation,summarization,entity_extraction}` — **0 مراجع** في الكود (grep مباشر). الوحيد الحي: `analysis_prompts.text_correction` (25 مرجع، `review_manuscript.py:141`). → **حُذِفت كلها**، بقي `analysis_prompts` فقط. ملاحظة §5 القائلة «`analysis.*`/`review.*` غير مسكونة» كانت **نصفها خطأ** → صُحِّحت.

---

## B. التدقيق الكامل لكل ادعاء (بعد التصحيح)

| # | الادعاء | المصدر | الفحص | الحالة |
|---|---|---|---|---|
| 1 | المشروع = حزمة `src/pipeline/` بـ 6 حزم فرعية | AGENTS §5, CLAUDE | `ls src/pipeline/` = ingestion, preprocessing, ocr, output, correction, evaluation | ✅ مطابق |
| 2 | `main.py` يستورد `src.pipeline.*` | AGENTS §5 | `"src.pipeline" in main.py` = True | ✅ مطابق |
| 3 | `config/settings.yaml` + `config/prompts.yaml` موجودان | AGENTS §5, CLAUDE | `Path(...).exists()` = True | ✅ مطابق |
| 4 | prompts.yaml = `analysis_prompts` فقط + `text_correction` | CLAUDE, spec FR-002 | `ruamel.load` → `['analysis_prompts']` + `{text}` موجود | ✅ مطابق |
| 5 | GT كاملة = 620 بيت | AGENTS §8/§12, CLAUDE | regex `^\s*[٠-٩]+` = 620 | ✅ مطابق |
| 6 | GT تغطي ص23..ص67 فقط | AGENTS §8/§12 | alignment.json: أول matched=ص23، آخر=ص67 | ✅ مطابق |
| 7 | `baseline/` غير موجود | AGENTS §2/§8/§11/§14 | `not Path("baseline").exists()` = True | ✅ مطابق |
| 8 | CER 25.0% / WER 59.9% | AGENTS §3/§8/§12, CLAUDE | quality_report.json = 0.250 / 0.599 | ✅ مطابق |
| 9 | استرجاع التشكيل 82.0% | AGENTS §8/§12, CLAUDE | diacritics_total.accuracy = 0.820 | ✅ مطابق |
| 10 | Python = 3.11.16 فقط | AGENTS §9, CLAUDE | `myenv/bin/python --version` = 3.11.16 | ✅ مطابق |
| 11 | openai 3.3.1 (لا 2.54.0) | AGENTS §9/§12 | `openai.__version__` = 3.3.1 | ✅ مطابق |
| 12 | jiwer 4.0.0 | AGENTS §9 | `pip list` = jiwer 4.0.0 | ✅ مطابق |
| 13 | paddleocr 3.7.0 / paddlepaddle-gpu 3.2.0 | AGENTS §9 | `pip list` مطابق | ✅ مطابق |
| 14 | **surya-ocr غير مثبَّت** (بعد التصحيح) | AGENTS §3/§9/§12/§13 | `SuryaLineDetector().available = False` | ✅ مطابق |
| 15 | **camel-tools غير مثبَّت** + البيانات موجودة (بعد التصحيح) | AGENTS §3/§9/§12/§13 | `MorphologicalVerifier().available = False` + `~/.camel_tools/data/morphology_db/calima-msa-r13` | ✅ مطابق |
| 16 | Atria غير فعّال على صفحات حقيقية | AGENTS §3/§12, CLAUDE | spec 005 research §R2.2 | ✅ مطابق |
| 17 | CLAUDE.md لا يحوي ادعاءات معكوسة | spec SC-001 | grep «Do NOT recreate src»/«config/ is gone»/«dataset is EMPTY» = 0 | ✅ مطابق |
| 18 | `.claude/skills/clean-code-guard` = symlink | AGENTS §14.1 | `ls -la` → `-> ../../.agents/skills/clean-code-guard` | ✅ مطابق |
| 19 | قرارات التأجيل الثلاثة موثَّقة | AGENTS §14.1 | grep archive/opencode.json/PROJECT_SUMMARY | ✅ مطابق |
| 20 | `raw_text/` + `ground_truth/` غير ملموسة | spec FR-009 | sha256 = 91b3f61101170b233619 (ثابت) | ✅ مطابق |

**النتيجة**: 20/20 ✅ بعد التصحيح. **3 اكتشافات كبرى** (A1/A2/A3) صُحِّحت ضمن هذا الـ spec.

---

## C. قرارات التأجيل (تُمنع إعادة الاكتشاف)

1. `data/archive/debug_page107_resolved.zip` — **يُبقى** (دليل تاريخي، 1MB).
2. `config/opencode.json` (محذوف من شجرة العمل) — **يُترك** (هجرة opencode، خارج ممر المشروع، §10).
3. `docs/PROJECT_SUMMARY.md` — **يكتفي بوسم «تاريخية»** (لقطة موسوعية 2026-09-06 للمسطّح القديم؛ إعادة كتابة = جهد/قيمة منخفضة).
4. `.claude/skills/clean-code-guard` — **symlink مقصود** (ليس تكرارًا).

---

## D. الانحدار والتحقق

| البند | النتيجة |
|---|---|
| `py_compile` لكل المعدَّل | OK |
| كل الاختبارات | 129+ OK |
| `main.py --start 24 --end 26` | exit 0 |
| sha256 الأدلة | 91b3f61101170b233619 (ثابت) |
| كاش OCR | 193 entry سليم |
| الأسرار | لا توجد في أي مخرج |
| تصنيف التغيير | REVIEW_ONLY + INFRASTRUCTURE (لا OCR_BEHAVIOR) |
