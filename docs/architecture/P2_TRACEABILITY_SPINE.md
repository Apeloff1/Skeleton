# P2 Requirements-to-Runtime Traceability Spine

P2-TRACE-01 is the dependency-ready lane after architecture/contract convergence. It is subordinate to the canonical masterplan and does not create a parallel completion or maturity authority.

## Scope

The lane implements the explicit gaps in VOL-112, VOL-113, and VOL-122 through VOL-131.

The canonical master trace is sharded by masterplan depth pass. Its current shape is **421 volumes, 963 requirements, 9,115 trace nodes, 25,119 typed edges, and 11 shards**. The sharding is an implementation detail; the validator treats the shards as one deterministic graph.

Additional derived registries deepen that graph:

- `machine/requirement_registry.json` gives all 963 masterplan requirements stable IDs and binds them to implementation, tests, evaluations and existing evidence.
- `machine/capability_taxonomy.json` classifies all 421 volumes and normalizes the declared capability vocabulary while keeping runtime availability separate.
- `machine/nfr_registry.json` derives 37 NFR identities from the 31 engineering work packages. It deliberately does not invent thresholds.
- `machine/behavior_specifications.json` expresses normal and degraded behavior for the assembled runtime capabilities and binds scenarios to requirement IDs.
- `machine/state_machine_catalogue.json` binds operation/execution state machines to the actual contract source, schema enums, transition maps and tests.
- `machine/interface_standard.json`, `machine/schema_registry.json` and `machine/compatibility_model.json` connect the 86 canonical interfaces to all 36 runtime schemas and mixed-version policy.
- `machine/protocol_registry.json` introduces a canonical internal protocol envelope with operation, correlation, causation, trace/span, deadline, idempotency, retry and unknown-outcome semantics.
- `machine/maturity_registry.json` gives every masterplan volume a SHA-256 identity over current evidence/accountability inputs and a path-based invalidation watch set.

## Fail-closed validation

`scripts/check_traceability_spine.py` regenerates and compares the derived registries against the masterplan, engineering pass, runtime capability registry, state topology, interface ledger, runtime schemas and accountability ledger. A registry cannot silently rewrite its source obligation.

`scripts/check_master_traceability.py` independently regenerates every sharded node and edge from the masterplan and detects dangling/stale trace data.

`scripts/check_nfr_registry.py` preserves the engineering policy that thresholds must be explicitly bound before promotion. When measurement evidence is supplied, a threshold miss is non-compensable.

`scripts/check_trace_pr_impact.py` resolves pull-request changes against implementation trace paths and maturity invalidation watches. Trace-control files are explicitly recognized; an unrelated implementation path with no trace or maturity mapping fails closed.

## Protocol authority

The canonical `ProtocolEnvelope` lives in `skeleton/contracts/protocol.py` and is mirrored byte-for-byte under the governed AI contract tree. Existing worker, shell/model and replication protocols are tracked as adapters rather than silently declared compliant.

This lane does not claim that those adapters are already migrated, that the 688 requirements without current evidence are complete, or that any volume has earned a maturity promotion.
