# Projects contract `skeleton.projects.v1`

The normative spec is `docs/architecture/contracts/projects.md` + `projects.schema.json`.
This page shows how main implements it.

- **Schema:** `PROJECTS_SCHEMA_ID = "skeleton.projects.v1"`, `PROJECTS_SCHEMA_VERSION = "1.0.0"`
  (`skeleton/contracts/projects.py`). Dataclasses: `ProjectBrief`, `ProjectCreateRequest`,
  `Project`, `ProjectListQuery`, `ProjectList`, `ProjectBuildLinkRequest`, `ProjectBuildLink`,
  `BuildStartRequest`, `Build`, `BuildList`. The limits are a title of 200 characters, a summary of
  8,000, 32 constraints and 64 builds, with IDs matching `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`.
- **Build statuses:** `pending, queued, running, succeeded, failed, cancelled`.
- **Routes** (`skeleton/api/projects_routes.py`, mounted at `/api/v1/projects`):
  `POST ""`, `GET ""`, `GET /{project_id}`, `POST /{project_id}/builds`,
  `GET /{project_id}/builds`, `GET /{project_id}/builds/{build_id}`.
- **Auth is two-layer:** `install_gate` (`x-gf-seal` client/service attestation) **and** an end-user
  session `Authorization: Bearer <session>` resolved by `AppServices.auth.resolve_session`.
  `actor_id` is the session user and `tenant_id` is `APP_TENANT_ID` (default `default`). Both are
  server-derived, and scope fields in the body are rejected.
- **Errors:** the envelope is `{"error":{"type","code":"PROJECT.*","message","context":{}}}`. The
  status map is `PROJECT_HTTP_STATUS`: INVALID 400, UNAUTHENTICATED 401, NOT_FOUND 404,
  BUILD_CONFLICT / NAME_CONFLICT / IDEMPOTENCY_MISMATCH 409, UNAVAILABLE 503.
- **Storage:** `skeleton.persistence.app_foundation.projects_v1.ProjectsV1Store` (SQLite).
- **Executor brief:** `build_playable_game` accepts the same v1 brief object through `coerce_brief`.

## References

- `skeleton.contracts.projects:PROJECTS_SCHEMA_ID`
- `skeleton.contracts.projects:PROJECTS_SCHEMA_VERSION`
- `skeleton.contracts.projects:ProjectBrief`
- `skeleton.contracts.projects:Build`
- `skeleton.contracts.projects:BUILD_STATUSES`
- `skeleton.contracts.projects:PROJECT_HTTP_STATUS`
- `skeleton.contracts.projects:ProjectContractError`
- `skeleton.api.projects_routes:build_router`
- `skeleton.api.projects_routes:router`
- `skeleton.persistence.app_foundation.projects_v1:ProjectsV1Store`
- `skeleton.app_services.ports:SessionPrincipal`
