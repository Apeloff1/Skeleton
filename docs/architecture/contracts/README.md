# Internal and API contracts

Typed contracts live in `skeleton/contracts/`. Human-readable HTTP and boundary notes live in this directory. Version fields are part of the contract; callers reject any other version.

| Contract | Typed module | Notes |
|----------|--------------|-------|
| Projects resource | `skeleton/contracts/projects.py` | [projects.md](projects.md) and [projects.schema.json](projects.schema.json). `skeleton.projects.v1` at `1.0.0`, mounted at `/api/v1/projects`. |
| Subsystem boundaries | `skeleton/contracts/subsystem_boundaries.py` | Kernel, agents, memory, GameForge facade, API error envelope. Version `1.0.0`. |
| Health probes | `skeleton/contracts/health.py` | Parses the existing liveness and readiness JSON. Does not add routes. |
| Operation envelope | `skeleton/contracts/protocol.py` | Existing transport-neutral internal protocol. |
| Memory record | `skeleton/contracts/memory_record.py` | Existing durable memory authority. |
| Job queue | `skeleton/app_services/job_api.py` | [docs/contracts/job_queue.md](../../contracts/job_queue.md). Public enqueue, status, result, and cancel API used by Projects builds (`game.build`). |

Projects is the contract for the #4097 router. The router blob is identical at `959eec134` and at the current #4097 head `c71ad467`. It creates a project from a string or structured brief, lists, gets, starts or links a build, and paginates the build list. The session supplies `actor_id`. `tenant_id` is the deployment-scoped `APP_TENANT_ID`. A started build's `execution_id` equals its `build_id`, and the `game.build` worker runs `build_playable_game`.
