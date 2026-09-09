<!--
Sync Impact Report
==================
Version change: (unratified template) → 1.0.0
Rationale: Initial ratification. The prior file at this path was an unpopulated
scaffold (all placeholder tokens). This is the first concrete constitution for
this project, so it is adopted as MAJOR version 1.0.0 rather than a template bump.

Modified principles: n/a (first ratification, no renames)

Added sections:
  - Core Principles I–VIII (Reverse-Engineering-First Extraction Order,
    Evolutionary Implementation, Faithful Reconstruction over Plausible
    Generation, Raw Evidence Immutability & Layered Outputs, Diacritic
    Preservation & Non-Corrective Extraction, Measurement-Driven Improvement,
    Resource-Constrained Local-First Design, Generalized Scope)
  - Scope Boundaries & Interface Policy
  - Development Workflow & Quality Gates
  - Governance

Removed sections: none (template placeholders only)

Deferred / follow-up TODOs:
  - TODO(GROUND_TRUTH_CLEANUP): the Claude-produced reference transcript for the
    primary test manuscript still needs cleanup (removal of inserted
    explanations/glosses not present in the original) before it is usable as
    the official CER/WER benchmark. Tracked as a deferred, non-governance task
    — see "Next Actions" in the command output, not blocking constitution
    ratification.
  - TODO(RATIFICATION_DATE): confirmed as 2026-09-06 (date of this ratification
    session) in the absence of an earlier documented adoption date for a formal
    constitution governing this codebase.
-->

# Arabic Manuscript OCR Pipeline Constitution

## Core Principles

### I. Reverse-Engineering-First Extraction Order (NON-NEGOTIABLE)
Every input PDF MUST first be probed for a usable embedded text layer (a real,
correctly-mapped digital text layer — e.g. from prior digital typesetting or a
prior correct OCR pass with a valid ToUnicode CMap). If — and only if — a page
lacks a usable text layer does the system fall through to the imaging pipeline:
Render → Preprocess → Layout Detection → Segmentation → OCR. This decision MUST
be made per page, not per document: a single PDF MAY legitimately mix pages
that qualify for direct extraction with pages that require full OCR, and the
system MUST route each page independently without manual page-range
configuration.
Rationale: decoding an existing text layer is strictly more accurate and
cheaper than re-deriving text from pixels. Treating this as an afterthought
optimization rather than the mandatory first step risks silently OCR'ing pages
that already have a perfect answer available, discarding it for a worse one.

### II. Evolutionary Implementation Principle (NON-NEGOTIABLE)
This project is a restructuring of an existing, working codebase — not a
greenfield rewrite. Whenever `/speckit.plan` or `/speckit.implement` calls for
creating a file, module, or component, the equivalent existing file MUST first
be identified and read. If an equivalent already exists, it MUST be modified,
extended, or refactored in place; it MUST NOT be discarded and rewritten from
scratch merely because a clean-slate design would look tidier. A full rewrite
of an existing module is permitted only when explicitly justified in the plan
(e.g. the existing approach is architecturally incompatible with a ratified
principle below) — never as a default.
Rationale: the existing code encodes hard-won knowledge (known failure modes,
tuned constants, edge cases already handled). Discarding it by default
reintroduces already-solved bugs and wastes the investment this restructuring
is meant to build on.

### III. Faithful Reconstruction over Plausible Generation (NON-NEGOTIABLE)
A vision-capable model (multimodal LLM) MUST NEVER be granted open-ended
"read this image and tell me the text" authority over any word or line whose
base OCR confidence is below the configured threshold. The only sanctioned
escalation path for a low-confidence token is:
1. The suspect word is passed to a morphological/lexical analyzer, which
   generates a bounded list of plausible candidates (morphologically and
   visually/shape-plausible alternatives).
2. Only then is the cropped image of that word, together with the specific
   closed candidate list, sent to the vision model — and it is asked
   exclusively: "which of these listed candidates exactly matches the image?"
   Free-form transcription in this path is forbidden; the model selects from a
   closed set or explicitly declines (e.g. "none of these match").
Any vision-model output produced outside this constrained closed-list
verification path MUST always be treated as an unverified, low-trust
candidate — never as final authority — and MUST NOT silently replace the base
OCR engine's output merely because it "looks like" more plausible or more
elegant Arabic.
Rationale: multimodal LLMs are fluent in Classical Arabic and will, under
uncertainty, complete a fragment with grammatically and stylistically
plausible text that is not actually present on the page. Restricting them to
closed-set discrimination against a real crop eliminates their capacity to
invent content while still using their visual-matching strength.

