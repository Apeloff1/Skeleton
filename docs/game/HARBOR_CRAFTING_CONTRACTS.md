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

## Interactive terminal play

`contract-live --contract-save SAVE --expected-contract-digest SHA` opens
the real movement/crafting/NPC terminal UI with hint, undo/redo and checkpoints.
On earned victory it emits `CONTRACT_EARNED` and a `CONTRACT_SAVE` JSON line;
save that line's JSON payload to continue. A victory with the wrong ending,
insufficient crafting/gathering or missed deadline emits `CONTRACT_REJECTED`
and the ordinary replay checkpoint, without advancing the contract save.
The CLI rejects stale leases before accepting terminal input.

## Bounded contract route solver

`contract-plan --contract-save SAVE` uses the existing bounded canonical
movement, collision, gathering, crafting and delivery solver to propose real
winning actions for the next contract. It returns an earned, source-bound
portable plan and next save only when the complete gameplay replay satisfies
all authored constraints. `contract-verify-plan --contract-plan PLAN`
rebuilds the route and contract continuation. Impossible or unsupported
contract constraints fail closed instead of producing a fake victory.
