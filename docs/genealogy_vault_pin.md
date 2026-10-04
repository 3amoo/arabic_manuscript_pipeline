# Genealogy Vault — External Dependency Pin

The Phase 1 base-letter corrector (`scripts/vault_vote_correct_names.py`
via `scripts/genealogy_crossref.py`) cross-references the OCR output
against a **separate, actively-maintained Obsidian vault**. This project
depends on that vault for:

- the canonical spellings the corrector applies (Phase 1),
- the review queue rows that fed those decisions (Group D),
- the GT-verification gate's rare-word index lives on the hand
  transcription instead, but the two are siblings — the vault's verse
  files and the GT are the same poem).

An unpinned external dependency this central is a real risk: if the
vault's files change or move, every Phase 1 correction's evidence chain
points at nothing. This file closes that risk.

## The pin

| field | value |
|---|---|
| path | `/home/omar/Desktop/Obsidian/علم شرعي/علم الأنساب` (the `DEFAULT_VAULT` constant in `scripts/genealogy_crossref.py`) |
| files | 11 markdown, 172 KB, no subdirectories |
| snapshot hash | `a3ee796507873d4546af0e6d7bec0505bdbb982d36a122053c870dec01660a72` |
| pinned | 2026-09-22 |
| re-verified | 2026-10-02 — vault drifted from the pinned hash (`7e92a8e6...`), same 11 files, 168 -> 172 KB. See "Drift audit (2026-10-02)" below |

The snapshot hash is `sha256sum *.md | sort | sha256sum` — the same
composition `verify_all.py` uses for the evidence invariant, so the
check is mechanically identical, not a hand-written digest.

## How to verify (and what a mismatch means)

```bash
cd "/home/omar/Desktop/Obsidian/علم شرعي/علم الأنساب" \
  && sha256sum *.md | sort | sha256sum | cut -d' ' -f1
```

Compare against the hash above.

- **Match** — the vault is unchanged; every Phase 1 correction's vault
  evidence still points at the text it was verified against.
- **Mismatch** — the vault moved on. This is not a pipeline failure:
  the vault is a living project and its changes are usually genuine
  corrections. But it means the vault evidence behind the applied
  corrections is stale, so the reviewed rows
  (`logs/vault_review_56.jsonl`) and the applied corrections
  (`logs/vault_vote_corrections.jsonl`, 8 skeletons / 29 token fixes)
  should be re-run: `scripts/vault_vote_correct_names.py --review` and
  re-apply. The GT gate (Task 4) will still hard-block anything the
  ground truth contradicts, so the verified tier cannot silently rot.

## Why a pointer and not a copy

The vault is a personal Obsidian project with its own workflow. Copying
it in would fork it: the vault stays the source of truth and this file
is the contract between the two projects. If the vault ever becomes
unreachable, the snapshot below is the fallback record of what the
corrections were verified against.

## Snapshot — per-file hashes (2026-09-22)

```
38f847765876ec0aed534025e4df3d343914c10f11a2d8cad7dac4121e81697b  خارطة العرب.md
468c516389c4be49589f195436c7f814288bb8f906901b7d287b1f14ad545a25  02  نسخة المذاكرة (5).md
510c9805cad277ce68ae19b6ad9b46e6535adb4385f1f458616cd2a0c7093a3f  03 الأبيات من 201 حتى 300.md
58cdf62373dc36870bf72b4df608176460ff63546cbdc176a35842b4e7aa72d2  02  نسخة المذاكرة (1).md
68ec0b6534e97a01996f515292bc3fe0c76c8fd4ec0f965b14859b427f8458ae  02  نسخة المذاكرة (3).md
6e6993ddd7df947e0d7e4e6e1253cbe3c04be533459831662a6d08a0ac532d17  01 الأبيات من 1 حتى 106.md
89f7d8ebd0fda1d13011de1b1f5f3a759155b06877e79b887094216c9c68c6da  01 علم الأنساب الصغير - مختصر للمبتدئين (يوتيوب).md
b1d7a7284bdb47006c38a1d94db80aab07df906c3c9f827d127245532594bcc0  02  نسخة المذاكرة (4).md
dbf784b3fb5076e62798a393b69d6f4586a48f9ad40fafb14127c6150268a4bd  02 الأبيات من 107 حتى 200.md
e7a6cf002f90c4b887bd4563d7e0920654f17cf20c9c3c46ab42867703d14f00  02  نسخة المذاكرة (2).md
eee485c30898ebb5b14c0b4e4ed29e3ad87acdc482d77884f984cae449ab416e  00 الشاتات كلها.md
```

## Drift audit (2026-10-02)

The vault **has** moved since the original pin: the hash changed from
`7e92a8e6...` to `a3ee7965...`, with the same 11 files growing 168 -> 172 KB
(content edits, no additions or deletions). This is the scenario the pin was
written for, so the impact was audited rather than assumed.

**What was checked:** the 8 skeletons corrected by Phase 1
(`logs/vault_vote_corrections.jsonl`), re-counted against the current vault
index (`genealogy_crossref.py --report` re-runs cleanly: 267 skeletons).

| corrected to | attestations at apply time | now | verdict |
|---|---|---|---|
| عمرو | 11 | 11 | unchanged |
| كعب | 21 | 21 | unchanged |
| سعد | 12 | 12 | unchanged |
| عامر | 18 | 18 | unchanged |
| وهب | 5 | 5 | unchanged |
| هشام | 1 | 1 | unchanged, single-attested |
| عثمان | 1 | 1 | unchanged, single-attested |
| نوفل | 1 | 1 | unchanged, single-attested |

All 8 corrected forms still exist as vault skeletons — the drift did not remove
any name the corrections depend on. Five are unchanged in count; three
(`هشام`, `عثمان`, `نوفل`) remain at **1 attestation**.

**Why those three still stand.** They were human-accepted in
`logs/vault_review_56.jsonl` with reasons that do not depend on the vault count:
`مشام -> هشام` ("not an Arabic word; target هشام بن عبد الملك"), `عمان ->
عثمان` ("target is the city Amman vs the caliph عثمان; dotting slip"), and
`نوقل -> نوفل` ("ق/ف dotting slip; target نوفل بن الحارث"). Each identifies
the historical figure and the specific OCR defect. A `review_accepts()` human
override is what let them past the `MIN_VAULT_EVIDENCE = 2` guard in the first
place (`vault_vote_correct_names.py:341`), so the low count was known and
deliberate, not an oversight.

**None of the three has any ground-truth support** — `هشام`, `عثمان`, and
`نوفل` appear in zero of the 620 GT verses (the GT's single `عمان` is
`النعمان` in v250, a different word). They rest on the human's reading plus one
vault attestation. That is weaker evidence than the other five, and it should be
said plainly rather than left implicit in a count.

**No action taken.** The corrections were human-accepted on substantive grounds,
the corrected forms are still attested, and reverting them would restore forms
the human judged to be OCR defects. But the three single-attested corrections
are the ones to revisit first if the vault ever contradicts them, and this
section is the record of that.
