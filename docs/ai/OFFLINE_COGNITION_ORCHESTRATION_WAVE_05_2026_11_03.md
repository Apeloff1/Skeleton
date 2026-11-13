# Offline cognition wave 5/8: safeguarded orchestration

This wave reuses the existing canonical operational AI runtime. Its finite
orchestration core composes the already-owned DAG planner, read-only tool
intents, operator source permits, source SHA receipts and durable replay
distinctions. It does not add a model provider or execute any tool.

Eight families: task_decompose, dependency_plan, tool_proposal,
tool_result_proof, deadline_gate, retry_classification,
operator_escalation, circuit_recovery.

Source plans are **inert**: a plan hash is not an operator grant.
The critical-path estimate must fit both a finite duration ceiling and an
explicit monotonic deadline. Tool replies are accepted only when they
match the original approved source SHA, tenant, subject and intent.
A native effect that might have been dispatched is fenced until canonical
spine reconciliation, never retried on transport error or crash.
A committed effect can be read through canonical replay only.
Circuit recovery returns a held request; no signed external operator approval
is inferred from a boolean field.

Source checks after commit:
    python -m unittest skeleton.testing.test_offline_cognition_orchestration -v
    python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q
    python -m skeleton.ai.runtime.operational_ai.offline_cognition.cli

L00-L02: canonical AI owner and typed scopes preserved.
L03-L05: compiled DAG and read-only intent are not effect authority.
L06-L07: fail closed for foreign source, source tampering, stale grants,
ambiguous dispatch, unknown transitions and cross-principal circuits.
L08-L09: bounded tasks, deadlines, token costs, byte payloads and explicit
circuit thresholds; independent p95/p99 evidence remains required.
L10: adversarial tests and policy casebooks; real native GGUF held.
L11-L12: derived circuits cannot replace authoritative durable native state;
recovery and operator review require external receipts.
L13: enterprise, release, hardware and comparator superiority claims held.
