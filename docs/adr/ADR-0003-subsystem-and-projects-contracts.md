# ADR-0003: Versioned subsystem contracts and the Projects resource

Status: **accepted**

Decision source: the app foundation client and frontend need a Projects contract before routes exist.

## Context

Kernel, agents, memory, GameForge, and the API already exchange data through a mix of Python dataclasses, machine protocol rows, and HTTP handlers. The app foundation client (auth, agents, builds, SSE parsing) and the frontend shell are landing against that surface. Builds are engine executions. The backend has no Projects routes, and the client therefore has no `ProjectsClient`.

Publishing handlers before the schema would freeze a path the client cannot see. Publishing a second, informal shape in the client would fork the resource.

## Decision

`skeleton/contracts/subsystem_boundaries.py` publishes version `1.0.0` envelopes for kernel events, agent tasks, memory writes, the GameForge `run`/`intake` facade, and the API error object. GameForge pipeline internals stay behind a request digest.

`skeleton/contracts/projects.py`, `docs/architecture/contracts/projects.md`, and `docs/architecture/contracts/projects.schema.json` publish Projects schema `skeleton.projects.v1` at version `1.0.0`:

- `POST /api/v1/projects` creates a project from a brief
- `GET /api/v1/projects` lists projects for an actor and tenant
- `GET /api/v1/projects/{project_id}` returns one project
- `POST /api/v1/projects/{project_id}/builds` links an existing engine `execution_id`

These routes are not mounted. A later router must use this schema. Linking a build does not submit an execution; submit stays `POST /api/v1/engine/executions`. Errors use the existing Skeleton envelope (`error.type`, `error.code`, `error.message`, `error.context`) and never carry secrets.

Health payloads keep their current JSON. `skeleton/contracts/health.py` parses them. Public configuration snapshots go through `skeleton/config/public_snapshot.py`.

## Consequences

The foundation client can add `ProjectsClient` against `PROJECT_ROUTES` without waiting for storage. Until handlers exist, calling the paths is a defect, not a feature.

Scope matches builds: `actor_id` and `tenant_id` travel with every call. A missing project and a project outside that scope share `PROJECT.NOT_FOUND`.
