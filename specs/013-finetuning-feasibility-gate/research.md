# Research — spec 013 (Fine-tuning Feasibility Gate)

**Date**: 2026-09-18. All findings verified by direct execution. Nothing in the repo was modified (invariant `91b3f61101170b233619` holds); all artifacts live in `/home/omar/.opencode/scratch/` and `/tmp/opencode/`.

## R1 — Can PaddleOCR train on this machine at all? (yes, with four setup fixes)

The paddlex wheel does NOT ship the training path. Getting `tools/train.py` to run required fixing four separate gaps, each of which fails silently or cryptically:

1. **The training config is not in the wheel.** `paddlex/configs/modules/.../*.yaml` are *inference* configs; the trainer needs PaddleOCR's *training* YAML from `configs/rec/PP-OCRv5/multi_language/arabic_PP-OCRv5_mobile_rec.yaml` (fetched from GitHub). Without it: `'arabic_PP-OCRv5_mobile_rec' is not a registered model name.`
2. **The training registry is never populated on `import paddlex`.** It lives in `paddlex.repo_apis.PaddleOCR_api`, which is only imported when `paddlex.__init__._initialize()` runs AND `flags.EAGER_INITIALIZATION` is set — in practice you must `import paddlex.repo_apis.PaddleOCR_api` explicitly.
3. **The runner shells out to a source tree.** `PADDLE_PDX_PADDLEOCR_PATH` must point at a full PaddleOCR checkout (the sdist is missing `ppocr/modeling`, `ppocr/losses`, `ppocr/optimizer`). The env var is read at **register-import time**, so it must be set *before* importing the API package.
4. **Three deps were absent** from `myenv`: `scikit-image`, `albumentations`, `lmdb` (all pulled in by `ppocr.data`). Installed this spec.

**Verified working invocation** (from the PaddleOCR tree root):
```
python tools/train.py -c <training yaml> -o Global.save_model_dir=<out>
```
Runs to completion on the GTX 1650 at **batch 4, 384px-wide images**, ~60 samples/s, max_mem ~2.3GB.

## R2 — The dataset: real pipeline crops, GT-labeled

**Method** (`build_ft_dataset.py`): for each `matched` page in the spec-008 alignment, render at 200 DPI (the production setting), run `preprocess_page`, then mirror `_run_page_once`'s layout path (`layout.binarize` → `dilate_text` → `find_components` → `remove_border_components` → `compute_content_bbox` → `find_footnote_boundary`) to get the poetry bbox, then mirror `extract_poetry_region`'s band plan (`binarize` → `remove_edge_frame_lines` → `detect_gutter` → `detect_text_lines` → `split_oversized_lines` → per-band `classify_line` → `crop_nonempty_x`). The right/left crops are the *same arrays* OCR sees at inference.

**Labeling**: a GT verse is `NN hemistichA ... hemistichB`; the verse-number prefix is stripped, and the right/left crops get hemistichA/hemistichB respectively.

**Pairing verified**: OCR-ing 4 random crops with the production model returned text recognizably matching the assigned GT verse (with the known diacritic errors), confirming the band↔verse mapping is correct, not off-by-one.

**Result**: 404 crops over 26 pages — 346 train / 58 val (pages 63-67 held out by page, not by crop). 11 `matched` pages were skipped because band count ≠ GT verse count (several have full-width rows the gutter detector merged). Charset: 57 distinct label chars, all representable in the 747-char model dict except 2 ornamental parentheses (﴾﴿), which are in the full dict anyway.

## R3 — The hardware constraints that shaped the run

