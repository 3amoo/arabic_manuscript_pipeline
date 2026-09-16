# Quickstart Validation: Ink-Density Gate

**Feature**: 004-ink-density-gate
**Date**: 2026-09-09

## Prerequisites

- `myenv/bin/python` available at project root
- Existing test suite passes: `myenv/bin/python -m unittest tests.test_escalation_policy -v` (16 pre-existing tests in this file; the "39" figure referenced in the spec is the sum across `test_escalation_policy.py` (16) + `test_output_generator.py` (12) + `test_cer_normalization.py` (11))
- `settings.yaml` present with `vision_fallback` section

## Validation Scenarios

### V1: Unit Tests — Ink Density Calculation

**Command**:
```bash
myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGate -v
```

**Expected**: All tests in the `InkDensityGate` class pass. Covers:
- Blank crop → ink_ratio ≈ 0.0, blocked
- Kashida-only crop → ink_ratio measured, blocked if below threshold
- Punctuation-only crop → ink_ratio measured, blocked if below threshold
- Normal Arabic text crop → ink_ratio above threshold, not blocked
- Faint text crop → ink_ratio measured, outcome depends on threshold
- `None` image → fail-closed (blocked), reason=`ink_density_unavailable`, no Vision call

### V2: Integration — Blocked Crops Skip Vision

**Command**:
```bash
myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGateIntegration -v
```

**Expected**: Tests prove that:
- A blank crop triggers early return from `_maybe_escalate_line()` without calling `vision_engine.transcribe()`
- A `None` crop does the same (fail-closed): early return, no Vision call, audit entry with `reason="ink_density_unavailable"`
- The `result["text"]` dict is not mutated
- An escalation entry is produced with `accepted=False`, `source="ink_density_gate"`, `escalated_text=None`

### V3: Regression — Existing Tests Unchanged

**Command**:
```bash
myenv/bin/python -m unittest tests.test_escalation_policy -v
```

**Expected**: All 16 pre-existing tests in `test_escalation_policy.py` pass unchanged (0 failures, 0 errors) — the new ink-density tests are additive only. The "39" total seen elsewhere refers to the sum across the three suites (16 + 12 + 11). The ink-density gate does not alter any existing behavior.

### V4: Pipeline Smoke — Benchmark Pages

**Command**:
```bash
myenv/bin/python main.py --start 24 --end 26
```

**Expected**: Exit code 0. Output files generated in `output/`. Compare `full_manuscript.txt` with the prior commit — text should be identical for all crops that passed the ink-density gate (i.e., crops with sufficient ink).

### V5: Configuration — Threshold Tuning

**Command** (manual test):
1. Set `vision_fallback.ink_density_threshold: 0.005` in `settings.yaml`
2. Run V4
3. Observe that more crops pass the gate (lower threshold = fewer blocks)
4. Reset to `0.02`

**Expected**: Threshold change takes effect without code modification. A one-time warning is logged if the key is missing.

### V6: Audit Trail — Escalation Log

**Command**:
```bash
cat output/عمود\ النسب\ نسخة\ 2/review/escalations.jsonl | python3 -m json.tool
```

**Expected**: Blocked entries visible with `source: "ink_density_gate"`, `escalated_text: null`, `ink_ratio` values. Can be filtered:
```bash
grep '"ink_density_gate"' output/*/review/escalations.jsonl
```

### V7: Deterministic Stub Run — SC-003 Validation

**Command** (run after implementation):
```bash
myenv/bin/python -m unittest tests.test_escalation_policy.InkDensityGateStub -v
```

**Expected**: A stub/mock vision engine records how many times `transcribe()` is called. With the gate enabled, the call count decreases by ≥10% compared to gate-disabled baseline on the fixture set representing pages 24–26.

---

## Validation Log (T019, 2026-09-10)

| Scenario | Result | Notes |
|---|---|---|
| V1 — Unit tests (InkDensityGate) | **PASS** | 7/7 OK: blank blocked, kashida/punctuation blocked, faint passes, real text passes, `None` fail-closed, small crop no crash. |
| V2 — Integration (InkDensityGateIntegration) | **PASS** | 4/4 OK: blank and `None` skip Vision, `result["text"]` not mutated, audit schema valid. |
| V3 — Regression (full test_escalation_policy) | **PASS** | 32/32 OK — all 16 pre-existing tests unchanged, 16 new gate/config tests additive. |
| V4 — Pipeline smoke (pages 24–26) | **PASS** | Exit 0. `full_manuscript.txt`, `raw_text/page_024..026.txt`, and `escalations.jsonl` all byte-identical to the pre-gate baseline snapshot. 100% OCR cache hits; 0 Vision escalations this run. |
| V5 — Threshold tuning | **PASS** (mechanism) | Config flip 0.02 → 0.005 verified read at startup (`override read: 0.005000`) and restored to 0.02. Full manual pipeline run at 0.005 NOT repeated: on this manuscript the gate blocks 0 crops at either threshold (calibration), so output would not change — the knob's behavior is covered by `InkDensityGateConfig` unit tests (T013) and the read-path check above. |
| V6 — Audit trail | **PASS** (audit path) | 33 live entries in `escalations.jsonl`; **0** with `source: ink_density_gate` — consistent with calibration (0 blocks on this manuscript). Audit schema/write path verified by `InkDensityGateIntegration.test_audit_schema_after_page_merge`; the `--start 24 --end 26` run writes every dict verbatim via `save_escalations()`. |
| V7 — Deterministic stub (SC-003) | **NOT VERIFIED / N/A** | `InkDensityGateStub` was never built (not implemented, not run). Criterion not met — see SC-003 explanation in `research.md` §Validation Summary. |
