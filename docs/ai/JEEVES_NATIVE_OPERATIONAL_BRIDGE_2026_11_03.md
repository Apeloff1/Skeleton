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

## Signed original-source grounding

The operator can elect to attach independently HMAC-authenticated local source
material through the **existing** offline cognition manifest authority and
the canonical native ExecutionSpine evidence callback. This is off by default
and never populated by model-originated text.

Use these explicit options with chat, agent or REPL:

--source-root /private/approved-sources
--signed-source-manifest /private/operator/signed-source-manifest.json

The external key must be provisioned through the existing
SKELETON_OFFLINE_OPERATOR_KEY_HEX environment variable. No key value,
private original-source content, or private manifest is committed to GitHub
or printed to stderr. Both source options must be present together.
The original source manifest binds tenant, subject, installed model digest,
tokenizer digest, original file SHA256 and operator attested source rights.
The existing descriptor-anchored file reader rejects symlinks, parent path
swaps, multiple hardlinks, modified source contents, unbounded files,
foreign owners and stale or invalid HMAC approvals.

The new NativeSignedEvidenceProvider converts only independently verified
original byte excerpts to the existing native Evidence type, tagged explicitly
as untrusted source **data**, never as system instructions or tool grants.
The same original files and signed manifest are checked again inside the
canonical native commit fence. A source modification or expired authority
holds the pending operation for explicit reconciliation. Source provenance
is not semantic entailment or independent legal-rights proof.

### Explicit source tools for Jeeves agent mode

When using agent mode (rather than plain chat or REPL), an operator may
expose only approved original-source excerpts through the existing Jeeves
ToolRegistry, ToolExecutor and mandatory epistemic runtime guard.

Supply all three flags:

--source-root /private/approved-sources
--signed-source-manifest /private/operator/signed-source-manifest.json
--enable-source-tool

Agent mode refuses a source manifest without this explicit source-tool
permission. Plain chat and REPL may use the same pair of source flags to
install an evidence-provider callback in the canonical native spine.
Their prompts are raw bounded user text; agent prompts are larger structured
JSON envelopes, so agent source selection is performed through the host tool,
not by mistakenly treating the JSON envelope as a direct source query.

The signed source tool has exactly one query argument. It does not accept
model-selected pathnames, shell commands, arbitrary file access, permissions,
network URLs, writes or new HMAC signatures. Before returning an observation,
it reopens and re-verifies the signed original source bytes, exact passage SHA,
principal, approval epoch and source bounds. EvidenceRefs preserve those byte
digests and are explicitly not semantic-truth or host-authority proofs.

The CLI attaches a maximum-three-call READ_ONLY ToolGrant only after the
operator explicitly enables the tool. Host policy and epistemic verification
still independently decide every proposed model-originated tool call.
No mutating or external grant exists in this composition.

## Continuous local chat, without reloading the model

The single-process REPL retains one source-approved installed model and one
SQLite owner-bound conversation across multiple entered lines:

python -m skeleton.jeeves.agent.native_cli --mode repl --model-root /private/installed-gguf --state-dir /private/native-state --tenant local --subject operator

Input is a bounded UTF-8 line, output one machine-readable JSON record per
turn. Supported commands are :status, :history (explicit history disclosure
to the operator's local stdout), :quit (leave the durable session open for
explicit resume) and :close (close but do not erase the durable session).
A literal colon-prefixed prompt can be entered by doubling its first colon.
The REPL makes no hidden retry after ambiguous native execution, and does not
claim live token streaming or in-flight device cancellation.

## Explicit real native acceptance, never source fixture acceptance

A separate controlled operator entry point is available for the required
real-model, real-SQLite acceptance sequence. It must never run automatically
in CI or on an unapproved checkpoint. It requires both --approve-native
and --prompt-stdin. The original private prompt and model response are not
printed; output contains hashed model, tokenizer, prompt and answer identity.

