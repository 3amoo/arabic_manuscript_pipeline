# Batch 4-6 out-of-GT triage — fresh crop OCR vs stored guess

Rows 61-118 of the manual review queue (logs/review_batch_4/5/6.md) are all
`out_of_gt_scope` (pages 68-111, beyond the page-67 end of ground truth), so there is
no verse to confirm them against. As a proxy, every review crop was re-OCR'd directly
with the pipeline's own `OCREngine` (arabic_PP-OCRv5_mobile_rec, GPU) and compared to
the row's stored `guess` and to the surrounding `data/output/.../raw_text/page_NNN.txt`.

**Method / caveats**
- This model cannot view images. Every classification below rests on OCR text only, so
  it is a *triage* of where a human's eyes will pay off, not a verification.
- 55 unique crops carry the 58 queue rows (p088_03, p090_11, p092_01 are full-bayt
  BOTH crops counted twice), so counts are given both per-crop and per-row.
- Agreement is measured with character 3-gram Jaccard on diacritic-stripped text
  (word-token overlap is useless here — Arabic OCR merges and splits words freely).
  `sim` below is that score against the best-matching line of the page raw text.
- A low-confidence garbled OCR is NOT treated as a recovered reading. Rows labelled
  RECOVERED still need a human to confirm the reading before it enters the corpus.

## Classification rules applied

| class | rule |
|-------|------|
| **RECOVERED** | fresh OCR yields real Arabic words (≥20 letters, several ≥3-letter chunks) AND ties to an actual line of the page (3-gram sim ≥ 0.25 to that line) — either the guess's own line, or a *different* line, which is then flagged mis-paired. A few short/low-confidence rows are marked **MARGINAL** in the note. |
| **DEGRADED** | fresh OCR is fragmentary or garbled — best page-line sim < 0.25, or only a few letters — so nothing can be adopted from the crop; a human must read the image. |
| **NOT_TEXT** | fresh OCR returns empty, a lone glyph, or a dot-leader / page-number run — the crop looks like index furniture (all on p.111), not a text line. Candidates for the noise gate rather than review. |

## Triage table

