# Shell AI Operations Runbook

## Scope

This runbook covers operating the AI-facing shell control plane.

It assumes the lower ShellService and ShellRunner are already configured.

The AI shell must never be used as a fallback around a degraded lower shell.

If the lower shell is not ready, AI shell execution is unavailable.

## Startup order

Recommended startup order:

1. construct ShellPolicy
2. construct ShellRunner
3. construct ShellExecutor
4. construct ShellService
5. start ShellService
6. construct CommandCatalog
7. construct AIToolCatalog
8. construct EffectRegistry
9. construct AIShellPolicy and AIPolicyStore
10. construct model provider ports
11. construct AIPlanner
12. construct AIPlanCritic
13. construct AIPlanCompiler
14. construct AIShellOrchestrator
15. construct AIShellGovernance
16. construct AIShellDiagnostics
17. construct AIShellService
18. start AIShellService
19. accept planning traffic

Do not accept AI planning traffic before diagnostics complete.

## Startup diagnostics

AIShellDiagnostics should be clean before READY.

Important findings:

missing effect contract

unstructured model provider

model without tool-use support

empty tool catalog

orphan effect contracts

Missing effect contracts are an execution-risk issue.

Do not dismiss them as documentation gaps.

## Ready state

AIShellService may create sessions only when READY.

The lower ShellService must also be ready.

A degraded or failed AI service should reject new sessions.

Do not bypass the AI service and call the model directly.

## Session creation

Create one AIShellSession per user or system operation.

Use a bounded nonsecret session ID.

Do not place secrets in the session ID.

Do not reuse terminal sessions.

## Intent creation

Create AIIntent from caller goals and deterministic constraints.

Set:

intent kind

allowed and denied commands

maximum steps

maximum timeout

network permission

write permission

destructive permission

reversibility requirement

success criteria

Do not let the planning model create its own outer intent constraints.

## Review sequence

Call AIShellService.review.

The service:

asks the planner for a structured proposal

runs deterministic critique

checks quarantine

builds the review view

compiles when eligible

pins the reviewed control surface

Return AIReviewView to operators when approval is required.

## Review display

A review UI should show:

goal

proposal ID

proposal fingerprint

model ID

confidence

uncertainty

risk score

risk band

policy reasons

guardrail findings

assumptions

logical commands

exact argv

cwd

environment key names

timeout

effects

reversibility

compensation metadata

dependencies

continue-on-failure

Do not hide material action data behind a summary.

## Approval

When critique requires approval:

enqueue the review

claim with authenticated reviewer identity

display full review

decide using claim ID

create AIPlanApproval only after positive review

bind approval to caller principal

use a short TTL

The plan approval must not be shared between principals.

## Review queue fencing

Every claimed review has a claim ID.

A stale reviewer must not decide after another reviewer has claimed or decided.

Treat ReviewQueueConflict as a normal concurrency failure.

Reload current queue state.

## Execution

Call AIShellService.execute.

The service rechecks:

service readiness

execution pin

intent fingerprint

proposal fingerprint

tool catalog digest

effect digest

AI policy fingerprint

schema digest

plan fingerprint

quarantine

approval if required

Only then does AIShellOrchestrator call ShellService.

## Stale plan

If execution reports stale:

do not suppress it

do not reuse old approval

do not patch the pin manually

create a new review

If control-plane state changed, the human or autonomous policy decision must be
made against the new state.

## Policy change

Use AIShellGovernance.plan_policy_change.

Inspect every migration finding.

Review widening carefully.

Examples of widening:

larger action limit

lower confidence threshold

higher uncertainty allowance

removing denied effects

adding auto-execute risk bands

relaxing reversibility

## Policy rollout

Use AIPolicyRolloutManager.

PREPARED:

target is recorded

global active policy remains base

no principal receives target

CANARY:

global active policy remains base

policy_for returns target only for selected principals

BROAD:

compare-and-swap activates target globally

target revision is recorded

COMPLETE:

rollout is terminal

ROLLED_BACK:

canary or broad change is stopped

A rollout cannot silently overwrite a concurrent policy revision.

## Canary operation

Before entering CANARY confirm:

evals passed

