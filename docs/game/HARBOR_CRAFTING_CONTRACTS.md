# Lantern Quay playable delivery contracts

The original authored contract board in `fixtures/harbor_lantern_quay_contracts.json`
binds to the canonical Lantern Quay world. Each ordered delivery contract is
earned by actual movement, gathering, crafting, NPC trading, delivery and ending
actions. Deadlines, activity requirements, coins, reputation and distinct
consequences are independently replayed. A claimed score never grants success.

Run `python -m skeleton.game.gameplay.harbor_crafting_cli contract-init
--contracts PATH` to produce a portable initial save. Use `contract-next
--contract-save SAVE` for the next playable objective. Use `contract-play
--contract-save SAVE --actions ACTIONS --expected-contract-digest SHA` to
execute the canonical game and emit the next save; `contract-append` accepts
an independently replay-verified gameplay bundle. `contract-verify` checks
every replay and source digest. Save each command's JSON stdout as the new
portable checkpoint. Invalid actions, stale leases and forged outcomes fail
without a partial save.

Transactional source-bound authoring uses `contract-author --contracts BOARD
--contract-edits EDITS --expected-source-digest SHA --expected-contract-digest
SHA` followed by `contract-verify-author --contract-revision REVISION`.
Allowed edits are bounded order constraints, never executable source code.
Digests are replay integrity checks, not identity signatures or authentication.
No device, consumer installer or release certification is asserted.
