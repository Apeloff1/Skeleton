# Auto-Merge Control Plane

## Purpose

Skeleton's auto-merge control plane is a trusted-default-branch service for
landing pull requests only after exact-head evidence proves that a mutation is
safe under repository policy.

The control plane is not a shortcut around CI, review, branch rules, or security
gates. It is a deterministic consumer of those signals. Its job is to make the
merge boundary stricter, repeatable, auditable, and resistant to races.

The implementation lives in:

- `skeleton/pr_automation/automerge_model.py`
- `skeleton/pr_automation/automerge_evidence.py`
- `skeleton/pr_automation/automerge_policy.py`
- `skeleton/pr_automation/automerge_stack.py`
- `skeleton/pr_automation/automerge_github.py`
- `skeleton/pr_automation/automerge_ledger.py`
- `skeleton/pr_automation/automerge_engine.py`
- `skeleton/pr_automation/automerge_cli.py`
- `.github/workflows/automerge-control-plane.yml`

The static contract gate is `scripts/check_automerge_contract.py`. Focused
regressions are under `skeleton/testing/test_automerge_*.py`.

## Authority model

The workflow always loads executable control-plane code from the repository
default branch. It never checks out a pull-request head into the privileged
reconcile job.

The global workflow permission set is empty. Permissions are granted per job.
The validation job receives only `contents: read`. The reconcile job receives
the scopes needed to inspect Actions evidence, read status/check state, update
pull requests, merge into the repository, and dispatch post-merge validation.

Pull-request content is data, never executable policy.

The control plane has no shell-execution primitive, no dynamic imports, no
`eval`, no `exec`, and no dependency on a PR-provided script.

Critical changes to the automation trust surface are deliberately human-merge
only. This includes the workflow itself and the Python policy/runtime package.
That boundary prevents the auto-merge system from approving mutations to its
own authority.

## Core invariant

Every mutation is bound to one immutable candidate snapshot.

A snapshot contains:

- repository and PR identity;
- exact base and head references;
- canonical lowercase 40-character commit SHAs;
- fork identity;
- mergeability state;
- complete changed-file inventory;
- additions and deletions;
- labels;
- review evidence;
- unresolved review-thread count;
- exact-head workflow evidence;
- stack relationship;
- risk classification;
- ancestry evidence.

The snapshot is fingerprinted with canonical JSON and SHA-256.

Immediately before a mutation, the engine fetches the candidate again and
compares all merge-relevant identity, diff, label, review, and thread evidence.
It also re-reads the default-branch head.

If anything moved, the planned action is discarded.

## One mutation per snapshot

The engine intentionally avoids batch-mutating from one stale repository view.

A reconciliation pass:

1. resolves the current default-branch SHA;
2. lists the bounded open-PR inventory;
3. captures full immutable snapshots;
4. constructs the stack graph;
5. evaluates every candidate;
6. selects at most one mutation;
7. revalidates the selected candidate;
8. executes the SHA-bound mutation;
9. records a receipt;
10. discards cached state before any further decision.

This matters because a successful merge changes the base SHA for every other
root PR. Reusing the old decision batch would turn previously valid evidence
into stale evidence.

## Exact-head workflow evidence

The control plane does not trust an aggregate green badge.

For each required workflow it selects the newest attempt whose
`head_sha` exactly matches the candidate head.

By default the evidence must also come from a `pull_request` event.

The newest run number wins. Within a run number the newest attempt wins.
Timestamp is used as a final deterministic tie breaker.

A newer failure, cancellation, or pending rerun overrides an older success.

A success from another head SHA is diagnostic only and cannot satisfy policy.

Missing evidence is an explicit blocking state.

Supported gate states are:

- success;
- failure;
- pending;
- missing;
- skipped;
- cancelled;
- unknown.

Skipped runs only count as success when a specific gate requirement explicitly
allows skipped evidence.

## Stability window

A candidate does not mutate at the same instant the last required workflow
turns green.

The latest success timestamp across required gates must remain successful for a
configurable stability window.

The default is 30 seconds.

This catches common race patterns such as:

- a rerun being requested immediately after an old success;
- workflow fanout arriving slightly later than the first validation result;
- a synchronization event replacing a just-completed run;
- delayed security workflows appearing after ordinary tests.

The window may be configured down to zero for controlled environments, but the
production workflow keeps a nonzero default.

## Required baseline workflows

The CLI always adds a non-removable safety baseline:

- CI/CD;
- Merge Readiness;
- Secret scanning;
- Malware Gate;
- Repository Hygiene Gate;
- Artifact Policy;
- Provenance Policy;
- PR Hygiene.

