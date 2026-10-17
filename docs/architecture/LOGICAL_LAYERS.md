# Logical layers

Machine authority: `machine/logical_layers.json`
Validator: `scripts/check_architecture_logical_layers.py`
Rule: `ARCH-LOGICAL-LAYERS`

| Order | Layer | May import | Canonical paths |
|------:|-------|------------|-----------------|
| 0 | domain | domain | `skeleton/kernel`, `skeleton/contracts` |
| 1 | infrastructure | domain, infrastructure | `skeleton/persistence`, `skeleton/observability`, `skeleton/config` |
| 2 | application | domain, infrastructure, application | `skeleton/intelligence`, `skeleton/memory`, `skeleton/retrieval`, `skeleton/agents`, `skeleton/automation`, `skeleton/forge` |
| 3 | interface | all classified layers | `skeleton/api`, `skeleton/app` |

Domain code may not import FastAPI, Flask, Django, Requests, HTTPX, SQLAlchemy, database drivers, Redis, or aiohttp. Application code may not import FastAPI, Flask, Django, or Starlette.

Unclassified Skeleton imports are reported and do not grant a higher-layer dependency. The numbered `PY-L0`–`PY-L4` ladder in `machine/python_package_layers.json` stays in force beside this view.

Known upward edges are debt, not permission to add another one. They are listed in the machine file and must match the scanner exactly.
