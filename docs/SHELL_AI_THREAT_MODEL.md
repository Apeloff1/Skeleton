# Shell AI Threat Model

## Purpose

This threat model covers risks introduced when language models can plan host
process activity.

It complements the lower-level Shell Execution Plane Threat Model.

The lower-level threat model focuses on process creation and OS-facing
boundaries.

This document focuses on:

- model output
- prompt and tool injection
- model routing
- model-provider failure
- structured tool contracts
- effect declarations
- planning loops
- human approval
- observations
- verification
- memory
- calibration
- policy rollout
- MCP exposure
- recovery
- evaluation
- provenance

## Primary security objective

The key security objective is:

A compromised, hallucinating, prompt-injected, misconfigured, or simply wrong
model must not gain more host execution authority than deterministic policy has
already granted.

Model quality is not an authorization boundary.

Model trust is not an authorization boundary.

Model consensus is not an authorization boundary.

Model confidence is not an authorization boundary.

## Trust assumptions

The AI shell treats the following as untrusted or partially trusted inputs:

- model responses
- model rationale summaries
- tool descriptions from configuration
- prior model observations
- user-provided goals
- user-provided context
- MCP request arguments
- external provider metadata
- model confidence
- model uncertainty
- model critique
- candidate consensus
- cached planning results
- long-running task metadata

The following are trusted code or governance configuration:

- ShellRunner
- ShellPolicy
- ShellExecutor
- CommandCatalog
- ArgumentPolicy
- EnvironmentPolicy
- WorkspacePolicy
- effect contracts after review
- AIShellPolicy after review
- tool input guard code
- tool output guard code
- secret/environment resolver
- policy store
- approval registry
- quarantine controls
- review-queue state machine
- eval dataset ownership
- operator actions

Trusted code can still contain defects.

Defense in depth remains necessary.

## Threat: free-form shell output

A model may output a command line rather than a structured action.

Examples include:

rm -rf ...

curl ... pipe sh

python -c ...

The supported AI protocol has no raw shell field.

Unknown action fields fail parsing.

ModelOutputGuard can reject known free-form shell field names.

AIPlanCompiler only accepts AIAction.

ShellRunner still uses argv-only process creation.

## Threat: shell syntax smuggling through argv

A model may place semicolons, pipes, redirects, wildcards, command substitution,
or quotes in arguments.

ModelOutputGuard records a shell-metacharacter warning.

Those characters remain literal argv at the runner boundary.

Residual risk remains if the authorized executable itself interprets an argument
as shell or code.

ArgumentPolicy must therefore constrain interpreters and wrapper commands.

## Threat: executable-path selection

A model may try to choose /bin/sh, an attacker-controlled executable, or an
alternate interpreter path.

AIAction contains a logical command name only.

AIToolCatalog omits host paths.

MCP tool descriptors omit host paths.

ShellPolicy resolves the logical name to a pinned executable.

A model cannot introduce a path through the normal protocol.

## Threat: command-catalog poisoning

A developer or compromised configuration could expose an overly broad command.

AIToolCatalog faithfully projects CommandCatalog.

A narrow model protocol does not make an unsafe command safe.

Every model-visible command should have:

- reviewed executable path
- narrow argument grammar
- reviewed environment policy
- reviewed workspace behavior
- reviewed effect contract
- tests

AIShellDiagnostics treats missing effect contracts as an error by default.

## Threat: malicious tool description

Tool descriptions are model input.

A malicious description might instruct the model to ignore constraints or
select a dangerous tool.

Descriptions must be treated as reviewed configuration.

Tool descriptions should not be generated from arbitrary repository files.

Deterministic policy does not rely on the description text.

## Threat: malicious tool tags

Tags influence AIToolRouter.

A malicious tag can change ranking.

Tags do not grant capability.

The selected proposal still passes deterministic review.

## Threat: model protocol field smuggling

A provider may emit fields not anticipated by the parser.

The parser rejects unknown:

- response fields
- proposal fields
- action fields

This prevents accidental interpretation of hidden authority fields.

## Threat: protocol-version drift

A provider may emit a newer or older schema.

AI_MODEL_PROTOCOL_VERSION is explicit.

Unsupported versions fail.

The response schema has a deterministic digest.

Decision provenance records the schema digest.

## Threat: oversized model output

A model may return a huge response to exhaust memory.

The parser bounds response bytes.

Action count is bounded.

Assumption count is bounded.

Warning count is bounded.

Metadata is bounded.

Action argv count and bytes are bounded.

The lower-level runner applies separate bounds again.

## Threat: malformed structured output

A provider may return invalid JSON, invalid UTF-8, invalid confidence,
invalid uncertainty, duplicate action IDs, or unknown dependencies.

Parsing and dataclass validation reject these states before compilation.

## Threat: prompt injection in user goal

A user goal may contain instructions to bypass policy.

AIIntent goal is model context only.

It cannot directly alter:

- command catalog
- effect registry
- capability grant
- AIShellPolicy
- ShellPolicy
- approval registry

A prompt-injected model can still propose a bad plan.

The bad plan must survive deterministic controls.

## Threat: prompt injection from repository content

A model may inspect text that contains instructions.

