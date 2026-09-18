# Shell Plane Threat Model

## Security objective

Prevent repository, model, user, workflow, or network-controlled data from silently expanding host process authority.

The shell plane assumes that approved executables can themselves be powerful. Therefore safety is not defined as "no shell metacharacters" alone. Safety requires controlling executable identity, argv shape, environment, cwd, stdin, runtime resources, concurrency, and evidence leakage.

## Assets

Protected assets include:

- host filesystem outside task workspaces;
- repository source and Git metadata;
- runtime credentials and environment secrets;
- SSH agents and credential helpers;
- cloud metadata credentials;
- GitHub and model-provider tokens;
- local sockets and daemon control endpoints;
- CPU/time/process capacity;
- disk/log capacity;
- audit evidence integrity;
- command policy integrity;
- generated-project/user-authored data.

## Trust boundaries

### Model and prompt input

Model output and prompts are untrusted for executable selection, environment authority, cwd roots, and policy changes.

Model output may select among already-authorized logical commands only when the surrounding tool contract permits it.

### HTTP/API input

API clients cannot supply executable paths. API fields that eventually become argv must pass command-specific argument policy.

### Repository content

Repository content is data, not policy. A checked-out branch must not be allowed to rewrite the active authority grant or security threshold merely by changing a manifest consumed from that branch.

### Workflow/event context

GitHub event fields and workflow inputs are untrusted strings. Existing workflow security gates remain independent of the Python shell plane.

### Parent environment

The parent process environment is sensitive by default. Inheritance is an explicit allowlist, not a baseline.

### Filesystem paths

Path strings are untrusted until resolved. Workspace checks operate on resolved paths and compare authority against resolved roots.

## Threat: shell injection

Classic payloads include:

```text
; rm -rf ...
&& curl ...
| sh
$(command)
`command`
> sensitive-file
```

Mitigation:

- no shell string execution;
- argv-only process calls;
- `shell=False` literal;
- repository-wide static scanner rejects direct unsafe subprocess patterns;
- adversarial tests prove metacharacters remain one literal argv element.

Residual risk:

An executable may implement its own expression language or `--eval` flag. That is why command-specific argument policy is required for high-risk tools.

## Threat: executable substitution

Attack:

An attacker changes `PATH`, cwd, aliases, or a manifest so a trusted command name resolves to an attacker-controlled binary.

Mitigation:

- policies hold resolved absolute executable files;
- runtime command objects use logical names;
- manifests cannot carry executable paths;
- registry freezing and fingerprints expose configuration change;
- policy diffs mark target changes as authority widening.

Residual risk:

An authorized executable file could be replaced on disk after policy construction by a privileged local actor. Deployments that need stronger guarantees should bind executables to immutable images or add inode/content-digest verification at a lower platform layer.

## Threat: environment credential leakage

Attack:

A child receives `GITHUB_TOKEN`, cloud keys, model keys, proxy credentials, SSH agent endpoints, or other ambient values.

Mitigation:

- empty environment is the conceptual baseline;
- only explicitly inherited keys are copied;
- only allowed custom keys are accepted;
- per-key validation and byte limits;
- total environment byte limit;
- tool/status/audit surfaces expose key names or hashes, not values.

Residual risk:

A deliberately allowed environment variable may itself contain sensitive content. It remains the command owner's responsibility to justify every allowed key and to use redaction when any value may enter child output.

## Threat: cwd/path escape

Attack:

A task uses `..`, symlinks, alternate spellings, or an absolute path to execute in a more privileged directory.

Mitigation:

- cwd is resolved before containment checks;
- resolved cwd must be under an allowed root;
- denied subroots can override broad allowed roots;
- policy narrowing permits only descendant roots;
- max relative depth can reduce traversal surface.

Residual risk:

The shell plane confines cwd, not every path an executable can access. Strong filesystem isolation requires OS/container sandboxing in addition to these controls.

## Threat: argument-level authority escalation