Environment configuration can add required workflows. It does not remove this
baseline.

Additional gates are derived from the changed-file surface.

## Path-sensitive gate expansion

Code changes add:

- Backend Quality;
- Frontier Contracts;
- ARM64 Ubuntu Validation.

Dependency changes add:

- Dependency Review;
- Dependency Security.

Security or workflow changes add security-oriented workflow requirements.

Release/deployment changes add Reproducible Release.

This mapping means a documentation-only PR does not need unrelated expensive
lanes, while code and security changes cannot accidentally inherit the lighter
documentation policy.

## Risk classification

The engine assigns one of four tiers.

### Low

Typical low-risk examples:

- documentation;
- markdown;
- test-only changes without production code.

### Medium

Typical medium-risk examples:

- backend code;
- frontend code;
- Skeleton runtime code;
- ordinary scripts.

### High

Typical high-risk examples:

- dependency manifests and lock files;
- release files;
- container/deployment configuration.

### Critical

Typical critical examples:

- GitHub workflows;
- local GitHub actions;
- PR automation implementation;
- security control-plane paths.

Critical candidates may pass all technical gates and still remain human-merge
only.

This is intentional authority separation, not a CI failure.

## Candidate trust classes

The policy distinguishes:

- repository owner;
- Dependabot;
- explicitly trusted bots;
- unknown authors.

The default workflow recognizes the repository owner and Dependabot.

Unknown authors are held.

Same-repository heads are required by default. Fork heads are held even when
their checks are green.

## Opt-in and opt-out

Auto-merge labels are normalized case-insensitively.

Default opt-in label:

- `automerge`

Default opt-out labels:

- `do-not-merge`
- `automerge:off`

An opt-out always wins.

Repository-owner candidates may be configured for implicit opt-in.

Dependabot may be configured for implicit opt-in.

Other trusted bots still require explicit policy support.

## Reviews

Review state is evaluated per reviewer.

The latest decisive review from each login wins.

`COMMENTED` reviews do not replace a prior approval or change request.

Policy may require a minimum approval count.

Active `CHANGES_REQUESTED` reviews block by default.

Unresolved review threads block by default.

Unknown thread state also blocks. The system does not interpret an unavailable
review-thread API response as zero unresolved threads.

## Mergeability

GitHub must affirmatively report the PR as mergeable.

Known clean state is accepted.

`unstable` may be accepted when every exact-head workflow required by the
control plane is independently successful. This avoids blindly depending on a
single aggregate state while preserving strict named-gate evidence.

Dirty, blocked, behind, and unknown merge states hold.

The candidate head must contain the exact base commit represented by the
snapshot.

## Root PR binding

For a root candidate targeting the default branch, the snapshot base SHA must
equal the default-branch head resolved for the reconciliation iteration.

If the default branch moves between inventory capture and mutation, the
candidate is discarded and must be reconsidered from fresh state.

The merge request also includes the expected head SHA so GitHub rejects the
mutation if the PR head changes after the final local revalidation.

## Stacked PRs

A PR is treated as a stack child when its base branch is the head branch of
another open PR.

The stack graph detects:

- roots;
- children;
- leaves;
- orphans;
- cycles;
- duplicate head-branch owners.

A child base SHA must equal its parent's current head SHA.

If the parent branch moved, the child is held until GitHub presents a fresh
candidate snapshot.

Orphans and cycles are fail-closed.

Duplicate ownership of a head branch is treated as ambiguous and blocks
automatic stack landing.

## Stack landing order

Stack landing is leaf-first.

Only a leaf child may be selected for automatic merge into its parent branch.

The engine emits at most one child mutation per stack root in a pass.

After a child merge, the workflow stops the current reconciliation by default.

That pause is essential because the parent PR head has changed and every check
on the parent may now be stale. A later workflow wake captures the new parent
head and requires exact-head validation again.

The engine never assumes that checks on the child satisfy checks on the updated
parent.

## Direct merge mode

`merge_direct` performs a SHA-bound GitHub merge request after all local gates
and final revalidation succeed.

The merge method is configurable.

The default is squash.

The GitHub merge endpoint receives the expected head SHA.

A rejected merge is retained as a mutation receipt; it is not silently retried
inside the same stale decision.

## Native auto-merge mode

`enable_native` enables GitHub native auto-merge after the same local policy
evaluation.

Before enabling it, the adapter fetches the PR again and verifies the expected
head SHA.

Native mode is idempotency-protected by the merge ledger. The same action key is
not repeatedly enabled during one reconciliation history.

Native auto-merge remains subject to GitHub repository configuration and native
branch rules.

