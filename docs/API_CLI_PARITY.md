# API / CLI feature parity

Skeleton exposes a versioned application command contract beneath both HTTP and command-line transports. The contract is intentionally transport-neutral: operation names, normalized result envelopes, CLI exit codes, HTTP status mappings, and runtime handlers live in `skeleton.application`.

## Contract surfaces

| Operation | API | CLI | Shared handler | Notes |
| --- | --- | --- | --- | --- |
| `run` | `POST /api/v1/commands/execute/run` | `skeleton command run '{...}'` | Yes | Uses the live GameForge runtime. The legacy `/gameforge/run` route now delegates to the same handler. |
| `tool` | `POST /api/v1/commands/execute/tool` | `skeleton command tool '{"action":"list"}'` | Yes | Shared contract currently exposes safe capability listing; unrestricted invocation remains outside this foundation. |
| `memory` | `POST /api/v1/commands/execute/memory` | `skeleton command memory '{"query":"..."}'` | Yes | Queries the unified memory service. |
| `status` | `POST /api/v1/commands/execute/status` | `skeleton status` | Yes | Does not force runtime boot. |
| `configuration` | `POST /api/v1/commands/execute/configuration` | `skeleton config` | Yes | Returns non-secret application/runtime metadata only. |
| `admin` | `POST /api/v1/commands/execute/admin` | `skeleton command admin '{"action":"summary"}'` | Yes | Shared mode is inspection-only in this first contract version. |

The complete machine-readable matrix is available from `GET /api/v1/commands/contracts` and `skeleton contracts`.

## Result envelope

Successful commands return the same logical envelope on both surfaces:

```json
{
  "contract_version": "1.0",
  "command": "status",
  "ok": true,
  "data": {}
}
```

Failures return:

```json
{
  "contract_version": "1.0",
  "command": "memory",
  "ok": false,
  "error": {
    "code": "unavailable",
    "message": "memory service is not initialized"
  }
}
```

## Error semantics

| Error code | CLI exit | HTTP status |
| --- | ---: | ---: |
| `invalid_command` | 2 | 404 |
| `invalid_argument` | 2 | 422 |
| `unsupported_operation` | 3 | 501 |
| `unavailable` | 3 | 503 |
| `forbidden` | 4 | 403 |
| `conflict` | 5 | 409 |
| `internal_error` | 70 | 500 |

Transport adapters should not invent alternate meanings for these codes. New command families should be added to the shared contract first, then registered with runtime handlers and surfaced through both transports.

## Streaming

Contract version 1.0 records streaming capability in command metadata but does not introduce a shared streaming protocol. Commands are request/response in this version. A later contract version can add event framing without changing the existing result/error envelope.

## Creator CLI: explicit evidence boundary (2026-10-13)

The **creator CLI** `python -m skeleton run` is the ten-stage
`skeleton.context.pipeline.GameForgeRun` application workflow. It is
**not yet equivalent** to `skeleton command run` or the HTTP
`POST /gameforge/run` legacy handler: those currently call
`state.gameforge.run` and can produce different file manifests.
Do not claim creator/API parity until [#3613](https://github.com/Apeloff1/Skeleton/issues/3613)
lands a single canonical execution adapter and fixture-based manifest
comparison.

Creator CLI now supports questionnaire intake and real headless Godot
boot verification:

```sh
python -m skeleton cockpit BIND ERA cozy_wholesome
python -m skeleton cockpit BIND ARCHETYPE auto
python -m skeleton cockpit SNAPSHOT --out ./creator-steering.json
python -m skeleton run "a peaceful village" --answers ./answers.json \
    --out ./output/village --playtest require --repair-mode apply
python -m skeleton cockpit RESTORE ./creator-steering.json
python -m skeleton run "a new village" --era soulslike --playtest auto
```

`--answers` accepts a UTF-8 JSON object whose keys and values are
strings, with a 1 MiB size limit. Missing/invalid input fails without
launching the forge. `--playtest off` is the default; `auto` records
the Godot boot result when available; `require` makes a missing or
failed headless boot fatal and reports the failing `emit` stage.
`--repair-mode` accepts `apply` or `suggest`.

The console persists **operator steering only** in
`~/.skeleton/cockpit.json` (override with
`SKELETON_COCKPIT_STATE`). Era, ten tensor axes, era blend, hardware
generation, and archetype survive separate invocations. `SNAPSHOT
--out` and `RESTORE` export/import that exact steering schema.
A command-line `--era` overrides a saved era/era blend. Execution
ledgers, model traces, transient inference state and credentials are
**not** persisted by this creator-control file. Writes are atomic and
private to the local operator account.
