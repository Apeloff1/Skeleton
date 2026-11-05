# envelope — native AI control contracts

There are 24 independently expected executable acceptance cases at
skeleton/ai/runtime/operational_ai/guarded_request/scenarios/envelope/.
The associated focused test module validates both permissive boundaries
and adversarial denials against real gate code. This is policy coverage,
not real-model, consumer-device or release qualification.

Required invariants: explicit verified provenance, principal-bound custody,
finite resource limits, no hosted fallback, no tool authority generated
from model text, and no silent retry after ambiguous external effects.