| row | crop | pg | region | stored guess | fresh crop OCR (conf) | class | note |
|-----|------|----|--------|--------------|----------------------|-------|------|
| 61 | p068_03.png | 68 | verse_right | وعاادَقَلَهُمربكَُلْ مُرَْق ... مَصَالالِح قَبْلُْ وَْ يَّْْق | وغَادَقَلهُمبَكُلْ مُرْهَقمُصَالِح قَبْلُ وَلم مَزّقِ (0.65) | **RECOVERED** | Same line as guess (p.68 l.9); fresh splits into real words — «وغادَقَلَهُم بكلْ مُرْهَق مَصالح قَبْلٌ» — cleaner than the merged guess. |
| 62 | p070_10.png | 70 | verse_left | أن كان أوْصَاة بهنم إِ اَُهمْ ... حَوََْْةُأمُْةُ الِْى تَحْصُْهْ | أن كَان أَوْصَْاةُ بهم إِ امهمْ حَوَْةُ أهَُُ الَِى َضْنهم (0.62) | **RECOVERED** | Same line as guess (p.70 l.15); fresh reads «أن كان أوصاةً بهم ... حوّة أمهم» with real word breaks. |
| 63 | p071_11.png | 71 | verse_right | حَحَ  تلاَا وتلَِينَ ابَْةُ ... وبسِوَى الْفَرْضَ اِسْتبَدٌّ مِنهُ | حَحجّ لاأ وَلَايِينَ ابُْةُوسِوْى الْفَرَْ اسْبَدَمِنةُ (0.53) | **DEGRADED** | Best page match IS the guess line (p.71 l.17) but only 3-gram sim 0.23 — too garbled to use as a reading. |
| 64 | p074_15.png | 74 | verse_left | وحَمَةُ وأمُ كُثوم نزْلْ ... أن لأنُعَاد لِفَريْش، وَل | وخَمَة وأمُ كُثوم نزْلْ أَن لأنعَادَلِفَيْش، وقَ (0.58) | **RECOVERED** | Same line as guess (p.74 l.20); sim 0.65, one unbroken reading incl. «أنّ لنعاد لفريش». |
| 65 | p077_14.png | 77 | verse_left | لأحَدذَ اليْعَةَلِلقيَامصيرَة ... َلَى قُرْش اللقاح لوَِر | لأَحَدَّالبيََّْلِقيَارَةعَى َريْش َقَاح لْوَاترَة (0.52) | **DEGRADED** | Same line as guess (p.77 l.19) but sim 0.14; fresh merges the whole bayt into one smear. |
| 66 | p082_06.png | 82 | verse_right | وَُالِْي لَيسَ َ كَُِ سِوَى ... عَباَِْ وي الَْاَِالَوَى | وهُوَالِْ َيسَ َُكِنََُِىَاَِوِي الَْاَِ لَوَى (0.50) | **DEGRADED** | Same line as guess (p.82 l.12) (sim 0.36) but the mid-section is bare-harakat noise; only «وهو ... ليس ... الآي» survives. |
| 67 | p084_03.png | 84 | verse_left | جَدُ الَةِ لِْنَ اسَْوَْرَا ... أبو الحلَِفوفَضْلَهَم سَرِى | جَدُ الَاَة لِنَ اْتَوزَاأَُوللَاِفوفَلَهَم سَرَى (0.52) | **DEGRADED** | Same line as guess (p.84 l.8) but sim 0.21; neither reading is usable. |
| 68 | p084_15.png | 84 | verse_left | نَالُوا بخَدْع زَهْرة الحياقِ ... ومَا لَهُمْ حَردَّلَةَرفي الآَِي | م الخندع من الخديعة  والخردلخب شحر، أي القليل التافه (0.84) | **RECOVERED** | MIS-PAIRED: crop reads the PROSE GLOSS at p.84 l.30 («الخدع من الخديعة والخردل ... أي القليل التافه»), NOT the verse at l.21 in the guess. Best OCR conf in the batch (0.84). |
| 69 | p086_10.png | 86 | verse_left | الَادِم القَاِل فَوْلاَ عَيا ... َاليَِْى م أَِذْ أَي | الَادِمِ القَاِل فَُوْلاَ غَيايَليَفى لم ألِحِذْ أَيا (0.59) | **RECOVERED** | Same line as guess (p.86 l.15); better word segmentation («الئادم القاحل فولا غيا ...»). |
| 70 | p086_14.png | 86 | verse_left | حِين َلاَِلاَوَة رَاِقَة ... خُْهَاأنّرُكُم َاعِفَ | حِينَ تَلاَِلَوَة رَاَةخُِهَاأندَرُكُ مَاِفَ (0.48) | **DEGRADED** | Same line as guess (p.86 l.21) but conf 0.48 / sim 0.30 with heavy distortion. |
| 71 | p087_09.png | 87 | verse_left | بالأخْذِمِنهُنم أَمَرَ النَيُ ... ََِدُ، مُعَاذُ، أَىُ | بالأخذِمِنهُمْ أَمَرَ النَيُ  قَيدُ، مُعَاذْهُ، أبَىُ (0.63) | **RECOVERED** | Same line as guess (p.87 l.14); «بالأخذ منهم أمر النبي ... مُعاذ» reads cleanly. |
| 72 | p087_13.png | 87 | verse_right | والعَلَتِوهيعَبْدّنُوْقَلُ ... أميَةَ الأَصْعَرُ فِيمَا نَقلوا | والْعبَلَت وهِيَعَبْدّنُوَْلُأمَيةَ الأُصْعَرُ فيمَا نَقلوا (0.63) | **RECOVERED** | Same line as guess (p.87 l.21); markedly better — full second hemistich «أمية الأصعر فيما نقلوا». |
| 73 | p088_02.png | 88 | verse_right | لِسََِ ِبِْيَشنْجُبِ بَِيَغْرُِبِ ... مَللِلِ قَخطَان قرِيع العَرَب | ِسَيَ بن يَشْجُبِ بن يَغرُبِسَلِلِ قَخطان قرِيعِ العَرَب (0.73) | **RECOVERED** | Same line as guess (p.88 l.8); recovers a genealogy: «[أ]يسي بن يشجب بن يغرب ... قحطان قريقع العرب». |
| 74+75 | p088_03.png | 88 | BOTH | نَسَََْيُْمَُْمََينَا ... عشررَ االأزْدَالاسشعَرينَا | نَسَبَ حَيرُمُرْمَل بَينَا عَشَرَة الأزْدَ الاشَعَرِنا (0.68) | **RECOVERED** | Same line as guess (p.88 l.10); reads «نسب ... بينا عشرة الأزد الأشعرينا». |
| 76 | p088_05.png | 88 | verse_right | وقَذْ َيََوااملَ ... عََاْ خم وجُذام عَامِلََة | وقَدْ يَامُا، ومَن أشأاَغَسانُ خمّ وجُذام َامِلة (0.58) | **DEGRADED** | Best page match is the guess line (p.88 l.15) at only sim 0.18. |
| 77 | p088_06.png | 88 | verse_left | طِيبُْ َوَء مَياَْوتَُ لَة ... مِنْ َِيِه َِملُْ َرِيب نَزَلَة | طِبُهَوَاء سَيَا يَُوتُ لَة مبِنْ حِينْهِ قملُ غرِيب نَْلة (0.69) | **DEGRADED** | Best page match is the guess line (p.88 l.16) at only sim 0.11; fresh diverges from the guess. |
| 78 | p088_07.png | 88 | verse_left | وَمَا َلْدَمِفوْنَة ... وَمِن ذَتَ الَِيَرَوََْة | وَمَاتَْدَِنَ العُنََومِن ذَات سّْم لَيَُوَُْة (0.54) | **DEGRADED** | Best page match is the guess line (p.88 l.19) at only sim 0.08; no usable overlap. |
| 79 | p089_01.png | 89 | verse_left | اأَغطِى للصّْنَم حَفافيِ ... وَحخَطُةَُيغْطَلِلإلَيِ | أَغطِىَ للصْنَم حَط افَيِوَحَطَُة قَ يَغطَُلِلإلَِ (0.59) | **RECOVERED** | Same line as guess (p.89 l.6); first hemistich readable («أغطى للصنم ...»), second still noisy. |
| 80 | p089_12.png | 89 | verse_left | ونَزَتَ في البَذْل فِيمَا عبت ... وَامْرَاة هُوِنَةَ إن وَ | وَوَتَُ في لبِذْل فِمَاعبَهوَامَاُؤْمَِة إن وَ (0.54) | **DEGRADED** | Best page match is the guess line (p.89 l.19) at only sim 0.21. |
| 81 | p090_08.png | 90 | verse_left | وآالُ َبادِ ملَوكَ الاندُلَس ... م نَسل فِيالطُق وَا الّدُ | لُ ادمل ال لِ الط و الد (0.55) | **DEGRADED** | Fresh OCR is 5 fragmentary letters; they look like bits of the guess line («...ملوك الأندلس... الـط... الـد») but nothing recoverable. |
| 82+83 | p090_11.png | 90 | BOTH | حَر الوَى وَن بَِي الَُيْقتَين ... شَرد وَالسّيْل مُجيح البتين | وَُكَذا الأَكُرَاذُ والْمَهَََِللأُمُيَْينَ ُم لمَازَة (0.55) | **RECOVERED** | MIS-PAIRED: crop matches p.90 l.18 («وهكذا الأكراد والمهلبية ... الأمويين هم المازبة»), NOT l.22 in the guess. |
| 84 | p092_00.png | 92 | verse_right | اوجَّ يِم َ في يَدِهِ ... وشَرِبَ الْسَُْمْ وْلمَّايُودِوِ | وَجَّ سيِمْ سَاعَةِ في يَّدِوَشَربَ السَْمْ وَلْمَايُودِ (0.63) | **RECOVERED** | Same line as guess (p.92 l.6); reads «وجّه [الـ]سم ساعة في يده ... ولم يود». |
| 85+86 | p092_01.png | 92 | BOTH | بََُدَُةُخلِدِ اََْدَتَِْا ... عَِِةِْعرَمْرَمَاد | وبنَةُ كُرامَةُ اسنْتَوْهَها شويل مِن طَة وإذْ وَهَبَهَا (0.65) | **RECOVERED** | MIS-PAIRED: crop matches p.92 l.7 («وبنة ... شويل من طة وإذ وهبها»), NOT l.9 in the guess. |
| 87 | p092_04.png | 92 | full_width | تبالووالزية | نسب الووالزة (0.56) | **RECOVERED** | MARGINAL: short crop, fresh «نسب الوالزة» is more word-like than guess «تبالووالزية» but only 11 letters at conf 0.56 — needs eyes. |
| 88 | p092_06.png | 92 | verse_right | اأَ لََّابَوالِمَا ... حَارَبَن َعَِمَا | أَنَ لَُاْ بَنَ والِدِمِمَا حَارنَةَ بَن مَفى عجدِمَا (0.68) | **DEGRADED** | Best page match is the guess line (p.92 l.17) at only sim 0.14. |
| 89 | p092_07.png | 92 | verse_right | َْعََةقََيقيَا ... عَن ثنذِرِ مَاء الْسّْمَاء الأذْكِيّا | تَلبَة العَقَاءُ عَن مُزيْقِيا عَن مَْذِر مَاء السشْمَاء الَذْكِيا (0.67) | **RECOVERED** | Same line as guess (p.92 l.19); second hemistich recovered («... عن مُريقيا عن مـذير ماء السماء الأذكيا»). |
| 90 | p093_00.png | 93 | verse_left | لا أحْدّأذل بسن حلدِيس ... أمْكذا يفغَْلُ بْعروِس | لاأحدُأذلُ مِن حدِيأمُكذاً ُفغَلْ بالغرُوس؟ (0.64) | **RECOVERED** | Same line as guess (p.93 l.5); «لا أحدُ أذلُّ من ... أمكذا يفعل بالعرس» — first hemistich usable. |
| 91 | p093_02.png | 93 | verse_left | الَْوْضُةُْرَ الرُذّي بنَفيِي ... ََرُ مُن أن يُفْعل ذَا بعْريوِ | لَخحوَضة عرَ الرّى بنَيحيرَ مُن أن يفعلَ ذا بيرميوِ (0.59) | **RECOVERED** | Same line as guess (p.93 l.9); tail recovered: «... من أن يفعلَ ذا بعروي». |
| 92 | p093_06.png | 93 | verse_left | اأقيِمْ بَافتمِلَقَدذْدَبُ الشّْحر ... أْ جميرَُ فذْ أَحْذَْ شُيِفا بُحرَا | رأقيم بايِ لقددَب الشر أجمير قذ أعذَْت شنا هُحرا (0.65) | **DEGRADED** | Best page match is the guess line (p.93 l.15) at only sim 0.23. |
| 93 | p094_07.png | 94 | verse_left | ووَِأتبنِِأل الْيمَنْ ... رَوَن نَّنْ | عَوْفُ بن عفرا معَاْها ُبفي السَنْع ذَكَُان َبَادة الأبي (0.60) | **RECOVERED** | MIS-PAIRED: crop matches p.94 l.20 («عوف بن عفرا ... في السبع ذكوان عبادة الأبي»), NOT l.10 in the guess (itself near-noise). |
| 94 | p098_00.png | 98 | verse_left | حَارنَة البرْ رَآى جبريلا ... ممَع النَيَُ وَوََْى تَرِْياَ | حَارَة البَرُرَأى جِرِيلاَمَع النيُ وَوَى تَرِْاَ (0.63) | **RECOVERED** | Same line as guess (p.98 l.5); reads «حار[ة] البرّ رأى جبريلا ...». |
| 95 | p098_12.png | 98 | verse_left | زَيْدُ بَنُدَابَتَِيِمَا الْمِبَدِ ... َاضَلخير الخلق خَيرَ مَسْجلي | َيْدُ بنُ َابت يِمَا الْمِرَدََِلحير الخلق حَيرَ مَسْجد (0.56) | **RECOVERED** | Same line as guess (p.98 l.19); reads «زيد بن ... [المـ]رد ... خير الخلق خير مسجد». |
| 96 | p098_15.png | 98 | verse_right | عَْنِ النَيَيِلَِان َلََِ ... بَمدذْ أَفَل لأنمِمُفلٍِِ | َنِ النَيُ ِلِان لَفلَقِبمدذْح أفَلِ الأنمِمُفلِ (0.60) | **RECOVERED** | Same line as guess (p.98 l.25); tracks the guess closely (sim 0.40). |
| 97 | p100_01.png | 100 | verse_left | يرِخَاء اتقِى حخَرُ لَظَى ... إذذ هُلَن نَلوا ابريمنَ أْعَظا | بيِرِاء اقى َرلََىإ ن تلوا الرِنَ الَْا (0.49) | **DEGRADED** | Does not agree with the guess (sim 0.06); fresh is a different, noisy reading of p.100 l.6. |
| 98 | p101_12.png | 101 | verse_left | ي الحَد ذَ إْهوْ َيرُ مُغن ... أنزل َ لي وَاِي | الَدَْوَيرُ نأنَ ّ ل وَاِ (0.47) | **DEGRADED** | Fresh OCR is 9 garbled letters; the guess is also a fragment — nothing to recover. |
| 99 | p104_00.png | 104 | verse_left | وحمي الدبْر والقيل ... هُرُ لة الْعَرْشُوبَلْعَِيلِ | وَْمِى ّ الدّبْر والقِيل هُؤْلَة لْعَرُْ وبَالعغَِيلِ (0.63) | **RECOVERED** | MARGINAL: same line as guess (p.104 l.5); «والدبر والقيل» readable, the rest noisy. |
| 100 | p104_05.png | 104 | verse_left | وكَغبِ الاخَار بَوْتِ عُمَرَا ... أخبرَُ وَهْوَ َابُِ ودَّرّى | وَكب الاخَار عَوْتِ عُمَا أَخبَرَ وهْوَ َابِعيُ ودَّرّى (0.64) | **RECOVERED** | Same line as guess (p.104 l.12); good word segmentation («وكعب الأخار ... أَخبرَ ...»). |
| 101 | p106_15.png | 106 | verse_right | قِْسُ بنُ مَكشُوح لْمرَاِيُ اهُمَام ... شَبِيةُ خَالِ أذَةُ الحِمَام | قِسُ ب مَكشوح لمرَاِيُ َُامبي الِ أذَاق الِمَا (0.49) | **RECOVERED** | MARGINAL: same line as guess (p.106 l.21); first hemistich «قِس بن مكشوح ...» readable; conf 0.49. |
| 102 | p107_09.png | 107 | verse_left | وي أبى الَقطَان عَمار نَْلْ ... ََنُ اكرذ َنة لَل | الحذم القاطع الشجاع (0.79) | **RECOVERED** | SUSPECT: reads a clean 3-word prose epithet «الحذم القاطع الشجاع» (conf 0.79, best in batch) that matches NOTHING on p.107 — crop is probably a marginal gloss; the verse in the guess stays unconfirmed. |
| 103 | p108_03.png | 108 | verse_left | ببصَربَة وفَضٌّ مَختُومَا عغلَى ... َؤالِياورّكَال مِن مينهءقَذْ خَلاَ | بَرَ وّ مً َيم لاً (0.51) | **DEGRADED** | Fresh OCR is 8 scattered letters, no word ≥3 chars; the guess (a full verse at p.108 l.8) cannot be confirmed from the crop. |
| 104 | p108_13.png | 108 | verse_left | وأَرَْدْه للهَدَى ورَغَة ... ِِهِ لَيىُ بزَوَال الَسْعَة | وأَرَْدُْ لِهُدَى ورَغََ فِيهِ لَىُ بزَوَالِ المسعَة (0.56) | **RECOVERED** | Same line as guess (p.108 l.20); reads «وأردُّ للهدى ورغَ ... فيه ... بزوال المسعة». |
| 105 | p110_07.png | 110 | verse_left | أزكِى الصّْلاةٍ والسّلام مَا مسْجَا ... لَلَ وَاَهُ أنحجمَُْي | أزْكى الصّْلافِ والسّْلام مَا سَجْا لَيلْ ومَا ََهُ ألجم الذُجَى (0.59) | **RECOVERED** | Same line as guess (p.110 l.12); reads the closing formula «أزكى الصلاة والسلام ما سجا ليل» — clearest recovery. |
| 106 | p111_00.png | 111 | full_width | uوباa | uوباua (0.58) | **DEGRADED** | Fresh «uوباua» vs guess «uوباa» — identical mixed-script junk; no improvement. |
| 107 | p111_01.png | 111 | full_width | متبلب.................... | ة.................1 (0.57) | **NOT_TEXT** | Fresh OCR is a dot-leader run + one digit («ة.................1»); crop is an index entry's leader rule, not a text line. |
| 108 | p111_02.png | 111 | full_width | ة٠ودت٠...... | ٣ةودت٠..........٠..............4٠.٠ (0.50) | **NOT_TEXT** | Fresh OCR is dot-run + digits («٣ةودت٠..........٠..............4٠.٠»); agrees with the guess but both are leader-run fragments. |
| 109 | p111_05.png | 111 | full_width | تعريفبتطموللم | تريقبقطمولم (0.50) | **DEGRADED** | Fresh «تريقبقطمولم» vs guess «تعريفبتطموللم» — same garbled index entry, no improvement (sim 0.11). |
| 110 | p111_06.png | 111 | full_width | ١لهورته١4 | ١قهته١4 (0.56) | **NOT_TEXT** | Fresh «١قهته١4» is an index page-number fragment; only the digits agree with guess «١لهورته١4». |
| 111 | p111_09.png | 111 | full_width | ه١ن.37 | مة فىتاريخ لبهيت لحرلم (0.61) | **RECOVERED** | SUSPECT: crop reads a real index phrase («...في تاريخ البيت...») while the guess is a page-number fragment «ه١ن.37» — guess belongs to a different band. |
| 112 | p111_10.png | 111 | full_width | بل م | بب28 (0.55) | **NOT_TEXT** | Fresh «بب28» — two letters + a page number; the crop gave back no real word. |
| 113 | p111_11.png | 111 | full_width | يو | نسب تبي صلى ١ذعليه رسلم ٠٠٠٠٠٠٠٠٠٠و (0.60) | **RECOVERED** | SUSPECT: crop reads «نسب ... صلى ... عليه رسول ...» while the guess is the 2-char fragment «يو» — guess belongs to a different band. |
| 114 | p111_12.png | 111 | full_width | ن | ان32٠ (0.41) | **NOT_TEXT** | Fresh «ان32٠» — two letters + a page number. |
| 115 | p111_13.png | 111 | full_width | قولفيحبة | سبقر6 (0.57) | **NOT_TEXT** | Fresh «سبقر6» — four letters + a page digit; the guess «قولفيحبة» is a different fragment. |
| 116 | p111_14.png | 111 | full_width | يم٠.٠................٩ | ون.............٠...............٠٠...37 (0.56) | **NOT_TEXT** | Fresh «ون.............٠...............٠٠...37» — dot leader + page number 37. |
| 117 | p111_17.png | 111 | full_width | شكر و ل ليةالبر | القول بة (0.54) | **DEGRADED** | Fresh «القول بة» (2 words) vs guess «شكر و ل ليةالبر» — both fragmentary. |
| 118 | p111_21.png | 111 | full_width | نسكريساللأار | كر لالاشواذانه (0.67) | **DEGRADED** | Fresh «كر لالاشواذانه» vs guess «نسكريساللأار» — single garbled chunks, no reliable match on the page. |