red-team suite passed

AI diagnostics clean

shell diagnostics clean

model provider healthy

approval path tested

no open critical incidents

During CANARY monitor:

planning failure rate

guardrail blocks

risk distribution

approval volume

execution failure rate

verification failure rate

provider health

latency

model confidence error

quarantine events

## Broad rollout

Move to BROAD only when canary evidence is satisfactory.

BROAD activates the target policy in AIPolicyStore.

Capture:

old policy fingerprint

target fingerprint

rollout ID

target revision

snapshot digest

eval result digest

operator identity

## Rollback

Rollback before COMPLETE is explicit.

If still in CANARY, active global policy remains base.

If in BROAD, rollback writes base policy as a new revision.

Do not hide rollback history.

After rollback:

open incident if needed

capture snapshot

run diagnostics

run evals

investigate failures

## Provider health

ProviderHealthRegistry tracks health.

UNKNOWN is normal before first attempt.

DEGRADED means routing should prefer a better provider if available.

UNHEALTHY means repeated failure or extreme latency.

QUARANTINED means do not use.

## Provider circuits

ModelCircuitRegistry prevents repeated failure amplification.

If a provider circuit opens:

route to another eligible provider

do not widen tool access

do not reduce policy checks

do not switch to raw shell fallback

After recovery interval:

permit half-open probe

close only after configured success

## Model rate limiting

AIModelRateLimiter protects provider and planning pressure.

Rate limits should use stable provider IDs.

Do not key by arbitrary user input.

When limited:

return overload or use another configured provider

do not skip planning and execute directly

## Resilient planner

ResilientAIPlanner may try multiple planners.

All planners in one resilience pool should use compatible:

tool catalog

effect registry

AI policy

response protocol

A fallback provider changes intelligence source.

It must not change execution authority.

## Replanning

BoundedReplanner may replan from sanitized observations.

Set a small maximum round count.

Stop on duplicate proposals.

Stop on deterministic policy denial.

Do not transform replanning into an infinite autonomous loop.

## Observation exposure

Default to METADATA_ONLY.

Use DIGEST_ONLY for high sensitivity.

Use REDACTED_EXCERPT only when a real task needs text.

Blocked patterns are defense in depth.

They are not complete secret detection.

## Output guardrails

Tool output guards run after a child completes.

A tripwire should:

mark the AI session failed

record journal event

prevent the model from consuming unsafe output

open incident if severity warrants

Remember that a side effect may already have happened.

## Input guardrails

Input guardrails are prevention controls.

Use them for:

destructive flags

unsafe paths

interpreter modes

network targets

plugin loading

config-file overrides

continue-on-failure restrictions

sensitive tool-specific semantics

## Quarantine

Quarantine can target:

model ID

proposal fingerprint

logical command

Use quarantine when:

provider compromise suspected

repeated unsafe proposal appears

tool effect contract is wrong

command implementation is under investigation

critical incident is open

Quarantine should be visible in operator status.

## Quarantine TTL

Use temporary quarantine for transient incidents.

Use permanent quarantine for unresolved security concerns.

Expired quarantine is removed automatically.

Permanent quarantine requires explicit release.

## Long-running MCP tasks

MCPTaskRegistry does not run work.

A task should be bound to explicit execution orchestration.

Recommended flow:

create task

review action

approve if needed

claim execution externally

set RUNNING

execute through AIShellService

verify

set SUCCEEDED or FAILED

Never treat task existence as execution authorization.

## MCP authorization

Unknown MCP principals are denied.

MCPPrincipalPolicy should be derived from authenticated caller identity.

Do not trust a model-provided principal.

Use allowed tool sets for narrow clients.

Use timeout ceilings.

Keep MCP authorization additive to AI and shell policy.

## MCP tool caching

MCPToolList contains ttlMs, cacheScope, and digest.

Clients may cache the list.

A cached list is not authority.

The server still validates current tool state.

AIShellService stale-plan checks reject drift.

## MCP routing

Transport adapters may use Mcp-Method and Mcp-Name for routing and metering.

A real gateway should verify header/body consistency.

Do not authorize only from an unverified header.

## Session checkpoints

