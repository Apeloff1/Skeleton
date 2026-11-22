# GameForge expedition durability, authored packages and mission recovery

This integration joins the previously recovered narrative campaign, the
existing Lantern Quay game and mission owners, canonical local package
distribution, and the shared transactional revision journal.

## Source contracts

The expedition request retains the existing explicit local binding fields:
objective, source, required_ending and witness. Mission-based episodes add
both mission_board and required_missions; neither is accepted alone.

The board is validated against the exact local world. Required IDs must
exist in the board, and the original authored witness must earn all of
them. An ending with an expired or unfulfilled required mission is not a
completed outer objective. The original dependency and deadline semantics
are unchanged: a dependent mission only starts counting after its
prerequisites were complete at the beginning of that transition.

Campaign rewards and mission points have distinct units and authorities.
The local board and episode evidence expose the actual completed missions,
progress, points and report digest. No points are converted to campaign
currency and no reward is conferred before the explicit outer resolve.

## Attach a recovered playable distribution

Use the new expedition authoring request to bind local packages without
pretending their demo is a player's saved progress:

```python
import json
from pathlib import Path

campaign = json.loads(Path("campaign.json").read_text(encoding="utf-8"))
fixtures = Path("skeleton/game/gameplay/fixtures")
world = json.loads((fixtures / "harbor_lantern_quay.json").read_text(encoding="utf-8"))
missions = json.loads((fixtures / "harbor_lantern_quay_missions.json").read_text(encoding="utf-8"))
source = {
    "schema": "skeleton.gameforge.expedition.author.v1",
    "campaign": campaign,
    "bindings": [{
        "objective": "s0",
        "world": world,
        "mission_board": missions,
        "choice": "signal",
        "required_missions": ["dispatch"],
    }]
}
Path("author.json").write_text(json.dumps(source), encoding="utf-8")
```

```sh
python -m skeleton gameforge-expedition author < author.json > composition.json
python -c "import json;print(json.dumps(json.load(open('composition.json'))['request']))" > expedition.json
```

An optional binding package is an existing canonical Lantern Quay
distribution. It must independently verify and match the separately
provided authored world, mission board and choice exactly. Otherwise the
canonical package owner generates the package. The receipt records each
package, source and mission board digest, demo ending, and mission points.
The returned expedition request separately passes integrated design
admission. Its actual player genesis receives no completed missions,
inventory, outer rewards or automatically applied demo actions.

## Recovery

The original campaign assistance planner first derives a candidate from
the actual narrative checkpoint. At each upcoming local objective,
recovery replays the exact local event ledger. It can:

- Verify a suffix of the authored local witness.
- Verify a bounded witness splice after additional wait actions, without
  assuming that the moving merchant or mission deadlines remained unchanged.
- Use the existing canonical crafting planner from the independently
  replayed current state, then verify its candidate.
- Search actual local transitions with bounded retained nodes and immutable
  parent links, using the same mission progress advancement as the report
  owner. Search state preserves resource quantities, moving merchant phase,
  inventory, money, mission counts, prerequisites and earned consequences.
  A visited state at an earlier tick dominates an otherwise identical state
  because authored time constraints are upper deadlines. The heuristic
  ordering is not a global optimality guarantee.

A complete proposed suffix is independently replayed through both local
and outer owners before the combined planner reports a completion witness.
No proposal is applied automatically.

The local retained-state ceiling is 4096 per unfinished episode; dialogue
expansion has a separate 4096 ceiling for the outer plan. Default budgets
are 1024 each. Existing canonical greedy navigation has a separate
per-route cap and is skipped on local budgets below 64. A verified witness
suffix is not counted as a search expansion. Search exhaustion is distinct
from an exhaustive unreachable-state result, an alternate terminal ending,
missed required prerequisite deadline, or depleted tick budget. Replay
size limits can also reject a candidate. This is not a physical performance
or globally optimal planning guarantee.

## Durable workspace

The existing campaign journal remains in its original two SQLite tables.
An expedition journal uses two separate fixed tables and the complete
expedition replay adapter. No JSON value selects a SQL identifier or
runtime adapter. Both namespaces can coexist within the same local
operator-owned database, including identically named slots. They must
not accept one another's source, receipts or portable archives.

