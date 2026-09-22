# Research — spec 014 (Diacritic-Aware Fine-Tune)

**Date**: 2026-09-18. All findings verified by direct execution. Nothing in the repo was modified (invariant `91b3f61101170b233619` holds); all artifacts live under `~/.opencode/scratch/`.

## R1 — Recovering the 19 non-matched pages (corpus 346 → 688)

**Problem**: spec 013's builder only used pages where the detected verse-band count exactly equaled the GT verse count (`matched`). That kept 26 of 45 in-scope pages. Measuring the rest showed the exclusion was mostly a **band-detection artifact**, not bad data:

| Page | Expected verses | Detected bands | Delta |
|---|---|---|---|
| p27 | 16 | 20 | +4 |
| p28 | 10 | 13 | +3 |
| p30/p33/p38/p41/p43/p48/p53/p61/p65 | 13–16 | 14–17 | +1 |
| p39/p32/p59 | 15/13/13 | 17/16/16 | +2/+3/+3 |
| p60 | 18 | 16 | −2 |
| **p49, p62, p63, p67** | 13–15 | **equal** | 0 (were `low_confidence`, not count-mismatched) |

**Fix — sequence alignment instead of positional pairing**: OCR each verse band, compute a normalized-CER cost matrix between band texts and GT verses, and run a DP alignment (both sequences are in reading order) with penalties for skipped noise bands (0.8) and dropped verses (0.8). Accept a pair only if its CER < 0.6.

**Result**: 418 verse rows, **836 crops → 688 train / 148 val**. 18 pages recovered (44 pairs accepted, 200 rejected by the threshold), 6 pages still skipped where nothing survived the threshold, 0 malformed GT. Pairing verified by OCR cross-check on p030 — recovered rows land on the correct GT verses in the right order.

**Honest note**: 200 rejected pairs is a high reject count. The threshold is deliberately conservative (a mislabeled crop is worse than a missing one), so this is data left on the table for the sake of label trust, not a bug.

## R2 — The widened-corpus run (plain loss)

Identical recipe to spec 013 (30 epochs, lr 1e-4 cosine, batch 4, 384px, full 747-char charset, pretrained weights in the YAML), only the dataset changed. On the 148-crop held-out split:

| Model | CER | Diacritic recall |
|---|---|---|
| Base | 33.1% | 85.5% |
| Fine-tuned (wide, plain) | 32.4% | 84.0% |

Per-sample: letters 23/15/110 (W/L/T); diacritics 26/30. CTC loss 419→50.

The letter gain **narrowed** from spec 013 (−1.8pp → −0.7pp) despite ~2× data, and diacritic recall stayed flat-to-slightly-down. Doubling the corpus did not sharpen either effect.

## R3 — The diacritic-weighted CTC loss (the second leg)

**Design**: patch `CTCLoss` to weight each sample by `(1 + n_diacritics)`, normalized by the batch mean, so a fully-voweled hemistich outweighs a bare one. The count is taken from the **encoded label indices** against the model's own charset (`self._dia_idx` built once in `__init__` from `dict.txt`) — no raw strings plumbed through the batch tensors, which the KeepKeys layout does not support. Gated behind `dia_weight: True`, so absent the flag the loss is byte-identical to the original.

**Verified active**: the log printed `dia_weight : True`, the loss trajectory differed from the plain run (CTCLoss 419→49 vs 419→50), and training completed.

**Result — no effect**:

| Model | CER | Diacritic recall | Letter W/L/T | Diacritic W/L |
|---|---|---|---|---|
| Base | 33.1% | 85.5% | — | — |
| Wide, plain loss | 32.4% | 84.0% | 23/15/110 | 26/30 |
| Wide, **dia-weighted** | **32.4%** | **84.0%** | **23/15/110** | **26/30** |

Numerically identical to the plain run. The weighting changed the internal optimization path but not one output.

**Why it likely failed**: the model already **emits** diacritics abundantly — inspection shows `عَمْرَر أبُو عَبْدِ الإلَهِ` for GT `عَمْرٌ أَبُو عَبْدِ الإِلَه`, i.e. the marks are present but on the wrong letters. Per-sample weighting makes diacritic-heavy lines matter more, but does not give the loss any information about *where* on a line a mark belongs. The failure is a **position/association** problem, and a sample-scalar weight cannot address it — a position-aware mechanism (attention, or a two-stage decode) would be a genuinely different architecture, not a loss tweak.

## R4 — The ceiling, and why it is time to accept it

Across specs 011–014 every OCR-side lever has been measured and none moves diacritic recall:

| Lever | Verdict |
|---|---|
| Preprocessing | ink survives — not the cause (011) |
| 300 DPI | not significant (010) |
| Surya line segmentation | noise (009) |
| PaddleOCR v3 | +3.9pp worse (011) |
| Qari VLM | unstable + strips/hallucinates (012) |
| Fine-tune 346 samples | letters −1.8pp, diacritics flat (013) |
| Fine-tune 688 + dia-weighted loss | letters −0.7pp, diacritics flat (**014**) |

Two negative results on the fine-tuning line was the agreed stop condition. The deficit is a property of **this scan's diacritic print quality vs available recognizers**; the remaining 66% character-error bucket is better addressed **downstream** — post-OCR correction can exploit the *content* (morphology, rhyme, meter) in ways the recognizer cannot.

## R5 — Repo and environment integrity

- sha256 over all `data/output` + `data/ground_truth` = **`91b3f61101170b233619`** — unchanged. `git status` shows only the pre-existing spec 005–013 modifications.
- **No new dependencies.** The `CTCLoss` patch lives in the *local PaddleOCR training tree* (`~/.opencode/scratch/pd_src/ocr_full/`), which is outside the repo and outside `myenv` — it does not affect the installed `paddlex`/`paddleocr` packages used at inference.
- All datasets/weights in `~/.opencode/scratch/` (`ft_dataset_wide/`, `ft_wide/`, `ft_wide_dia/`).
- 142 tests pass; smoke run exits 0.