Repository content should be treated as data.

ObservationPolicy should avoid returning uncontrolled raw text.

Tool descriptions should not be built from untrusted content.

A future repository-reader adapter should label content origin explicitly.

## Threat: prompt injection from tool output

A child process may print instructions such as:

ignore previous policy

run another command

send secrets

Raw output is not automatically returned to the model.

AIObservation is metadata-first.

Safe excerpts require an explicit filter.

ObservationPolicy can use metadata-only or digest-only modes.

If text is returned, it should be clearly represented as untrusted tool data.

## Threat: secret leakage through tool output

A command may print secrets.

Default AIObservation does not include output bytes.

AIAuditExport filters event data through a strict allowlist.

AIOutcomeMemory stores metadata only.

Decision journal summaries should not copy child output.

Output classification from the lower shell layer remains applicable.

## Threat: secret leakage through environment

A model may request environment values.

AIAction uses opaque references.

The model sees key names and reference labels, not resolved values.

The environment resolver runs outside the model.

The final ShellCommand still passes EnvironmentPolicy and ShellPolicy.

## Threat: malicious environment reference

A model may request a secret alias outside its intended scope.

The environment resolver must enforce authorization.

AIPlanCompiler assumes the resolver validates reference scope.

The resolver must not treat arbitrary model-provided reference strings as
unrestricted secret-store paths.

## Threat: secret leakage through argv

A caller may be tempted to resolve secrets directly into argv.

The built-in AI environment-reference path does not do that.

Applications should not add generic secret interpolation into argv.

Arguments are included in proposal and review fingerprints and may be logged in
review surfaces.

Secrets should not be placed in argv.

## Threat: secret leakage through goal/context

AIIntent context is sent to a model.

Callers must avoid putting secrets in context.

Context is not a secret transport.

Sensitive information should use dedicated retrieval and redaction policy.

## Threat: raw host-path leakage

AIToolCatalog and MCPToolSurface omit executable paths.

Review views omit executable paths.

The model can know logical command names without learning exact host layout.

This reduces host-specific prompt surface and executable substitution pressure.

## Threat: cwd escape

AIAction may include cwd.

AIPlanCompiler forwards cwd only after intent checks.

ShellRunner and WorkspacePolicy enforce actual path containment.

The AI layer does not replace filesystem containment.

## Threat: absolute-path file access from child

Cwd containment alone does not prevent an allowed executable from opening an
absolute path.

A hostile command may still access files available to its process identity.

Use workspace isolation or sandboxing for hostile code.

Effect metadata is not a filesystem sandbox.

## Threat: network access despite declared no-network effect

An effect contract is declarative.

A command marked read-only might still make a network call if implemented
incorrectly.

For adversarial code, enforce network isolation at OS, container, or sandbox
level.

Effect policy provides governance and review, not kernel enforcement.

## Threat: false effect metadata

A command may be mislabeled.

This can reduce risk score incorrectly.

Effect contracts should be code-reviewed.

High-risk commands should be verified by sandbox policy and tests.

Eval datasets should include side-effect expectations.

## Threat: missing effect metadata

A model-visible command without an effect contract creates uncertainty.

AIRiskAssessor records unknown commands.

AIShellPolicy denies unknown effects by default.

AIShellDiagnostics reports missing effect contracts.

## Threat: effect-registry drift

Effects may change after a plan is reviewed.

AIShellService pins effect digest at review.

Execution revalidates the digest.

Drift makes the plan stale.

The plan must be reviewed again.

## Threat: tool-catalog drift

A command description, capability, timeout, or model-visible tool list may change
after review.

AIShellService pins the tool-catalog digest.

Execution rejects drift.

MCP tool lists include a deterministic digest and cache hints.

## Threat: AI-policy drift

AIShellPolicy may change after review.

AIShellService pins the policy fingerprint.

Execution rechecks current governance policy.

A changed policy invalidates the reviewed plan.

## Threat: model-schema drift

The AI response schema may change after a plan is reviewed.

PlanPin records schema digest.

Execution staleness checks compare schema digest.

A plan reviewed under another schema should be re-reviewed.

## Threat: plan mutation after review

A plan or proposal could be mutated before execution.

AIPlanProposal and ExecutionPlan are frozen structures.

Proposal fingerprint and plan fingerprint are pinned.

Execution rejects mismatch.

## Threat: intent mutation after review

The caller may change the intent.

Intent fingerprint is pinned.

Approval also binds intent fingerprint.

Changed intent invalidates prior approval.

## Threat: model confidence spoofing

A model can report confidence of one.

Confidence does not grant authority.

Risk remains deterministic.

Guardrails remain deterministic.

Policy remains deterministic.

Calibration measures confidence error over time.

## Threat: uncertainty spoofing

A model can report uncertainty of zero.

Unknown effects and policy conflicts remain independent.

Calibration and evals can reveal systematic overconfidence.

## Threat: low sample trust inflation

ModelTrustRegistry discounts small sample counts.

Trust is advisory anyway.

Trust cannot alter ShellCapability grants.

## Threat: calibration poisoning

An attacker could create many easy tasks to inflate success metrics.

Calibration should be segmented by workload class in high-assurance systems.

