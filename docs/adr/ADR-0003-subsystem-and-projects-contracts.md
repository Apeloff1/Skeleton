# ADR-0003: Versioned subsystem contracts and the Projects resource

Status: **accepted**

Decision source: the app foundation client and frontend align to the Projects router Internal Systems is moving onto `/api/v1/projects`.

## Context

Kernel, agents, memory, GameForge, and the API already exchange data through a mix of Python dataclasses, machine protocol rows, and HTTP handlers. The app foundation client (auth, agents, builds, SSE parsing) and the frontend shell are landing against that surface. Builds are engine executions. The backend has no Projects routes, and the client therefore has no `ProjectsClient`.

Publishing a second Projects shape beside the #4097 router would fork the resource. The schema describes that router.

## Decision

`skeleton/contracts/subsystem_boundaries.py` publishes version `1.0.0` envelopes for kernel events, agent tasks, memory writes, the GameForge `run`/`intake` facade, and the API error object. GameForge pipeline internals stay behind a request digest.

`skeleton/contracts/projects.py`, `docs/architecture/contracts/projects.md`, and `docs/architecture/contracts/projects.schema.json` publish Projects schema `skeleton.projects.v1`. Version `1.1.0` describes the Projects router on PR #4097 (`skeleton/app_services/projects_api.py`, commit `7065e555`) at the mount Internal Systems is moving to: `/api/v1/projects` inside `create_app`, behind `install_gate`.

- `POST /api/v1/projects` creates a project from a brief. The brief is a string or a structured object (`title`, `summary`, `genre`, `constraints`).
- `GET /api/v1/projects` and `GET /api/v1/projects/{project_id}` return `ProjectOut` rows. The owner is the session user (`owner_id`).
- `POST /api/v1/projects/{project_id}/builds` starts a server-side build and returns a `Build` with `execution_id`. A body that includes `execution_id` links that execution and does not start another job.
- `GET /api/v1/projects/{project_id}/builds` and `GET /api/v1/projects/{project_id}/builds/{build_id}` read those builds.

`actor_id` and `tenant_id` are derived from the bearer session and are not request fields. Errors use the Skeleton envelope (`error.type`, `error.code` as `PROJECT.*`, `error.message`, `error.context`) and never carry secrets. The checked commit still serves `/api/app/projects` with `{"detail": ...}`; the contract is the moved shape, not a second resource.

Health payloads keep their current JSON. `skeleton/contracts/health.py` parses them. Public configuration snapshots go through `skeleton/config/public_snapshot.py`.

## Consequences

The foundation client adds `ProjectsClient` against `PROJECT_ROUTES` and the `Project` / `Build` documents. The session user is `owner_id`. A missing project and a project owned by another session user share `PROJECT.NOT_FOUND`.

## Amendment (1.1.0)

Version `1.0.0` specified a contract-only project with `actor_id` and `tenant_id` on every body, RFC3339 timestamps, and a link-only `POST /builds` that did not start a build. That shape was a parallel spec. `1.1.0` replaces it with the checked #4097 resources (`ProjectOut`, `BuildOut`, epoch timestamps, bearer session, server-side `BuildService.submit`) plus the mount ruling: `/api/v1/projects`, brief string or object, `execution_id` on the Build, optional link, and the `PROJECT.*` envelope.
