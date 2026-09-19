# Migrating Host Execution to `skeleton.shells`

## Scope

This guide is for repository code that currently needs to launch a local process or is about to add host execution.

The migration objective is not merely replacing `subprocess.run` with another wrapper. The objective is making authority explicit and testable.

## Before migrating

Answer these questions for each execution site:

1. Why is a child process necessary?
2. Which executable must run?
3. Can the executable path be fixed during trusted startup?
4. Which argv shapes are actually needed?
5. Which environment keys are actually needed?
6. Which cwd roots are actually needed?
7. Is stdin necessary?
8. Which return codes are acceptable?
9. What timeout is realistic?
10. What output size is realistic?
11. Is retry safe?
12. Is the command mutating?
13. Does it need concurrency?
14. Which evidence should survive execution?

If those questions do not have bounded answers, the call site is not ready to become an autonomous/agent shell tool.

## Migration pattern: simple inspection command

Old shape:

```python
subprocess.run([tool, "--version"], capture_output=True, text=True)
```

Preferred shape:

```python
policy = ShellPolicy(
    executables={"tool": trusted_tool_path},
    cwd_roots=(workspace,),
    max_output_bytes=64 * 1024,
    max_input_bytes=0,
    max_env_bytes=1024,
    max_args=8,
    max_arg_bytes=1024,
    default_timeout=2.0,
    max_timeout=5.0,
)
runner = ShellRunner(policy)
executor = ShellExecutor(runner)
outcome = executor.execute(ShellCommand("tool", ("--version",), cwd=workspace))
```

For an agent-facing version, add a command definition restricting the option to `--version` rather than using `ArgumentPolicy.allow_any()`.

## Migration pattern: repository test command

A build/test command often needs longer execution and larger output, but it should still have bounded authority.

Use a `build`-class policy profile or a dedicated narrower policy.

Avoid passing the entire parent environment. Start with locale variables only, then add proven requirements individually.

## Migration pattern: generated project compiler

Recommended structure:

1. Generate into a task-specific workspace.
2. Make that workspace the only cwd root.
3. Register the compiler from trusted deployment configuration.
4. Permit only the required compile/project flags.
5. Deny plugin/config-path overrides unless explicitly required.
6. Set a project-size-informed timeout/output budget.
7. Execute under a `ShellSession` shared by compile/repair attempts.
8. Use deterministic compiler diagnostics as repair input.
9. Do not pass the entire compiler output directly to a model.
10. Record receipt IDs in generated-project evidence.

## Migration pattern: Git commands

Git is highly capable. Treat it as multiple logical command contracts even when they share one executable path.

For example, separate definitions can represent:

- read-only status;
- diff inspection;
- object verification;
- controlled branch operations.

Do not create one broad `git` agent tool with unrestricted arguments.

Particularly sensitive flags/features include:

- config overrides;
- external diff/textconv;
- hooks;
- credential helpers;
- remote URLs;
- upload-pack/receive-pack overrides;
- worktree paths;
- submodule recursion;
- protocol configuration.

Use positive argv grammar and dedicated wrappers/contracts for privileged Git mutation.

## Migration pattern: Python interpreter

Python can execute arbitrary code. A registered Python interpreter is not inherently a safe agent tool.

Prefer fixed templates such as:

```python
CommandTemplate(
    "compile-package",
    "python",
    ("-m", "compileall", "-q", "{target}"),
    slots={"target": TemplateSlot("target", safe_path_constraint)},
)
```

Avoid exposing unrestricted `-c`, script paths, `-m` module selection, startup hooks, or arbitrary environment settings to untrusted callers.

The primitive runner may still register Python for trusted internal test orchestration. That does not mean the same authority should be exported through `ShellToolAdapter`.

## Migration pattern: command with environment

Old code often relies on `env=os.environ.copy()`.

Replace that pattern with an `EnvironmentPolicy`.

Example:

```python
env_policy = EnvironmentPolicy(
    rules={
        "LANG": EnvironmentValueRule(pattern=r"[A-Za-z0-9_.-]+", max_bytes=64),
        "MODE": EnvironmentValueRule(choices=frozenset({"test"})),
    },
    inherited=frozenset({"LANG"}),
    fixed={"MODE": "test"},
)
```

Only add credential variables when the command is explicitly designed to receive that credential and the broader tool surface is trusted to invoke it.

## Migration pattern: retries

Do not mechanically preserve an existing retry loop.

Classify the operation first:

- read-only/transient lookup: retry may be reasonable;
- compiler failure: usually deterministic and not retryable without input change;
- timeout: retry only if a transient host condition is plausible;
- output flood: usually do not retry;
- mutating command: retry only with target-level idempotency.

