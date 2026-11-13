# Original rumor propagation and causal NPC knowledge

The rumor network is distinct from authored testimony: testimony records
what a witness says at a specific scene, while rumor propagation tracks which
characters learn a claim, through real choices and authored encounter routes.

A typed rumor has an original claim, stance, source NPC, initiating choice,
and authored text. A transfer route names the informed sender, recipient,
specific arrival scene and causal choice. Both NPCs must be present at the
transfer scene. Transfers use the knowledge state *before* the choice, so a
rumor cannot cross two hops in one transition. Seed and transfer witnesses
must be reachable in bounded exhaustive replay. Conflicting stances about
one claim cannot coexist in one NPC's knowledge in any reachable state.
Alternative mutually exclusive branches remain representable.

Authoring is source-leased to the canonical world and cast. A proposal is
unapproved. The operator CLI `python -m skeleton world-rumors --store DIR`
offers propose, inspect, save, edit, approve, editor, compile, verify, player,
and player-slot. All mutations use a descriptor-anchored world lock, digest
compare-and-swap and explicit approval. Editing revokes approval. The offline
editor exports unapproved typed JSON for canonical CLI revalidation; it does
not write to the store or grant authority. The CSP-hashed HTML5 player uses
textContent, has no network permissions and follows the same one-hop rules.
Receipts bind world/cast/rumor/proof digests and exact playable bytes.
Jeeves preview tools are read-only, including source-derived session replay.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_rumors.py -q`.
No device, consumer, production or release qualification is asserted.
