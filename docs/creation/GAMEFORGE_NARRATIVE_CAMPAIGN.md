# Recovered GameForge campaign and revision journal

The campaign joins the archived authored dialogue graph and save replay to the
existing seven-stage GameForge world/quest bridge. Neither subsystem is
reimplemented. A quest objective can require a specific grant earned in a
specific NPC conversation, itself bound to the generated world ID and region.

## Request

The exact schema is `skeleton.gameforge.campaign.request.v1`. Provide
`quest_request` (the existing GameForge quest request) and `dialogues` (a
bounded list). For example, using the quest request from
GAMEFORGE_QUEST_BRIDGE.md with a keeper placed in region r00, the historical
lantern harbor dialogue fixture can be integrated as follows:

```python
import json
from pathlib import Path

quest = json.loads(Path("request.json").read_text(encoding="utf-8"))
quest["quest"]["npcs"]["keeper"] = "r00"
dialogue = json.loads(Path(
    "skeleton/testing/fixtures/dialogue_original_lantern_harbor.json"
).read_text(encoding="utf-8"))
campaign = {
    "schema": "skeleton.gameforge.campaign.request.v1",
    "quest_request": quest,
    "dialogues": [{
        "npc": "keeper",
        "source": dialogue,
        "gates": {"s0": "restore-western-lens"},
        "witness": ["listen", "promise-repair"]
    }]
}
Path("campaign.json").write_text(json.dumps(campaign), encoding="utf-8")
```

The conversation must have the same generated world ID and its authored
witness must reach a real ending which grants every bound quest ID.
Conversation sources and grant mappings are independent authored inputs,
not inferred from caller-provided checkpoints. The witness is never
auto-applied to a player session.

## Operator interface

`python -m skeleton gameforge-campaign` and the installed
`skeleton-gameforge-campaign` command both accept one JSON document on stdin.

| Command | Fields |
| --- | --- |
| build | Campaign request itself |
| verify | request, receipt |
| play | request, actions |
| verify-play | request, receipt |
| resume | request, receipt, additional |
| create-slot | request, slot, operation |
| append-slot | request, slot, expected_revision, operation, additional |
| read-slot | request, slot, optional revision |
| history | request, slot |

The last four commands also take an explicit operator-owned
`--database PATH` argument, never a path derived from JSON. Use a private
local directory (0700 on POSIX), and a dedicated SQLite database.

```sh
mkdir -m 700 campaign-workspace
python -m skeleton gameforge-campaign build < campaign.json > design.json
python -c "import json;print(json.dumps({'request':json.load(open('campaign.json')),'slot':'harbor','operation':'create-1'}))" | python -m skeleton gameforge-campaign create-slot --database campaign-workspace/save.sqlite
python -c "import json;print(json.dumps({'request':json.load(open('campaign.json')),'slot':'harbor','operation':'play-1','expected_revision':0,'additional':json.load(open('design.json'))['witness']}))" | python -m skeleton gameforge-campaign append-slot --database campaign-workspace/save.sqlite
python -c "import json;print(json.dumps({'request':json.load(open('campaign.json')),'slot':'harbor'}))" | python -m skeleton gameforge-campaign history --database campaign-workspace/save.sqlite
```

An explicit dialogue action has fields type=dialogue, npc and choice.
The canonical authored dialogue engine checks prerequisites and ending
transitions. Movement must follow adjacent regions and objectives use
the base quest runtime. A grant from another NPC or an unfinished
conversation is not sufficient. Choosing a terminal branch without a grant
can strand a required objective; this is a legitimate authored dead end,
not automatic permission to bypass the gate. A new slot is the restart
boundary. Native game rendering is not performed.

## Durable storage semantics and bounds

- Each slot starts at revision zero with an empty action ledger.
- Appends check the expected revision under BEGIN IMMEDIATE, verify the
  prior checkpoint independently, then atomically insert the next revision
  and update the head. A failed action does not commit a revision.
- Repeating the same operation identity and exact request returns its
  original revision even after subsequent successful appends. Rebinding
  an identity to other input is rejected.
- Historical reads check the requested revision and its predecessor.
  The history command audits the entire retained chain from genesis.
- Limits: 128 slots, 256 revisions per slot, 32 MiB of logical receipts
  per slot, 256 MiB total, individual canonical documents <= 2 MiB,
  16 conversations, 128 choices per conversation and 8192 campaign actions.
  Physical SQLite overhead, journal space, disk quota and backup sizes
  are not proven by these logical bounds.
- The original request must be retained independently by the operator.
  Local digests do not authenticate an attacker-controlled source or protect
  against wholesale rollback/replacement of the database by its owner.
- Private local directory and existing-file checks reject observable
  symlinks, hardlinks and reparse points. Same-owner pathname races,
  hostile filesystems, encryption, Windows ACL enforcement and physical
  power-loss qualification are outside the implemented guarantees.
- The journal is local to one trusted operator, not a multi-tenant server
  or distributed database.

## Qualification

```sh
python -m pytest -q skeleton/testing/test_gameforge_campaign.py skeleton/testing/test_gameforge_quest_bridge.py skeleton/testing/test_original_quest_cli.py skeleton/testing/test_dialogue_session.py skeleton/testing/test_original_quest_slice.py skeleton/gameforge/test_gameforge_conductor.py
python -m compileall -q skeleton/app/gameforge_campaign.py skeleton/app/gameforge_campaign_cli.py skeleton/app/gameforge_campaign_store.py
python -m skeleton capabilities --main-cli-audit
```

Require clean-wheel install, actual process-termination/restart tests,
independent security review and exact-head mandatory CI. No merge or
release authorization. The browser, backend, native Godot, GGUF,
device and Windows/WSL2 evidence remain separate.