Trust remains routing advice only.

## Threat: model trust becomes authorization

This must not happen.

Provider routing may prefer a model.

No trust score is consumed by ShellExecutor.

No trust score is consumed by ShellRunner.

## Threat: model-provider compromise

A provider can return arbitrary protocol-valid proposals.

Provider compromise still faces:

- intent constraints
- guardrails
- effects
- risk
- AI policy
- approval
- stale-plan checks
- ShellService
- ShellExecutor
- ShellRunner

Compromise is therefore constrained by deterministic authority.

## Threat: provider outage

A failed provider could block planning.

ResilientAIPlanner can fall back.

Provider fallback must not widen tool or policy surfaces.

Every fallback planner should point at the same intended catalog and policy
fingerprint.

## Threat: provider failure amplification

Repeated provider errors could cause repeated costly calls.

ModelCircuitRegistry opens after configured failures.

AIModelRateLimiter bounds call rate.

AIBudget bounds calls per planning session.

## Threat: provider quarantine bypass

A quarantined provider should not be selected.

ProviderHealthRegistry can mark quarantine.

AIShellGovernance can quarantine a model ID.

AIShellService checks governance quarantine before review and execution.

## Threat: rate-limit key explosion

An attacker might create many unique provider keys.

AIModelRateLimiter has a maximum key count.

Keys should be stable model/provider IDs, not arbitrary user text.

## Threat: planning budget exhaustion

A model could trigger repeated calls, candidates, critiques, or verification
rounds.

AIBudget places independent ceilings on each.

Exhaustion fails explicitly.

## Threat: unbounded self-reflection

BoundedReplanner has a maximum round count.

It stops on duplicate proposals.

It stops on policy denial.

It stops when an acceptable plan appears.

No default infinite reflection loop exists.

## Threat: replanning feedback poisoning

Prior observations may include unsafe text.

BoundedReplanner expects sanitized mappings.

ObservationPolicy should be applied before textual observations are provided.

## Threat: duplicate proposal loop

A model might return the same rejected plan repeatedly.

BoundedReplanner fingerprints proposals.

Duplicate output stops the loop.

## Threat: candidate flooding

A model ensemble might create many candidate proposals.

AIBudget limits candidates.

CandidateSelector deduplicates identical fingerprints.

Candidate evaluation performs no execution.

## Threat: consensus as authority

Multiple models may agree on a dangerous plan.

ProposalConsensus only groups and reports.

Consensus does not grant execution.

The proposal still passes risk, policy, approval, and shell controls.

## Threat: colluding model critic

A model critic can say a plan is safe.

AIPlanCritic treats model critique as advisory.

A model critic cannot clear deterministic errors.

## Threat: specialist compromise

A specialist planner can return malicious actions.

Specialist selection changes who proposes.

It does not change tool authority.

The specialist output enters the same deterministic pipeline.

## Threat: handoff authority widening

A future handoff implementation must not automatically union capabilities from
source and destination models.

Authority must remain based on deterministic shell policy.

## Threat: direct interpreter access

An argv-safe interpreter may still execute arbitrary code with -c or similar
flags.

ModelOutputGuard warns on interpreter entry points.

Command ArgumentPolicy should deny unsafe interpreter modes where appropriate.

Hostile code requires sandboxing.

## Threat: package manager misuse

Package changes should be marked PACKAGE_CHANGE.

Package commands can execute lifecycle scripts and change dependencies.

They should generally require review or stronger sandboxing.

## Threat: deployment misuse

Deployment should be marked DEPLOYMENT or EXTERNAL_SIDE_EFFECT.

Deployment usually requires human approval.

Critical deployment proposals should be denied by policy.

## Threat: privileged execution

PRIVILEGED is denied by default AIShellPolicy.

Enabling it is an explicit high-risk policy change.

OS privilege controls remain authoritative below the AI layer.

## Threat: destructive VCS commands

VCS_WRITE contributes risk.

Commands such as force reset, branch deletion, or destructive clean require
narrow argument policy.

A generic git command with unrestricted argv is not safe simply because process
creation is argv-only.

## Threat: destructive filesystem commands

DELETE_FILESYSTEM is high risk.

Effect policy should mark deletion.

Argument policy should constrain paths.

Workspace policy should constrain roots.

A sandbox should be used for model-generated destructive work where possible.

## Threat: human approval ambiguity

A reviewer may approve without understanding the plan.

AIReviewView exposes:

- goal
- exact argv
- cwd
- environment key names
- effects
- risk
- confidence
- uncertainty
- dependencies
- reversibility
- compensation metadata
- proposal fingerprint

Approval UI should render this information clearly.

## Threat: stale human approval

An approval may remain after plan change.

AIPlanApproval binds proposal fingerprint.

Any proposal change invalidates the approval.

## Threat: cross-principal approval replay

Approval binds principal.

An approval for Alice cannot authorize Bob.

## Threat: cross-intent approval replay

Approval binds intent fingerprint.

A plan used for a different intent requires new approval.

## Threat: approval replay after consumption

Approval is single-use.

Consumed approval fails future require calls.

## Threat: expired approval

Approval has monotonic TTL.

Expired approval is rejected.