python -m skeleton.jeeves.agent.native_acceptance_cli --model-root /private/installed-gguf --state-dir /private/native-state --tenant local --subject operator --approve-native --prompt-stdin < /private/acceptance-prompt.txt

The optional --cold-restart flag closes the first supervised runtime, runs
the existing read-only SQLite restart doctor, reopens the exact approved
installed model into a fresh supervised stack and verifies that replaying
the original committed request requires **zero new model generations**.
This is meaningful cold model reload/replay evidence; it is not in-flight
native cancellation, memory pressure or clean Windows 11/WSL2 evidence.

This command must only run on the actual trusted and verified source installed
GGUF. It never ships model weights or replaces the existing installer.
Tests for its orchestration use explicitly simulated workers and are never
accepted as the physical evidence this operator command is designed to collect.

## Deterministic native quality evaluation

The operator-owned quality runner accepts a finite JSON casebook on stdin.
It uses the existing installed-model custody, canonical native supervisor,
SQLite receipt and read-only replay; it never adds model weights, synthetic
model-generated grades, arbitrary host tools or hosted provider fallback.

python -m skeleton.jeeves.agent.native_eval_cli --model-root /private/installed-gguf --state-dir /private/native-state --tenant local --subject operator --approve-native --cases-stdin < /private/jeeves-quality-cases.json

The casebook schema is jeeves.native_evaluation_casebook.v1, with a nonempty
list of cases. Each case has an operator-assigned case_id, private prompt
and at least one expected-output predicate: exact_sha256, required_terms
or forbidden_terms. Each also has optional minimum_generated_tokens and
maximum_generated_tokens. The runner reserves each case's full configured
native output ceiling before invoking the model, enforces case count,
token and wall budgets, and stops on ambiguous native execution.

Scores are explicit exact bytes, literal term checks and token bounds.
Only input/output digests, model/tokenizer identity, timings, case verdicts
and noncertification fields are disclosed. This tests selected expectations,
NOT factual truth, physical device quality, privacy of an actual laptop,
model licensing or release readiness.

The source tests use simulated workers; real native quality evidence only
exists after explicitly executing this operator CLI on a separately
verified and rights-approved installed GGUF model.

## Real SQLite custody integration (synthetic model only)

The new test_jeeves_native_sqlite_integration.py exercise runs with
a real protected SQLite WAL database, real interprocess session-lock file,
real source-bound ExecutionSpine, real event outbox and receipt ledger,
and real SupervisedAI and Jeeves adapter instances. It verifies that:
- one admitted request writes exactly one committed turn and outbox event;
- same request/prompt replay returns exactly committed bytes with no second generation;
- a cold reopened SQLite database can resume a principal-bound session;
- a different principal cannot read another identity's session;
- an ambiguous backend effect persists as a pending hold, including after restart;
- changed request contents and tampered output/receipt hashes fail closed;
- a closed session cannot generate a new turn.

The integration uses an explicitly labelled synthetic Generated receipt/backend
so it does not prove an installed GGUF, a real tokenizer, native device
isolation, Windows support or source legal rights. Passing source-only tests
must never be promoted to a physical device or release certification.

## Pre-activation operator admission

The CLI now validates task/REPL mode, chat-session and request identities,
the paired source-root/manifest contract, explicit read-only tool intent,
resource ceilings, absolute canonical source paths and bounded task budgets
**before** it reads task stdin, opens an operator key, starts an installer
check or loads the native model.

Invalid source flags, mixed session/agent operation, invalid grant scope,
relative source paths, unbounded worker budgets and malformed run modes
are rejected without allocating a model, using the existing fail-closed
operator CLI error response with no task or private path disclosure.
This pure-source preflight is not a substitute for model byte/source
rights verification, descriptor-anchored file admission, native GPU memory
reservation, SQLite transaction checks or independent device qualification.

## Signed-source preflight before GGUF model activation

