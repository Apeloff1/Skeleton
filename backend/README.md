# Skeleton application API

The FastAPI backend owns authenticated application accounts, conversations, project
state, crawler captures, studio jobs and API projections. The engine owns model
execution and provider credentials; backend feature code uses that canonical boundary.

## Start and configure

Follow the [root first-install guide](../README.md#first-install), preferably using
`python scripts/install_app.py --production --start` in the repository Python
environment. Compose starts Mongo, the engine, this backend and the frontend.
The generated private `.env` supplies stable database and service credentials.

- `/api/health`: application health; AI readiness is a separate observation.
- `/api/auth/*`: existing account/login authority; public users register as viewers.
- `/api/game-studio-health`: actual studio and optional native readiness.
- `/api/game-learning/resources`: bounded CPU/worker capacity.
- `/api/dragon-academy/runtime/readiness`: practice/knowledge store readiness.
- `/api/dragon-academy/crawler/readiness`: authenticated capture readiness.

Use the documented owner bootstrap for editor/admin operations. Do not disable auth,
copy engine tokens into browser code, or construct provider clients in route modules.

## Persistent state and native work

Mongo remains the application data authority. Existing reviewed-knowledge/practice
SQLite stores live in private persistent backend data; bootstrap creates empty schemas,
never artificial knowledge or training progress. Preserve their identities and volumes
when rebuilding images. Use canonical recovery instead of deleting a failing store.

The standard Alpine image has explicit optional native blockers. SDKs/cores installed
on a host do not automatically become usable in a container. Consult
[native readiness](../docs/ai/STUDIO_INSTALLATION_AND_NATIVE_READINESS.md) for supported
host installations, approved libraries/content and mandatory isolation.

See [assembly operations](../docs/APP_ASSEMBLY.md),
[studio operations](../docs/ai/STUDIO_CRAWLER_BUILDER_TRAINING.md) and
[first-install AI/crawler setup](../docs/ai/FIRST_INSTALL_AI_AND_CRAWLER.md).
