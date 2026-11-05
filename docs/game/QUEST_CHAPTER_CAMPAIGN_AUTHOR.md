# Chapter campaign authoring and compatibility

Use the canonical offline builder:

    python -m skeleton quest-campaign-author demo
    python -m skeleton quest-campaign-author edit --source-json '...' --operations-json '[...]' --expected-digest '<sha256>'
    python -m skeleton quest-campaign-author verify --receipt-json '...'
    python -m skeleton quest-campaign-author compatibility --receipt-json '...' --session-json '...'

An edit batch is an optimistic transaction against the canonical source digest.
The builder applies operations only to a detached copy, validates the complete
resulting campaign, optionally plays a deterministic preview, and emits a
replayable receipt. Supported operations are append_chapter,
remove_last_chapter, set_required_ending, set_required_flags,
set_granted_flags and replace_quest. All operations use authored data only.

An invalid quest, unearned unlock, duplicate reward, mismatched world, stale
digest, invalid operation, oversized payload or no-op transaction fails closed.
The receipt binds the old and new sources, normalized operations, source
digests and optional gameplay preview. It is not an authorship signature.

Compatibility checks compare verified saved sessions to the edited source.
An edited source cannot silently resume an older checkpoint; the user must
start a new campaign from that authored revision. The host application remains
responsible for player authorization, storage isolation and source provenance.
