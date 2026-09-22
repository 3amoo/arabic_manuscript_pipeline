# Commit Plan — Splitting 80 Changed Files by Closure Group

**Goal:** land Groups A, E, D, C as independently-bisectable commits, and
land Group B's rejection as a documentation-only commit (plus a decision
on whether B's exploratory code stays in the tree at all). Every commit
should be able to stand alone: checked out by itself, it should pass
`verify_all.py`, not just "the final state after all commits passes."
That's the whole point of splitting — if it only works bundled, splitting
bought you nothing.

**Order:** A → E → D → C → B-decision
(same order the work was done in, which is also the safest order for
dependencies — later groups may have been influenced by earlier ones,
the reverse is less likely).

---

## Task 0 — Pre-flight baseline check
**Priority: BLOCKING (do first, once)**

Before staging anything, confirm the *current, fully uncommitted* working
tree still passes cleanly — you already know it does per the last report,
but re-confirm right before you start cutting it apart, since staging/
stashing operations are exactly the kind of step where a stray `git add`
or forgotten file can silently change what's actually being tested:

```
HOME=./data/temp ./myenv/bin/python verify_all.py
```

If this doesn't pass right now, stop — fix that first, don't start
splitting a broken tree.

---

## Task 1 — Inventory: map every changed file to exactly one group
**Priority: BLOCKING**

Run `git status --porcelain` (or `git diff --name-only`) and go through
the full list of ~80 files, tagging each with the group it belongs to,
using the file lists from `CLOSURE_PLAN.md` as your starting map:

- **Group A:** `docs/escalation_threshold_audit.md` (the new 6-row visual
  audit + threshold-portability paragraph)
- **Group E:** `scripts/vote_correct_names.py`, `logs/vote_corrections.jsonl`
  (if committed — see note below), related test file(s)
- **Group D:** the new genealogy cross-reference module,
  `logs/genealogy_crossref_review.md`, related test file(s)
- **Group C:** `scripts/ingest_reviewed_corrections.py`, the
  `data/reviewed_corrections/` format/schema, updates to `measure_der.py`
  to consume the expanded gold set
- **Group B (decision only):** whatever remains of `scripts/restore_tashkeel.py`
  (if kept — Task 7 below decides this), plus the rejection writeup

**Flag every file touched by more than one group separately** — you
already know at least these are shared, since multiple groups update the
same running docs:
- `docs/accuracy_history.md` (likely touched by E, D, B's rejection note,
  and C)
- `README.md` / `docs/CHANGELOG.md` (if any group added a line there)
- `NEXT_DEVELOPMENT_PLAN.md` or `CLOSURE_PLAN.md` itself if progress got
  checked off inline

These shared files are the main risk in this whole plan — see Task 3.

**Note on log files (`logs/*.jsonl`, `logs/*.md` review queues):** decide
now whether these are meant to be version-controlled evidence or
git-ignored runtime output. If earlier work already gitignored
`data/output/`-style runtime artifacts, the new review-queue logs
probably belong in the same category — check `.gitignore` before
assuming they should be committed at all. Don't let "80 files changed"
quietly include things that were never meant to be tracked.

---

## Task 2 — Commit Group A (audit closure)
**Priority: do first among the four "real" commits**

```
git add docs/escalation_threshold_audit.md   # only the A-specific hunk if this file is shared — see Task 3
git stash push --keep-index                  # shelve everything else NOT staged
HOME=./data/temp ./myenv/bin/python verify_all.py   # must pass on A alone
git commit -m "docs: close escalation-threshold audit — ..."
git stash pop                                # restore the rest for the next round
```

If `verify_all.py` fails on A alone, that means A secretly depended on
something from a later group — stop and figure out what, don't force the
commit through.

---

## Task 3 — Handling shared files (`docs/accuracy_history.md`, etc.)
**Priority: BLOCKING before Tasks 4–6, since it affects all of them**

For any file multiple groups touched, use `git add -p` (patch mode)
instead of `git add <file>`, so you can stage only the hunk(s) belonging
to the group you're currently committing and leave the rest unstaged for
later:

```
git add -p docs/accuracy_history.md
# answer y/n per hunk — stage only Group A's addition this round
```

If a single paragraph genuinely mixes content from two groups (e.g. one
sentence references both E's vote-correction numbers and D's
cross-reference numbers), that's a sign the doc was written after the
fact rather than incrementally — in that case, don't force an artificial
split; just pick whichever group's commit is more central to that
paragraph and note in the commit message that it also documents a related
change from the other group, landing fully in the later group's commit
instead of splitting a single paragraph across two commits.

---

## Task 4 — Commit Group E (majority-vote correction)
Same pattern as Task 2: stage the module + test, stage only E's doc hunk,
stash the rest, verify, commit, pop.

Conservative under-merge bias is the design principle worth naming in the
commit message: distinct-but-similar genealogy names are deliberately not
merged.

---

## Task 5 — Commit Group D (genealogy cross-reference)
Before committing, resolve one open design question from the plan itself:
confirm the genealogy-vault index this reads from is treated as **read
only** — grep the new module for any write operations back into the
Obsidian vault's files and remove/flag any that exist, since the plan
explicitly scoped this as human-mediated, not automatic, in both
directions. Disagreements go to `logs/genealogy_crossref_review.md`,
separate from `manual_review_queue.md` (source-conflict vs OCR-confidence
is a different judgment call).

---

## Task 6 — Commit Group C (review-queue → gold corpus infrastructure)
Nothing left to stash by now if A/E/D already landed. Stage the module,
the gold-corpus format, and C's doc hunk; verify; commit.

---

## Task 7 — Resolve and commit Group B's disposition
**Priority: BLOCKING before you consider this whole plan done — this is
the one still-open question from the last review**

1. **Decide first:** is `scripts/restore_tashkeel.py` staying in the tree
   as a documented, dormant evaluation tool for a future retry, or being
   removed entirely since it didn't ship? Either is defensible; what's not
   defensible is leaving it in an ambiguous state where a future reader
   can't tell whether it's live, half-finished, or intentionally shelved.
2. **If keeping it:** add a module-level docstring stating plainly that it
   was evaluated, failed the genre gate, is not used in the production
   pipeline, and is kept for re-evaluation against a larger gold corpus
   (see Group C).
3. **If removing it:** delete the file(s), and make sure the rejection
   writeup in `docs/accuracy_history.md` stands on its own — the finding
   should survive even if the exploratory code doesn't.
4. Commit whichever path you chose, with the decision stated in the
   commit message.

---

## Task 8 — Final verification of the whole sequence
**Priority: BLOCKING, closes this plan**

After all 5 commits land, confirm that replaying them in order from a
clean checkout reproduces the same end state as before splitting:
`git log --oneline -5`, the full `verify_all.py` suite (must match the
pre-split baseline exactly), and `git status` (should be clean). If status
still shows leftovers, Task 1's inventory missed something — go back and
account for it rather than leaving it uncommitted indefinitely.

---

## Summary Table

| # | Task | What it produces |
|---|------|-------------------|
| 0 | Pre-flight baseline | Confirms starting point is sound |
| 1 | Inventory & group-mapping | A complete file→group map, shared files flagged |
| 2 | Commit A | Standalone, passing commit |
| 3 | Shared-file splitting strategy | Applies to every commit from here on |
| 4 | Commit E | Standalone, passing commit |
| 5 | Commit D | Standalone, passing commit |
| 6 | Commit C | Standalone, passing commit |
| 7 | Resolve + commit B's disposition | Explicit keep/remove decision, documented either way |
| 8 | Final full-sequence verification | Confirms the split reproduces the pre-split state exactly |
