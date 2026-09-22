# Tasks: Fine-tuning Feasibility Gate (spec 013)

**Input**: Design documents from `/specs/013-finetuning-feasibility-gate/`

**Prerequisites**: spec.md (required), research.md.

**Tests**: measurement-based — acceptance evidence is the base-vs-finetuned comparison on held-out pages.

**Organization**: grouped by user story.

## US1 — Build a labeled dataset from the pipeline's own crops (P1)

- [x] T001 [US1] Write `build_ft_dataset.py`: mirror `_run_page_once` + `extract_poetry_region`'s crop path verbatim (same render, preprocessing, band detection, gutter split, `crop_nonempty_x`), pairing crops with GT hemistichs via the spec-008 alignment — FR-001/FR-003.
- [x] T002 [US1] Verify pairing correctness: OCR 4 random crops with the production model and confirm the text is recognizably the assigned GT verse (no off-by-one).
- [x] T003 [US1] Split train/val by PAGE (pages 63-67 held out), never by crop — FR-002. Result: 346 train / 58 val over 26 matched pages.

## US2 — Verify a fine-tune is even possible on this hardware (P1)

- [x] T004 [US2] Obtain PaddleOCR's training config + full source tree; fix the four setup gaps (missing training YAML, un-imported training registry, `PADDLE_PDX_PADDLEOCR_PATH` unset before import, absent `scikit-image`/`albumentations`/`lmdb`) — research R1.
- [x] T005 [US2] Fit training into 3.6GB VRAM: batch 4, 384px image width, `fix_bs: true`, eval batch lowered from 128 — research R3.
- [x] T006 [US2] Confirm pretrained weights load (`load pretrain successful`) — after discovering the `-o Global.pretrained_model` override is silently ignored and must be set in the YAML (research R4).

## US3 — Measure the fine-tune's effect on held-out data (P1)

- [x] T007 [US3] Diagnose the three silent failure modes that produced garbage output: charset-shrunk head reset, ignored pretrained override, `max_text_length` < label length triggering infinite recursion in the dataset retry loop — research R4.
- [x] T008 [US3] Fix all three: dataset `dict.txt` = full 747-char `ppocrv5_arabic_dict.txt` (FR-006), pretrained path in YAML, `max_text_length: 48`.
- [x] T009 [US3] Train 30 epochs and evaluate base vs fine-tuned on the held-out pages with identical metrics (`normalize_text` CER + `analyze_diacritics`) — FR-004. Result: CER 28.6%→26.8%, recall 85.2%→83.9%.
- [x] T010 [US3] Per-sample win/loss/tie analysis: letters 14/5/39, diacritics 12/14 — the directional-but-not-decisive signal.
- [x] T011 [US3] Probe the data-size ceiling: 80 epochs overfits (`norm_edit_dis` 0.49→0.59), confirming 346 samples saturate at ~30 epochs.

## Post-spec notes

- **No code, config, or data in the repo changed** — FR-005 holds: sha256 `91b3f61101170b233619`, `git status` unchanged, 142 tests OK.
- **New `myenv` deps** (additive, never imported by `main.py`): `scikit-image`, `albumentations`, `lmdb`, `scipy`.
- Artifacts preserved at `/home/omar/.opencode/scratch/` (`ft_dataset/`, `ft_direct3/` = the working fine-tuned model, `pd_src/` = the PaddleOCR training tree, `build_ft_dataset.py`, `eval_gate.py`, `per_sample.py`).
- The gate's verdict: **fine-tuning works and transfers to unseen pages, but plain cross-entropy on 346 hemistichs does not move diacritic recall**. A full effort would need diacritic-focused changes to be justified (plan.md §6).
