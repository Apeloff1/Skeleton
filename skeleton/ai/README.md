# Canonical AI file tree

`skeleton/ai` is the governed assembly destination for AI implementation code.

The first migration is deliberately non-disruptive: build-plan-relevant code
from current `main`, including Jeeves, is mirrored here using the exact Git
objects already in the repository. Existing imports remain compatibility paths. Python mirrors must remain AST-equivalent to their sources, non-Python content remains byte-identical, and credential-bearing destinations must be pure non-owning compatibility facades declared by `machine/ai_file_tree.json`.

## Layout

- `providers/` — provider contract and credential-bearing runtime boundary.
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
