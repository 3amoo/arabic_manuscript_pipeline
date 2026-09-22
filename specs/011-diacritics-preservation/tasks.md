# Tasks: Diacritic-Preservation Measurement (spec 011)

**Input**: Design documents from `/specs/011-diacritics-preservation/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — this spec's acceptance evidence is the stage-isolation probe + the model A/B + the evidence invariant.

**Organization**: grouped by user story.

## US1 — Isolate the diacritic-loss stage (P1)

- [x] T001 [US1] Measure per-page diacritic recall with `analyze_diacritics` against the spec-008 alignment: mean 82.4%, worst p23 57.2%, best p31 98.2% (research R7).
- [x] T002 [US1] Diacritic-scale ink probe through every preprocessing stage (raw → deskew → CLAHE → denoise → binarize) on the worst and best pages (research R1): marks survive all stages (p23: 259→401; p31: 210→352).
- [x] T003 [US1] Upper-band (tashkeel zone) ink check in the final binarized crops (research R1): 8-12k upper vs 79-81k body → preprocessing EXONERATED, the pixels reach OCR.
- [x] T004 [US1] Direct recognizer probe on 8 real p31 verse-line crops (research R2): v5 emits 4-10 marks/line but misplaces them (e.g. `وللسَليموللاسِْسْقاء`) → the loss is recognition accuracy, not emission.

## US2 — Confirm the current recognizer is the best available (P1)

- [x] T005 [US2] Enumerate PaddleOCR 3.7's Arabic recognizers from the paddlex manifests (research R3): exactly two — `arabic_PP-OCRv5_mobile_rec` and `arabic_PP-OCRv3_mobile_rec`.
- [x] T006 [US2] Probe the alternatives: `arabic_PP-OCRv5_server_rec` fails ("No engine bindings registered"); `PP-OCRv6_medium_rec` emits 0 diacritics on Arabic (research R3).
- [x] T007 [US2] Back up the 45 in-scope `raw_text/` pages to `/tmp/opencode/v5_backup/` before the A/B.
- [x] T008 [US2] Set `text_recognition_model_name: arabic_PP-OCRv3_mobile_rec`; run pages 23–67 (207.4s, 1553 lines, 0% cache hits — expected, disjoint cache key).
- [x] T009 [US2] Full-corpus A/B against the unchanged spec-008 alignment (research R4): CER 27.0%→30.9% (+3.9pp), diacritic recall 82.4%→8.6%, 34/45 pages worse → **v5 confirmed correct**.

## US3 — Record the ceiling and redirect the roadmap (P2)

- [x] T010 [US3] Restore v5 outputs from backup; rebuild `full_manuscript.txt` via the real code path; verify sha256 `91b3f61101170b233619` after restore AND after a clean v5 smoke run (FR-005).
- [x] T011 [US3] Prove the v3 cache entries are inert (FR-006): `_hash_image` folds the model name into the key; identical bytes hash differently under v3 vs v5; a v5 lookup of a v3-cached image returns None.
- [x] T012 [US3] Make `text_recognition_model_name` an explicit `settings.yaml` knob with the v3-vs-v5 measurement documented inline (FR-004) — previously only a hardcoded default in `ocr_engine.py`.
- [x] T013 [US3] Full suite: 8 test modules, 142 tests OK (skipped=2); `main.py --start 24 --end 26` exits 0 with 100% cache hits at v5.
- [x] T014 [US3] Document the ceiling in `docs/AGENTS.md` §3 (diacritics row), §12 (known-issue entry with the full measurement chain), §13 (roadmap — fine-tuning as the remaining lever) and `docs/CHANGELOG.md` (FR-007).
- [x] T015 [US3] Write this spec-kit (spec/research/tasks/plan) including the refuted preprocessing premise (R1) and the ceiling conclusion (R5).

## Post-spec notes

- **No code change shipped** — the spec's deliverable is the measurement. The one config change (the explicit model knob) is documentation of an existing hardcoded default.
- The v3 cache rows are inert and left in place; no pruning, zero correctness risk.
- Roadmap redirected: the diacritic line is closed at the preprocessing/model-selection level. The only remaining OCR-side lever is **fine-tuning** the recognizer (Phase 4). Review-stage tools (camel-tools, vision fallback) remain available.
