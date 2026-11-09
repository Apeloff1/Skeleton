# Canonical AI file tree

`skeleton/ai` is the governed assembly destination for AI implementation code.

The first migration is deliberately non-disruptive: build-plan-relevant code
from current `main`, including Jeeves, is mirrored here using the exact Git
objects already in the repository. Existing imports remain compatibility paths. Python mirrors must remain AST-equivalent to their sources, non-Python content remains byte-identical, and credential-bearing destinations must be pure non-owning compatibility facades declared by `machine/ai_file_tree.json`.

## Layout

- `providers/` — provider contract and credential-bearing runtime boundary.
- `runtime/inference/` — executable local transformer/GGUF backends, pinned artifact/deployment/catalog loaders, fair admission and resource accounting.
- `model_runtime/` — native model execution, tokenization, checkpoints and standalone offline chat.
- `runtime/contracts/` — operation/conversation/context contracts.
- `runtime/persistence/` — durable state and recovery.
- `runtime/context/` — context compilation.
- `runtime/retrieval/` — retrieval and grounding.
- `runtime/memory/` — memory.
- `runtime/intelligence/` — admission, verification and execution.
- `runtime/frontier/` — routing, streams and frontier orchestration.
- `runtime/skills/` — tools and skills.
- `runtime/{api,vault,artifact_plane,observability,security,kernel,reliability,resilience,primitives,native}/` — plan-owned engine support planes, including the stable native ABI/acceleration boundary.
- `runtime/cortex/` — owned-model cognition, routing, interchange, multimodal and learning runtime; credential/network files remain non-owning facades during staging.
- `runtime/organism/` — engine organism DAG, policy/health/quality, resilience and operator-control support; encrypted secret storage remains a non-owning facade during staging.
- `runtime/contexts/` — extended/legacy context support retained under governed parity.
- `agents/jeeves/` — Jeeves reasoning and agent system.
- `agents/core/` — core agent/swarm execution runtime.
- `shell/` — AI control-plane/shell implementation: governance, planning, policy, verification, durable recovery, trust and release evidence.
- `mathematics/` — deterministic AI-native reference math: stable numerics, dense linear algebra, probability/information measures, bounded optimization, and parity oracles; no model or knowledge authority.
- `cognition/`, `learning/`, `evaluation/` — cognition, controlled learning, and evaluation support.
- `modeling/` — governed model registry, model-development training/evaluation, and publication support.
- `training/` — governed training control, distributed/checkpoint/recovery, evaluation-gate, post-training, curriculum, RL-environment, and verifier-model support.
- `runtime/extensions/{artifacts,audio,connectors,document_vision,plugins,speech,supply_chain,video,vision}/` — bounded multimodal, connector/plugin, and model-supply-chain contracts; credential references remain opaque and no implicit model execution/promotion authority is created.
- `research/historical/architecture_registry/` — base architecture metadata and numbered architecture rounds retained as non-authoritative research lineage.
- `simulation/`, `forge/` — explicit masterplan domains for bounded world-model simulation and candidate forge workflows.
- `build/shift_supervisor/` — planning/scheduling/build-control code promoted from the transitional `core/` root.
- `build/{automation,repo_intelligence}/` — repository-side AI build/control support.
- `build/documentation/` — deterministic generated/human documentation support for AI build and plan artifacts; no model execution authority.
- `compat/` — legacy runtime surfaces staged for convergence into an existing canonical owner; these paths never create new production authority.

No compatibility source may be deleted until imports, ownership, focused
tests, rollback evidence, App Assembly, and signed accountability are explicit.
Relocation alone never completes an AIQ task or work package.

## Running application composition

The product uses the existing application and engine processes. The active path
is `frontend/src/features/Jeeves` → `backend/routes/ai.py` →
`skeleton/api/engine_runtime.py` → `skeleton/provider_runtime.py`. The governed
`runtime/api` and `runtime/intelligence` destinations mirror those canonical
owners; the provider destinations remain non-owning facades. Edit the owning
source and synchronize its governed mirror instead of creating another executor.

