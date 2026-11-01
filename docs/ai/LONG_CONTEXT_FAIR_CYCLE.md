# Offline long-context fair-cycle proposals

The native runtime now supports bounded, deterministic fair-cycle observation
over durable generation-fenced stream heads. This is a payload-free diagnostic,
not a scheduler admission, an execution lease, or evidence of model inference.

The LongContextFairPlanner takes at most 64 StreamDemand values and explicit
PressureSignals. It verifies each head under the durable head lock, audits
checkpoint ancestry, observes spool disk capacity, and proposes at most one
bounded quantum per active stream. Stable digest ordering removes input-order
bias within a cycle. If the token budget cannot include every active stream,
the entire proposal holds instead of silently starving later streams.

Unknown, elevated or critical CPU, memory, thermal or energy pressure holds.
GPU and M-chip proposals hold without device qualification. Caller-provided
normal pressure is not attested; even a proposed plan is not an authorization.
A backend must revalidate live resource safety, authorize execution, prove
token consumption, and perform generation/window CAS before advancing.

The plan exposes only stream and checkpoint digests, window digests, positions,
weights and token counts. No token IDs or plaintext stream names are emitted.
The planner does not mutate cursor state. It does not guarantee fairness across
repeated calls or independently authenticate a scheduler principal.

CLI: use head-plan with one or more candidate specifications of the form
stream-id:checkpoint-digest:generation:weight:max-tokens. Explicitly supply
cpu, memory, thermal and energy pressure, plus a total token budget.
Defaults are unknown pressure, which correctly holds. CLI output remains
non-authorizing and payload-free.

Focused test: python -m unittest tests.flgb.test_long_context_fairness
All mandatory exact-head CI and security gates remain release prerequisites.
