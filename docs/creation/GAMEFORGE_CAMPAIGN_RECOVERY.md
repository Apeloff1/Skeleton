# GameForge campaign recovery, player board and portable checkpoints

The recovered narrative campaign now has a read-only player board, legal
action selection, deterministic completion assistance, alternate timeline
comparison and historical SQLite forks. All operations reuse the canonical
quest and dialogue engines.

## Commands

Use the existing installed `skeleton-gameforge-campaign` command or
`python -m skeleton gameforge-campaign`. Each command reads one JSON object
from stdin, and writes JSON to stdout except `html`, which writes an inert
standalone HTML player board.

| Command | JSON fields |
| --- | --- |
| board | request, receipt |
| verify-board | request, receipt, board |
| turn | request, receipt, board_digest, index |
| assist | request, receipt, optional max_expansions |
| verify-assist | request, receipt, assistance |
| compare | request, left, right, optional max_expansions |
| verify-compare | request, left, right, comparison |
| html | request, receipt |
| export-session | request, receipt |
| import-session | request, handoff |
| fork-slot | request, slot, parent_revision, expected_digest, child_slot |

The last command requires `--database PATH` pointing to the existing
operator-private SQLite workspace.

The board provides the current generated region, adjacent regions, nearby
NPC text, current reputation, earned grants, objective states, earned
reward totals and the actual legal actions. The index passed to `turn`
is zero-based and bound to the exact board digest. It advances one
explicit legal action only, returning the resulting receipt and board.
An outdated digest or a noninteger index is rejected.

HTML is a static offline report, not a browser-native runtime or editor.
Authored text is escaped; a restrictive CSP denies scripts, external
resources and forms. Run the CLI to enact legal choices.

## Completion search

The authored design witness is not a general-purpose recovery plan: a
player may have taken different choices. Assistance therefore starts
from independently replayed current dialogue and quest states. It checks
remaining objective grants, searches legal authored conversation choices
for a terminal ending satisfying all required grants per NPC, routes on
the generated region graph, and verifies every proposed action by
appending the entire plan through the canonical campaign owner.

Search retains choice suffixes instead of copying large saved traces.
The visited key includes the dialogue node, flags, grants, reputation,
phase and step count. Step count matters for the owner's finite
conversation budget. The search is deterministic and bounded to 4096
expansions; the default is 1024. The route planner uses sorted graph
adjacency. It is not a global shortest-path optimizer across all
objectives, conversations and regions.

Result statuses:

- completion_witness: the proposed suffix actually completes the canonical
  campaign on independent replay.
- already_completed: no action is needed.
- dialogue_unreachable: the identified required conversation cannot reach
  a granting ending from its current state under the finite authored model.
- budget_exhausted: exploration stopped at its resource limit; no claim of
  impossibility.
- action_budget_exhausted: the proposed suffix would exceed the campaign
  action ceiling; no claim that every possible route is too long.

No proposed moves are applied automatically. A decline can leave an
authored branch stranded; recovery requires a separate historical fork
rather than editing the existing action log.

## Branch recovery

Example: create an independent slot from historical revision 1, supplying
the exact known session digest of that revision.

```sh
python -m skeleton gameforge-campaign fork-slot --database campaign-workspace/save.sqlite < fork.json
```

The new slot receives the verified genesis-to-selected-revision prefix,
including its operation identities scoped to the new slot. Every copied
receipt is independently replayed. Both capacity accounting and the
entire copy run inside one SQLite write transaction. A wrong digest, bad
historical row, exhausted quota or preexisting destination rejects the
fork; the original slot is not changed. The new slot can subsequently
advance separately. The returned fork origin is a transaction observation,
not cryptographically authenticated durable ancestry. No automatic retry
of a fork is inferred if the child already exists.

Branch comparison independently replays both checkpoints under the same
request and shows their longest common action prefix, first divergence,
objective changes, rewards, reputation and scoped completion assistance.
No branch is merged into another and no progress is fabricated.

## Portable handoff

Export includes the original request, player receipt and board digest.
Import requires a separately trusted request, byte-identical source,
and complete re-execution and canonical equality of the envelope.
An imported handoff is not a signed artifact, identity certificate,
or cross-device attestation. It returns a verified checkpoint; it
does not silently write a local save slot.

## Qualification boundary

Run the campaign, quest bridge, original quest, dialogue and conductor
regression suites and compile all newly integrated application modules.
Then run the canonical CLI audit, clean wheel install, independent
process-loss/storage tests, and final-head mandatory CI. Native Godot
execution, backend/UI deployment, device, Windows/WSL2, Docker, GGUF,
security and release qualification remain independent. This work adds
abstract, source-bound gameplay and actual player-directed CLI actions,
not a native engine or browser-playable executable.
