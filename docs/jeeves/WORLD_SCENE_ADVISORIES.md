# Source-leased scene advisories

This Studio A vertical connects an original-world prompt to typed per-scene
advisory categories, safe summaries, explicit author review, durable source,
player-session replay, and a CSP-restricted HTML5 handoff.

`python -m skeleton world-advisories --store PRIVATE propose --world-id beacon --file request.json`
accepts a bounded JSON object with `prompt` and `entries`. Every canonical
scene must have exactly one entry. Each entry has `scene`, sorted unique
`categories` (conflict, fear, flashing, grief, loud_audio, romance, violence)
and a nonempty `safe_summary`. This is original author-supplied text, not a
claim that an LLM independently generated or classified content.

The operator uses `publish --create --file source.json --expected-digest LEASE`
(the digest argument is required by the CLI but ignored on create), then
`approve --expected-digest LEASE --note REVIEW`. A subsequent edit requires
the current digest, resets approval, and must be reviewed again.

`player --slot player` masks a scene whose categories have not all been
accepted. Repeating `--accept fear` and other category arguments is explicit
per-request opt-in, not a persistent account preference. `compile` requires
both the approved advisory source digest and exact player session digest.
`verify` independently regenerates and compares the receipt and HTML.
The editor exports an unapproved draft for CLI revalidation.

This feature does not modify the underlying gameplay transition engine,
persist player consent, enforce age verification, certify content suitability,
or claim device/release qualification. Any embedding game runtime must honor
the advisory view rather than displaying unmasked canon directly.
