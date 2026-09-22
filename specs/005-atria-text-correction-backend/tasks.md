# Tasks: Atria Text-Correction Backend

**Input**: Design documents from `/specs/005-atria-text-correction-backend/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

**Tests**: Explicitly requested in the spec's test plan (FR-010, SC-001–SC-008). All test tasks are included.

**Organization**: Tasks grouped by user story. US1 (P1) = the backend itself. US2 (P1) = rate-limit resilience. US3 (P2) = budget guard. US4 (P1) = regression preservation. Config/docs tasks (FR-013/FR-014) are the H2–H4 deliverables.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Backend implementation (US1 — P1) 🎯 MVP

**Goal**: A registered, working `AtriaTextBackend` that corrects text through the live API.

- [x] T001 In `src/pipeline/correction/text_correction_engine.py`, add module-level `_extract_openai_compatible_text(response, backend_name)` (null-safe `choices[0].message.content`; transient error for `finish_reason='length'`, permanent "empty response" otherwise) and `_extract_retry_after(exc)` (429-only, clamped [0,60], 5s default). Add `"empty response"` to `PERMANENT_ERROR_MARKERS`.
  **Acceptance**: `myenv/bin/python -m py_compile` passes; a `content=None`/`finish_reason='length'` response raises a message that does NOT match permanent markers, while `content=None`/other DOES.
- [x] T002 Add the `AtriaTextBackend` class (constants per data-model §1; `_budget_ok`; `correct` with the Retry-After retry loop and `max_tokens=REQUEST_MAX_TOKENS`) and register `"atria"` in `BACKEND_REGISTRY`.
  **Acceptance**: `BACKEND_REGISTRY["atria"] is AtriaTextBackend`; `AtriaTextBackend.DEFAULT_MODEL == "Atria-Dawn-Preview"`.
- [x] T003 Point `GroqTextBackend.correct()` at the shared null-safe extractor (removes the latent `None.strip()` crash — research R6).
  **Acceptance**: Groq test in the existing suites still passes; grep confirms no remaining bare `message.content.strip()`.
- [x] T004 Live smoke: construct `TextCorrectionEngine` with a single `atria` slot and correct a one-line Arabic prompt; confirm `source == "atria"` and validated Arabic output.
  **Acceptance**: prints `source: atria`; round-trip < 5s.

**توقف هنا وتأكد قبل الاستمرار**

---

## Phase 2: Rate-limit resilience (US2 — P1)

**Goal**: A 429 honors `Retry-After`, retries once, and a persistent 429 gives up.

- [x] T005 Test: inject a fake client raising a real `openai.RateLimitError` (httpx `Response` with `Retry-After: 1`) on the first call, then succeeding. Assert: one retry, sleep ≥1s, success, exactly 2 calls.
  **Acceptance**: passes without network.
- [x] T006 Test: a persistent 429 raises after exactly one retry (2 calls), and a non-429 error (HTTP 500) takes the no-Retry-After path.
  **Acceptance**: passes without network.

---

## Phase 3: Budget guard (US3 — P2)

**Goal**: Oversized prompts are refused before the API call.

- [x] T007 Test: `_budget_ok()` — a synthetic ~256k-token string is refused; a normal Arabic string passes; the exact boundary (`est + REQUEST_MAX_TOKENS == CONTEXT_TOKENS`) is refused.
  **Acceptance**: passes without network; zero API calls.

---

## Phase 4: Response validation & error classification (US1/US2)

- [x] T008 Test: `clean_and_validate_correction()` accepts plausible Arabic; rejects a refusal phrase and an all-Latin response (SC-005).
- [x] T009 Test: exact model-ID passthrough — assert the model string reaching the client equals `Atria-Dawn-Preview` byte-for-byte (SC-003).
- [x] T010 Test: permanent-vs-transient classification — `finish_reason='length'` error is transient; genuine empty-response is permanent (SC-006).

---

## Phase 5: Configuration & documentation (FR-013/FR-014)

- [x] T011 `config/settings.yaml`: add `text_correction.backends.atria` (`model: Atria-Dawn-Preview`, `api_key_env: ATRIA_API_KEY`) and append `atria` to `rotation_order`, with comments on case-sensitivity and the shared-RPM caveat.
- [x] T012 `docs/AGENTS.md`: §3 status row (planned/text-only), §9 openai-version correction + SDK note, §12 text-only + shared-RPM caveats, and the A1/A2/E1 rule adjacent to §4.13.
- [x] T013 `docs/CHANGELOG.md`: dated entry describing the new backend, the 429/Retry-After behavior, and the reasoning-content truncation finding.

---

## Phase 6: Regression & validation (US4 — P1)

- [x] T014 Run the three existing suites: `myenv/bin/python -m unittest tests.test_escalation_policy tests.test_output_generator tests.test_cer_normalization`. All 55 (32+12+11) must pass unchanged.
- [x] T015 New suite: `myenv/bin/python -m unittest tests.test_atria_text_backend` — all tests pass.
- [x] T016 §11 Definition of Done: `py_compile` on every modified file; `myenv/bin/python main.py --start 24 --end 26` exits 0; outputs in place; no `baseline/` change; no secrets in output.
