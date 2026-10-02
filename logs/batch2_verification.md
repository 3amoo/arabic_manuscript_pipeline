# Batch-2 programmatic verification — crop pairing vs all GT verses

METHOD. For each crop, OCR it fresh, then score EVERY gold verse
on that page by how many of its distinctive words (>=4 skeleton
chars) appear as near-match substrings of the crop OCR. Word
matching is substring-based because PaddleOCR concatenates words
on these bands (وضح+يسترة -> وضحيسترة).

A crop is PAIRING-OK when the aligned verse (from
logs/review_batch_2.md) is the top scorer AND beats the
runner-up by >= 0.15 — the alignment is then the unique best
explanation of the crop. WEAK = the aligned verse still wins but
the margin is thin; a human should glance at it.

This is a pairing check only. Full_line still requires you to
read the crop image, per the conservative rule.

| crop | pg | aligned GT# | top score | runner-up | margin | verdict |
|------|----|-----------|-----------|-----------|--------|---------|
| p036_02.png | ٣٦ | ١٧٥ | ١٧٥ (0.50) | ١٧٤ (0.17) | 0.33 | PAIRING-OK |
| p037_00.png | ٣٧ | ١٨٧ | ١٨٧ (0.43) | ٢٠٠ (0.00) | 0.43 | PAIRING-OK |
| p037_04.png | ٣٧ | ١٩١ | ١٩١ (0.17) | ٢٠٠ (0.00) | 0.17 | PAIRING-OK |
| p038_03.png | ٣٨ | ٢٠٤ | ٢٠٤ (0.25) | ٢٠٧ (0.17) | 0.08 | WEAK |
| p038_05.png | ٣٨ | ٢٠٦ | ٢٠٦ (0.33) | ٢١٣ (0.00) | 0.33 | PAIRING-OK |
| p039_09.png | ٣٩ | ٢٢٢ | ٢٢٢ (0.67) | ٢٢٨ (0.00) | 0.67 | PAIRING-OK |
| p040_01.png | ٤٠ | ٢٣٠ | ٢٣٠ (0.67) | ٢٣٧ (0.33) | 0.33 | PAIRING-OK |
| p040_03.png | ٤٠ | ٢٣٢ | ٢٣٢ (0.80) | ٢٣٦ (0.17) | 0.63 | PAIRING-OK |
| p040_08.png | ٤٠ | ٢٣٦ | ٢٣٦ (0.33) | ٢٣٩ (0.20) | 0.13 | WEAK |
| p042_02.png | ٤٢ | ٢٦١ | ٢٦١ (0.67) | ٢٦٨ (0.20) | 0.47 | PAIRING-OK |
| p042_08.png | ٤٢ | ٢٦٧ | ٢٦٧ (0.83) | ٢٦٨ (0.20) | 0.63 | PAIRING-OK |
| p043_07.png | ٤٣ | ٢٨١ | ٢٨١ (0.33) | ٢٨٣ (0.17) | 0.17 | PAIRING-OK |
| p044_05.png | ٤٤ | ٢٩٥ | ٢٩٥ (0.50) | ٣٠٤ (0.00) | 0.50 | PAIRING-OK |
| p044_07.png | ٤٤ | ٢٩٧ | ٢٩٧ (0.67) | ٣٠٤ (0.00) | 0.67 | PAIRING-OK |
| p044_08.png | ٤٤ | ٢٩٨ | ٢٩٨ (0.60) | ٣٠٤ (0.00) | 0.60 | PAIRING-OK |
| p044_10.png | ٤٤ | ٣٠٠ | ٣٠٠ (0.71) | ٢٩٦ (0.17) | 0.55 | PAIRING-OK |
| p045_09.png | ٤٥ | ٣١٤ | ٣١٤ (0.57) | ٣١٥ (0.20) | 0.37 | PAIRING-OK |
| p048_07.png | ٤٨ | ٣٥١ | ٣٥١ (0.33) | ٣٥٠ (0.17) | 0.17 | PAIRING-OK |

PAIRING-OK: 16 / 18
WEAK (thin margin, glance before confirming): p038_03.png, p040_08.png
