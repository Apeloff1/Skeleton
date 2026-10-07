# Builder Plane

The Builder Plane is the deterministic build-contract layer for autonomous,
maintainer-authorized feature work in Skeleton.

It does **not** add another privileged actor. Repository authority remains:

```text
Supervisor (read / plan)
    |
    v
Secretary (admit / revalidate)
    |
    v
Builder Plane (compile inert manifest)
    |
    v
feature-builder Worker (bounded proposal)
    |
    v
ordinary pull request -> CI / review / merge policy
```

The plane exists to turn one exact, maintainer-approved issue into a canonical
build graph with explicit budgets, custody, acceptance criteria, and evidence
requirements.

## Goals

The Builder Plane provides:

- deterministic compilation of approved work into a canonical manifest;
- exact binding to issue authority, repository snapshot, workflow execution,
  and immutable base commit;
- a small topologically ordered build graph;
- hard file, changed-line, byte, and test-description budgets;
- fail-closed transport with canonical JSON and digest validation;
- no model-selectable executable, module, shell, permission, token, workflow,
  branch, or arbitrary mutation primitive;
- end-to-end evidence that binds a newly published feature proposal to the
  exact manifest admitted by the Secretary.

It is deliberately smaller in authority than the Worker. The Builder Plane
describes and constrains work; it does not execute work.

## Authority source

Feature authority comes from `BuildAuthorization` in
`skeleton/automation/build_authority.py`.

An issue must:

1. be open;
2. carry an approved automation label;
3. contain bounded title/body/label data;
4. remain byte-for-byte equivalent to the issue observed by the Supervisor.

The current approval labels are:

- `automation-approved`
- `supervisor-approved`
- `build-approved`

The Secretary revalidates the issue immediately before compiling the Builder
manifest. The feature worker revalidates it again. Removing the approval label,
closing the issue, or editing the approved task revokes the old authority.

## Manifest identity

A `BuilderManifest` binds:

- repository identity;
- issue number;
- issue digest;
- build task digest;
- Supervisor snapshot fingerprint;
- execution fingerprint;
- immutable base SHA;
- proposal budgets;
- ordered build stages;
- derived planning signals;
- bounded acceptance criteria.

The manifest has its own `manifest_digest`, calculated over canonical JSON.
The digest is not a signature and is not treated as an authority source. It is
an integrity and correlation identity for data that is already inside the
Supervisor/Secretary custody chain.

## Deterministic graph

Every manifest currently contains six stages:

| Stage | Mutation | Purpose |
| --- | --- | --- |
| `inspect` | no | Identify the smallest relevant repository surface |
| `design` | no | State the behavioral contract and failure semantics |
| `implement` | yes | Produce the bounded source/test/docs proposal |
| `regression` | no | Require focused behavioral coverage |
| `validate` | no | Check structure, custody, budget, and immutable base |
| `evidence` | no | Emit bounded PR/worker evidence |

Exactly one stage may have `mutation_allowed=true`, and that stage must be the
`implement` stage. Dependencies may only point to earlier stages, making the
manifest graph acyclic by construction.

The stages are inert data. They are not commands and are never executed as
shell input.

## Budgets

The manifest constrains feature proposals below the worker's hard limits.

Current absolute Builder Plane caps are:

- files: 16;
- changed lines: 1,200;
- proposed path/content bytes: 240,000;
- test descriptions: 12.

The compiler may choose a smaller budget for a task. The feature-builder uses
the lower of its registered specialist file budget and the manifest file
budget.

Budget checks happen before filesystem mutation. The existing worker mutation
guards remain authoritative as a second layer.

## Signals

The compiler derives bounded planning signals from the approved issue title,
body, and labels. Signals currently include:

- `api-contract`
- `documentation`
- `integration`
- `performance`
- `regression`
- `testing`
- `observability`
- `resilience`
- `data-model`
- `cli`

If none match, the task receives `general-feature`.

Signals affect deterministic planning detail and budget selection. They do not
grant authority and do not select executables or repository permissions.

## Secretary integration

The Secretary is the compilation and dispatch boundary.

