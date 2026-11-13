# Source-bound NPC evacuation — playable vertical

This vertical extends the canonical offline scene mission director without
replacing its movement, collision, inventory, authored choices, mission DAG or
ending authority. Rescue actions are allowed only for NPCs actually present in
the player's current authored scene and inside their availability window.
Every NPC is unique, carrying capacity is finite, and a late rescue cannot
retroactively revive an expired person.

## Play and inspect

Run `python -m skeleton scene-evacuation demo` to play the original
**Lantern Tide Rescue** scenario. The player pledges to restore the lantern,
collects an earned field bandage, rescues the dock apprentice, retrieves the
brass key, protects the passengers, travels through the guarded gate, rescues
the watch keeper and reaches sanctuary. Only the canonical mission director
can complete the authored `lantern_restored` ending. Two living passengers
then earn 30 base credits plus 12 and 18 NPC-specific rewards.

`python -m skeleton scene-evacuation-board demo` displays legal actions
from the actual reducer, not optimistic suggestions. Each candidate is
applied to a verified checkpoint and rejected if it cannot legally execute.
The board exposes current scene, mission phase, earned supplies, passenger
health, capacity, rescued/lost identities, available actions and digest.

`python -m skeleton scene-evacuation-play demo` produces a player-facing
turn transcript and a final portable checkpoint. For interactive JSON-lines
input use `python -m skeleton scene-evacuation-play live`; each turn prints
the current legal board and checkpoint. Send a JSON action exactly as shown
or type `quit` to preserve the last checkpoint. Nothing is written to disk
implicitly; redirect output or provide the checkpoint explicitly on resume.

## Author and solve

`python -m skeleton scene-evacuation-author demo` edits the watch keeper's
authored reward from 18 to 21. Author edits require an exact expected source
digest and operate on a copy. Only NPC health, reward and time-window fields
can be changed. Revalidation and optional real gameplay preview occur before
the new source is returned; invalid edits publish nothing.

`python -m skeleton scene-evacuation-solve demo` verifies an authored
winning route as a canonical replay witness. Generic route search has
explicit maximum nodes and depth. A budget exhaustion is reported as
`inconclusive`, never as an unwinnable source or successful acceptance.
Hints are untrusted and must independently pass canonical replay.

`python -m skeleton scene-evacuation-accept demo` validates all intermediate
restart checkpoints, exact replay to the same terminal state, earned rewards,
and the portable checksum-bound import/export roundtrip. The portable
checksum detects accidental or adversarial modification but is **not**
an authorization signature. External content still requires provenance and
license checks before publication.

## Data and failure contracts

The `skeleton.scene_evacuation.v1` source has exact fields:
`evacuation_id`, `mission`, `npcs`, `capacity`,
`required_rescues`, `supplies`, `hazards`, `success_endings`,
`base_reward`, `turn_budget` and `schema_version`.
NPCs specify id, scene, initial health, first/last rescue ticks and reward.
Supplies refer only to canonical collected pickup keys; hazards refer only
to authored playable scenes. Every action produces a state digest, replay
receipt, event bus digest and parent-linked save record.

Invalid schemas, duplicate NPCs, missing scenes, out-of-range time windows,
unearned protection, capacity overflow, premature endings, terminal extra
turns, tampered saves and incompatible portable bundles fail closed.
The maximum is 16 NPCs, 16 hazards, 96 turns and 2 MiB of canonical JSON.
No source-supplied executable code, external calls or implicit reward grants
are permitted.

## Regression scope

Focused tests cover legal action enumeration, authored editing, source digest
fences, successful and partial consequences, hazard injury, expired rescues,
capacity, all intermediate restarts, portable tampering, budget exhaustion,
public CLI dispatch and player script acceptance. Release qualification
still requires exact-head CI, security, provenance and consumer-device gates.
