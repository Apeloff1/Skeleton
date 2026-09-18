# Shell AI 2026 Architecture

## Purpose

The Shell AI layer turns Skeleton's hardened process execution plane into a
model-facing execution substrate without giving a model a subprocess primitive.

The design assumes models can be strong planners, critics, routers, and
summarizers.

It does not assume that model output is authority.

The model proposes.

Deterministic controls review.

Human approval can authorize an exact reviewed proposal.

ShellService executes.

Receipts and verification describe what actually happened.

This distinction is the core architecture.

## Design target

The target is an agent runtime that can support Jeeves, specialist planners,
external model providers, and MCP-compatible tool clients while retaining one
host-process security boundary.

The design includes:

- structured model output
- typed tools
- strict protocol parsing
- tool input guardrails
- tool output guardrails
- human approval
- explicit sessions
- deterministic risk
- effect declarations
- bounded replanning
- provider health
- provider circuit breakers
- rate limiting
- staged policy rollout
- stale-plan detection
- execution provenance
- tamper-evident decision evidence
- outcome memory
- confidence calibration
- eval datasets
- adversarial red-team suites
- regression history
- MCP 2026 tool export
- bounded long-running task state

No item on that list may create an alternate process creation path.

## Fundamental invariant

A planning model never receives:

- a raw subprocess handle
- a shell parser
- a host executable path
- ambient environment values
- resolved secret values
- unrestricted process spawning
- direct ShellRunner authority
- direct ShellExecutor authority
- direct worker ownership
- direct queue mutation authority
- direct policy-widening authority

A planning model receives logical tool descriptions and bounded context.

A planning model returns structured actions.

Structured actions must survive deterministic review before becoming
ShellCommand values.

## Execution stack

The normal execution stack is:

AIIntent

AIToolRouter

AIModelRequest

AIModelPort

AIModelResponse

ModelOutputGuard

AIRiskAssessor

AIShellPolicy

optional human approval

AIPlanCompiler

ExecutionPlan

AIShellService stale-plan check

ShellService

ShellPlanExecutor

ShellDispatcher

ShellExecutor

ShellRunner

operating-system child process

The model is therefore several layers above child creation.

## Evidence stack

The return path is:

ShellResult

ExecutionReceipt

PlanExecutionReport

PlanVerifier

AIObservation

tool output guardrails

AIOutcomeMemory

AICalibration

AIDecisionProvenance

AIDecisionJournal

AIAuditExport

Evidence remains separate from authority.

## AI intent

AIIntent is the root planning object.

It contains:

- intent ID
- bounded goal
- intent kind
- hard planning constraints
- success criteria
- bounded context

Intent kinds include:

- inspect
- build
- test
- modify
- repair
- maintain
- deploy
- analyze

Intent kind is a routing signal.

Intent kind is not a capability grant.

## Intent constraints

IntentConstraint narrows planning.

It can define:

- allowed logical commands
- denied logical commands
- maximum action count
- maximum per-action timeout
- whether network effects are acceptable
- whether writes are acceptable
- whether destructive actions are acceptable
- whether reversibility is required

Constraint values are caller or policy data.

The model cannot widen them.

## Verification criteria

VerificationCriterion represents an observable success requirement.

A criterion has:

- criterion ID
- description
- required flag
- optional logical command binding
- accepted return-code set

PlanVerifier is passive.

It evaluates evidence already produced by the reviewed plan.

It does not secretly execute a new command.

If active verification is required, active verification should itself be a
separate reviewed plan.

## AI action

AIAction is the command-shaped object exposed to model output.

It contains:

- action ID
- logical command
- argv tuple
- optional cwd
- opaque environment references
- timeout
- dependencies
- continue-on-failure flag
- bounded purpose summary

AIAction has no host executable path field.

AIAction has no raw shell field.

AIAction has no secret value field.

## Environment references

A model may request an environment key through an opaque reference.

For example:

TOKEN -> secret/github-token

The model does not receive the resolved value.

AIPlanCompiler calls an external environment resolver.

The resolver receives:

- action ID
- environment key
- opaque reference

The resolver returns a string value.

Compilation fails when a reference remains unresolved.

The final command still passes ordinary environment policy.

## Model protocol

AIModelResponse is versioned.

Protocol version one is strict.

The parser rejects:

- unknown response fields
- unknown proposal fields
- unknown action fields
- malformed JSON
- invalid UTF-8
- oversized responses
- unbounded action arrays
- malformed dependency lists
- invalid confidence
- invalid uncertainty
- duplicate action IDs
- unknown dependencies