| Capability | Implementation and operating behavior |
| --- | --- |
| Local model selection | `runtime/inference/{artifact,deployment,catalog}.py`; explicit pinned artifacts or up to eight named models, without implicit downloads or external fallback. |
| Serving | `runtime/inference/{local,adaptive_serving,llama_cpp,native_runtime}.py`; one admission owner for trusted tenant/deadline scopes, bounded batches, memory headroom and physical worker drainage. |
| Response cooperation | `skeleton/intelligence/cooperation.py` and the canonical execution loop; bounded plan/draft/critique/refine stages preserve the original context and operation budget. |
| Operational learning | `skeleton/intelligence/runtime_learning.py` and `skeleton/persistence/execution_repository.py`; numeric feedback, drift, deferred replay credits, checkpoint recovery and bounded derived retention. Transformer weights do not train themselves through these controls. |
| Idle upkeep | `skeleton/jeeves/ai/studio_maintenance.py`; optional admitted chunks, durable result reuse, postcommit acknowledgements, physical custody and explicit failed-task retry. |
| Studio improvement | `backend/core/game_studio_agent.py`; source-bound child reconciliation, opt-in compatible numeric memory and explicit incumbent restoration through the existing editor gates. |
| Operator interface | Jeeves runtime optimization and the AI model inventory; current model, recovery, learner and maintenance observations plus administrator controls. |

Persistent engine execution uses one coordinator and one pinned engine namespace
per execution database. The coordinator holds OS file custody through drainage,
rejects inherited fork ownership and scans restart work in bounded pages. Parallel
model workers and game/training instances operate inside their existing admission
budgets. Separate engine installations need separate state volumes.

Use [AI and crawler first install](../../docs/ai/FIRST_INSTALL_AI_AND_CRAWLER.md)
for the configuration helper, portable model bindings, explicit administrator
bootstrap and startup commands. Build compilation and a materialized file tree
do not establish enterprise qualification or measured game quality.


## Standalone offline AI chat entry points

`model_runtime/offline_chat.py` owns the native-transformer checkpoint chat
product and the model-identified SQLite conversation authority. It implements
durable full-history preservation, exact-model/tokenizer identity, stable retry
receipts, transactional turn commits, exact-turn forks, portable backups and
restart recovery.

`skeleton/app/local_ai.py` and `skeleton/app/offline_chat_cli.py` expose
that same offline SQLite authority through the installed desktop UI and a
headless interface. `skeleton/app/offline_http.py` adds a strictly
loopback-bound, bearer-authenticated HTTP API and same-origin browser UI
from `skeleton/app/offline_web.py`. `skeleton/app/offline_knowledge.py`
adds operator-owned, model-scoped reference ingestion and deterministic
local search with exact source-byte provenance and cited passage offsets.
All routes support native checkpoints and explicitly operator-installed
GGUF/llama.cpp deployments. Only the model context *projection* is trimmed;
the full committed conversation remains durable. The HTTP server enforces
private credentials, origin/host restrictions, bounded request sizes and
ordered shutdown.

Reference retrieval currently remains **separate from generated chat**: no
evidence-grounded-answer quality claim follows simply from finding local
source text. Track the next closure and required product acceptance in
[Measured Completion Gaps](../../docs/ai/MEASURED_COMPLETION_GAPS_2026_10.md).
No weights are downloaded, tools are not granted, and there is no hosted-model
fallback. See [Offline Native Chat](../../docs/ai/OFFLINE_NATIVE_CHAT.md)
for runnable commands, release smoke, model requirements and limitations.

## Planned-path disposition

The machine manifest audits concrete `skeleton/*` roots referenced by the master
plan and construction contract. Each root must be one of: migrated into this
tree, intentionally external with a named architecture owner, represented by a
mapped implementation alias, or still absent. If a planned-but-absent engine
root later appears outside `skeleton/ai`, the AI file-tree gate fails until the
root is migrated or explicitly reclassified.

## AI-native ownership

Completed implementations created directly under `skeleton/ai` have no legacy
source to mirror. They are governed by `machine/ai_file_tree.json` under
`native_ai_owners` instead of receiving fabricated source→destination mappings.
A residual tree owner governs only AI-native files not already claimed by a
more-specific migration destination.

Every tracked file under `skeleton/ai` must resolve to either a governed migration
destination or a canonical native owner. The validator fails closed on unowned
tracked files, so newly landed completed work cannot silently bypass file-tree
governance.

## Completed-volume traceability

A mature masterplan volume (`implemented`, `hardened`, or `verified`) that resolves to a governed AI-tree source or destination must be listed in the most-specific owning mapping's `volume_refs`. The AI file-tree validator enforces this ledger so newly completed work cannot silently bypass canonical AI ownership. Traceability does not authorize source deletion, import cutover, completion signing, or independent verification.