## Counts

| class | crops | queue rows |
|-------|-------|------------|
| **RECOVERED** | 29 | 32 |
| **DEGRADED** | 19 | 19 |
| **NOT_TEXT** | 7 | 7 |
| total | 55 | 58 |

## Suspected mis-pairs (guess text belongs to a different line than the crop)

Evidence: the fresh crop OCR matches a *different* line of the same page's raw text much
better than it matches the stored guess (or matches nothing on the page at all).

| crop | row | guess says (raw line) | crop actually matches | strength |
|------|-----|----------------------|------------------------|----------|
| p084_15.png | 68 | verse «نالوا بخدع زهرة الحياق...» (p.84 l.21) | prose gloss «الخدع من الخديعة والخردل ... أي القليل التافه» (p.84 l.30, sim 0.74 vs 0.06) | strong — crop is a شرح/حاشية line, not the verse |
| p090_11.png | 82+83 | verse «حر الوى ون بـ...» (p.90 l.22) | verse «وهكذا الأكراد والمهلبية ... الأمويين هم المازبة» (p.90 l.18, sim 0.33 vs 0.02) | strong |
| p092_01.png | 85+86 | verse «بـدة خلد...» (p.92 l.9) | verse «وبنة ... شويل من طة وإذ وهبها» (p.92 l.7, sim 0.40 vs 0.00) | strong |
| p094_07.png | 93 | near-noise «وأتبنأل اليمَن ...» (p.94 l.10) | verse «عوف بن عفرا ... في السبع ذكوان عبادة الأبي» (p.94 l.20, sim 0.28 vs 0.00) | strong — the guess was noise from the wrong band |
| p107_09.png | 102 | verse «وي أبى القطان عمار...» (p.107 l.17) | nothing on p.107; clean prose epithet «الحذم القاطع الشجاع» (conf 0.79) | suspect — crop may be a marginal gloss not present in the page text |
| p111_09.png | 111 | page-number fragment «ه١ن.37» (p.111 l.21) | index phrase «...في تاريخ البيت لحرلم» | suspect — guess is furniture from another band |
| p111_11.png | 113 | 2-char fragment «يو» (p.111 l.27) | index line «نسب ... صلى ... عليه رسول ...» | suspect — guess is furniture from another band |

