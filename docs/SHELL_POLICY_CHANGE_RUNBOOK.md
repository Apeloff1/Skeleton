# Shell Policy and Change-Control Runbook

## Goal

Change shell authority without accidental widening, stale overwrite, or
unreviewed broad rollout.

This runbook applies to ShellPolicy, executable registry, command catalog,
argument policy, environment policy, workspace policy, capabilities, isolation
requirements, worker shell routing, retention policy, and service feature gates.

## Capture current state

Before editing capture policy revision, policy fingerprint, command catalog
names, policy health, shell status, diagnostics, receipt chain root, open
circuits, command budget exhaustion, current feature gates, maintenance windows,
and rollout state.

For a production service also capture a ShellSnapshot digest.

## Classify the change

Typical narrowing changes include reducing timeout, reducing output limit,
removing inherited environment keys, tightening argv grammar, disabling stdin,
disabling nonzero success, narrowing cwd roots, and reducing feature exposure.

Typical widening changes include adding executable, changing executable path,
increasing timeout, increasing output limit, adding environment key, adding
inherited environment key, adding cwd root, enabling stdin, enabling nonzero
success, broadening argument grammar, and allowing network access.

Typical breaking changes include removing commands used by callers, removing
executables, removing required env keys, removing cwd roots, narrowing return
codes expected by callers, and tightening argv grammar used by callers.

## Migration planner

Compare old and new policy.

Review every reported change.

Safe means authority generally narrows or backward compatibility improves. It
does not mean no security review is needed.

A newly added executable still deserves normal command-contract review.

## Contract lint

Run CommandContractLinter.

Explain warnings in the change.

Pay particular attention to interpreter commands with broad arguments,
inherited environment, stdin, nonzero success, large argv budgets, and large
environment allowlists.

## Compatibility

Define critical caller requirements.

Check required schema version, command names, environment key availability, and
inheritance constraints.

A target that breaks a critical caller should not enter canary until a caller
migration exists.

## Change proposal

Create a ChangeControl proposal.

Identify kind, target, summary, payload digest, proposer, and references.

Avoid secrets in metadata.

Prefer source-control or ticket references over copying entire configuration
payloads.

## Approval

Use unique approvers.

Do not count duplicate approval twice.

For high-risk changes require multiple approvals.

Approval applies to the proposed payload digest.

If payload changes after review, create a new proposal or digest.

## PolicyStore compare-and-swap

Read current revision.

Write target with expected revision.

If compare-and-swap conflicts, stop and read the latest policy.

Recompute migration diff against latest.

Reconcile concurrent change.

Obtain renewed review if the combined target differs.

Never force-overwrite a policy revision conflict.

## Prepare rollout

Create a rollout with rollout ID, target policy, canary percentage, and reason.

Prepared phase should select no principals.

Record base and target revisions.

## Canary entry checks

Before canary:

- policy health is clean
- representative commands dry-run successfully
- denied commands remain denied
- compatibility passes
- migration review is complete
- shell diagnostics are clean
- receipt chain verifies
- quality gates pass

## Canary monitoring

Watch command failure rate, timeout rate, output-limit rate, circuit opens,
command budget pressure, incident count, worker recovery, queue depth,
concurrency saturation, and latency.

Use correlation and receipt IDs to inspect exact failures.

## Canary failure

On security regression or unexplained broad failure:

- stop rollout progression
- pause affected admission if required
- open incident
- capture snapshot
- record rollout ID and target revision
- roll back
- verify base policy is active
- verify canary principals no longer selected
- verify diagnostics and receipt chain
- inspect failure evidence

Do not fix forward by widening unrelated policy.

## Broad rollout

Advance to broad only after canary criteria pass.

Broad rollout selects every principal through the rollout manager.

A separate feature gate can still restrict higher-level behavior.

Monitor the same indicators as canary.

## Completion

Mark complete only after broad observation passes.

Then mark ChangeControl applied, record final policy revision and fingerprint,
capture final snapshot, update documentation, and remove obsolete feature gates
or maintenance windows.

## Rollback behavior

The current rollout manager does not roll back a rollout already marked
complete.

A completed policy can still be changed by a new policy revision and change
request.

This forces explicit history rather than silent rewind.

## Executable path changes

Changing executable path requires review.

Validate target exists, is regular file, has expected permissions, has no
unexpected symlink, has correct version and architecture, and behaves
compatibly.

For high-assurance environments add artifact hash or provenance verification.

## Adding an executable

A new executable creates new authority even if no existing caller breaks.

Define:

- logical name
- absolute path
- tags
- required capabilities
- argument grammar
- environment policy
- workspace policy
- timeout/output expectations
- stdin policy
- nonzero return policy
- owning subsystem
- test coverage

## Environment changes

Adding an allowed environment key broadens input surface.

Adding an inherited key broadens ambient host coupling.

Review executable semantics for PATH, PYTHONPATH, LD_PRELOAD, DYLD variables,
NODE_OPTIONS, language startup hooks, proxy variables, and credential
variables.

Prefer fixed values where possible.

## Workspace changes

Adding cwd root broadens filesystem reach.

Removing a root can break callers.

When adding a root review path ownership, symlink behavior, sensitive files,
write permissions, build artifacts, secrets, and mount boundaries.

## Argument policy changes

Argument grammar is a command-specific security control.

When widening options ask whether the option can execute code, load plugins,
read config, change output path, enable network, invoke child commands, read
arbitrary files, or write arbitrary files.

Argv-safe execution can still be dangerous if the authorized grammar is broad.

## Timeout changes

Timeout widening increases resource exposure.

Use ResourceEstimator to quantify plans and retries.

A deadline never authorizes a timeout larger than policy.

## Output changes

Increasing output limit affects memory, pipe drain time, retention volume, and
incident evidence.

OutputRetentionPolicy remains separate.

Larger capture does not imply larger retention.

## Retry changes

Retry multiplies starts, runtime, output, and side effects.

Review idempotency.

Use command budgets and circuits.

## Capability changes

Capability grants should narrow by delegation.

Do not add capability solely because a caller is considered trusted.

Bind capability to operation.

Sensitive capabilities include custom environment, inherited environment,
stdin, nonzero success, long running, large output, retry, parallel, pipeline,
audit export, and manifest.

## Namespace changes

Adding principal broadens who can reach namespace.

Adding command prefix broadens surface.

Namespace remains additive to capability checks.

## Feature gate changes

Feature gates control rollout behavior, not authorization.

A disabled API path may hide behavior, but enabling it must still pass command
policy.

Use deterministic canary and explicit principals for risky features.

## Maintenance changes

Schedule maintenance before disruptive migration when needed.

A blocking maintenance window can deny new work by command prefix, principal, or
both.

Drain explicitly.

## Isolation changes

A weaker isolation requirement is a security widening.

Moving from sandboxed to workspace or host requires review.

Allowing network or home visibility requires review.

Adding write roots requires review.

Isolation declaration does not itself enforce OS sandboxing.

## Output retention changes

Increasing retained bytes or duration increases data exposure.

Review output classification.

Sensitive and secret outputs should remain byte-redacted by default.

## Approval-gated execution

For destructive or sensitive commands bind approval to principal, command, and
fingerprint.

Use short TTL.

Consume exactly once.

Do not accept a generic approval for arbitrary command fingerprints.

## Incident escalation

Open critical incident when a change creates shell injection possibility,
arbitrary executable path, cwd escape, secret environment leak, stale token
authority, evidence verification failure, or runaway child termination failure.

Open error incident for broad command failure, unexpected circuit opens, mass
timeouts, recovery spikes, or incompatible command contracts.

## Evidence package

For a change incident collect change ID, approvals, old and new policy revisions,
old and new fingerprints, migration report, rollout phase, canary percentage,
feature gates, snapshot digest, receipt root, failure counts, diagnostics, and
incident IDs.

Do not attach secret output unless necessary and approved.

## CI requirements

Canonical quality gate runs every skeleton/testing/test_shell_*.py file.

Repository process safety scanner must pass.

Python compileall must pass.

Backend security regression gate reruns shell tests.

## Emergency narrowing

Emergency narrowing is preferable to widening.

Examples are removing inherited key, disabling feature gate, pausing admission,
adding maintenance window, reducing timeout, reducing output, removing risky
command, and allowing a circuit to remain open.

Document emergency revision.

Follow with normal review and reconciliation.

## Emergency widening

Avoid if a safer workaround exists.

If unavoidable, isolate to explicit principal, use feature gate, require
approval, set shortest possible TTL, set tight command budget, capture before
and after snapshot, and remove widening immediately after incident.

## Post-change verification

Verify policy health, diagnostics, receipt chain, circuit state, command
budgets, representative command success, denied command rejection, environment
bounds, hostile metacharacters as literal argv, cwd escape rejection, stale
token rejection, and output-limit termination.

## Completion criteria

A shell policy change is complete when code and tests are merged, policy revision
is known, change is marked applied, rollout is complete or explicitly stopped,
compatibility is verified, diagnostics are clean, evidence is captured, obsolete
gates and windows are removed, and incident follow-up exists where required.