## Threat: approval after policy change

AIShellService stale-plan checks reject policy drift even if an old approval
still exists.

A reviewer therefore cannot accidentally authorize execution under a different
AI policy revision.

## Threat: concurrent human reviewers

Two reviewers may race to decide one proposal.

AIReviewQueue issues a claim ID.

Only the active claim can decide.

Stale or foreign claims fail.

## Threat: review queue expiration

A pending approval request may become stale.

ReviewQueueItem has expiry.

Expired pending or claimed items transition to expired.

## Threat: approval queue as execution queue

AIReviewQueue only stores review decisions.

It does not execute commands.

An approved review still needs the normal execution path.

## Threat: output guard misunderstanding

Output guardrails run after a tool executes.

They can block model consumption of a bad result.

They cannot undo a side effect.

Use input controls for side-effect prevention.

## Threat: automatic compensation

Automatically compensating could double damage.

AITransactionPlanner produces metadata only.

Compensation execution requires a new reviewed plan.

## Threat: false reversibility

A command may be labeled reversible when external effects are not fully
reversible.

Reversibility is not a transaction guarantee.

Human review should consider external state.

## Threat: verification omitted

If explicit success criteria are absent, PlanVerifier falls back to plan
execution success.

Critical workflows should provide explicit criteria.

## Threat: model claims verification

The model does not determine VerificationReport.

Verification is based on execution evidence.

A model statement that work succeeded is not sufficient.

## Threat: verification command side effects

PlanVerifier is passive.

It does not silently run a verifier command.

If verification itself requires a command, create a separate reviewed
verification plan.

## Threat: session-state bypass

AIShellSession uses explicit allowed transitions.

A plan cannot jump from new directly to executing.

Denied and failed states are terminal.

## Threat: session restart after terminal state

Terminal session state cannot silently restart.

A new session must be created.

This makes audit history clearer.

## Threat: checkpoint secret leakage

AISessionCheckpoint contains fingerprints, roots, phase, and identities.

It does not contain raw child output.

It does not contain resolved environment values.

## Threat: checkpoint replay after policy drift

AIRecoveryManager compares policy fingerprint.

A mismatch requires replanning.

## Threat: checkpoint replay after tool drift

Tool catalog mismatch requires replanning.

## Threat: checkpoint replay after effect drift

Effect digest mismatch requires replanning.

## Threat: interrupted execution

If execution or verification was in progress, recovery should not simply rerun.

AIRecoveryManager requires verification or manual review depending on evidence.

This reduces duplicate side effects.

## Threat: journal corruption during recovery

A bad decision-journal chain triggers manual review.

Recovery does not repair or silently rewrite journal hashes.

## Threat: stale session-store writer

AISessionStore supports expected revision.

A stale writer cannot overwrite a newer checkpoint when expected revision is
used.

## Threat: idempotency-key conflict

AIIdempotencyRegistry binds a key to request digest and proposal fingerprint.

Reusing a key with different data raises conflict.

## Threat: plan-cache policy drift

AIPlanCache entries bind:

- policy fingerprint
- tool digest
- effect digest

A mismatched current surface evicts the entry.

## Threat: cache becoming authority

A cached proposal is still a proposal.

It must pass current deterministic checks before execution.

## Threat: stale plan despite cache

AIShellService execution pinning is authoritative.

Even a cache hit cannot bypass current surface validation.

## Threat: quarantine bypass by alternate identifier

Quarantine keys should use canonical model IDs, proposal fingerprints, and
logical command names.

Provider adapters should not create changing aliases to evade quarantine.

## Threat: quarantine denial-of-service

An operator can quarantine important tools or providers.

This is an intentional safety control.

Quarantine changes should be audited.

## Threat: policy rollout too broad

Policy widening should use canary rollout.

Canary selection is deterministic.

Prepared phase selects nobody.

Broad and complete select everyone.

## Threat: canary identity manipulation

If principal identity is attacker-controlled and can be changed freely, a caller
may try to seek canary inclusion or exclusion.

Principal identity should come from authenticated application identity.

## Threat: implicit rollback after completion

Completed rollout cannot be rolled back implicitly.

A new policy revision should represent a post-completion change.

This preserves clear history.

## Threat: eval execution

Eval tooling should not create host side effects.

AIEvalRunner performs planning and critique only.

It does not call ShellService.

## Threat: eval dataset poisoning

A malicious eval dataset can create misleading quality results.

Eval datasets should be versioned and reviewed.

AIEvalDataset has a digest.

Regression history should record dataset identity.

## Threat: eval overfitting

A planner can improve on a narrow fixed set while degrading elsewhere.

Production evaluation should include:

- routine tasks
- adversarial tasks
- long-horizon tasks
- approval-required tasks
- deny cases
- recovery cases
- provider-failure cases
- ambiguous goals
- stale-policy cases

## Threat: eval score used as authorization

Eval score is not an execution signal.

No evaluator feeds directly into ShellCapability.

## Threat: regression ignored during rollout

AIRegressionHistory can identify case regressions.

Policy or model rollout procedure should stop on meaningful safety regression.

## Threat: red-team suite too narrow

Default red-team cases are a seed corpus.

