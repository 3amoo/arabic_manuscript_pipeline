# Fix Intermediate-Commit Integrity — Plan
**Every one of the 7 commits must pass `verify_all.py` standalone, not just the final tip**

**Context:** the commit-split was supposed to produce 7 bisectable
commits. The final tip (commit 7) passes cleanly and matches the
pre-split baseline byte-for-byte, but commits 2 through 6 (possibly
including 1, depending on how the Task 8 amendment was applied) currently
fail `verify_all.py`'s unit-test check with 4 errors when checked out in
isolation, because `test_fallback_visibility.py` and `scripts/fallback_report.py`
ended up in a state where one references the other inconsistently across
the sequence. This defeats the entire purpose of splitting — a future
`git bisect` would report false failures at every intermediate stop.

**Goal:** rewrite history so all 7 commits exist with the exact same
final file content they have now, but reordered/regrouped so that
whichever commit introduces `test_fallback_visibility.py` and whichever
introduces `scripts/fallback_report.py` are either the same commit, or
the test file's commit comes strictly after the dependency's commit —
and verify every single one of the 7 in isolation before considering this
closed.

**Do not skip the verification step for any commit "because it's probably
fine now"** — that assumption is exactly what produced this bug the first
time (Task 8 found the missing-files problem only at the very end, after
all 7 were already made, instead of catching it commit-by-commit).

---

## Task 1 — Diagnose the exact fault, precisely, before rewriting anything
**Priority: BLOCKING**

1. `git log --oneline --follow -- scripts/fallback_report.py` and the same
   for `tests/test_fallback_visibility.py` — get the exact commit hash
   each file first appears in, in the current (broken) history.
2. For each of the 7 commits, `git checkout <hash>` into a scratch
   worktree (`git worktree add /tmp/wt-check <hash>` — don't touch your
   main working tree for this) and run:
   ```
   HOME=./data/temp ./myenv/bin/python verify_all.py
   ```
   Record pass/fail for every one of the 7, not just the ones you suspect.
   You currently only know "intermediate commits fail" as a generality —
   get the precise list (e.g. "commits 2,3,4,5,6 fail; 1 and 7 pass") so
   you know exactly how much history needs to move, not just approximately.
3. Confirm the root cause matches the hypothesis: does the failing range
   correspond exactly to "commits where `test_fallback_visibility.py`
   exists but `scripts/fallback_report.py` doesn't (or vice versa, or a
   third file both depend on is missing)"? If the actual cause turns out
   to be something else (e.g. a different missing import entirely), fix
   the plan's remaining steps to match what you actually find here rather
   than assuming the diagnosis from the last report is complete.
4. Remove the scratch worktree (`git worktree remove /tmp/wt-check`) once
   done.

---

## Task 2 — Decide the correction: merge or reorder
**Priority: BLOCKING**

Based on Task 1's findings, pick one of two corrections (don't guess —
let the actual dependency direction decide):

- **(a) Same-commit merge:** if `test_fallback_visibility.py` and
  `scripts/fallback_report.py` are tightly coupled (the test exists
  specifically to test that script, or both were part of the same
  original piece of work — likely, since both trace back to the earlier
  "fallback-visibility" plan, not to any of the A/E/D/C/B closure groups),
  the cleanest fix is putting both files in the **same** commit. Given
  neither belongs conceptually to Groups A/E/D/C/B, the right home is
  **commit 1 (baseline)** alongside `measure_der.py` and
  `ab_upscale_der.py`, which Task 8 already identified as belonging there
  for the same reason.
- **(b) Strict reorder:** if there's a genuine reason they need to stay in
  different commits (e.g. the test file also covers something from a
  later closure group and splitting it further is impractical), reorder
  so the dependency (`fallback_report.py`) lands in an earlier commit than
  the file that imports it, with no commit in between where only the
  importer exists.

Given what's described, (a) is almost certainly correct — both files are
pre-closure infrastructure, not part of any of the 5 closure groups, so
there's no reason for them to be split across different commits in the
first place. Only fall back to (b) if Task 1 reveals a real coupling to a
specific closure group's commit that makes merging awkward.

---

## Task 3 — Rewrite history with `git rebase -i`
**Priority: BLOCKING**
**Do this on a new branch, not directly on the branch you've been working
on, until it's verified — you can always fast-forward/replace afterward.**

1. `git branch backup-before-rebase-fix` (safety net — do this before
   anything else in this task).
2. `git rebase -i <parent-of-commit-1>` (i.e., rebase from before the
   very first of the 7 commits).
