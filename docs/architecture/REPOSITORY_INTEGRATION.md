# Repository integration

The [Repository Atlas](REPOSITORY_ATLAS.md) and `.machine/repository.toml`
describe placement. `machine/repository_migration_plan.json` records migrations;
`machine/ai_file_tree.json` governs source/mirror parity. These contracts serve
different purposes and must agree before a change is ready to merge.

## Combined tree migrations

The integration preserves the landed School, research-lineage, and application
workspace changes (TREE-030 through TREE-032) while incorporating the pending
domain migrations from the tree stack ending at `c03767494f3b0940e7408f2ba445c8d23a56b108`.
Incoming batches receive unique IDs TREE-033 through TREE-040; `source_batch_id`
preserves their original branch-local IDs. Existing ledger entries keep their IDs.

| Capability | Canonical implementation | Compatibility surface |
| --- | --- | --- |
| Era binding | `skeleton/simulation/era/` | `skeleton/era/` |
| Social evidence | `skeleton/research/social/` | `skeleton/social/` |
| Galaxy | `skeleton/distributed/galaxy/` | `skeleton/galaxy/` |
| Network | `skeleton/distributed/network/` | `skeleton/network/` |
| Mesh | `skeleton/distributed/mesh/` | `skeleton/mesh/` |
| Graphs | `skeleton/knowledge/graphs/` | `skeleton/graphs/` |
| Chronicle | `skeleton/provenance/chronicle/` | `skeleton/chronicle/` |
| Integrations | `skeleton/tools/integrations/` | `skeleton/integrations/` |

Distributed runtime, research, knowledge, provenance, and tools now have concrete
source packages in place of their previously absent planned roots. Existing
imports remain supported. Capability discovery and lazy loading resolve Galaxy
and Social directly to their canonical owners.

Research's package entrypoint is governed separately from its Social child.
Historical, acquired, and external AI research remains in its existing quarantine
namespaces. The validator accepts a composed source namespace only when **every
tracked source member** is covered by an explicit mapping; an empty parent or an
unmapped sibling cannot qualify. This does not authorize research production use
or retirement of compatibility packages.

## Integration repairs

- School and persistence primitives use canonical self-imports. Learner evidence
  returns the updated `SkillState` promised by its API.
- Gameplay and Godot dataclass defaults use factories so Python 3.11 can import
  them. Their immutable mapping behavior is preserved.
- Agent/swarm code shares a string-compatible `AgentId`, including explicit
  names for deterministic ballots and generated identities for live rosters.
  Swarm quorum resolves kernel errors through the absolute canonical namespace.
- Corresponding governed AI mirrors contain the same repairs.
- Migration regressions check stable ownership and relative ordering rather than
  assuming their batch will forever be the final ledger entry. Taxonomy ignores
  configured generated directories such as `__pycache__`.

## Frontend portability

`frontend/components/UI/` retains the established screen components and async
states. The formerly lowercase `components/ui/` reusable components now live in
`frontend/components/primitives/`. Keeping distinct directory names prevents
Windows from combining two directories that Linux treats separately. Internal
imports use the new paths; component implementations are preserved.

## Validation and rollback

Run the mandatory architecture, construction, capability-interface,
state-topology, provider-bootstrap, application-assembly, and AI-file-tree
validators. Run namespace/taxonomy regressions, affected gameplay and School
tests, and the engine assembly suite. The Merge Readiness workflow now includes
namespace, taxonomy, atlas, and combined-integration regression coverage.

`tests/test_repository_integration.py` verifies the **staged Git tree** against
the updated mapping identities. Stage the integration before running it locally;
CI naturally validates the committed checkout. Source/mirror parity is separately
checked against file contents by `scripts/check_ai_file_tree.py`.

For the frontend, install locked dependencies with lifecycle scripts disabled,
apply `frontend/scripts/patch-node-modules.js`, then run `yarn typecheck`,
`yarn test:operation-stream`, `yarn test:conversation`, and `yarn export:web`.

Windows checkouts of historical paths may require repository-local
`git config core.longpaths true`. If the host also restricts Python filesystem
path lengths, invoke the file-tree check through an extended absolute path
(`\\?\C:\...\scripts\check_ai_file_tree.py`) or use a short checkout directory.

The migration is reversible as one integration change: revert its code, mirrors,
metadata, tests, and frontend moves together. It changes no stored user data or
database schema. Preserve compatibility packages until the repository's separate
cutover requirements have been satisfied.

Passing structural and unit checks does not prove a deployed system is healthy.
Docker/Compose builds, live Mongo/provider checks, release evidence, and independent
verification retain their existing gates. Other planned feature roots remain
explicitly recorded as absent until an actual implementation and its acceptance
evidence exist.