Repository-specific threats must be added.

Examples include:

- hidden network flags
- plugin loading
- arbitrary config path
- response-file syntax
- package lifecycle scripts
- VCS destructive flags
- interpreter escape flags
- unsafe environment variables

## Threat: metrics cardinality attack

AIShellMetrics keys by logical command only.

Raw argv, correlation ID, user text, and output are not metric dimensions.

## Threat: audit export leakage

AIAuditExporter has an allowlist of event-data keys.

Unknown fields are dropped.

Raw output is not exported.

Audit destinations still require access control.

## Threat: journal as chain-of-thought store

AIDecisionJournal stores bounded summaries.

It should not store hidden model reasoning.

It should not store raw prompts unless independently reviewed.

## Threat: journal capacity exhaustion

AIDecisionJournal has a maximum event count.

Capacity exhaustion fails rather than silently dropping integrity-linked events.

For long-running production systems, export and rotate explicitly.

## Threat: outcome-memory poisoning

Outcome memory is advisory.

A bad record can affect analytics.

It cannot change shell policy automatically.

Do not build self-modifying authority directly from memory success rates.

## Threat: provider routing poisoning

Provider health or calibration could be manipulated.

Routing changes which model proposes.

Routing still does not alter deterministic execution policy.

## Threat: compromised fallback provider

Resilient planning can fall back after failure.

Fallback providers must not have a wider command surface.

Every fallback output remains untrusted.

## Threat: all providers unavailable

ResilientAIPlanner fails closed when no provider is eligible.

It does not bypass planning and directly execute.

## Threat: model circuit bypass

Callers should use stable provider IDs.

Creating a new provider ID for every attempt defeats circuit state and should be
forbidden by integration policy.

## Threat: MCP unknown principal

MCPAuthorization denies principals without policy.

There is no implicit anonymous allow.

## Threat: MCP tool authorization confusion

MCP principal policy operates on logical tool names.

The underlying AI shell still performs its own policy checks.

MCP authorization is additive.

## Threat: MCP timeout widening

MCPPrincipalPolicy has a maximum timeout.

A request exceeding that ceiling is denied before AIAction construction.

The final shell timeout ceiling still applies later.

## Threat: MCP wrong protocol revision

MCPAIShellGateway compares request revision to the exported surface.

Unsupported revisions fail.

This avoids silently interpreting breaking protocol changes.

## Threat: MCP wrong method

The AI shell gateway accepts tools/call for prepared tool actions.

Other methods fail.

A transport adapter can expose listing separately.

## Threat: MCP unknown tool

Gateway checks the exported descriptor list.

Unknown tool names fail.

## Threat: MCP raw command injection

MCP tool calls provide structured arguments.

MCPAIShellGateway constructs AIAction.

It does not concatenate a command string.

## Threat: MCP cache staleness

Tool lists include digest and ttlMs.

Clients should refresh after expiry or change notification at a higher
integration layer.

AIShellService stale-plan checks remain the final defense if a client used a
stale list.

## Threat: MCP routing-header spoofing

Transport adapters must treat headers and body consistently.

The in-process MCPRequestEnvelope derives routing headers from its own method and
name.

A real HTTP gateway should verify that headers agree with parsed request data.

## Threat: MCP task mistaken for execution

MCPTaskRegistry represents state only.

Creating a task starts nothing.

External workers must explicitly execute through AIShellService.

## Threat: MCP task state forgery

Only trusted application code should update task state.

Task IDs should not be interpreted as authority tokens.

## Threat: long-running task duplicate execution

A task registry alone does not provide idempotent execution.

Use idempotency keys, admission leases, or queue claim tokens when binding tasks
to workers.

## Threat: MCP task restart after terminal state

Terminal tasks reject updates.

A new task is required.

## Threat: sandbox confusion

The AI shell is not an OS sandbox.

AI policy and effect metadata do not restrict syscalls.

For untrusted code use:

- container isolation
- VM isolation
- namespace isolation
- seccomp
- filesystem mounts
- network policy
- resource quotas

The AI layer should sit above those controls.

## Threat: child process forks descendants

ShellRunner process-group termination mitigates timeout descendants on supported
platforms.

A stronger sandbox can provide cgroup or container-level lifecycle control.

## Threat: memory exhaustion in child

ShellRunner bounds output and time.

It does not universally enforce memory RSS.

A sandbox or OS resource adapter should enforce memory where needed.

## Threat: CPU exhaustion

Timeout bounds wall-clock runtime.

CPU quotas require OS-level enforcement.

## Threat: disk exhaustion

Workspace and output bounds do not guarantee disk quotas.

Sandbox or filesystem quotas are required for hostile writes.

## Threat: file descriptor exhaustion

The runner closes inherited file descriptors.

Child-created descriptor counts require OS-level limits for strong containment.

## Threat: process count exhaustion

Fork bombs require process or cgroup limits.

AI policy alone is insufficient.

## Threat: side-channel leakage

A child may infer host information through timing, filesystem metadata, or
network.

High-assurance deployments need stronger isolation.

## Threat: subprocess scanner bypass in new AI code

AI modules should not call subprocess.

Repository process-safety scanning should continue to cover skeleton.