Model output is treated as untrusted external input.

## Structured response schema

The AI shell exports a JSON-schema-like contract.

The schema covers:

- protocol version
- request ID
- proposal identity
- intent identity
- actions
- confidence
- uncertainty
- assumptions
- rationale summary
- model ID
- warnings
- metadata

The schema rejects additional properties.

The schema has a deterministic digest.

Decision provenance binds that digest.

## Rationale handling

The protocol stores rationale_summary.

It does not request hidden chain-of-thought.

It does not require private reasoning traces.

It does not place internal model reasoning in the decision journal.

The rationale summary is bounded review metadata only.

## Command catalog

CommandCatalog remains the source of logical command contracts.

AIToolCatalog creates a model-visible projection.

AIToolCard exposes:

- logical command name
- description
- tags
- required capability names
- allowed environment key names
- timeout ceiling
- stdin policy
- nonzero-return policy

AIToolCard intentionally omits the executable path.

## Portable manifest

AIToolManifest packages:

- manifest version
- tool catalog digest
- effect digest
- response schema digest
- model-visible tool cards
- structured response schema

This allows provider adapters and remote tool protocols to share the same
reviewed shell contract.

## Effect contracts

EffectContract declares expected command effects.

Current effect classes include:

- read filesystem
- write filesystem
- delete filesystem
- network
- process control
- package change
- VCS read
- VCS write
- secret access
- privileged execution
- deployment
- external side effect

Effects are review data.

They do not replace operating-system containment.

## Effect registry

EffectRegistry is bounded and deterministic.

A model-visible command without an effect contract is treated as uncertain.

AIShellPolicy denies unknown effects by default.

AIShellDiagnostics reports missing effect contracts.

Adding a model-visible command is therefore a deliberate governance event.

## Idempotency metadata

EffectContract can declare idempotency.

Idempotency influences routing and planning.

It does not grant retry authority.

It does not bypass command budgets.

It does not bypass ShellExecutor.

Incorrect idempotency metadata is an operational defect.

## Reversibility metadata

EffectContract can declare reversibility.

A reversible contract may declare a compensation command.

Reversibility is planning metadata.

It is not a database transaction.

It is not proof that all external state can be restored.

## Transaction planning

AITransactionPlanner constructs reverse-order compensation metadata.

It identifies:

- source action
- compensation command
- uncompensated actions

It does not execute compensation automatically.

A compensation command must pass the same review path as any other action.

## Deterministic risk

AIRiskAssessor computes risk without a model.

Risk dimensions include:

- filesystem
- network
- secrets
- privilege
- destructive behavior
- external side effects
- complexity
- uncertainty
- reversibility

Model critique cannot override risk.

## Risk bands

Risk bands are:

- low
- medium
- high
- critical

Critical proposals are not directly executable by AI policy.

Risk bands are configuration evidence, not shell authority.

## Constraint conflicts

Risk rises when proposal effects conflict with intent constraints.

Examples include:

- network effect while network is disallowed
- write effect while writes are disallowed
- destructive effect while destruction is disallowed
- nonreversible plan while reversibility is required

These conflicts are visible in review.

## Confidence

AIPlanProposal includes model-reported confidence.

Confidence is bounded between zero and one.

Confidence is not authority.

AIShellPolicy can define a minimum confidence.

AICalibration compares model confidence to actual outcomes.

## Uncertainty

AIPlanProposal includes model-reported uncertainty.

Uncertainty is also bounded.

Uncertainty is not assumed to be one minus confidence.

AIShellPolicy can reject high uncertainty.

Risk scoring can add uncertainty penalties.

## Guardrails

ModelOutputGuard performs deterministic proposal checks.

It checks:

- intent identity
- command constraints
- timeout ceilings
- step ceilings
- shell-like metacharacters
- interpreter entry points
- environment references

Some findings are warnings.

Some findings are errors.

Shell-like punctuation remains literal argv at the process boundary.

## Free-form shell fields

Free-form fields such as shell, raw_command, command_line, and script are not
part of the supported protocol.

ModelOutputGuard can reject those fields when inspecting free-form payloads.

The supported command surface is AIAction.

## Tool input guardrails

AIToolGuardRegistry supports input guards per logical command.

Every guard runs before compilation and execution.

A denial raises ToolGuardTripwire.

A tripwire is not advisory.

A model cannot override it.

