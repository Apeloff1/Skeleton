# Shell execution policy

Skeleton host commands should be treated as a capability, not as arbitrary shell text. The canonical runtime helper is `skeleton.shells.ShellRunner`.

## Contract

- Commands are explicit argv vectors. There is no `shell=True`, `os.system`, shell string parsing, or implicit command interpolation.
- Executables are registered by logical name and resolved from absolute paths when the policy is created. Runtime `PATH` lookup is not used.
- Child processes receive only environment keys named by the policy. Full ambient environment inheritance is intentionally unavailable.
- The working directory must resolve inside an allowed root.
- Argument count/bytes, stdin bytes, total child-environment bytes, combined stdout/stderr bytes, and wall-clock runtime are bounded.
- Timeouts and output-limit violations terminate the process; on POSIX the runner starts a new session and terminates the process group.
- Error messages do not echo child output or argv, reducing accidental credential/log disclosure.

## Example

```python
from pathlib import Path
import sys

from skeleton.shells import ShellCommand, ShellPolicy, ShellRunner

workspace = Path("/srv/skeleton/workspaces/job-42")
policy = ShellPolicy(
    executables={"python": sys.executable},
    cwd_roots=(workspace,),
    allowed_env=frozenset({"LANG"}),
    inherited_env=frozenset({"LANG"}),
    max_timeout=30.0,
    max_output_bytes=256_000,
)
runner = ShellRunner(policy)
result = runner.run_checked(
    ShellCommand("python", ("-m", "compileall", "-q", "."), cwd=workspace)
)
```

Do not accept a user/model supplied executable path and register it on demand. The allowlist is the authority boundary. Treat any expansion of executable, environment, or cwd grants like another capability change and cover it with tests.

## Static enforcement

`scripts/check_repository_process_safety.py` remains the repository-wide regression gate for direct process calls. It rejects shell execution and statically provable string-shaped subprocess commands across `backend/`, `skeleton/`, and `scripts/`. `ShellRunner` complements that static gate by providing a reusable runtime policy for code that genuinely needs host execution.
