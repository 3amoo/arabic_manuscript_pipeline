# Quickstart — spec 008 (Alignment Cursor Recovery)

Runnable validation for the alignment-cursor fix. Every command is re-runnable and deterministic.

## Prerequisites

- myenv venv (Python 3.11.16) — system Python 3.14 forbidden (AGENTS.md §9)
- Evidence present and immutable:
  ```
  find data/output "data/ground_truth" -name '*.txt' -exec sha256sum {} \; | sort | sha256sum | cut -c1-20
  # must print: 91b3f61101170b233619
  ```
- spec-006 baseline report exists at `data/evaluation_reports/006/` (left untouched by this spec)

## 1. Run the fixed aligner (writes the new baseline layer)

```
myenv/bin/python -m src.pipeline.evaluation.align_ground_truth \
  --document "عمود النسب نسخة 2" \
  --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md" \
  --output "data/evaluation_reports/008/alignment.json"
```

**Expected**: summary prints page counts. Versus the spec-006 run, `unmatched` drops from 2 → 0 *scored-as-windowless* (pages 59/67 become `unmatched` + `recovered: true` with real windows), and `recovered: true` appears on exactly those entries.

## 2. Verify the recovery invariants

```
myenv/bin/python - <<'PY'
import json
a = json.load(open('data/evaluation_reports/008/alignment.json'))['alignment']
# SC-001: no coverage gap > LOOKBACK between consecutive in-scope windows
prev = None; bad = []
for e in a:
    if e['gt_start'] is None: continue
    if prev is not None and e['page'] == prev['page'] + 1:
        gap = e['gt_start'] - prev['gt_end'] - 1
        if gap > 12: bad.append((e['page'], gap))
    prev = e
print('gaps > LOOKBACK:', bad or 'NONE ✓')
# SC-002: pages 59/67 recovered with real windows
for p in (59, 67):
    e = next(x for x in a if x['page'] == p)
    print(f'p{p}: status={e["status"]} recovered={e.get("recovered")} window={e["gt_start"]}-{e["gt_end"]}')
PY
```

**Expected**: `gaps > LOOKBACK: NONE ✓`; p59/p67 each show `recovered=True` with a non-null window covering GT ~490–501 and ~606–620.

## 3. Score with the fixed harness

```
myenv/bin/python -m src.pipeline.evaluation.evaluate_cer \
  --document "عمود النسب نسخة 2" \
  --gt-file "data/ground_truth/عمود النسب/عمود_النسب.clean.md" \
  --alignment "data/evaluation_reports/008/alignment.json" \
  --report-dir "data/evaluation_reports/008" \
  --diacritics-metrics --heatmap
```

**Expected (SC-003/SC-005)**: page 60's CER drops from 71.2% to ~54.1% (verse-lines-only scoring — the official method); pages 59/67 show a real non-zero CER (64.9% / 47.3%) flagged `unmatched+recovered`; the summary states clean / low-confidence / recovered counts (26 / 17 / 2 on this corpus).

## 4. Regression guard — the 26 matched pages must not move

```
myenv/bin/python - <<'PY'
import json
old = {e['page']: e for e in json.load(open('data/evaluation_reports/006/alignment.json'))['alignment']}
new = {e['page']: e for e in json.load(open('data/evaluation_reports/008/alignment.json'))['alignment']}
moved = [p for p,e in old.items() if e['status']=='matched'
         and (new[p]['gt_start']!=e['gt_start'] or new[p]['gt_end']!=e['gt_end'] or new[p]['status']!='matched')]
print('matched pages that moved:', moved or 'NONE ✓ (FR-004)')
PY
```

**Expected**: `NONE ✓`.

## 5. Full test suite + smoke + evidence integrity

```
myenv/bin/python -m unittest tests.test_gt_alignment tests.test_diacritic_metrics tests.test_cer_normalization \
  tests.test_escalation_policy tests.test_output_generator tests.test_atria_text_backend \
  tests.test_benchmark_cer_wer tests.test_clean_ground_truth
timeout 300 myenv/bin/python main.py --start 24 --end 26   # must exit 0
find data/output "data/ground_truth" -name '*.txt' -exec sha256sum {} \; | sort | sha256sum | cut -c1-20
# must still print: 91b3f61101170b233619
```

**Expected**: all tests OK (129+ including new cursor-recovery tests), main.py exit 0, sha256 unchanged (FR-009).

## 6. Determinism (FR-008)

Re-run step 1 and diff:
```
cp data/evaluation_reports/008/alignment.json /tmp/opencode/run1.json
# (re-run step 1)
diff /tmp/opencode/run1.json data/evaluation_reports/008/alignment.json && echo 'byte-identical ✓'
```

**Expected**: byte-identical.
