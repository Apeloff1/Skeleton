# Source graph orphan recovery

The installed command `python -m skeleton orphan-source-graph --root .`
enumerates local Python source without importing it. It seeds possible
reachability from both package metadata formats and the root package and
CLI. Additional service or application roots may be supplied explicitly
with repeated --entry options. Production test directories are excluded.
Absolute, relative, package initializer and recognized literal dynamic
imports contribute edges; unresolved computed calls are counted. A
missing root, ambiguous source identity, unreadable file, skipped link,
metadata drift or inventory ceiling is visible as incomplete evidence.

The planner condenses cycles into indivisible components and orders the
unreferenced component DAG dependency-first. Component IDs, source hashes,
graph, roots and plan are deterministic; output may be truncated without
changing the complete plan digest. Byte-identical groups are discovery
leads, not authorization to collapse mirrored modules or change ownership.
The graph is a conservative static model: a conditional import is not
runtime reachability, dynamic plugins and backend/frontend consumers may
not be detected, and an unreferenced candidate is not proof of an orphan.
Use explicit domain roots and review owner boundaries before integrating.
No source modules are executed or modified. This is a trusted-checkout
audit, not filesystem isolation or an atomic snapshot.

The same package now recognizes independently pinned portfolio receipts
in the existing archive inspector; inspection proves historical bytes,
not fresh source replay. All runtime, native, release and merge holds
remain in force.


## Ownership-aware pagination and owner activation

Use --machine-ownership to observe the existing fixed machine/ai_file_tree.json
mapping declaration. The report labels declared sources, staged destinations,
native owners, residuals, exclusions, overlays and ambiguity; compares
observed content hashes without collapsing paths or equating identical
bytes with equivalent runtime behavior. The declaration itself is bound
into the candidate plan digest. A subsequent page requires both independent
plan and source inventory digests and the returned next_component_offset.
A changed plan or source inventory rejects continuation. This is a review
tool, not an authorized migration or ownership signoff.

Additional explicit installed owner routes:
- `local-ai-boot` → `skeleton.ai.runtime.operational_ai.deployment.boot.cli:main`
- `local-ai-bootstrap` → `skeleton.ai.runtime.operational_ai.deployment.bootstrap.cli:main`
- `local-durable-worker` → `skeleton.ai.runtime.operational_ai.durable_jobs.worker_cli:main`
- `local-flight-events` → `skeleton.ai.runtime.operational_ai.transport.flight.event_stream.cli:main`
- `local-flight-outbox` → `skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.cli:main`
- `local-flight-control` → `skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli:main`
- `local-flight-metrics` → `skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.operator_cli:main`
- `local-laptop-client` → `skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli:main`
- `local-laptop-runtime` → `skeleton.ai.runtime.operational_ai.laptop_runtime.cli:main`
- `dragon-research-game` → `skeleton.ai.webcrawler.game_builder_cli:run`
- `era-source-validate` → `skeleton.ai.simulation.era.scripting.cli:main`

All routes preserve exact caller arguments and original return status.
They do not automatically bind a principal, provision state, launch a
daemon, submit a flight job, use credentials, train a model or approve
publication by installation. Owner-specific local qualification is required.
The route and ownership tests are selected in the existing gate but were
not executed by registration.
