# Combat campaign authoring (offline, source-bound)

Use `python -m skeleton combat-campaign-author demo` to edit an original
Lantern Harbor encounter and preview a full canonical combat campaign.
The command returns the canonical authored source, exact source digests, a
verified full combat session (including per-encounter save lineage), and a
replay-derived receipt. The preview is a gameplay result, not a promise that
every authored campaign is winnable.

To edit your own campaign, start from `combat-campaign demo` or supply a
canonical campaign source and compute its canonical digest with
`skeleton.game.gameplay.flgb_gameplay_runtime.dig(normalize_campaign(source))`.
Call `combat-campaign-author edit --source-json '<source>' --operations-json
'<edits>' --expected-digest '<sha256>'`. Edits are a nonempty JSON array of
at most 24 operations. Supported kinds are `set-reward` with
`encounter_id,value`, `set-turn-limit` with `encounter_id,value`, and
`set-foe-stat` with `encounter_id,actor_id,stat,value`; allowed foe stats
are max_hp, attack, defense and speed. Every edit rejects unknown IDs, hero
changes, no-ops, unsupported fields, invalid integers and out-of-budget
values. The transaction does not mutate its caller's source.

Run `combat-campaign-author verify --source-json '<original-source>'
--receipt-json '<authoring-result>'` to independently reapply every edit,
replay the canonical combat engine and compare the entire result, including
save lineage and exported state. The authoring receipt is an integrity check,
not an authentication signature: externally trusted publication still
requires application authorization and provenance checks. CLI inputs and
exports are capped at 128 KiB and reject duplicate JSON keys.
