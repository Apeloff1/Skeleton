# Jeeves Native Operational Bridge — Source-Checked GGUF

## Canonical ownership

This incremental Jeeves agent bridge lives inside the existing
skeleton/jeeves/agent package. It consumes the existing SupervisedAI,
ExecutionSpine, signed native work-order and source-bound installation layers
without adding a second model provider, independent tokenizer, parallel SQLite
source of truth or new top-level runtime root.

Branch dependency: the first-laptop source-preflight draft and all of its
stacked native model/work-order prerequisites must be independently qualified
before promotion. This bridge must remain draft while that stack is held.

## Runtime flow

1. Verify an installed GGUF source receipt, operator-approved model rights,
   exact model bytes, active tokenizer and actual local process boundaries
   using the existing activate_checked entry point.
2. Construct one principal-bound NativeJeevesRuntime. No hosted provider is
   permitted and the bridge's provider router has precisely one attempt.
3. Validate Jeeves RunInputs tenant/user scope against the actual execution
   spine identity. Model-proposed identities cannot change it.
4. Render a canonical JSON native prompt containing the original role labels,
   untrusted context, declarations of proposed host tool schemas, and the
   requested structured-output contract. Bound bytes, count and schema before
   native reserve; the canonical spine separately performs exact tokenizer
   admission. No silently clipped context or fabricated model capacity.
5. Derive one stable native session and request identity from the original
   principal/model/request. Explicitly revalidate existing session ownership.
6. Before inference, check authoritative read-only replay. If committed,
   return it without invoking the native model a second time.
7. If no committed receipt exists, execute the one admitted native request
   through TurnBridge and SupervisedAI. Native uncertainty remains held by the
   existing durable session/lease coordinator, never silently retried.
8. Verify the committed native model/tokenizer identity, text SHA-256, session
   identity, native request identity, finish reason, token budgets, and
   structured-output shape before admitting content as a Jeeves ModelResponse.
9. Feed the model response to the existing StrictJeevesAgentRuntime.
   The model is a proposer. Existing tool policies and the epistemic guard
   decide every host execution; no model-suggested grant becomes authority.
10. Do not equate a source fixture, local import or mock worker with real
    installed-GGUF native execution, model rights, hardware validation,
    enterprise release certification or operational availability.

## Operational plain chat mode

Not every locally installed GGUF model reliably emits Jeeves planning and
verification JSON. The new `NativeJeevesChat` is a conversational path
through the *same* private SQLite session, process isolation, model/tokenizer
identity checks, native receipt custody, and exact replay. It does not
require untrusted model JSON to answer an ordinary question. The user
message and assistant response are committed in a single native session.
Historical context is assembled by the canonical native spine.

To run the plain conversational mode (does not require an agent plan):

`python -m skeleton.jeeves.agent.native_cli --mode chat --model-root /private/installed-gguf --state-dir /private/native-state --tenant local --subject operator --task-stdin < /private/task.txt`

To resume the same explicitly principal-bound conversation, supply
`--session <existing-private-session-id>`; use a stable `--request-id` to
read-only replay the exact previous user turn instead of calling the native
model again. Both are validated by the canonical durable session authority.
The chat facade independently checks that the worker result matches a
committed SQLite response and refuses ambiguous native effects. No model
output triggers privileged tools, external network calls or memory
inference/admission.

## Operator invocation

Use a pre-installed, independently approved original GGUF model.

python -m skeleton.jeeves.agent.native_cli --model-root /private/installed-gguf --state-dir /private/native-state --tenant local --subject operator --task-stdin < /private/task.txt

Optional bounded resource arguments: --context, --max-output-tokens,
--threads, --gpu-layers, --capacity-root, --capacity-budget-bytes,
--max-steps, --max-model-calls, --max-wall-seconds.

The operator entrypoint uses stdin for a bounded user task, not shell
arguments. It writes only an explicitly successful verified final answer to
stdout. Errors use type names without path/prompt/credential disclosure.
A model that cannot produce the required plan or answer JSON fails closed.

## Required source validation

After the source publication and repairs are complete, run these in order:

1. python -m unittest skeleton.testing.test_jeeves_native_prompt_and_schema -v
2. python -m unittest skeleton.testing.test_jeeves_native_provider_bridge -v
3. python -m unittest skeleton.testing.test_jeeves_native_chat -v
4. python -m compileall -q skeleton/jeeves/agent/native_prompt_boundary.py skeleton/jeeves/agent/native_schema_boundary.py skeleton/jeeves/agent/native_receipt_boundary.py skeleton/jeeves/agent/native_provider.py skeleton/jeeves/agent/native_runtime.py skeleton/jeeves/agent/native_readiness.py skeleton/jeeves/agent/native_chat.py skeleton/jeeves/agent/native_cli.py
5. python scripts/check_architecture_map.py
6. python scripts/check_ai_app_construction.py
7. python scripts/check_capability_interfaces.py
8. python scripts/check_provider_bootstrap.py
9. python scripts/check_enterprise_ai_superiority.py --json
10. python scripts/check_enterprise_ai_implementation_notes.py --json

Also rerun the full mandatory exact-final-head Merge Readiness, Backend
Quality, App Foundation E2E, Workflow Input Security, Sealed Context Guard,
Artifact Policy, Malware Gate, Repository Hygiene, Secret Scanning and
Dependency Review gates. Skips, pending, failed, cancelled or stale statuses
never count as successful qualification.

## Honest readiness levels

- Source-level contract tests: simulate the coordinator and model output,
  cannot establish real GGUF inference or SQLite durability.
- Installed model custody: existing installer can attest source and local
  package bytes; operator rights approval is not independent license review.
- Actual native execution: requires a real approved GGUF and a successful
  source-bound, independently witnessed process and committed SQLite receipt.
- Device acceptance: requires clean Windows 11/WSL2 and target laptop
  environment, memory pressure, restart, native cancellation, resource bounds,
  privacy behavior and performance observations.
- Release: requires all exact-head gates, independent review, checked
  prerequisite PRs, and explicit operator approval.

Important hold: Native request replay is restart-safe in the authoritative
ExecutionSpine, but this initial Jeeves orchestration composition uses
in-process checkpoints. Do not call it restart-safe agent control or
reexecute ambiguous external effects after process loss. Future progression
must integrate the already existing durable Jeeves owner, not a duplicate
orchestrator or store.

Implicit memory writes are disabled by default until a consent-bound durable
memory policy is independently verified. The native bridge supports
model-proposed plan steps but does not turn model text into tool grants.