### IV. Raw Evidence Immutability & Layered Outputs (NON-NEGOTIABLE)
The raw OCR output layer (the base engine's direct transcription, prior to any
vision-fallback escalation or text-correction pass) MUST be persisted exactly
as produced and MUST NEVER be overwritten in place by any downstream stage.
Every downstream improvement (vision-fallback escalation, LLM text
correction, morphological correction, etc.) MUST be written to its own
separate output layer/artifact, with the original raw layer retained
unmodified and always retrievable. A failed or rejected downstream step MUST
fall back to leaving the raw layer as the effective output for that unit of
text — it must never be dropped or left blank.
Rationale: without an immutable raw layer, a bad downstream decision (a
hallucinated vision correction, an overzealous text-correction rewrite) is
unrecoverable and undetectable. Layered outputs make every transformation
auditable and reversible.

### V. Diacritic Preservation & Non-Corrective Extraction — "OCR ≠ Editing" (NON-NEGOTIABLE)
Preservation of diacritics (tashkeel) is a first-order design priority that
overrides convenience or simplicity elsewhere in the pipeline. Consequently:
- Morphological image operations that erode fine strokes (e.g. Erosion,
  Dilation, and similar morphological transforms) are FORBIDDEN by default on
  any path that touches the image immediately feeding OCR, because they risk
  destroying thin diacritic marks. Enabling such an operation on that path
  requires an explicit, documented, opt-in exception with measured evidence
  (see Principle VI) that diacritic fidelity is not degraded.
- The system's job is to recover what is actually printed/written on the
  page — not what "should" be correct by grammar, spelling, or classical
  convention. Any linguistic/stylistic correction (spelling normalization,
  grammar fixes, phrasing cleanup) MUST live in a separate, clearly labeled,
  optional stage that is disabled by default and MUST NEVER be merged into
  the primary extraction path.
Rationale: for a manuscript-fidelity tool, an invented "correction" is a
worse failure than a visible OCR error, because it is silent and
undetectable without comparing back to the source image.

### VI. Measurement-Driven Improvement (NON-NEGOTIABLE)
No change that touches OCR behavior or image preprocessing may be described
or merged as an "improvement" without an accompanying CER/WER measurement
(via `jiwer` or an equivalent standard metric) run against the project's
designated benchmark corpus, showing the actual before/after delta.
"Improvement" claims based on visual spot-checking alone are not acceptable
for any change to this path.

Ground Truth policy (read carefully — this is a deliberate, non-obvious
decision): the project's designated benchmark reference for its primary test
manuscript is a transcription produced by a large language model (Claude)
reading page images, and is itself pending a cleanup pass (removing
explanatory glosses/annotations the model inserted that are not part of the
original text). This reference is knowingly adopted as the **official
measurement benchmark** for CER/WER despite not being a human-certified
critical edition. This is an explicit, deliberate choice, not an oversight:
- The project's stated goal is **NOT** "achieve 100% identity with this
  reference." The reference is a **practical, aspirational upper bound** —
  a stand-in for "the quality level a strong multimodal LLM reading the same
  images achieved" — not an infallible ground truth.
- Reaching parity with this benchmark is a meaningful, measurable milestone.
  Exceeding it, disagreeing with it in specific spots after manual review, or
  discovering it is wrong in places are all legitimate outcomes and MUST NOT
  be treated as constitution violations.
- This distinction MUST be preserved in any future documentation, dashboard,
  or reporting derived from CER/WER numbers: reported scores are "distance to
  this working benchmark," not "distance to absolute truth."

### VII. Resource-Constrained, Local-First Design (NON-NEGOTIABLE)
The system MUST be designed by default for a local execution environment with
severely limited GPU resources (reference constraint: 4GB VRAM). This is the
default assumption for every architectural and model-selection decision, not
a documented exception. Any component that assumes materially more GPU memory
or compute than this (larger local models, heavier batch sizes, etc.) MUST be
explicitly flagged as an opt-in, non-default configuration, and MUST degrade
gracefully (not crash) when run in the constrained default environment.
Rationale: the tool must remain usable on the hardware it was actually built
for; assuming generous compute by default would silently break the primary
deployment target.