An explicitly supplied source manifest is now HMAC-authenticated, decoded,
checked against the operator's tenant/subject and one-hour approval epoch,
and all original source bytes are read from descriptor-anchored private
files **before** the model installer activates a GGUF backend.

The preflight returns a source-only SHA receipt with no prompt, original
source text, model key, or private file paths. It does not claim the real
model was loaded. After activation, the actual native GGUF model and
tokenizer identities are compared to the signed source scope. Subsequent
selection and SQLite commit still independently reopen and verify the
signed source bytes: a preflight does not grant perpetual authority if
files are swapped or approval expires during generation.

Expired HMACs, foreign tenants, invalid source roots, symlinks, substituted
files, unsigned source content or source cap violations now prevent
unnecessary native startup. Source rights remain operator-attested only,
not independently licensed by this feature.

## Complete bounded Jeeves agent loop (synthetic model only)

The SQLite integration suite now also drives the full existing strict
Jeeves planner, reasoning-step executor, host verifier and finalizer through
three independently reserved and committed ExecutionSpine native requests.
A script-shaped synthetic backend returns deterministic model-output JSON,
while host planning contracts, token usage, checkpoints, model identity,
SQLite/WAL commits and outbox accounting remain real implementations.

The test checks that the strict agent returns a completed bounded answer,
uses exactly three source-bound model requests, performs zero ungranted
tools, and generates exactly three committed SQLite receipts and events.
Foreign-tenant attempts must be blocked before the first model call.

This is *interface* evidence. It is not evidence that an actual GGUF can
follow the planning/finalization schema, that the model reaches acceptable
reasoning quality, that the target laptop handles a cold real inference,
or that the app has achieved a complete operational AI deployment.

## Required source validation

After the source publication and repairs are complete, run these in order:

1. python -m unittest skeleton.testing.test_jeeves_native_prompt_and_schema -v
2. python -m unittest skeleton.testing.test_jeeves_native_provider_bridge -v
3. python -m unittest skeleton.testing.test_jeeves_native_chat -v
4. python -m unittest skeleton.testing.test_jeeves_native_signed_evidence -v
5. python -m unittest skeleton.testing.test_jeeves_native_repl -v
6. python -m unittest skeleton.testing.test_jeeves_native_acceptance_cli -v
7. python -m unittest skeleton.testing.test_jeeves_native_quality_eval -v
8. python -m unittest skeleton.testing.test_jeeves_native_sqlite_integration -v
9. python -m unittest skeleton.testing.test_jeeves_native_source_tool -v
10. python -m unittest skeleton.testing.test_jeeves_native_operator_preflight -v
11. python -m unittest skeleton.testing.test_jeeves_native_source_preflight -v
12. python -m compileall -q skeleton/jeeves/agent/native_prompt_boundary.py skeleton/jeeves/agent/native_schema_boundary.py skeleton/jeeves/agent/native_receipt_boundary.py skeleton/jeeves/agent/native_provider.py skeleton/jeeves/agent/native_runtime.py skeleton/jeeves/agent/native_readiness.py skeleton/jeeves/agent/native_chat.py skeleton/jeeves/agent/native_repl.py skeleton/jeeves/agent/native_signed_evidence.py skeleton/jeeves/agent/native_source_tool.py skeleton/jeeves/agent/native_operator_preflight.py skeleton/jeeves/agent/native_source_preflight.py skeleton/jeeves/agent/native_acceptance_cli.py skeleton/jeeves/agent/native_quality_eval.py skeleton/jeeves/agent/native_eval_cli.py skeleton/jeeves/agent/native_cli.py
13. python scripts/check_architecture_map.py
14. python scripts/check_ai_app_construction.py
15. python scripts/check_capability_interfaces.py
16. python scripts/check_provider_bootstrap.py
17. python scripts/check_enterprise_ai_superiority.py --json
18. python scripts/check_enterprise_ai_implementation_notes.py --json

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
