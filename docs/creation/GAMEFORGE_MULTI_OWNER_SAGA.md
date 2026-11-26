# GameForge multi-owner saga

The saga composes the generated GameForge narrative campaign, its local
crafting and mission expedition, and two independent recovered gameplay
owners. It does not reimplement those engines or trust demonstration saves
as player progress.

## Authoring and admission

A saga request uses schema `skeleton.gameforge.saga.request.v1` with
`expedition` (the existing expedition source) and `episodes` (one to eight
advanced objective bindings). Each binding has `objective`, `kind`,
`source`, `rules`, and a legal local `witness`.

Supported fixed kinds:

| Owner | Rules | Earned completion |
| --- | --- | --- |
| survey_expedition | survey, weather, dialogue, required_ending | survey, merchant permit, actual required ending |
| convoy_contract | convoy, contracts, choice | successful escort, every required contract, eligibility for authored relief or salvage |

Each binding has its own world state. A second game at an objective is
admitted only after the base expedition exposes that objective's resolve
action. The player remains in the correct generated region. Travel and
dialogue are still checked by the base owners. Local advancement records
explicit `{"type":"episode","objective":"s1","action":{...}}` events. The
required canonical advanced outcome must be earned before an explicit
resolve can advance the outer objective. Local points, credits, reputation,
inventory, energy and bounty remain local and are not converted into
global rewards.

The authoring interface uses schema `skeleton.gameforge.saga.author.v1`
with an independent expedition and `bindings`. It accepts an explicit
survey witness and an optional exactly matching canonical survey package.
Convoy witnesses can come from the existing solver or explicit authored
actions. The generated request, design receipt and empty player genesis
are independently reconstructed. The source chooses the convoy contract
consequence; it is not a new player-choice event in this adapter.

## Commands

All JSON commands consume one bounded JSON document from stdin. The
canonical command is `python -m skeleton gameforge-saga`; the installed
entrypoint is `skeleton-gameforge-saga`.

| Command | Input |
| --- | --- |
| author | author request |
| verify-author | request, composition |
| build | saga request |
| play | request, actions |
| resume | request, receipt, additional |
| verify / verify-play | request, receipt |
| board | request, receipt |
| turn | request, receipt, board_digest, index |
| verify-board | request, receipt, board |
| evidence | request, receipt, objective |
| verify-evidence | request, receipt, evidence |
| assist | request, receipt, optional dialogue_budget/local_budget |
| verify-assist | request, receipt, recovery |
| compare | request, left, right |
| verify-compare | request, left, right, comparison |

The board's authoritative choice indices are zero-based and exact-digest
bound. Survey maps reveal only canonical seen tiles, while local convoy
status reports actual hull, threat, waypoint, tokens and bounty. Full
canonical episode evidence is reconstructed on demand, not embedded in all
checkpoints.

Recovery uses the base expedition planner and independently replays
an exact advanced witness suffix or bounded wait splice. An unmatched
advanced timeline returns no verified continuation, not a proof of
unreachability. Full advanced state-space search is not implemented.
All proposed progress remains unapplied until explicitly executed.

## Persistent application

The same SQLite owner supports an isolated fixed saga namespace with
complete independent saga replay. These commands also require
`--database PATH` in an operator-private directory:

| Command | Fields in addition to request, slot |
| --- | --- |
| create-slot | operation |
| append-slot | expected_revision, operation, additional |
| read-slot / board-slot / assist-slot | optional revision |
| history / snapshot-slot | none |
| fork-slot | parent_revision, expected_digest, child_slot |
| restore-slot | archive |
| turn-slot | expected_revision, operation, board_digest, index |
| apply-recovery-slot | expected_revision, operation, recovery |
| compare-slots | other_slot, optional revision/other_revision |
| evidence-slot | objective, optional revision |

Recovery assistance can additionally accept dialogue_budget/local_budget.
The store uses exact-operation retry, revision CAS, historical forks,
compact full-revision archives and independently replayed restore.
Campaign, expedition and saga records remain isolated even when their
slot names coincide. The same namespace capacity and retention ceilings
apply; signed origin, physical storage and whole-database rollback
protection are outside this guarantee.

An interactive terminal is also installed:

```sh
python -m skeleton gameforge-saga-live --source saga.json --database /private/workspace/saves.sqlite --slot adventure --create
python -m skeleton gameforge-saga-live --source saga.json --database /private/workspace/saves.sqlite --slot adventure
```

Choose a displayed one-based menu number to commit exactly that action.
`list` or `status` refreshes; `hint` is read-only; `quit` or EOF leaves
the last committed revision. Stale writers refresh the menu without
automatically rebasing or replaying an unintended action. Oversized input
aborts rather than treating the trailing bytes as another command.
The source path is explicit; no shell execution or network is introduced.

## Qualification

```sh
python -m pytest -q skeleton/testing/test_gameforge_saga.py skeleton/testing/test_gameforge_expedition.py skeleton/testing/test_gameforge_campaign.py skeleton/testing/test_gameforge_quest_bridge.py skeleton/testing/test_original_quest_cli.py
python -m compileall -q skeleton/app/gameforge_saga.py skeleton/app/gameforge_saga_owners.py skeleton/app/gameforge_saga_board.py skeleton/app/gameforge_saga_author.py skeleton/app/gameforge_saga_store.py skeleton/app/gameforge_saga_cli.py skeleton/app/gameforge_saga_live.py
```

Also run existing survey, weather, dialogue, convoy, contract, mission,
package and journal owner tests, main CLI audit and clean-wheel installation.
The owner reports and repeated full replay may impose significant latency;
physical performance, crash recovery, native Godot, graphical integration,
device/Windows/WSL2, security, Docker/GGUF and release assertions remain
unqualified. No merge/release authorization.
