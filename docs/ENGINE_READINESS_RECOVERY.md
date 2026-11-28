# Engine readiness and recovery

Compose admits the backend only after the engine readiness probe succeeds.
The engine readiness endpoint returns HTTP 503 before recovery completes,
during drain, or when its health provider is unavailable or reports unready.
The standalone image liveness probe remains independent. Missing optional
model artifacts do not by themselves prevent application startup.

## Qualification (disposable installation only)

1. Run `python -m pytest -q tests/test_infra_engine_readiness_contract.py`.
2. With a configured local environment, run `docker compose config --quiet`.
3. Start the stack with `docker compose up -d`; inspect `docker compose ps`
   and confirm the engine becomes healthy before backend admission.
4. Verify `curl --fail http://127.0.0.1:8010/api/v1/health/ready`
   (adjust for the configured port). Record status and exact image/source SHA.
5. On a disposable stack, stop the engine, verify backend engine-dependent
   requests fail closed, then start the engine and verify readiness and a
   real engine-dependent request recover. Frontend diagnostics must remain
   available. Compose startup dependencies do not continuously supervise
   already-running dependents.

Do not remove volumes, recreate existing Chroma containers, or change
migration state to perform these checks. Preserve all existing recovery
and release holds. These commands are qualification instructions, not
executed evidence.