Any new subprocess call outside ShellRunner requires security review.

## Threat: developer creates convenience raw-shell tool

A future developer may add raw_shell for convenience.

This violates the architecture.

Use narrow logical commands and argument contracts instead.

## Threat: tool adapter bypasses AI review

External adapters such as MCP should prepare AIAction or AIIntent.

They should not call ShellRunner directly.

## Threat: direct ShellService call from untrusted model adapter

Provider adapters should return structured responses only.

They should not receive ShellService.

## Threat: Jeeves bridge privilege confusion

JeevesShellModelPort adapts IntelligenceOrchestrator into a planning model.

The bridge does not own a runner.

Jeeves output remains untrusted.

## Threat: unsafe model handoff

A future handoff should pass bounded intent and context.

It should not pass secret environment values.

It should not pass a mutable capability object that can be widened.

## Threat: inconsistent provider schemas

CallableAIModelPort funnels mapping, string, and bytes responses through one
strict parser.

Provider-specific adapters should preserve this behavior.

## Threat: provider claims structured output but violates it

Parser validation remains authoritative.

Capability declaration only affects diagnostics and routing.

## Threat: policy migration misclassification

Migration classification is review assistance.

Operators remain responsible for understanding changes.

No migration class automatically applies policy.

## Threat: rollback restores old vulnerability

Rolling back a policy can re-enable previously fixed behavior.

Rollback should be used for operational recovery and followed by review.

Base policy remains recorded in history.

## Threat: review display truncates material data

Approval UI should not hide exact argv, cwd, effects, or environment key names.

If display truncation is necessary, the full reviewed payload should remain
inspectable before approval.

## Threat: reviewer social engineering

The model rationale can contain persuasive text.

Approval UI should visually separate model rationale from deterministic risk and
effect data.

Deterministic findings should have higher visual priority.

## Threat: rationale-summary secret leakage

Models may echo sensitive prompt data into rationale_summary.

Keep prompt context nonsecret.

Apply redaction at provider integration if necessary.

## Threat: assumptions treated as facts

Proposal assumptions are model statements.

They should not be considered verified evidence.

Review should distinguish assumptions from execution facts.

## Threat: continue-on-failure hides dependency failure

continue_on_failure is visible in review and proposal fingerprint.

Sensitive workflows should reject it with tool input guardrails unless
explicitly justified.

## Threat: dependency graph hides execution order

AIReviewView includes dependencies.

ExecutionPlan topological order is deterministic.

Approval UIs may render the derived order explicitly.

## Threat: plan complexity

Large plans increase review and failure risk.

Intent constraints and AIShellPolicy limit action count.

Risk scoring increases for larger plans.

## Threat: output digests as sensitive data

A hash of low-entropy output can leak information through guessing.

Treat output digests as internal evidence.

Do not expose them publicly without considering information sensitivity.

## Threat: receipt root exposure

Receipt roots reveal no child output directly but identify execution evidence.

Treat them as internal audit metadata.

## Threat: correlation-ID injection

Correlation IDs should be bounded application identities.

Do not put secrets into correlation IDs.

Do not use correlation IDs as authorization.

## Threat: task or session ID used as authority

Session IDs and task IDs are identifiers.

They are not capability tokens.

Authorization must use principal policy and approvals.

## Threat: stale quarantine record

Time-bounded quarantine expires automatically.

Permanent quarantine requires explicit release.

Operator tooling should surface active quarantine clearly.

## Threat: quarantine record capacity

AIQuarantine is bounded.

Capacity exhaustion fails.

High-volume automated quarantine should have explicit retention strategy.

## Threat: review queue capacity

AIReviewQueue is bounded.

If full, new review requests fail.

The system should not bypass review because the queue is full.

## Threat: session-store capacity

AISessionStore is bounded.

Capacity exhaustion should cause explicit operational failure.

Do not execute untracked sessions as a fallback.

## Threat: evidence storage pressure

Decision journal, outcome memory, calibration, review queue, and regression
history have bounds.

Durable production storage should be explicit.

Memory pressure must never trigger an unsafe fallback path.

## Threat: monitoring outage

Metrics and tracing failure should not grant authority.

Core deterministic checks should remain synchronous and local where practical.

## Threat: trace leakage

Tracing systems can capture sensitive data if configured poorly.

The AI shell keeps its own journal summaries minimal.

External tracing adapters should redact prompts, output, environment values, and
secrets.

## Threat: tracing unavailable

Execution should not depend on a remote tracing backend being reachable.

Local receipts and decision journal remain the primary evidence primitives.

## Threat: policy engine exception

A policy exception should fail closed.

Do not interpret an exception as approval.

## Threat: guard exception

A guard exception should stop the tool call or fail the AI operation.

Do not catch and ignore guard exceptions by default.

## Threat: effect-registry exception

Unknown or failed effect lookup should increase uncertainty or deny.

Do not assume no effects.

## Threat: model parser exception

Parser failure should stop planning.

Do not fall back to treating raw model text as shell.

## Threat: compiler exception

Compilation failure should prevent execution.

Do not reconstruct a command manually from model text.

## Threat: stale-plan exception

