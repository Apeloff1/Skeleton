# Offline quest chapter campaign

The chapter campaign composes the existing source-bound quest and expedition
engines into a playable multi-chapter narrative. Each authored chapter has a
distinct quest ID, an ending that unlocks the next chapter, required flags from
earlier chapters, and original rewards. A wrong ending closes the campaign
without manufacturing the next chapter's reward.

Use the canonical CLI:

    python -m skeleton quest-campaign demo
    python -m skeleton quest-campaign simulate --source-json '...' --actions-json '[...]'
    python -m skeleton quest-campaign verify --session-json '...'
    python -m skeleton quest-campaign resume --session-json '...' --actions-json '[...]'
    python -m skeleton quest-campaign export --session-json '...'
    python -m skeleton quest-campaign import --bundle-json '...'

The demo plays Lantern Harbor's beacon and night-watch chapters using the
canonical quest and tactical arena runtime. The campaign journal contains
ordered, normalized quest actions and transitions. Every checkpoint and
portable bundle is verified by reconstructing all actions from the source,
including NPC choices, earned crafting, combat rewards, endings and unlocks.

## Source contract

The v1 campaign source requires schema_version, world_id, campaign_id and
chapters (one through four). Every chapter requires id, quest, required_ending,
requires_flags and grants_flags. Quest sources use the existing
skeleton.expedition_quest.v1 contract. Required endings must exist in their
quest source. Unlock flags must have been granted by earlier chapters. A flag
can be granted only once, and all quests must belong to the campaign world.

The session is capped at 96 campaign actions and 2 MiB of canonical JSON.
The authored source is capped at 128 KiB. Unsupported fields, duplicated IDs,
invalid unlock dependencies, tampered action receipts, altered save lineage,
forged rewards, and noncanonical payloads fail closed.

A SHA-256 digest detects corruption but does not prove who authored a source.
Host applications must independently authenticate the source, authorize the
player, and protect their own save storage. Export/import never executes
untrusted code and never contacts a remote provider.

The acceptance suite covers full demo play, split resume equivalence,
alternate endings, unauthorized rewards, source validation, portable replay
integrity and canonical CLI dispatch. No on-device or hosted release
qualification is implied by the source contract alone.
