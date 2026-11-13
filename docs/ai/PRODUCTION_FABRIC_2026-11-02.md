# AI production fabric — original playable games, deterministic and offline

This additive production fabric is owned by `skeleton/ai/runtime/production_fabric`. It is deliberately **not** a replacement for the application’s existing Jeeves provider, persistent operation coordinator, browser UI, deployment builder, trainer, or release authority. No mutable mirror source tree is changed. The app may integrate through `product.compat.studio_view` once a separate scoped integration PR proves parity and canary/rollback readiness.

## Executable architecture (MBW build sequence)

| Wave | Runtime ownership | Capabilities |
| --- | --- | --- |
| MBW-00 | `contracts/` | duplicate-key-safe JSON, canonical byte hashes, strict world schemas, flags/state, deterministic graphs, budgets, identities, logical clocks |
| MBW-01 | `persistence/` | SQLite event hash chain, WAL, revision CAS, idempotency, projection rebuild, snapshots, lease fencing, inbox/outbox, export receipts |
| MBW-02 | `context/` | source-bound document identity, BM25 retrieval, explicit trust-aware projection, memory scope, citation spans, canon conflict detection |
| MBW-03 | `security/` | least-authority grants, approval quorum, original-asset rights holds, replay fence, safe logical paths, policy-gated tool callback registry |
| MBW-04 | `planning/` | playable scenes and endings, Dijkstra route solving, DAG quests, branching dialogue, actor intent, director, economy, combat, weather, factions and replayed runtime |
| MBW-05 | `product/` | offline API/CLI, immutable world registry, source-bound content catalog, portable definition import/export, read-only studio compatibility |
| MBW-06 | `evaluation/` | structural and state-aware ending search, benchmark score, tamper/replay, safety adversarial cases, rights/readiness hold, trace coverage |
| MBW-07 | `delivery/` | build order, source manifest, per-file and PR byte limits, preflight, provenance, rollback plan, non-attested operator runbook |

## One complete original game path

Run from a checkout (Python 3.11+; no external credentials, API calls or model weights):

```python
from skeleton.ai.runtime.production_fabric.product.content.catalog import WORLDS
from skeleton.ai.runtime.production_fabric.planning.engine import ProductionEngine
from skeleton.ai.runtime.production_fabric.evaluation.structural import evaluate

engine = ProductionEngine(WORLDS["cloudbreak_signal"])
print(engine.inspect("player"))
engine.play("player", "token1", "enter_archive", 0)
engine.play("player", "token2", "learn_secret", 1)
engine.play("player", "token3", "prepare_crossing", 2)
engine.play("player", "token4", "choose_hidden", 3)
assert engine.inspect("player")["state"]["ended"]
assert engine.verify("player")["recoverable"]
assert evaluate(engine.world)["status"] == "pass"
```

For durable on-disk play, explicitly construct `ProductionEngine(world, Journal("operator-owned.sqlite"))`, or invoke:

```bash
python -m skeleton.ai.runtime.production_fabric.product.cli \
  --world ./operator-owned-world.json --db ./operator-owned.sqlite \
  --request '{"method":"inspect","session":"player"}'
```

The catalog consists of 72 separate, original-text, playable world definitions across 24 settings and three play styles. It also contains 24 quest DAGs and 24 branching dialogue graphs with explicit prerequisites. This is source-authored game material, **not** verified commercial originality or independently approved licensing. The source-bound packaged examples are tools and fixtures, not evidence of polished 3D graphics, device installation, AI model training, production inference, or consumer readiness.

## Acceptance and controls

- Full-source coverage and native AI owner: `machine/ai_file_tree.json` residual canonical native root, no newly invented legacy mirror mappings.
- All source paths are included by explicit prefixes in `machine/ai_ecosystem_bundle_v1.json`; the package byte size still requires real operator-approved assets for 1.9 GB.
- Tests: run `python -m unittest discover -s tests/production_fabric -p 'test_*.py' -v` after completing the change set. Each authored world tests both endings, replay, and locked secret; each quest/dialogue module has dedicated prerequisite tests.
- No deployment or model execution is implicitly enabled, no tools are invoked from untrusted model text, and file provenance/rights must be explicitly approved before redistribution.
- SQLite file path is operator-trusted local state only. This does not qualify untrusted directory paths, cross-machine distributed leases, untrusted model artifact ingestion, production signing, or adversarial filesystem concurrency. Do not call it release-ready without independent exact-head CI, device, restore, and security qualification.
- Every change must remain below 100 MB per source file and below 2 GB per PR, with no compressed or binary artifacts committed.

**Qualification status: draft / local smoke only.** Check exact-head CI and independent review before promotion.
