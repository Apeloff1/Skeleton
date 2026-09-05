# Freeze — 2026.09.05-adaptive-policy

Repo: Apeloff1/Skeleton  
Ritual: `python -m skeleton product`, `python -m skeleton adaptive-policy`, and `python -m skeleton ready --walk -n 3`

Shipped this lineage: five-brain Hoag galaxy, codec T0–T5, decoder prior
(CPU canonical), CCL vault, adaptive caps, wiki SELECT, banks,
write-back, lattice+gated KV, health, next, journal, field seed, ready,
bound field ledger, field-walk/house-round-robin/CDX handle work, the
corrective-control segment across forge/plan/game-logic/NPC/dialogue,
direct operator diagnostics surface over failures/repairs/activity/recurring,
policy enforcement with dynamic thresholds and repair gating,
multi-pass repair autonomy with learned policies and telemetry,
and now adaptive policy with self-tuning thresholds based on quality history.

Policy enforcement now includes:
- Dynamic thresholds loaded from persisted policy.json into all 5 verifiers
- Repair enable/disable gating at all repair entry points
- Repair class toggles (script_patch, project_closure, scene_stub, plan_fill, pipeline_seed)
- gate_check and repair_gate CLI commands
- Policy state surfaced in product, nervous, and doctor cards

Repair autonomy now includes:
- Multi-pass repair engine with early stopping (accepted, no improvement, max passes)
- Learned max-pass capping based on historical improvement patterns
- Persistent repair session ledger (repair_sessions.jsonl)
- Repair effectiveness metrics and session cards

Telemetry now includes:
- Per-attempt duration, scores, deltas, action counts
- Error capture with full stack traces
- Persistent telemetry ledger (repair_telemetry.jsonl)
- Operator cards for telemetry and error summaries

Learned policy now includes:
- Action effectiveness tracking across surfaces
- Surface+reason strategy success rates
- Failure pattern frequency analysis
- Strategy suggestions for new failures

Orchestrator now includes:
- Unified repair entry point with full orchestration
- Repair function registry (register_repair / orchestrated_repair)
- Wires multi-pass + telemetry + learned policy + policy enforcement
- Operator card showing all registered surfaces and their stats

Adaptive policy now includes:
- Self-tuning thresholds based on historical accept rates
- Configurable target accept rate (default 85%), adjustment rate, window size
- Per-surface adaptive config overrides
- Dry-run mode for safe preview before applying
- Operator card showing current adaptive state per surface

Not claimed: pixel lattice UI, production transformer KV cache,
import-time HuggingFace downloads, third-party prose on shelves.

G grows only through MHC×S with clips. 10× is a path, not a stamp.
