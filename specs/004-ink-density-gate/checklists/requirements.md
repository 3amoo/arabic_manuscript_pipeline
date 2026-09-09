# Specification Quality Checklist: Ink-Density Gate for Vision Escalation

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-09 (revised)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Revision Notes (v1 → v2)

Items changed in this revision:

1. **Binary polarity corrected everywhere**: FR-001, FR-005, Key Entities (Ink Density), Edge Cases, Assumptions — all now correctly state ink=255, bg=0 after `THRESH_BINARY_INV`.
2. **Integration point corrected**: FR-002 changed from `_should_escalate_line()` to `_maybe_escalate_line()` (the function that has `crop_img`). Describes early-return pattern.
3. **JSON schema defined**: Key Entities — Blocked Escalation Entry now has a complete JSON schema with `escalated_text: null`, `source: "ink_density_gate"`, `ink_ratio` field, and three reason codes.
4. **Audit semantics clarified**: User Story 2 and FR-006 explicitly state blocked entries are audit records, not Vision responses.
5. **Kashida/punctuation claims softened**: Edge Cases and Acceptance Scenarios 2–3 now say "ink ratio depends on measured value" instead of claiming fixed percentages.
6. **Versioned fixtures defined**: New Test Fixtures section defines `ink-density-fixtures-v1` with schema. SC-001 and SC-002 reference it.
7. **Fail-closed documented as `ink_density_unavailable`**: FR-011 and Edge Cases use the new reason code with fail-closed semantics (block + audit record, no Vision call). Remaining risk documented.
8. **Scope explicitly bounded**: FR-008 through FR-010 reaffirm no changes to cache, poetry, noise, repeated_verbatim, echo.
9. **FR-016 confirmed single**: No duplication, no repeated text.

## Revision Notes (v2 → v3)

Items changed in this revision (behavioral decision resolved before implementation):

1. **Fail-open → fail-closed for `ink_density_unavailable`**: FR-011 and Edge Cases in `spec.md`, R5 in `research.md`, and `quickstart.md` V1/V2 now state that when `crop_img` is `None` or binarization fails, the gate blocks and does NOT call Vision. `data-model.md` already drew this exact transition and is unchanged.
2. **Test-count claims corrected**: `quickstart.md` no longer claims 39 tests live inside `test_escalation_policy.py` alone; it now states 16 pre-existing there, with 39 = 16 + 12 + 11 across the three suites (escalation policy, output generator, CER normalization).
3. **Test modification scope clarified**: `plan.md` now labels `test_escalation_policy.py` ADD-only — new `InkDensityGate` classes are appended; the 16 pre-existing tests remain unchanged, satisfying SC-004.
