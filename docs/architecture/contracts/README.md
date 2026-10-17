# Internal and API contracts

Typed contracts live in `skeleton/contracts/`. Human-readable HTTP and boundary notes live in this directory. Version fields are part of the contract; callers reject any other version.

| Contract | Typed module | Notes |
|----------|--------------|-------|
| Projects resource | `skeleton/contracts/projects.py` | [projects.md](projects.md) and [projects.schema.json](projects.schema.json). `skeleton.projects.v1` at `1.1.0`, mounted at `/api/v1/projects`. |
| Subsystem boundaries | `skeleton/contracts/subsystem_boundaries.py` | Kernel, agents, memory, GameForge facade, API error envelope. Version `1.0.0`. |
| Health probes | `skeleton/contracts/health.py` | Parses the existing liveness and readiness JSON. Does not add routes. |
| Operation envelope | `skeleton/contracts/protocol.py` | Existing transport-neutral internal protocol. |
| Memory record | `skeleton/contracts/memory_record.py` | Existing durable memory authority. |

Projects is the contract for the #4097 router (create from a brief, list, get, start or link a build). The session supplies the owner. A started build's `execution_id` is the engine execution at `/api/v1/engine/executions/{execution_id}`.