Staleness should require replanning or re-review.

Do not suppress staleness to preserve latency.

## Threat: approval service outage

If approval is required and approval service is unavailable, execution should
not proceed.

## Threat: eval service outage

Eval unavailability during development should be visible.

Production execution policy may not depend on every eval service call, but model
or policy rollout gates should.

## Threat: regression history manipulation

Regression history is not hash chained today.

For high-assurance model governance, export signed eval results externally.

Decision execution evidence is separately hash chained.

## Threat: audit-export destination compromise

AIAuditExporter redacts content before export.

The destination still requires authentication, access control, and retention
policy.

## Threat: forged audit export

AIAuditExport has a digest but not a signature.

Use HMAC or public-key signing in an external audit pipeline when independent
authenticity is required.

## Threat: policy-store history tamper

AIPolicyStore is in-memory revision history.

Durable high-assurance environments should persist signed policy artifacts.

## Threat: MCP auth configuration drift

MCP principal policy can drift separately from AIShellPolicy.

Both are additive.

A widening in one layer should not be assumed safe simply because another layer
usually denies.

Governance should diff both surfaces during deployment.

## Threat: anonymous MCP access

Unknown principals are denied.

Do not create a broad anonymous MCPPrincipalPolicy for execution tools without
explicit intent.

## Threat: remote MCP transport risks

This module is transport-neutral.

A real remote transport must add:

- authenticated principal derivation
- TLS
- issuer validation
- audience validation
- replay protection where applicable
- request size limits
- origin controls
- gateway rate limits
- logging redaction

Transport security is outside the in-process envelope.

## Threat: header/body mismatch

A remote MCP adapter may receive Mcp-Method and Mcp-Name headers plus a body.

The adapter should reject disagreement.

The internal request object should have one canonical interpretation.

## Threat: task polling abuse

Long-running task status could be polled at high rate.

Use rate limiting at the transport layer.

Task state does not need unrestricted public access.

## Threat: task metadata leakage

MCPTask includes principal, tool, and correlation ID.

Treat task records as internal or authenticated data.

## Threat: model-generated principal

Principal identity must come from authenticated caller context.

Never accept the model's claimed principal as authorization identity.

## Threat: model-generated approval identity

approved_by must come from authenticated reviewer context.

Never trust a model-generated approver name.

## Threat: model-generated policy change

A model may suggest policy changes.

Applying policy is a governance action.

Policy store changes must come from trusted application/operator code.

## Threat: self-modifying autonomy

The AI shell should not automatically widen AIShellPolicy based on success.

Learning can change routing or recommendations.

Authority widening requires explicit governance.

## Threat: self-modifying tool catalog

The model should not register new executables or commands directly.

New tool registration is a reviewed code/configuration change.

## Threat: model asks for missing tool

Unknown logical commands fail.

Do not dynamically map arbitrary requested names to host PATH.

## Threat: PATH lookup

The lower ShellRunner uses pinned executables.

MCP and AI layers expose only logical names.

Ambient PATH must not become an implicit model tool catalog.

## Threat: dynamic shell wrapper creation

Do not generate shell scripts from model text and execute them.

If a workflow needs a script-like operation, create a narrow reviewed tool with
structured parameters.

## Threat: temporary-file command injection

A model could place executable content into a temp file and invoke an allowed
interpreter.

This is an argument/workspace/sandbox problem.

Restrict interpreter tools and write locations.

Do not assume argv-only execution prevents code execution through files.

## Threat: response-file syntax

Some programs interpret arguments beginning with @ as file-based argument lists.

ArgumentPolicy should account for executable-specific response-file behavior.

## Threat: config-file injection

Many tools load configuration from cwd, home, environment, or flags.

Environment and workspace policy should minimize implicit configuration.

Use clean environment and isolated workspace when possible.

## Threat: plugin loading

Compilers, test runners, editors, and package managers may load plugins.

Plugin paths and config files can convert a benign command into code execution.

Effect contracts should reflect this behavior.

Sandboxing remains important.

## Threat: network proxy variables

Allowed environment keys such as HTTP_PROXY can redirect traffic.

Environment policy should understand semantic power, not only key names.

## Threat: language startup variables

PYTHONPATH, NODE_OPTIONS, RUBYOPT, and similar variables can cause code loading.

Avoid inheriting them for model-controlled execution.

## Threat: home-directory startup files

ShellRunner is not a complete home-directory sandbox.

Tools can read startup/config files available to process identity.

IsolationRequirement from the lower shell plane should be used where needed.

## Threat: model-generated destructive confirmation

Some tools accept flags such as --yes or --force.

ArgumentPolicy should classify those flags.

A model saying it is sure does not replace human approval.

## Threat: plan approval after dependency changes

A plan may depend on repository state that changes after review.

Current PlanPin covers control-plane contracts, not arbitrary repository content.

High-assurance workflows should include workspace or source digest in future
execution seals.

## Threat: time-sensitive external state

A plan may be safe when reviewed but dangerous later because external state
changed.

Use short approval TTL, fresh verification, and external preconditions.

## Threat: race after stale-plan check

Filesystem and external state can change after control-plane staleness check.

Strong atomicity requires deeper sandbox or transaction support.