- **3.6GB usable VRAM** caps batch size. At 512px-wide images, batch 8 OOMs; at 384px, batch 4 fits (~2.3GB peak).
- **Eval batch size defaults to 128** in the config — that alone OOMs the card on wide images. Must be set to 4-8.
- **Crops are 8:1 aspect** (~1400×175). The default `RecResizeImg` target `[3,48,320]` **squashes a 1400px line into 320px** (4.4× horizontal compression) — the text becomes unreadable. The training image width had to be raised to 384 (a multiple of 8, PPLCNetV3's downsample factor) and the `MultiScaleSampler` scales set to line-shaped `[[384,48]]`. The default `[[320,32],[320,48],[320,64]]` never matches an 8:1 line.
- **`fix_bs: false`** (the config default) makes the sampler derive the real batch from `base_elements/(w*h)`, which explodes to 64+ on these images and OOMs. `fix_bs: true` is required for a small GPU.

## R4 — Two failure modes that produced garbage output (and their fixes)

Both were initially misread as "fine-tuning doesn't work." Recording them because they are traps:

1. **The head reset.** PaddleX always points `Global.character_dict_path` at the dataset's own `dict.txt`. My first dataset shipped a *57-char* dict derived from the labels, so the model rebuilt its classifier head at 60 outputs — the pretrained 749-wide head was **discarded**, and the log printed `shape of model params head.ctc_head.fc.weight [120, 60] not matched with loaded params [120, 749]`. Training from a random head on 346 samples produced gibberish (`كاـكجهك`). **Fix**: make the dataset's `dict.txt` BE the full `ppocrv5_arabic_dict.txt` (747 chars), so the head loads. (A reduced charset is a legitimate choice for a *from-scratch* train, not for a fine-tune.)
2. **The pretrained-model override never applied.** `-o Global.pretrained_model=<path>` on the command line was silently ignored (the log still said `train from scratch`), so run #2 trained from random weights. **Fix**: set `pretrained_model:` *in the YAML*. Only then does the log read `load pretrain successful`.

There was also a **third, subtler trap**: `MultiScaleDataSet.__getitem__` retries failed samples with a bare `except:` and a recursive `self.__getitem__(...)`. When *every* sample fails (in my case because `max_text_length: 25` was smaller than my shortest label, 26 chars), this becomes **infinite recursion** that presents as a `RecursionError` deep inside `copy.deepcopy` in the label encoder — the actual cause is invisible. **Fix**: `max_text_length` must exceed the longest label (mine reach 45; set to 48).

## R5 — The measured result (base vs fine-tuned on held-out pages)

30 epochs, lr 1e-4 cosine (1-epoch warmup), batch 4, 384px, full pretrained weights:

| Model | CER (letters) | Diacritic recall |
|---|---|---|
| Base v5 | 28.6% | 85.2% |
| Fine-tuned | **26.8%** | 83.9% |

Per-sample (58 val crops): **CER 14 wins / 5 losses / 39 ties**; diacritics 12 wins / 14 losses.

Training dynamics that bound this: CTC loss fell 414→52 over 30 epochs. Pushing to **80 epochs overfit** — `norm_edit_dis` degraded 0.49→0.59, so 346 samples genuinely saturate; the 30-epoch point is near the data-size optimum, not merely under-trained.

**Reading it honestly**: the fine-tune improves *letter* accuracy on unseen pages (−1.8pp, 2.8× win rate) but does **not** improve diacritic recall — the specific thing the whole program was aimed at. A gate that improves general OCR but not diacritics is a **partial pass**: it says fine-tuning *works and transfers*, while saying the diacritic deficit needs something more than plain cross-entropy on 346 hemistichs.

## R6 — Repo and environment integrity

- sha256 over all `data/output` + `data/ground_truth` text = **`91b3f61101170b233619`** — unchanged. `git status` shows only pre-existing spec 005-012 modifications.
- **New `myenv` dependencies** (needed by PaddleOCR's data pipeline): `scikit-image`, `albumentations`, `lmdb` (+ `scipy`, `imageio`, `tifffile`, `lazy-loader` as transitive deps). These are additive and do not affect the pipeline's runtime path — `main.py` never imports them.
- All training artifacts, weights, and datasets live outside the repo (`/home/omar/.opencode/scratch/`); nothing was written into `data/` or `config/`.
- Disk note for future runs: `/tmp` is a 7.8GB tmpfs and filled up with model checkpoints — large training runs should write to the nvme (~120GB free), not `/tmp`.