### VIII. Generalized Scope — Not Book-Specific (NON-NEGOTIABLE)
This tool is built for Arabic manuscripts in general, not for one specific
book. A specific test manuscript (a fully-vocalized poetry/genealogy
manuscript) serves as the primary development and benchmarking case, but no
rule, threshold, heuristic, or piece of documentation in this project may be
phrased in a way that implicitly assumes that one manuscript's characteristics
(its specific font, its specific layout, presence/absence of poetry hemistich
splits, presence/absence of marginal commentary) as a universal constant.
Every constraint or default MUST be framed as reflecting a class of documents
("fully-vocalized Arabic manuscripts," "poetry-with-commentary layouts") or
explicitly marked as a benchmark-specific calibration value subject to
recalibration for other manuscripts.
Rationale: designing against a single book's idiosyncrasies produces a tool
that quietly fails on the very next manuscript it is pointed at, defeating
the stated purpose of a reusable pipeline.

## Scope Boundaries & Interface Policy

- **Interface (Non-Negotiable, current scope)**: the supported user-facing
  interface is a command-line interface (CLI) only. All current design
  decisions MUST optimize for CLI usage (scriptability, stdin/args → stdout,
  structured + human-readable output).
- **Graphical interface (Out of Scope — current phase)**: a GUI is explicitly
  out of scope for the current project phase. It may be considered as a
  distant future phase, but MUST NOT influence any current architectural or
  API-shape decision (e.g. do not pre-build abstractions "for the future GUI"
  at the cost of CLI simplicity today).
- **Multi-manuscript generality (Non-Negotiable)**: see Principle VIII. Any
  proposal to hardcode a rule that only works for the current benchmark book
  is out of scope for the primary pipeline; it belongs, if anywhere, in a
  benchmark-specific configuration/calibration file, never in core logic.
- **Linguistic/stylistic auto-correction as a first-class default (Out of
  Scope)**: automatic grammar/style correction integrated into the primary
  extraction path is explicitly out of scope; see Principle V. It may exist
  only as a separate, opt-in, clearly-labeled stage.

## Development Workflow & Quality Gates

- **Existing-code check (process gate)**: before implementing any planned
  file/module in `/speckit.plan` or `/speckit.implement`, the equivalent file
  in the current codebase MUST be located and read first (Principle II). The
  plan/tasks output MUST record which existing file(s) a given task builds on,
  or explicitly justify why none exists / why a rewrite is warranted.
- **Measurement gate**: any pull request or task that changes OCR behavior,
  preprocessing, layout/segmentation logic, or the vision-fallback/
  text-correction paths MUST include a CER/WER comparison against the
  designated benchmark (Principle VI) in its description/summary. A change
  without this comparison MUST NOT be described as an improvement or merged
  as one.
- **Non-negotiable-principle check**: any change that would disable raw-layer
  immutability (Principle IV), grant free-form vision authority outside the
  closed-candidate path (Principle III), or enable morphological
  erosion/dilation on the pre-OCR image path (Principle V) without a
  documented, measured exception MUST be rejected in review regardless of
  claimed benefit.
- **Benchmark corpus hygiene**: cleanup of the Claude-produced reference
  transcript (removing inserted glosses/explanations not present in the
  original manuscript) is tracked as ongoing benchmark-corpus maintenance, not
  as a one-time blocking prerequisite — but no CER/WER number should be
  reported as authoritative until the specific pages it covers have had this
  cleanup applied.

## Governance

This constitution supersedes ad-hoc practice for this project. Where a prior
undocumented convention in the existing codebase conflicts with a
Non-Negotiable principle above, the principle wins, and the conflicting
behavior is tracked as a migration item in `/speckit.plan`, not silently kept.

**Amendment procedure**: amendments are proposed as an edit to this file
together with a rationale (which principle/section changes and why). Any
amendment that removes or redefines a Non-Negotiable principle is a MAJOR
version change and MUST include a migration note describing impact on
already-planned or in-flight work. Adding a new principle or materially
expanding an existing section is a MINOR version change. Wording
clarifications, typo fixes, and non-semantic rewording are PATCH changes.

**Versioning policy**: semantic versioning (MAJOR.MINOR.PATCH) as described
above, tracked in the version line at the bottom of this file.

**Compliance review**: `/speckit.plan` and `/speckit.implement` outputs MUST
be checked against the Non-Negotiable principles above before being accepted;
any deviation MUST be explicitly called out and justified in the plan, not
silently introduced. Reviewers evaluating a change MUST treat an unmeasured
"OCR improvement" claim (Principle VI) as incomplete, not merely
unpolished.

**Version**: 1.0.0 | **Ratified**: 2026-09-06 | **Last Amended**: 2026-09-06
