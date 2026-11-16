# GameForge expedition — recovered local playable engine

This bridge joins an existing generated GameForge campaign to the original
Lantern Quay grid, crafting, moving merchant, delivery and consequence
engine. It does not create another crafting or dialogue engine.

An independently authored binding selects a generated quest objective, a
local game source, a required earned ending and an example witness. The
campaign and harbor engines both have to accept the combined witness
before a design receipt can be issued. A design witness is not awarded
to a player.

## Source contract

Use the existing campaign request from GAMEFORGE_NARRATIVE_CAMPAIGN.md.
Bind one to eight local episodes to distinct generated objective IDs:

```python
import json
from pathlib import Path
from skeleton.game.gameplay.harbor_crafting import demo_actions

campaign = json.loads(Path("campaign.json").read_text(encoding="utf-8"))
local = json.loads(Path(
    "skeleton/game/gameplay/fixtures/harbor_lantern_quay.json"
).read_text(encoding="utf-8"))
request = {
    "schema": "skeleton.gameforge.expedition.request.v1",
    "campaign": campaign,
    "episodes": [{
        "objective": "s0",
        "source": local,
        "required_ending": "beacon",
        "witness": demo_actions()
    }]
}
Path("expedition.json").write_text(json.dumps(request), encoding="utf-8")
```

A second episode may use the same authored local map; its ledger, inventory,
coins, merchant stock and terminal outcome remain distinct. Every binding
requires its own replay witness. A beacon ending is not interchangeable with
a safe-harbor ending.

## Installed interface

Use `python -m skeleton gameforge-expedition` or the installed console
script `skeleton-gameforge-expedition`. Commands consume bounded JSON on
standard input and return JSON to standard output.

| Command | Input |
| --- | --- |
| build | Expedition request |
| play | request, actions |
| resume | request, receipt, additional |
| verify | request, receipt (design) |
| verify-play | request, receipt (session) |
| board | request, receipt |
| verify-board | request, receipt, board |
| turn | request, receipt, board_digest, index |
| evidence | request, receipt, objective |
| verify-evidence | request, receipt, evidence |

The outer campaign retains its legal move, dialogue and resolve events.
A local event is an explicit object:

```json
{"type":"harbor","objective":"s0","action":{"op":"move","direction":"east"}}
```

A local event is legal only at the active objective's generated region
and after meeting its required authored dialogue grant. The existing
harbor engine controls collision, walking, resource depletion, inventory,
crafting, merchant interactions, delivery and unlocked endings. The
local game pauses when the player leaves its region, preserving its
own deterministic tick count; no passage of wall-clock time is asserted.

The canonical outer objective still requires a separate explicit resolve
event after local victory. Skipping the episode, forging an inventory,
resolving an out-of-order objective or submitting a different ending
cannot grant rewards. An alternate earned ending may strand the branch.
The operator may independently replay a prior action prefix to start
a different branch; no prior receipt is modified.

## Player board

The board projects only the combined legal actions, suppressing outer
resolve events while their episode gates are unsatisfied. Each episode
includes its grid, tick budget, resources, inventory, merchant stock,
coins, delivery and ending. Grid symbols are # blocked, . floor,
R resource, D dock, M merchant and @ player. Occupants overlay tiles.
The turn command chooses one zero-based legal action under the exact
board digest and returns a new receipt and board. Stale digests are rejected.

## Source-bound evidence and limits

The integrated replay independently checks each local harbor bundle and
compares its state with every applied local step. The evidence command
exports that canonical bundle together with the exact expedition source
and player checkpoint identities. Verification rebuilds the evidence
using an independently supplied request and checkpoint. It does not
trust a self-declared checksum, coin balance, delivered flag or ending.

The limits are eight episodes, at most 256 ticks per local episode,
8192 combined actions and the shared canonical JSON ceiling. The
owner's own harbor-bundle byte ceiling remains in force. These bounds
do not establish physical performance or storage capacity.

The existing campaign SQLite journal accepts campaign receipts, not
these stronger expedition receipts; expedition durability and persistent
branch management require a separate integration. This command performs
no automatic database writes, native rendering, model calls, network
requests, engine export or release.

## Qualification

```sh
python -m pytest -q skeleton/testing/test_gameforge_expedition.py skeleton/testing/test_gameforge_campaign.py skeleton/testing/test_gameforge_quest_bridge.py skeleton/testing/test_original_quest_cli.py skeleton/testing/test_dialogue_session.py skeleton/gameforge/test_gameforge_conductor.py
python -m compileall -q skeleton/app/gameforge_expedition.py skeleton/app/gameforge_expedition_board.py skeleton/app/gameforge_expedition_cli.py
python -m skeleton capabilities --main-cli-audit
```

Also run the existing harbor-engine suite, clean-wheel installation and
installed expedition command, exact-head mandatory CI and independent
device/security checks. Native Godot, Windows/WSL2, backend/UI, GGUF,
Docker, physical storage and signed release remain separate boundaries.
No merge or release authorization.