Attack:

A safe executable is invoked with a dangerous feature such as arbitrary code evaluation, config override, output path, plugin loading, network target, or recursive delete.

Mitigation:

- `ArgumentPolicy` allows explicit options only;
- option values have regex/choice/length constraints;
- positional values are typed by position/variadic rule;
- deny tokens and deny patterns add targeted defense;
- option repeats and `option=value` syntax are controlled;
- total argv count and bytes are bounded.

Recommended practice:

Prefer positive allowlists over broad deny regexes. Deny patterns should be a second line of defense, not the primary grammar.

## Threat: stdin smuggling

Attack:

A tool with a safe argv receives a program, credential, or destructive command through stdin.

Mitigation:

- stdin requires the `stdin` capability;
- command definition must independently allow stdin;
- bytes are bounded;
- stdin is absent by default.

Recommended practice:

Disable stdin for commands that do not need it. Where structured stdin is necessary, validate the structure before converting to bytes.

## Threat: resource exhaustion

Attack:

A process runs forever, floods stdout/stderr, receives huge stdin, creates excessive retries, or an autonomous loop spawns too many commands.

Mitigation:

Primitive limits:

- wall-clock timeout;
- combined output byte limit;
- stdin byte limit;
- environment byte limit;
- argv count/byte limits.

Aggregate limits:

- session command count;
- failure count;
- cumulative duration;
- cumulative stdout/stderr;
- retry count.

Coordination limits:

- bounded batch workers;
- bounded queue capacity;
- lease capacity;
- token-bucket rate limiting;
- circuit breakers.

Residual risk:

The runner does not currently impose OS CPU, memory, file-count, or process-count cgroups/rlimits. Container/runtime policy should provide those controls for untrusted workloads.

## Threat: retry amplification

Attack:

A failing operation is retried aggressively, multiplying side effects or load.

Mitigation:

- retries disabled by default;
- `retry` capability required;
- retryable return codes explicit;
- timeout retry opt-in;
- output-limit retry opt-in and discouraged;
- max attempts explicit;
- deterministic backoff capped;
- session retry budget;
- circuit breaker can stop repeated failure.

For mutating commands, use an idempotency strategy or disable retries.

## Threat: duplicate side effects

Attack:

The same logical request is submitted repeatedly and performs duplicate mutation.

Mitigation:

`DedupeRegistry` binds a caller-supplied idempotency key to a command fingerprint. Reusing the key with another fingerprint fails.

A completed reservation can record a receipt ID.

Residual risk:

The registry is process-local and TTL-bound. Durable exactly-once semantics require transactional support in the underlying target system.

## Threat: concurrency stampede

Attack:

Many workers simultaneously invoke the same expensive or conflicting command.

Mitigation:

- `LeaseRegistry` offers TTL ownership for a key;
- `RateLimiter` bounds per-key admission;
- `ShellWorkQueue` makes claimed ownership explicit;
- parallel execution requires the `parallel` capability;
- batch worker count is bounded.

Residual risk:

Process-local leases are not distributed locks.

## Threat: pipeline dependency confusion

Attack:

A plan runs a dependent step after a failed prerequisite, references an unknown prerequisite, or hides a cycle.

Mitigation:

- pipeline IDs unique;
- unknown dependencies rejected;
- self-dependencies rejected;
- DAG cycle detection during construction;
- failed dependencies become blocked;
- stop/continue behavior explicit.

## Threat: manifest authority expansion

Attack:

A JSON plan supplies `/bin/sh`, `shell=true`, arbitrary extension fields, enormous payloads, or new policy knobs.

Mitigation:

- strict schema version;
- unknown fields rejected;
- logical command names only;
- executable paths absent from schema;
- payload/step/arg/env/string limits;
- parsed plan still goes through command admission and capability checks.

## Threat: secret leakage through output

Attack:

A child prints credentials or sensitive repository content and a tool response forwards it to logs/models/users.