Each namespace retains the existing 128 slot, 256 revision, 32 MiB per
slot and 256 MiB total logical receipt limits. These are namespace quotas,
not a physical database byte quota; sharing a database can consume both.
The shared canonical 2 MiB document and node ceilings still apply.

The inherited journal supports:

- Genesis with an empty ledger; expected revision compare-and-swap.
- Exact-operation retry after a lost response and stale revision refusal.
- Verification of the selected revision and its predecessor on reads.
- Full retained chain audit with historical reads.
- Atomic historical fork with exact known parent digest, preserving
  original revisions and independent child progress.
- Compact snapshot containing operation identities, action suffixes, and
  expected receipt digests, rather than duplicating all receipt bytes.
- Atomic restore into a new slot from an independently retained source.
  Each revision is regenerated through the fixed runtime owner; an
  incorrect digest, duplicate operation, invalid action, quota error or
  existing destination aborts the whole slot reconstruction.

An archive records a claimed origin slot for provenance display, not
authenticated origin or durable signed parentage. The source must remain
independently held. No encryption, cross-device identity certification,
whole-database rollback protection or hostile-filesystem security claim.

## Installed command surface

`python -m skeleton gameforge-expedition` or
`skeleton-gameforge-expedition` reads one bounded JSON document.

| Command | Required JSON fields |
| --- | --- |
| author | Authoring request |
| verify-author | request, composition |
| assist | request, receipt (optional dialogue_budget, local_budget) |
| verify-assist | request, receipt, recovery |
| compare | request, left, right (optional budgets) |
| verify-compare | request, left, right, comparison |
| create-slot | request, slot, operation |
| append-slot | request, slot, expected_revision, operation, additional |
| read-slot | request, slot (optional revision) |
| history | request, slot |
| fork-slot | request, slot, parent_revision, expected_digest, child_slot |
| snapshot-slot | request, slot |
| restore-slot | request, slot, archive |
| board-slot | request, slot (optional revision) |
| turn-slot | request, slot, expected_revision, operation, board_digest, index |
| assist-slot | request, slot (optional revision and budgets) |
| apply-recovery-slot | request, slot, expected_revision, operation, recovery |
| compare-slots | request, slot, other_slot (optional revision, other_revision and budgets) |

All slot commands and history require an explicit `--database PATH`
under an operator-private directory. Existing schema checks apply to
noncreation commands. Compare-slots reports the observed revision of each
side; the two reads are not a simultaneous cross-slot transaction.
Turn-slot binds an explicit action choice to the exact historical board
and then calls the journal CAS. Applying recovery is a separate explicit
operation that revalidates the entire proposal and then appends via CAS.
Neither command silently rebases a stale write.

Both snapshot-slot and restore-slot are also available from the existing
`gameforge-campaign` command, operating only on its own namespace.

## Qualification boundary

```sh
python -m pytest -q skeleton/testing/test_gameforge_expedition.py skeleton/testing/test_gameforge_campaign.py skeleton/testing/test_gameforge_quest_bridge.py skeleton/testing/test_original_quest_cli.py skeleton/testing/test_dialogue_session.py skeleton/gameforge/test_gameforge_conductor.py
python -m compileall -q skeleton/app/gameforge_expedition.py skeleton/app/gameforge_expedition_board.py skeleton/app/gameforge_expedition_cli.py skeleton/app/gameforge_campaign_store.py skeleton/app/gameforge_expedition_store.py skeleton/app/gameforge_expedition_author.py skeleton/app/gameforge_expedition_recovery.py skeleton/app/gameforge_expedition_local_recovery.py skeleton/game/gameplay/harbor_crafting_missions.py
python -m skeleton capabilities --main-cli-audit
```

Run the existing harbor mission, package and gameplay suites as well.
The shared mission transition refactor requires canonical report parity
and independent review. A clean installed wheel, actual process-crash
and storage-capacity qualification, mandatory exact-head CI, backend/UI
integration, native Godot, physical devices, Windows/WSL2, Docker, GGUF,
security and release provenance remain independent. No merge, release or
native attestation is authorized by this source candidate.
