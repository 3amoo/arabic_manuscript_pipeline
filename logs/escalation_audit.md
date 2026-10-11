# Escalation hallucination audit

Review-only. This is a finding list for a human; it changes nothing
in the corpus. See `scripts/escalation_audit.py`.

- input: `data/output/عمود النسب نسخة /escalations.jsonl`
- rows scanned: 1
- accepted (scored): 1
- accepted but no backend text (skipped): 0
- not accepted (already gated, unscored): 0
- **flagged for review: 0**
- flag threshold: normalized CER > 1.00 (edit distance exceeds the whole OCR text length)

## No rows flagged

Every accepted escalation agrees with the OCR text it replaced
at the character level better than the hallucination threshold.
This is a snapshot, not a guarantee - re-run after any pipeline
run that produces new escalations.

## All accepted rows, scored

| page | region | normalized CER | verdict |
| --- | --- | --- | --- |
| 43 | verse_right | 0.30 | ok (agrees with OCR) |
