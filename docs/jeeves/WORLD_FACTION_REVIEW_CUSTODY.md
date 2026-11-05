# Faction reputation: durable approval boundary

The faction source store now treats every direct publish as an unapproved
authoring operation, even when the supplied JSON has an `approved: true`
field or was constructed by the pure `approve_factions` helper. Only
`FactionStore.approve` can publish an approved revision; it acquires the
same descriptor-anchored world lock, checks the exact expected digest,
validates the human review note and persists the approved canonical source.
The operator CLI approve action calls that method. Editing or replacing
an approved source revokes approval and invalidates compiled handoff until
renewed review. This closes an input-level authorization bypass without
removing validation or weakening the compiler's approval gate.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_factions.py
skeleton/testing/test_jeeves_world_factions_review_custody.py -q`.
This is a source repair, not an executed test or release certification.