Mitigation:

- raw output omitted from tool response by default;
- optional output views are bounded;
- `SecretRedactor` handles known key names and token-like patterns;
- audit records store byte counts/digests rather than raw output;
- execution exceptions do not include child output.

Residual risk:

Pattern redaction cannot prove all secrets are removed. Do not expose raw child output to broader trust domains unless the command/output contract explicitly allows it.

## Threat: high-cardinality telemetry leakage

Attack:

Arguments, paths, user IDs, prompts, or secrets become metric labels and create both leakage and monitoring instability.

Mitigation:

Metrics are keyed by registered logical command only. Correlation IDs, argv, cwd, task IDs, and env values are excluded.

The metric registry also has a command-key cardinality bound and overflow bucket.

## Threat: audit tampering

Attack:

Execution history is modified or reordered.

Mitigation:

`ReceiptChain` uses sequence numbers, previous hashes, and SHA-256 receipt hashes. `verify()` checks continuity and content.

JSONL audit output is append-oriented, rejects symlink targets, and bounds event size.

Residual risk:

Local hash chaining is evidence of internal consistency, not an external signature. Strong non-repudiation requires signing/remote immutable storage.

## Threat: policy drift

Attack:

A child configuration gradually gains more executables, roots, environment keys, or resource ceilings.

Mitigation:

- `narrow_policy` rejects widening;
- `intersect_policies` keeps common authority;
- `is_narrower_or_equal` gives a machine check;
- `diff_policies` labels changes as wider/narrower;
- registry snapshot digest detects metadata drift.

Recommended CI behavior:

Treat policy widening as review-required. Do not auto-approve a widening change solely because tests pass.

## Threat: stale queue/lease ownership

Attack:

A worker completes work using a stale claim after ownership changed.

Mitigation:

Queue completion requires the current claim ID. Lease renewal/release requires the current lease ID.

TTL expiration is checked on access.

## Threat: unsafe hook behavior

Attack:

An optional observability hook changes execution outcome or leaks raw internals.

Mitigation:

Pre-hooks receive bounded metadata and can veto before spawn.

Post-hooks receive metadata plus result and are isolated: failures are recorded by exception type and do not change successful process outcome.

Do not register hooks from untrusted plugins without an independent plugin capability model.

## Threat: command output used as executable input

Attack:

Output from one process is interpolated into another command as shell text.

Mitigation:

The shell plane has no shell-string interpolation primitive. Pipelines link step dependency status, not automatic output substitution.

If an application wants to derive arguments from prior output, it must parse and validate those values into individual argv elements under the destination command's argument policy.

## Threat: Windows/POSIX semantic differences

The runner avoids shell syntax, which removes a major portability class. Process-group termination semantics differ across operating systems.

On POSIX the runner starts a new session and targets the process group. On other systems it uses process terminate/kill primitives.

Platform-specific job objects or sandboxing can be added beneath the same high-level executor contract without changing manifests or agent interfaces.

## Security invariants

The following invariants should remain true across future work:

1. No runtime manifest can add an executable path.
2. No model/tool request can widen its capability grant.
3. No child environment receives an unknown key through the canonical executor.
4. No cwd outside an allowed resolved root reaches the canonical executor.
5. No batch or pipeline bypasses `ShellExecutor`.
6. No retry happens unless a retry policy and capability allow it.
7. No raw secret-bearing output is present in normal audit events or receipts.
8. No command metric label derives from argv, cwd, prompt, or env values.
9. Policy narrowing helpers cannot widen authority.
10. Direct Python process calls remain covered by the independent repository scanner.

## Out of scope

The shell plane is not a replacement for:

- containers;
- seccomp/AppArmor/SELinux;
- cgroups/rlimits;
- VM isolation;
- distributed locks;
- remote attestation;
- executable code signing;
- filesystem ACLs;
- network egress policy;
- secrets management.

Those controls compose below/around this subsystem.