## Observe mode

`observe` evaluates the entire repository and emits decisions without
mutation.

This is useful for:

- rollout;
- policy tuning;
- incident investigation;
- branch-rule migration;
- proving new required-workflow mappings.

Ready candidates are reported as ready, but no action object is executed.

## Tamper-evident ledger

Every decision and mutation is appended to a hash chain.

Each record includes:

- monotonically increasing sequence;
- record kind;
- subject;
- structured payload;
- previous record hash;
- record hash;
- timestamp.

The first record points to a fixed genesis hash.

The ledger verifier recalculates every record hash and checks the full previous
hash chain.

Mutation receipts store the action idempotency key so replayed or restarted
workers can prove that a specific immutable action was already attempted.

The workflow uploads the ledger and reconciliation report as retained Actions
artifacts.

Missing artifact files fail the upload step.

## Mutation receipts

A receipt records:

- PR number;
- action idempotency key;
- requested head SHA;
- observed head SHA;
- base branch;
- whether GitHub reported a merge;
- merge SHA when present;
- bounded message;
- recording time.

A report cannot claim a mutation for a PR without corresponding decision
evidence.

A default-branch head change without a recorded successful merge is considered
internally inconsistent.

## Post-merge validation

Merges performed with the workflow token may not create the same event fanout
as a human/PAT merge.

The control plane therefore explicitly dispatches trusted post-merge workflows
after a successful direct default-branch merge.

The default dispatch set is:

- `merge-readiness.yml`
- `queue-drain.yml`

Both are loaded from the default branch.

This provides fresh integration evidence and wakes queue recovery without
executing PR code.

## Queue interaction

The control plane uses repository-wide non-preemptive concurrency.

Only one reconciliation runs at a time.

A pending wake may coalesce behind the active run, but a new wake does not
cancel the active privileged mutation job.

This avoids duplicate merge attempts during high workflow fanout.

The existing queue-drain control plane remains responsible for stale Actions
workload recovery. Auto-merge does not duplicate its cancellation policy.

## Workflow triggers

The control-plane workflow can wake from:

- manual `workflow_dispatch`;
- completion of Merge Readiness;
- a five-minute staggered schedule;
- trusted changes to its own default-branch implementation.

The privileged workflow does not use `pull_request_target`.

It also does not use a normal `pull_request` trigger for mutation. That design
keeps the executable reconcile implementation on trusted default-branch code.

The PR that changes auto-merge itself is validated by Merge Readiness's existing
PR Automation Tests lane.

## Merge Readiness integration

The Merge Readiness `PR Automation Tests` job:

- compiles `skeleton/pr_automation`;
- runs the static auto-merge workflow contract;
- runs the existing PR automation suite;
- runs the focused auto-merge model, evidence, policy, stack, engine, and
  contract suites.

This means a proposed change to the privileged workflow cannot bypass
validation merely because the workflow is not yet present on `main`.

## Configuration

The CLI is configured with environment variables.

Important variables include:

- `AUTOMERGE_MODE`;
- `AUTOMERGE_MERGE_METHOD`;
- `AUTOMERGE_MAX_MERGES`;
- `AUTOMERGE_MAX_STACK_MERGES`;
- `AUTOMERGE_MAX_OPEN_PR_SCAN`;
- `AUTOMERGE_MAX_CHANGED_FILES`;
- `AUTOMERGE_MAX_LINE_DELTA`;
- `AUTOMERGE_STABILITY_SECONDS`;
- `AUTOMERGE_REQUIRED_APPROVALS`;
- `AUTOMERGE_REQUIRE_RESOLVED_THREADS`;
- `AUTOMERGE_REQUIRE_NO_CHANGES_REQUESTED`;
- `AUTOMERGE_SAME_REPOSITORY_ONLY`;
- `AUTOMERGE_ALLOW_OWNER_WITHOUT_OPT_IN`;
- `AUTOMERGE_ALLOW_DEPENDABOT_WITHOUT_OPT_IN`;
- `AUTOMERGE_ALLOW_STACK_CHILD_MERGE`;
- `AUTOMERGE_REQUIRED_WORKFLOWS`;
- `AUTOMERGE_OWNER_LOGINS`;
- `AUTOMERGE_TRUSTED_BOTS`;
- `AUTOMERGE_OPT_IN_LABELS`;
- `AUTOMERGE_OPT_OUT_LABELS`;
- `AUTOMERGE_POST_MERGE_WORKFLOWS`.

Malformed booleans and integers fail configuration instead of being silently
coerced.

Numeric limits are bounded.

## Bounded work

The control plane does not scan unbounded repository history.

