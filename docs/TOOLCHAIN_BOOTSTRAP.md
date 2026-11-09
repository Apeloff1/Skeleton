# Toolchain Bootstrap

Issue: #807, batch B004.

Skeleton has one local bootstrap contract for the core development toolchain:

```bash
mise run bootstrap
```

The command is defined in `.mise.toml`. It performs two ordered actions:

1. `mise install` installs the exact Python, Node, and uv versions pinned by
   the repository.
2. The pinned Python runtime executes
   `scripts/verify_toolchain_bootstrap.py`, which validates the installed
   versions and the host capabilities required by the build.

## Pinned tools

The canonical pins are shared with CI and self-checked by
`scripts/check_toolchain_contract.py`:

- Python 3.11.16
- Node 24.20.0
- uv 0.12.15

Do not add an independent version source. Changes to these pins must update the
existing CI/toolchain contract and the B004 bootstrap manifest together.

## Host prerequisites

The bootstrap intentionally does **not** download or install its own bootstrap
manager. Install `mise` through your trusted operating-system/package-manager
path first. The repository does not use curl-to-shell bootstrap code.

The verifier requires and checks:

- a host listed in `machine/toolchain_bootstrap.json`;
- Git 2.40 or newer; and
- Java 21 or newer.

The manifest currently permits Linux, macOS, and Windows on the declared
x86-64/ARM64 architecture spellings.

## Fail-closed behavior

The verifier rejects:

- drift between `.mise.toml`, the machine manifest, and canonical CI pins;
- missing or changed bootstrap task steps;
- unsupported OS/architecture values;
- missing Python/Node/uv/Git/Java/mise executables;
- Python, Node, or uv versions different from the exact pins;
- Git or Java versions below the declared capability floor; and
- malformed or unbounded bootstrap metadata.

It emits a small deterministic JSON evidence record after successful
verification. It does not print environment variables, credentials, package
manager state, or arbitrary host information.

## Offline / restricted environments

The verification phase never opens the network. `mise install` may need its
normal package/tool downloads when the pinned tools are absent. In a restricted
environment, pre-populate the mise cache or tool installations through your
approved artifact mirror, then run the same `mise run bootstrap` command.

The repository does not silently fall back to unpinned system Python, Node, or
uv when installation or verification fails.