## Tool output guardrails

Output guards run against AIObservation after a tool call.

They can fail the AI session.

They cannot undo a side effect that already happened.

Input policy is therefore the prevention layer.

Output policy is the result-validation layer.

## Observation model

AIObservation is metadata-first.

By default it includes:

- observation ID
- correlation ID
- logical command
- success
- return code
- timeout flag
- output-limit flag
- duration
- stdout byte count
- stderr byte count
- stdout digest
- stderr digest

It does not include raw output by default.

## Observation policy

ObservationPolicy can expose:

- digest only
- metadata only
- redacted excerpt

Redacted excerpt mode applies bounded text exposure and configured blocked
patterns.

Applications should default to metadata only.

## Safe excerpts

ObservationBuilder accepts an explicit excerpt filter.

The filter receives child output.

The filter must return a string.

The string is bounded.

Raw stdout should never be forwarded automatically to a planning model.

## AI autonomy policy

AIShellPolicy defines:

- autonomy mode
- maximum actions
- minimum confidence
- maximum uncertainty
- auto-execute risk bands
- approval-required risk bands
- denied effects
- unknown-effect behavior
- reversibility requirement

AIShellPolicy has a deterministic fingerprint.

## Autonomy modes

Observe means no execution authority from the AI layer.

Propose means the model can propose but human approval is required.

Low-risk autonomous means configured low-risk plans may execute after
deterministic review.

Supervised supports broader reviewed operation according to policy.

None of these modes widen ShellExecutor capability grants.

## Policy revisions

AIPolicyStore is revisioned.

It supports compare-and-swap.

Concurrent policy edits cannot silently overwrite each other.

Decision provenance records the policy fingerprint used.

## Policy migration

AIPolicyMigrationPlanner classifies changes.

Narrowing changes are usually safe.

Widening changes require review.

Some narrowing changes are breaking because they can invalidate existing
clients.

Examples of review-required changes include:

- larger action ceiling
- lower confidence threshold
- higher uncertainty ceiling
- removing effect denials
- adding autonomous risk bands
- relaxing reversibility

## Policy rollout

AIPolicyRolloutManager supports:

- prepared
- canary
- broad
- complete
- rolled back

Canary selection is deterministic by rollout ID plus principal.

A prepared rollout selects nobody.

A broad rollout selects everybody.

A completed rollout cannot be implicitly rolled back.

A new explicit change is required after completion.

## Human approval

AIPlanApproval binds:

- principal
- intent fingerprint
- proposal fingerprint
- approver
- expiry

Approval is single-use.

Approval cannot cross principals.

Approval cannot cross proposals.

Approval cannot cross intents.

## Human review view

AIReviewBuilder produces a redacted but complete review surface.

It includes:

- goal
- proposal identity
- proposal fingerprint
- model ID
- confidence
- uncertainty
- risk
- policy reasons
- guardrail findings
- assumptions
- logical command
- exact argv
- cwd
- environment key names
- timeout
- effect declarations
- reversibility
- compensation command
- dependencies
- continue-on-failure state

It does not include resolved environment values.

It does not include executable host paths.

## Review queue

AIReviewQueue supports asynchronous human review.

Queue items transition through:

- pending
- claimed
- approved
- rejected
- expired

A claim has a claim ID.

A stale or foreign claim cannot decide the review.

This fences concurrent reviewers.

## Planning budget

AIBudget bounds:

- model calls
- candidates
- proposed actions
- critique calls
- verification rounds

Planning loops therefore have a deterministic ceiling.

## Model provider health

ProviderHealthRegistry tracks:

- attempts
- successes
- failures
- consecutive failures
- consecutive successes
- average latency
- last error type
- explicit quarantine

Health states include:

- unknown
- healthy
- degraded
- unhealthy
- quarantined

Provider health affects routing.

It does not grant shell authority.

## Model circuit breaker

ModelCircuitRegistry prevents repeated provider failure amplification.

Circuit states are:

- closed
- open
- half-open

Repeated failures open the circuit.

Recovery time permits half-open testing.

Successful half-open calls close the circuit.

Failure in half-open reopens it.

## Model call rate limiting

AIModelRateLimiter uses token buckets.

Limits can be global or provider-specific.

Planning rate limits are separate from shell command budgets.

This prevents model-side overload from becoming host-side overload.

## Provider routing

AIProviderRouter scores providers by:

- health
- latency
- empirical trust
- structured-output support
- tool-use support
- critique support

Routing is advisory.