Controls include:

- bounded open-PR inventory;
- bounded REST pagination;
- bounded GraphQL review-thread pagination;
- bounded HTTP retries;
- bounded HTTP timeout;
- bounded root merges per reconciliation;
- bounded stack merges per reconciliation;
- changed-file count budget;
- line-delta budget.

A pagination bound failure is blocking.

It is never treated as an empty remainder.

## Failure behavior

The system prefers a hold over an inferred success.

Examples that hold:

- missing workflow result;
- pending rerun;
- cancelled newest attempt;
- workflow failure;
- unknown conclusion;
- stale successful workflow from another head;
- unresolved thread;
- unavailable thread state;
- insufficient approvals;
- active change request;
- unknown author;
- fork;
- dirty mergeability;
- stale base SHA;
- parent branch move;
- stack cycle;
- stack orphan;
- duplicate stack branch owner;
- malformed changed path;
- excessive diff;
- trust-surface mutation;
- mutation-boundary identity change.

## Failure isolation

A bad candidate does not make an unrelated candidate eligible or ineligible by
itself.

Independent roots are evaluated separately.

Stack graph corruption blocks affected stack mutations.

The decision report retains holds for diagnosis while allowing an independent,
eligible root to be considered.

## Security properties

The design aims to preserve these properties:

### Exact identity

No merge decision relies on a short SHA, uppercase SHA, or branch name alone.

### No PR-code execution

Privileged reconcile code comes from the trusted default branch.

### Least privilege

Write scopes exist only on the reconcile job.

### Self-protection

Critical automation paths are not auto-merged.

### Race resistance

Candidate state and default-branch state are reread at the mutation boundary.

### Server-side head binding

Direct merges include the expected head SHA.

### Evidence freshness

The newest exact-head attempt for every required workflow is authoritative.

### Review completeness

Unknown thread state fails closed.

### Stack integrity

Child branch ancestry and child base SHA are bound to the parent head.

### Replay resistance

Action idempotency keys are written into the tamper-evident ledger.

### Deterministic policy

Policy and candidate snapshots are independently fingerprinted.

## Operational rollout

A conservative rollout sequence is:

1. land the implementation through normal human review;
2. run the workflow in observe mode;
3. inspect reports for unexpected holds or unexpected ready candidates;
4. enable direct mode with a root merge cap of one;
5. keep stack merging enabled only after root behavior is stable;
6. raise merge budgets gradually if repository throughput requires it.

The workflow defaults are still bounded even after direct mode is enabled.

## Incident response

If merge behavior is suspicious:

1. disable or remove the workflow from the default branch;
2. apply the `automerge:off` or `do-not-merge` label to affected PRs;
3. inspect the retained report and ledger artifact;
4. verify the ledger hash chain;
5. compare action keys and exact requested SHAs with GitHub merge commits;
6. inspect the newest exact-head workflow attempts;
7. inspect stack topology and parent-head movement;
8. restore in observe mode first.

Because the implementation is default-branch code, disabling the trusted
workflow immediately stops future privileged reconciliations.

## What the system deliberately does not do

It does not:

- bypass failed checks;
- infer success from missing evidence;
- auto-merge its own critical policy code;
- run arbitrary PR scripts;
- merge fork heads by default;
- reuse a decision batch after a merge;
- treat old-head success as current evidence;
- treat cancelled checks as green;
- auto-resolve review threads;
- dismiss change requests;
- rewrite branch protection;
- force-push contributor branches;
- force-merge conflicts;
- suppress security scanners;
- cancel arbitrary in-progress validation;
- treat stack ancestry as branch-name-only authority.

## Testing strategy

The focused test matrix covers:

- canonical SHA/ref validation;
- immutable identity fingerprints;
- workflow attempt ordering;
- stale-head rejection;
- pending/failure/cancelled supersession;
- skipped-gate policy;
- review-state precedence;
- thread handling;
- stability windows;
- dependency/code/security/release gate expansion;
- trust classes;
- label policy;
- risk tiers;
- fork rejection;
- diff budgets;
- stack roots/children/leaves;
- cycles;
- orphans;
- duplicate head branches;
- parent-head SHA binding;
- landing plans;
- base-head binding;
- one-mutation selection;
- native/direct/observe modes;
- ledger idempotency;
- post-merge dispatch;
- report consistency;
- workflow least privilege;
- trusted checkout;
- forbidden dynamic execution imports.

## Design principle

Auto-merge should make merging boring.

A candidate is either proven safe for one exact immutable state or it is held.
The system never needs to guess, race, or weaken a gate to keep the queue
moving.
