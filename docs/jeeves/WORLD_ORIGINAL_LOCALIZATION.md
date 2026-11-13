# Reviewed original narrative localization

This Studio A vertical connects original author-supplied translated scene,
choice and ending text to a typed locale proposal, source-leased edits, full
coverage proof, explicit author approval, offline HTML5 language switching,
source-verified player-session replay and deterministic artifact receipts.

Locale identifiers are bounded two-letter language tags with optional
uppercase region. Every locale must translate exactly the world scene IDs,
choice IDs and ending IDs, in canonical order; missing, duplicate or unknown
entries fail closed. Brace placeholders must match the source string.
The system never silently falls back to the source language or represents
copied source text as an AI translation. Author-supplied text is reviewed.
World changes invalidate the digest lease and require retranslation.

CLI: `python -m skeleton world-localization --store DIR propose --world-id
harbor --prompt "Original French edition" --locale-json JSON`. Operator
actions include `save --create --localization-json JSON`, `inspect`,
`edit --expected-digest HASH --operation-json JSON`, `approve
--expected-digest HASH --review-note TEXT`, `editor`, `compile`,
`verify`, `player --locale fr --choices-json JSON`, and `player-slot
--locale fr --slot ID`. Editing always revokes approval. Source custody
uses a descriptor-anchored world lock and digest compare-and-swap.
The browser editor exports unapproved typed JSON for CLI revalidation.

The playable has no network, external scripts or dynamic HTML injection;
all narrative is placed via textContent and the inline script is CSP-hashed.
Receipts bind source and proof digests to the exact playable bytes.
Jeeves tool previews are read-only, including typed author proposals.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_localization.py -q`.
No device or release qualification is claimed.