3. In the interactive rebase, if going with Task 2's option (a):
   - Mark commit 1 (baseline) as `edit`.
   - Mark whichever commit currently introduces
     `test_fallback_visibility.py` (and `scripts/fallback_report.py`, if
     it's a different commit) as `edit` as well.
   - When the rebase stops at commit 1: `git cherry-pick --no-commit
     <the-other-commit>` to pull those specific files' changes forward
     into the paused baseline commit, then remove those files from
     whatever commit originally introduced them later (so they don't
     appear twice), then `git commit --amend`.
   - This is fiddly with plain rebase mechanics — if it gets messy, the
     more reliable manual alternative is: `git rebase -i` marking only the
     *later* commit (the one wrongly introducing the files) as `edit`,
     use `git reset HEAD~1` at that stop to unstage its changes, split out
     the fallback_report.py/test_fallback_visibility.py hunks specifically
     with `git add -p`, commit the rest of that commit's original content
     as-is, then separately go back and fold the extracted hunks into
     commit 1 via a second short rebase pass, or simpler still: abandon
     the interactive rebase and rebuild the sequence from scratch (Task 4
     as an alternative) if the manual patching gets too error-prone —
     don't fight `rebase -i` mechanics for hours over a 7-commit history
     when a clean rebuild is faster and less risky.
4. After every `commit --amend` during the rebase, before moving to
   `git rebase --continue`, run `verify_all.py` against that commit's
   state (you're already sitting on it mid-rebase, no worktree needed for
   this part) — catch a mistake immediately, not at the end.
5. `git rebase --continue` through the rest — since only file *locations*
   changed, not final content, the remaining commits (closure groups
   A/E/D/C/B) should apply cleanly with no conflicts. If any of them DOES
   conflict, that's new information suggesting a real dependency you
   didn't know about — stop and re-diagnose rather than blindly resolving
   the conflict in favor of one side.

---

## Task 4 — Alternative: rebuild the sequence from scratch (use if Task 3's interactive rebase gets messy)
**Priority: fallback path, not the default**

If Task 3's `rebase -i` surgery is taking too long or produces confusing
intermediate states:
1. From the current (broken but final-content-correct) tip, `git reset
   --soft <parent-of-commit-1>` — this un-commits everything back to a
   single unstaged pile of changes while keeping the working tree exactly
   as it is now (the known-good final state).
2. Re-run the entire original commit sequence from `COMMIT_PLAN.md`
   (Tasks 2–7) again, except this time explicitly include
   `scripts/fallback_report.py`, `scripts/measure_der.py`,
   `scripts/ab_upscale_der.py`, and `tests/test_fallback_visibility.py`
   together in the baseline commit from the very start, instead of
   discovering the gap at the end.
3. Run the same `git stash push --keep-index` +
   `HOME=./data/temp ./myenv/bin/python verify_all.py` + commit + `git
   stash pop` cycle from `COMMIT_PLAN.md`, but this time **do not skip
   the per-commit verify step for any commit** — Task 1 of this plan
   exists specifically because that step was apparently skipped or
   passed incorrectly last time for at least one commit.
4. This produces a fresh, correct 7-commit (or possibly 6, if two commits
   naturally merge once the dependency is fixed) history with the exact
   same final tree, built once, correctly.

---

## Task 5 — Full verification of the corrected history
**Priority: BLOCKING — closes this plan**

1. For **every** commit in the corrected sequence (not a sample — all of
   them, exactly like Task 1's audit but now expecting all-pass), use
   `git worktree add` to check it out in isolation and run
   `HOME=./data/temp ./myenv/bin/python verify_all.py`. Record a clean
   pass/fail table, same shape as Task 1's, and confirm it's now 100%
   pass across the board.
2. Diff the final tip's tree against the `backup-before-rebase-fix`
   branch's tree (`git diff backup-before-rebase-fix HEAD`) — this must
   be **empty**. The whole point of this exercise is fixing history
   shape, not changing the actual delivered content; if this diff is
   non-empty, something was lost or altered during the rebase and needs
   to be found before proceeding.
3. Once confirmed clean, replace whatever branch/ref your prior work was
   on with this corrected sequence, and delete `backup-before-rebase-fix`
   only after you're fully confident (keep it around for a day or two as
   a cheap safety net costs nothing).
4. Update `COMMIT_PLAN.md` (or add a short note to it) recording that the
   baseline commit's file list was corrected to include
   `fallback_report.py`/`measure_der.py`/`ab_upscale_der.py`/
   `test_fallback_visibility.py` from the start, so if this project ever
   needs a similar split again, the lesson (verify every intermediate
   commit as you go, not just the inventory step and the final tip) is
   recorded, not just fixed silently.

---

## Summary Table

| # | Task | Priority | Purpose |
|---|------|----------|---------|
| 1 | Diagnose exact failing commits + root cause | BLOCKING | Know precisely what's broken before touching history |
| 2 | Decide merge vs. reorder | BLOCKING | Pick the correct fix shape |
| 3 | `git rebase -i` surgical fix | BLOCKING (primary path) | Fix history in place |
| 4 | Rebuild from scratch (fallback) | Use only if Task 3 stalls | Same result, simpler mechanics |
| 5 | Verify every commit + diff against backup | BLOCKING | Confirm the fix is complete and lossless |