Capture AISessionCheckpoint for operations that may survive service restart.

Checkpoint includes:

phase

intent fingerprint

proposal fingerprint

decision journal root

receipt root

policy fingerprint

tool catalog digest

effect digest

It excludes child output.

## Session store

Use expected revision for writers.

On AISessionConflict:

reload current

compare state

reconcile

do not overwrite blindly

## Recovery after restart

Use AIRecoveryManager.

Possible results:

NONE

RESUME_REVIEW

REQUIRE_REPLAN

REQUIRE_VERIFICATION

MARK_FAILED

MANUAL_REVIEW

Follow the result.

Do not rerun interrupted side-effectful work automatically.

## Journal corruption

If AIDecisionJournal.verify fails:

stop trusting the journal

block automatic resume

capture current state

open incident

preserve corrupted evidence

compare external audit exports

do not rewrite hashes to make verification pass

## Receipt-chain mismatch

If receipt root advanced during interrupted execution:

require verification

inspect receipts

determine whether the command executed

avoid duplicate execution

## Audit export

Use AIAuditExporter.

It exports an explicit allowlist of decision metadata.

It does not export raw child output.

Store exports in access-controlled durable storage when needed.

## Decision provenance

Record AIDecisionProvenance with completed work.

Important fields:

intent fingerprint

proposal fingerprint

tool catalog digest

effect digest

AI policy fingerprint

schema digest

model ID

risk score

approval ID

receipt root

## Metrics

Track low-cardinality metrics.

Recommended dimensions:

logical command

model provider ID

risk band

AI service phase

Do not use:

raw argv

user goal

output text

secret reference

arbitrary correlation IDs

as metric labels.

## Dashboard

Recommended AI dashboard fields:

service phase

AI diagnostics status

shell service phase

active policy revision

active policy fingerprint

provider health

provider circuit state

planning rate limits

planning failures

guardrail blocks

average risk

approval count

execution failures

verification failures

quarantines

review queue depth

decision journal validity

eval pass rate

latest regression delta

## Incident severity

Critical:

raw subprocess bypass

approval bypass

secret exposure to model

stale reviewed plan executed

corrupted evidence accepted

model-controlled policy widening

High:

effect contract wrong

quarantine bypass

MCP authorization bypass

provider fallback widens tools

review claim fencing broken

Medium:

provider routing defect

eval regression

observation exposure wider than intended

Low:

cosmetic status problem

## Incident response

For a critical AI shell incident:

quarantine affected model or command

stop relevant rollout

enter maintenance if needed

capture AI snapshot

capture shell snapshot

capture receipt root

capture decision journal root

export redacted evidence

record policy revision

record tool/effect digests

identify affected sessions

invalidate pending approvals if needed

verify no alternate process path exists

repair

run red-team suite

run eval dataset

restart canary from base policy

## Provider compromise

If a model provider is suspected compromised:

quarantine provider

open its circuit

disable routing to it

review recent proposal fingerprints

inspect approvals tied to its plans

compare outcome memory

run regression suite on alternate provider

do not delete evidence

## Unsafe command contract

If a logical command is found too broad:

quarantine command

remove or narrow it in CommandCatalog

update ArgumentPolicy

update EffectContract

run migration analysis

rerun evals

invalidate old reviewed plans through digest drift

## Model upgrade

Before changing production model:

register new provider ID

run compatibility check

run eval dataset

run red-team dataset

inspect calibration

canary provider routing

compare regression history

do not reuse old trust score under a new model ID

## Eval schedule

Run fast deterministic evals on every relevant code change.

Run provider-backed planning evals on model/config changes.

Run adversarial evals before autonomy widening.

Run recovery evals before session-store changes.

Run MCP contract tests before remote deployment.

## Shutdown

Recommended shutdown:

stop new AI sessions

enter DRAINING

stop review queue intake

allow bounded current work to finish or cancel

capture checkpoints

verify decision journal

verify receipt chain

capture audit export

transition STOPPING

transition STOPPED

No hidden planner workers need shutdown because core components start no hidden
background loops.

## Principle

Operational pressure must not cause a fallback around deterministic authority.

A degraded AI shell should become less available.

It should never become less governed.
