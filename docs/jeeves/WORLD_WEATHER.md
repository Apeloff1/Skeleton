# Reviewed deterministic weather — Studio A

Weather is a distinct original-world authoring plane. Authors provide a typed
prompt, one atmospheric description and weather/visibility condition for every
canonical scene, and optional deterministic per-choice overrides. All scene and
choice identifiers are source-bound. No LLM authorship or generated weather
simulation is claimed.

Use `python -m skeleton world-weather --store PRIVATE propose --world-id harbor
--file authored.json` where authored.json contains `prompt`, `scenes` and
`overrides`. Review the returned unapproved proposal, then publish its complete
JSON using `publish --create --expected-digest ignored --file source.json`.
Use `inspect` to obtain its exact digest, `approve --expected-digest DIGEST
--note REVIEW` for operator authorization, then `player --slot SLOT` to
replay the canonical session and `compile --slot SLOT --expected-digest
APPROVED_DIGEST --expected-session-digest SESSION_DIGEST` to produce an
offline CSP-restricted HTML snapshot and a deterministic receipt. `verify`
checks both receipt and compiled bytes against current source/session.
`editor --expected-digest DRAFT_DIGEST` exports an offline HTML draft editor.
The editor cannot approve or publish content.

The typed Jeeves tool `world.weather_propose_preview` is read-only and
returns an unpersisted typed proposal; `world.weather_preview` and
`world.weather_player` inspect custody and replay. Studio Engine may
include the reviewed weather plane as an optional environment handoff,
without claiming native engine execution, device qualification or release.

## Interactive playable handoff

After approving the source, `compile-playable --world-id harbor
--expected-digest APPROVED_DIGEST` emits an offline, CSP-hashed interactive
HTML5 choice graph with original scene prose, visible conditions, choice-specific
weather overrides, earned endings, and restart. `verify-playable --world-id
harbor` independently regenerates the page from approved source and compares
both its SHA-256 receipt and exact bytes. This is a runnable browser player,
not a claim that a native engine has been built or that a device is qualified.

Weather authoring is intentionally separate from world-graph transitions:
conditions never invent a flag, enable an unearned choice, or teleport a player.
The optional Studio Engine recipe carries scene conditions and choice overrides
with source digests; it fails closed on unapproved or stale weather custody.
Node-backed regression fixtures exercise the actual browser JavaScript and
offline editor when Node is available, while Python tests cover authorization,
source replay, receipt tampering and the optional engine manifest.
