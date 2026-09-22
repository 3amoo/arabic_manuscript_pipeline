# Tasks: Surya Line-Detector Activation + A/B CER Measurement (spec 009)

**Input**: Design documents from `/specs/009-surya-activation/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — this spec's acceptance evidence is the A/B comparison + the evidence invariant, not unit tests (surya is a third-party model; no unit test can validate it).

**Organization**: grouped by user story; each story independently testable.

## US1 — Clean install, zero dependency damage (P1)

- [x] T001 [US1] Snapshot the protected dependency versions before install: `openai`, `pillow`, `opencv-python-headless`, `torch` (research R1). These are the packages the 2026-09-06 attempt broke.
- [x] T002 [US1] Install `surya-ocr==0.22.1` with `--no-deps` via `myenv/bin/python -m pip install` (never `myenv/bin/pip` — AGENTS.md §9 pip warning).
- [x] T003 [US1] Import surya and collect the genuinely-missing third-party imports one by one; install exactly `beautifulsoup4`, `filetype`, `platformdirs` (research R1). Do NOT install surya's full dependency tree.
- [x] T004 [US1] Verify `pip check` is clean and the protected versions are unchanged (FR-001). Verify `SuryaLineDetector().available == True` (FR-002).

## US2 — Root-cause the silent "0 text lines" failure (P1)

- [x] T005 [US2] Confirm the default `DetectionPredictor()` in surya 0.22.1 is server-backed (spawns `python -m surya.detection.server`); note that `MODEL_DTYPE` is a pydantic computed_field and NOT env-overridable (research R2 — dead end recorded).
- [x] T006 [US2] Direct model probe: load the EfficientViT checkpoint `text_detection/2025_05_07` on a fixed page image at fp16-on-CUDA and at fp32; assert fp16 → all-NaN heatmap (nan=60000, max=nan) and fp32 → valid (nan=0, max≈0.957). This is the proof the bug is in the model path, not our integration.
- [x] T007 [US2] Confirm the NaN survives the uint8 cast as zeros and the server responds HTTP 200 with an empty text_lines list — i.e. the failure is **completely silent** (no exception, no log).
- [x] T008 [US2] Implement the fix in `surya_line_detector.py`: use `DetectionPredictor.local(dtype=torch.float32)` (in-process, no server subprocess). Verify it returns a non-zero line count on the same image. Write the full root-cause explanation into the module docstring (FR-003) so it is never re-discovered.
- [x] T009 [US2] Confirm `TORCH_DEVICE=cpu` is an alternate (slower) fp32 path and is not chosen; keep the in-process fp32 fix.

## US3 — Honest before/after A/B CER (P1)

- [x] T010 [US3] Back up the classical `raw_text/` outputs for the in-scope pages to `/tmp/opencode/` BEFORE any surya run (research R4 — per-run backups, since pages were surya-run individually then corpus-wide).
- [x] T011 [US3] Activate surya in `config/settings.yaml` (`layout_detection.line_detector: surya` + `surya: {device: cuda, confidence_threshold: 0.4}`).
- [x] T012 [US3] Run the corpus 23–67 with surya enabled (706s, 1322 lines actually OCR'd, cache 9.1% hits — most lines differ from classical so the cache mostly misses).
- [x] T013 [US3] Compute per-page CER for BOTH variants against the **same** spec-008 `alignment.json` (OCR-independent windows — no re-alignment confound). Report corpus weighted CER, improved/worse/same counts, top deltas (research R3).
- [x] T014 [US3] Compute the oracle pick-per-page upper bound (23.9%) and explicitly label it **undeployable** (needs GT). Also measure a GT-free rule (verse-count agreement → 26.4%) to prove the headroom is not capturable (FR-004).
- [x] T015 [US3] Record the regression-on-good-pages evidence (p55 10.4%→23.3%, p40 11.2%→23.5%, p66 +20.6pp) so the decision is not based on the average alone.

## US4 — Decide, revert safely, and record (P2)

- [x] T016 [US4] Apply the decision: **reject** surya as default (research R3 — −0.6pp is noise; 17/45 regress; segmentation is not the bottleneck per the error budget). Comment out the `layout_detection` block in `settings.yaml` with the measured result summarized in-file (FR-005).
- [x] T017 [US4] Restore the classical `raw_text/` pages from backups (including the individually-run pages 24/25/26/60). Rebuild `full_manuscript.txt` via the real `_rewrite_full_manuscript` code path (it is a pure function of raw_text — research R4), NOT by copying an old file.
- [x] T018 [US4] Reconstruct the two deleted `corrected_text/` passthrough files byte-exactly via `strip_header` + the `source: raw` format (they are deterministic per spec-005's E1 behavior — research R4).
- [x] T019 [US4] Verify the evidence invariant: sha256 over every `.txt` under `data/output` + `data/ground_truth` = `91b3f61101170b233619` (FR-006).
- [x] T020 [US4] Smoke: `main.py --start 24 --end 26` exits 0 (classical path, 100% cache hits, 12.3s). Verify `layout_detection` absent from parsed settings still falls back to classical safely (`config.get('layout_detection', {})` in main.py:1084).
- [x] T021 [US4] Full suite: 8 test modules, 142 tests OK (skipped=2) (FR-006).
- [x] T022 [US4] Document the measured negative result in `docs/AGENTS.md` §3 (status → "measured, not active"), §9 (dependency line), §12 (known-issue entry with the fp16 root cause + A/B numbers), §13 (roadmap phase 2 + ensemble line → "measured, rejected") (FR-007).
- [x] T023 [US4] Add the `docs/CHANGELOG.md` entry (install strategy, fp16 root cause, A/B numbers, decision, evidence restoration) (FR-007).
- [x] T024 [US4] Write this spec-kit: `spec.md`, `research.md`, `tasks.md`, `plan.md` even though the result was negative — a negative result that isn't written down gets re-litigated (FR-007).

## Post-spec notes

- Surya stays **installed** (the fp16 fix is valuable regardless) and `SuryaLineDetector().available == True`; only the activation is off.
- Reactivation path for a future maintainer: uncomment the `layout_detection` block in `settings.yaml`; nothing else needs to change.
- The next spec (010) follows the measured lever ranking in research R5: character errors (66% of the budget, ~half diacritics) via 300 DPI + diacritic-preserving preprocessing.