The selected provider still produces untrusted output.

## Resilient planning

ResilientAIPlanner can try multiple AIPlanner instances.

A failed provider can fall back to another.

Quarantined providers are skipped.

Open circuits are skipped.

Rate-limited providers are skipped.

Provider fallback changes who proposes.

It does not change what may execute.

## Bounded replanning

BoundedReplanner performs observation-driven planning for a fixed number of
rounds.

Replanning stops on:

- accepted plan
- policy denial
- duplicate proposal
- maximum rounds

Replanning never becomes an unbounded reflection loop.

## Specialist routing

SpecialistRegistry maps intent kinds to planner models.

Specialists have deterministic priority.

Specialist selection is model routing only.

It does not change the shell command catalog.

## Candidate selection

CandidateSelector compares multiple proposals without executing them.

Candidate utility uses:

- confidence
- uncertainty
- risk
- action count
- guardrail status
- policy status

Unsafe candidates receive severe penalties.

## Consensus

ProposalConsensus groups proposals by command shape.

Shape includes:

- logical command
- argv
- cwd
- environment key names
- timeout
- dependencies
- continue-on-failure

Model identity does not affect shape.

Consensus is advisory.

Consensus cannot authorize execution.

## Compiler

AIPlanCompiler bridges model data into ExecutionPlan.

It validates:

- intent identity
- step count
- command constraints
- timeout constraints
- environment references

ExecutionPlan then validates graph structure.

## Compiled plan evidence

CompiledAIPlan records:

- intent fingerprint
- proposal fingerprint
- effect digest
- environment reference names
- plan fingerprint

It does not record resolved environment values.

## Stale-plan pinning

AIShellService pins a reviewed plan surface.

The pin binds:

- intent fingerprint
- proposal fingerprint
- tool catalog digest
- effect digest
- AI policy fingerprint
- model schema digest
- execution plan fingerprint

Before execution the service recomputes those values.

Any mismatch rejects the plan as stale.

This prevents time-of-review versus time-of-execution drift.

## AI session

AIShellSession has explicit phases:

- new
- planning
- proposed
- review
- approved
- executing
- verifying
- complete
- denied
- cancelled
- failed

Invalid transitions fail.

Terminal states cannot restart silently.

## AI session checkpoint

AISessionCheckpoint records:

- session identity
- phase
- intent identity and fingerprint
- proposal identity and fingerprint
- transition count
- journal root
- receipt root
- policy fingerprint
- tool catalog digest
- effect digest

The checkpoint contains no child output.

## Session store

AISessionStore maintains checkpoint revisions.

It uses compare-and-swap semantics.

A changed checkpoint supersedes the prior version.

Identical checkpoints are idempotent.

History is bounded.

## Recovery

AIRecoveryManager compares checkpoint state with current control state.

Recovery decisions include:

- none
- resume review
- require replan
- require verification
- mark failed
- manual review

Policy, tool, or effect drift requires replanning.

Journal corruption requires manual review.

Interrupted execution generally requires verification.

## AI service lifecycle

AIServiceState phases include:

- new
- starting
- ready
- degraded
- maintenance
- draining
- stopping
- stopped
- failed

AIShellService only creates new sessions when ready.

The AI service also requires the lower-level ShellService to be ready.

## AI diagnostics

AIShellDiagnostics checks:

- effect coverage
- structured-output model capability
- tool-use capability
- empty tool catalog
- orphan effect contracts

Diagnostics are run during service start.

## Quarantine

AIQuarantine can quarantine:

- model
- proposal fingerprint
- logical command

Quarantine can be permanent or time bounded.

AIShellService checks quarantine before review and before execution.

## Outcome memory

AIOutcomeMemory stores bounded outcome metadata.

It records:

- intent fingerprint
- proposal fingerprint
- risk score
- success
- duration
- verification result
- command count
- model ID
- observation time

It does not store raw child output.

## Calibration

AICalibration measures:

- attempts
- successes
- verified successes
- average latency
- confidence error
- smoothed success probability

Calibration is advisory.

## Model trust

ModelTrustRegistry combines empirical success, verification rate, and confidence
calibration into a trust signal.

Small sample sizes are discounted.

Trust cannot grant capabilities.

## Decision journal

AIDecisionJournal is hash chained.

Events contain:

- sequence
- previous hash
- event hash
- event kind
- timestamp
- session ID
- intent ID
- proposal ID
- bounded summary
- bounded data

It is not a hidden reasoning store.