For an admitted feature build it:

1. revalidates the live `BuildAuthorization`;
2. compiles a `BuilderManifest`;
3. validates the manifest against the exact snapshot and execution identity;
4. transports the manifest as bounded base64 canonical JSON;
5. transports the expected manifest digest separately;
6. dispatches the registered `feature-builder` worker in its detached
   worktree.

A feature worker is not dispatched with Builder authority merely because a
model asks for feature work. The repository issue state remains the authority
source.

Non-feature workers do not receive a Builder manifest. A leaked manifest is
rejected at worker admission.

## Worker admission

The feature-builder requires all of the following:

- Secretary delegation;
- exact worker identity;
- exact Supervisor execution fingerprint;
- exact Supervisor snapshot fingerprint;
- current live build authorization;
- exact Builder manifest;
- matching Builder manifest transport digest;
- deterministic manifest recompilation/custody validation.

A mismatch fails closed before model generation or filesystem mutation.

The model prompt receives a bounded JSON rendering of the manifest. The full
approved issue body is still carried by `BuildAuthorization`; the manifest
does not duplicate it.

## Mutation boundary

The Builder Plane does not replace existing worker containment.

The worker still:

- starts from the immutable admitted base SHA;
- requires a clean worktree;
- checks that remote `main` has not advanced;
- rejects blocked paths;
- restricts mutations to registered safe prefixes;
- rejects symlink traversal;
- writes regular text files only;
- verifies staged paths and file modes;
- creates one deterministic worker branch;
- publishes through an ordinary pull request;
- cannot merge its own proposal.

Model output remains data and is never executed as a command.

## Publication evidence

A newly created feature PR records:

- Supervisor snapshot fingerprint;
- execution fingerprint;
- immutable base SHA;
- proposal digest;
- authorized issue number;
- build task digest;
- Builder manifest digest.

The worker also emits the Builder manifest digest in its machine-readable
result. The Secretary parses that field and compares it with the manifest it
compiled before dispatch.

This closes the Builder custody chain:

```text
approved issue
  -> BuildAuthorization.task_digest
  -> BuilderManifest.manifest_digest
  -> feature proposal
  -> worker evidence
  -> Secretary digest verification
```

An ordinary PR/CI result is still not equivalent to merge authority. Existing
security gates, branch protection, review rules, and merge readiness remain
authoritative.

## Failure semantics

The plane fails closed when:

- repository or digest identities are malformed;
- manifest JSON contains duplicate keys;
- the manifest contains unexpected or missing fields;
- a stage graph is malformed or cyclic;
- more than one stage can mutate;
- a budget exceeds a hard Builder cap;
- manifest transport is malformed or oversized;
- snapshot, execution, base, task, or issue custody differs;
- deterministic recompilation does not reproduce the same manifest;
- Builder data reaches a non-builder worker;
- the feature proposal exceeds a manifest budget;
- published worker evidence carries a different manifest digest.

Failure never upgrades permissions or falls back to unrestricted feature
execution.

## CI coverage

Builder Plane changes are included in the workflow-input-security path surface.

Merge Readiness runs:

- `tests/test_builder_plane.py`
- `tests/test_builder_plane_integration.py`

The Supervisor workflow contract also asserts that those files remain wired
into the security and merge-readiness workflows, preventing silent coverage
drift.

## Key files

- `skeleton/automation/build_authority.py` — maintainer authority
- `skeleton/automation/builder_plane.py` — deterministic manifest compiler
- `skeleton/automation/secretary.py` — live admission and dispatch
- `skeleton/automation/specialist_bots.py` — worker admission and publication
- `skeleton/automation/supervisor_runtime.py` — immutable custody/evidence
- `tests/test_builder_plane.py` — manifest unit contracts
- `tests/test_builder_plane_integration.py` — cross-boundary contracts

## Design rule

The central rule is:

> The Builder Plane may make autonomous building more structured, repeatable,
> and capable, but it may not make repository authority implicit.

New Builder capabilities should therefore prefer stronger manifests, evidence,
deterministic decomposition, validation, and recovery semantics over broader
token permissions or executable model output.
