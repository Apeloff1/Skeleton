# First-line Troubleshooting

For support staff and operators. Every command here is from the root [README](../../README.md)
or [APP_ASSEMBLY.md](../APP_ASSEMBLY.md).

## 1. Is it installed and set up?

```bash
python -m skeleton app preload
python -m skeleton app setup
python -m skeleton app install
# before the Python package is installed:
python scripts/install_app.py
```

Windows users normally use the Setup wizard; its launcher ships its own Python runtime.

## 2. What does the app think its state is?

```bash
python -m skeleton app status         # canonical topology
python -m skeleton app status --live  # probe live runtime health
python -m skeleton app check          # validate the assembly
```

If `check` fails, collect the output and route to engineering (see Routing below).

## 3. Does it start?

```bash
python -m skeleton app up      # frontend + backend + Skeleton API + Mongo
python -m skeleton app smoke   # verify public surfaces
```

- Fails immediately with container or compose errors: Docker Desktop is missing, stopped, or lacks the Compose plugin (macro M3).
- Only the engine is needed: `python -m skeleton run` boots the in-process engine without the full stack, which helps isolate whether the problem is in the services or the engine.

## 4. Developer-side checks

```bash
python -m skeleton dev health
python -m skeleton test
```

## What to collect for a bug report

- OS and version; install method; app version or commit
- Exact command and full output
- `app status --live` and `app check` output
- Whether `app smoke` passes

## Routing

Use the ownership map in [ARCHITECTURE_MAP.md](../ARCHITECTURE_MAP.md) to pick the owning lane,
then file a GitHub issue with the bundle above. For user-visible outages, start the
[incident comms runbook](incident-comms.md).
