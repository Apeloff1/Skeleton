# Historical self-host deployment recovery — source integration candidate

The archived `feat/gf-deployment-nsog-20261024` branch implemented a guarded
self-hosting plane but diverged from today's expansive `skeleton/__main__.py`.
This reconciliation imports its eight original modules and eight regression
files into the current main tree, without overwriting the modern CLI or
compatibility namespace.

## Integrated source

- `skeleton/deployment/profile.py` — validated offline, local, and service profiles
- `validation.py` — structured fail-closed profile policy
- `envfile.py` — deterministic redaction, bounded env files, atomic writes
- `health.py` — process and HTTP preflight/readiness
- `manifest.py` — source-bound Docker/package identity and digest verification
- `units.py` — systemd/Compose service renderers
- `boot.py` — validate -> preflight -> launch -> readiness -> serve
- `cli.py` — operator profiles, inspect, validate, check, probe, manifest,
  render units, boot and dry-run.

The only existing mainline file modified is `skeleton/__main__.py`: a lazy
`python -m skeleton deploy` command dispatch is inserted near `app`,
preserving all modern game, Jeeves, and runtime commands. Existing
`skeleton/deployment/__init__.py` stays import-light and retains all
compatibility exports; no eager service import or provider activation.

## Qualification and limitations

**Review-only and no launch claim.** Historical code can contain old assumptions.
Exact-head tests must include eight deployment regression files, CLI
`--help` and dry-run, source compile, profile/env redaction and permission
tests, path/symlink policy, process cleanup, signal and timeout handling,
network service isolation, and Docker manifest parity. Regression evidence
must be independently verified on Windows 11/WSL2, Linux/systemd, Docker,
and native/offline local-model hosts before release.

Do not consider queued, skipped, cancelled, superseded or ancestor checks
passing. Do not execute `deploy boot` against a live service without
operator-approved profile and environment. No mutation of main occurs here.