## Decision provenance

AIDecisionProvenance binds:

- intent fingerprint
- proposal fingerprint
- tool catalog digest
- effect digest
- policy fingerprint
- schema digest
- model ID
- risk score
- approval ID
- receipt root

A completed AI execution can therefore be tied back to exact contracts.

## Audit export

AIAuditExporter exports redacted decision evidence.

It filters event data through an explicit allowlist.

Raw output is not exported.

Unknown event data is dropped.

## Replay

AIDecisionReplay verifies journal integrity and expected configuration digests.

Replay does not call a model.

Replay does not execute a command.

## Metrics

AIShellMetrics keys by logical command.

It tracks:

- planning attempts
- planning failures
- reviews
- approvals
- executions
- execution failures
- verification failures
- guardrail blocks
- average reviewed risk

Raw argv is not used as a metric key.

## Evaluation dataset

AIEvalDataset is versioned and digestible.

Each case can define:

- intent
- required commands
- forbidden commands
- required effects
- forbidden effects
- maximum actions
- approval expectation
- metadata

Evaluation datasets are immutable data.

## Eval runner

AIEvalRunner is planning-only.

It asks a planner for a proposal.

It runs deterministic critique.

It checks case expectations.

It does not execute shell commands.

This allows frequent safety and quality evaluation without host side effects.

## Red-team suite

AIRedTeamRunner evaluates adversarial proposal shapes.

Default cases include:

- command allowlist escape
- timeout widening
- shell-like punctuation
- interpreter code entry point

More repository-specific adversarial cases should be added over time.

## Regression history

AIRegressionHistory stores bounded eval runs.

It compares:

- pass rate
- case regressions
- case improvements

Model rollout should stop on meaningful safety regression.

## MCP 2026 surface

MCPToolSurface exports AI shell tools through a stateless, transport-neutral
tool surface.

The surface identifies protocol revision 2026-07-28.

Tool descriptors expose:

- tool name
- description
- full object-root input schema
- object-root output schema
- effect annotations
- idempotency
- reversibility
- approval recommendation

Executable host paths are omitted.

## MCP tool listing

MCPToolList is deterministic.

It contains:

- protocol revision
- ordered tools
- ttlMs
- cacheScope
- digest

Clients can cache a tool list and detect catalog change.

## MCP routing headers

MCPRequestEnvelope exposes:

- Mcp-Method
- Mcp-Name

This allows a transport adapter or gateway to route and meter requests without
parsing an arbitrary command string.

## MCP authorization

MCPAuthorization maps principals to:

- allowed tools
- denied tools
- maximum timeout

Unknown principals are denied.

A timeout above principal policy is denied.

This authorization layer remains additive to AI and shell policy.

## MCP gateway

MCPAIShellGateway validates:

- protocol revision
- method
- tool existence
- argument shape
- environment reference shape
- principal authorization

The gateway returns MCPPreparedToolCall.

It does not execute the tool.

The prepared call still enters the normal AI shell review path.

## MCP long-running tasks

MCPTaskRegistry represents explicit long-running operation state.

Task states include:

- pending
- running
- succeeded
- failed
- cancelled

Creating a task starts no background process.

Task state is orchestration metadata only.

## No hidden background execution

Constructing AI shell components starts no hidden planner loop.

Constructing MCPTaskRegistry starts no task.

Constructing AIShellService starts no model call.

Constructing AIReviewQueue starts no reviewer worker.

All active work remains explicit.

## Sandbox compatibility

The AI shell is designed to sit above stronger isolation.

A sandbox-backed future runner can preserve:

- AI intent
- model protocol
- tool cards
- effects
- risk
- approval
- compiler
- evidence
- evals
- MCP export

Stronger process containment can be added below the same model contract.

## Production readiness rule

Autonomous execution should only be enabled when:

- the command catalog is narrow
- model-visible commands have effect contracts
- argument policy is narrow
- environment policy is reviewed
- workspace policy is reviewed
- shell diagnostics are clean
- AI diagnostics are clean
- evals pass
- red-team cases pass
- policy revision is known
- approval path is tested
- receipt chain verifies
- decision journal verifies
- incident procedure exists
- provider fallback does not widen authority

## Conclusion

A production AI shell is not a language model with terminal access.

It is a typed planning system wrapped around a deterministic execution authority.

Models provide intelligence.

Policy provides authority.

The runner provides process containment.

Evidence provides accountability.

Those roles remain deliberately separate.