Independent corroboration that **page 111's band↔line pairing is scrambled**: the crop
index → raw-text line mapping is non-monotonic — p111_09→l.21, p111_10→l.19, p111_11→l.27,
p111_12→l.23, p111_13→l.29, p111_14→l.25, p111_17→l.31, p111_21→l.36. Two of these
rows were already flagged `UNVERIFIED-PAIRING` in pairing.json (p111_09, p111_13).
Page 111 is the book's فهرس (index), which also explains the dot-leader NOT_TEXT rows.

## What the human should look at first

Start with the four **strong mis-pairs** (p084_15, p090_11, p092_01, p094_07): each is a
queue row whose stored guess is simply the wrong line, and the crop OCR already tells you
which line it really is. Fixing those four also fixes 7 queue rows at once (three are BOTH
crops). Next, the clean high-confidence recoveries where the crop OCR and the guess are
unambiguously the same line and the fresh text is more readable — p110_07 (a closing
«أزكى الصلاة والسلام» verse), p088_02 (a genealogy: «يسي بن يشجب بن يغرب ... قحطان
قريقع العرب»), p087_13, p084_15's gloss and p107_09's epithet are the most trustworthy.
The 5 MARGINAL RECOVERED rows (p092_04, p093_00, p093_02, p104_00, p106_15) are worth a
quick glance but their OCR conf is 0.49-0.64, so adopt nothing without reading the image. The 19 DEGRADED rows are where human reading of the
actual image is unavoidable — the crop OCR contributes nothing there; p108_03 and p090_08
are the worst (8 and 10 usable letters respectively against full-verse guesses). The 7
NOT_TEXT rows are all on page 111's index and are probably better handled by the noise
gate than by review — but check first that the gate would not swallow the real entry text
to the left of each dot leader.

---

No data was written outside `logs/`. `data/reviewed_corrections.jsonl` was not touched,
the `data/output` corpus was not regenerated, and the OCR result cache was disabled so
no cache writes landed in `data/output/.cache`. Raw per-crop OCR results are kept in
`/tmp/opencode/batch456_crop_ocr.json`.