The stale guard protects configuration drift, not all world-state races.

## Threat: multi-process policy inconsistency

In-memory stores are process-local.

A multi-instance service needs shared or replicated durable policy state.

MCP 2026 stateless routing makes this especially important for remote deployment.

Policy fingerprint should travel with requests or be checked centrally.

## Threat: multi-instance review queue

In-memory AIReviewQueue does not coordinate across processes.

A production distributed implementation needs transactional claim fencing.

The in-memory state machine defines expected semantics.

## Threat: multi-instance idempotency

AIIdempotencyRegistry is local.

Distributed deployments require shared idempotency state or sticky ownership for
the planning transaction.

## Threat: model-provider data retention

External providers may have their own retention policies.

Provider adapters should follow organization data-handling requirements.

Keep model requests minimal.

Avoid secrets.

## Threat: compliance scope expansion

Adding shell AI can increase data governance scope.

Review:

- prompts
- observations
- audit events
- model provider logs
- review decisions
- task metadata
- evaluation datasets

## Threat: user expectation mismatch

Users may believe an AI recommendation already executed.

API surfaces should distinguish:

- proposed
- reviewed
- approved
- executed
- verified

AIShellSession phase should be exposed in operator UI.

## Threat: false success from return code

A zero return code may not prove desired state.

Use VerificationCriterion for material workflows.

## Threat: verification based on same faulty command

A command can return success incorrectly.

Independent verification is stronger when feasible.

A separate verification plan should use a different observable signal.

## Threat: non-deterministic command

Retries and caching may be unsafe for nondeterministic commands.

EffectContract idempotent should be false unless reviewed.

AIPlanCache stores proposals, not execution results.

## Threat: side-effect retry

Retry occurs in the lower executor only when explicitly configured.

AI planning metadata must not imply retry permission.

## Threat: multi-round task confusion

A multi-round agent may reuse old observations after policy changes.

Plan pinning and recovery checks should force replanning when control-plane
digests change.

## Threat: stale MCP tool list

A client may cache tools beyond TTL.

The service still validates current tool existence and plan staleness.

Client caching is an optimization, not authority.

## Threat: unauthorized tool discovery

Tool-list visibility can reveal capabilities.

MCPToolSurface currently emits a full configured list.

A remote integration may need principal-filtered discovery.

Discovery authorization should be added at the transport/service layer.

## Threat: tool-list digest used as secret

Tool-list digest is not secret.

It is change-detection metadata.

Do not use it as an authentication token.

## Threat: policy fingerprint used as secret

Policy fingerprint is not an authentication token.

It identifies policy state.

## Threat: proposal fingerprint collision

SHA-256 is used for practical collision resistance.

Fingerprint identity assumes standard cryptographic properties.

## Threat: time source manipulation

Expiry and runtime state use monotonic clocks where possible.

A malicious host can still manipulate process environment and runtime.

Host compromise is out of scope for application-level controls.

## Threat: compromised host

If the host OS is fully compromised, the attacker can bypass Python-level
policy.

Use OS hardening, container isolation, least privilege, and external evidence
for stronger threat models.

## Severity guidance

Critical examples:

- alternate raw subprocess path from model output
- shell=True introduced into AI adapter
- arbitrary executable path selection
- model-controlled policy widening
- approval bypass
- stale reviewed plan executing after policy drift
- resolved secret values exposed to model by default
- quarantine bypass that restores dangerous execution
- corrupted evidence accepted as valid

High examples:

- tool-catalog drift not detected
- effect drift not detected
- cross-principal approval replay
- review claim fencing failure
- provider fallback widening tool surface
- MCP authorization bypass
- destructive effect mislabeled as low risk
- unsafe interpreter flags exposed without sandboxing

Medium examples:

- provider health routing defect
- eval regression not surfaced
- excessive observation excerpt
- task-state inconsistency without execution authority impact
- audit export metadata overexposure

Low examples:

- status formatting
- non-security display ordering
- cosmetic diagnostic wording

## Security review checklist

Before merging AI shell changes verify:

- no subprocess call was added outside the runner
- no shell parser was added
- model output remains structured
- unknown fields fail
- executable paths stay hidden from model tool cards
- environment values stay outside model protocol
- effect coverage exists for model-visible tools
- risk is deterministic
- model critique cannot override deterministic denial
- approvals bind exact plan and principal
- stale-plan checks remain enabled
- review claims are fenced
- planning loops are bounded
- provider fallback does not widen authority
- quarantine is checked before execution
- observations are redacted
- audit exports omit child output
- eval runner performs no execution
- MCP gateway prepares actions only
- task creation starts no background work
- tests cover hostile and stale states

## Residual-risk statement

The Shell AI layer substantially reduces risks associated with model-directed
host execution.

It does not turn ordinary host execution into a security sandbox.

A permitted child process still has the rights of its OS identity unless
stronger containment is applied.

For adversarial untrusted code, combine this AI control plane with:

- dedicated sandbox
- isolated filesystem
- restricted network
- resource quotas
- least-privilege identity
- external secret broker
- durable policy store
- independent audit evidence

The AI shell should remain the planning and authority-control layer above those
mechanisms.