Then encode the narrow decision in `RetryPolicy` and a session retry budget.

## Migration pattern: loops and autonomous repair

Put the entire loop inside one `ShellSession`.

Example budgets can include:

- 8 process spawns;
- 4 failures;
- 120 seconds cumulative execution;
- 4 MiB total output;
- 2 retries.

The loop should terminate when any budget is exhausted. Budget exhaustion is an explicit state, not a reason to silently open a larger policy.

## Migration pattern: parallel tests

Use `BatchExecutor` instead of creating an unbounded thread/process fanout around `ShellRunner`.

Grant `parallel` explicitly to the caller.

Choose a worker bound based on repository/runner capacity, not the number of discovered tests.

If commands share mutable files or a build directory, use leases or separate workspaces.

## Migration pattern: dependency workflow

Use `PipelineSpec` for explicit step dependencies.

Do not encode sequencing as a shell string such as:

```text
command-a && command-b || command-c
```

Instead model `command-b` as depending on `command-a` and make failure/continue behavior explicit.

This yields better evidence because each process attempt has its own receipt.

## Migration pattern: model-created plan

Do not let a model emit a shell script.

Prefer one of these:

1. model chooses a registered command template and slot values;
2. model emits a versioned shell manifest containing logical command names;
3. model emits a higher-level task that deterministic code converts to a pipeline.

Then run preflight before execution.

Reject plans containing executable paths, unknown manifest fields, or command names not present in the catalog.

## Migration pattern: user-visible output

Use `ShellToolAdapter` for agent/tool surfaces.

Raw output is omitted by default.

When output is needed:

- request a bounded view;
- redact it;
- prefer parsed structured facts over raw logs;
- avoid echoing credentials, repository secrets, signed URLs, or auth headers;
- preserve the receipt ID so operators can correlate the execution.

## Replacing direct `subprocess` wrappers

A wrapper is worth keeping only when it adds domain semantics above `ShellExecutor`.

Examples of useful domain wrappers:

- `GodotProjectCompiler`;
- `ReadOnlyGitInspector`;
- `PythonCompileCheck`;
- `FrontendTypecheckRunner`.

Examples of wrappers to avoid:

- `run_command(command: str)`;
- `safe_subprocess(args)` with no policy;
- `execute_shell(text)`;
- wrappers that call `shlex.split` on untrusted text;
- wrappers that copy `os.environ` by default;
- wrappers that accept executable path as a request field.

## Tests to add for every migrated command

At minimum, test:

- accepted normal argv;
- unknown option rejection;
- hostile metacharacters remain literal data;
- oversized argv rejection;
- cwd escape rejection;
- unexpected environment key rejection;
- secret environment non-inheritance;
- timeout behavior;
- output bound behavior where practical;
- caller capability denial;
- command definition timeout ceiling;
- retry behavior if enabled;
- audit/receipt output does not expose sensitive values.

For high-risk executables, add adversarial flags specific to the tool.

## How to stage migration safely

Recommended order:

1. Add a command definition and tests without changing the call site.
2. Add policy/runner/executor construction near trusted application startup.
3. Route one narrow call site through `ShellExecutor`.
4. Compare behavior/evidence in tests.
5. Remove the old direct process call.
6. Run repository process-safety and shell regression suites.
7. Repeat for the next call site.

Avoid a repository-wide mechanical rewrite in one commit. Command contracts require domain-specific review.

## Policy review checklist

For every authority change, inspect:

- executable additions or retargets;
- cwd root expansion;
- environment-key additions;
- parent inheritance additions;
- timeout increases;
- output/input/env size increases;
- argument count/byte increases;
- new argument options;
- broader regexes/choices;
- stdin enablement;
- nonzero-success enablement;
- retry enablement;
- parallel/pipeline capability grants.

Use `diff_policies()` for machine-readable authority-direction hints, but keep human review for tool-specific semantics.

## CI integration

The shell regression suite should run with the canonical security/quality gates.

The independent process-safety scanner remains mandatory. The shell subsystem does not create an exemption for new direct subprocess sites.

A future call site that cannot use the canonical shell plane should document why, preserve argv-only execution, and add dedicated security tests.

## Completion criteria for a migrated surface

A surface is migrated when:

- no direct process spawn remains in the domain code;
- executable identity is trusted configuration;
- args/env/cwd are bounded and validated;
- aggregate loops have budgets;
- retries are explicit;
- evidence is receipt/audit based;
- user/model output exposure is bounded/redacted;
- tests cover adversarial input;
- canonical process-safety scanner still passes.
