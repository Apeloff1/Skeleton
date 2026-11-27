# Mongo health and recovery qualification

The Compose Mongo probe authenticates against admin and explicitly exits zero only when ping returns numeric 1. Shell or connection failures must remain nonzero. Skeleton and backend wait for Mongo health on initial startup; this does not guarantee automatic dependent restarts after a later outage.

## Qualification (isolated disposable environment)

Use the existing setup procedure to supply test credentials and an isolated Compose project on a disposable host (container names are fixed). Never reuse production volumes or ports.

1. Run `python -m pytest -q tests/test_compose_mongo_ping_exit.py` and `docker compose config --quiet`.
2. Start Mongo using `docker compose up -d mongo`; inspect health with `docker inspect --format '{{.State.Health.Status}}' tutolage-mongo`. Expect healthy with valid credentials.
3. In the disposable environment, execute the same mongosh probe with deliberately incorrect credentials and confirm nonzero exit. Do not print credentials or enable shell tracing.
4. Start the dependent services and verify their readiness endpoints. Stop Mongo, verify application readiness/error behavior, then start Mongo and verify recovery. Record exact commit, image digest, platform, health transitions and exit codes.
5. Verify previously inserted disposable test data remains readable after restart.

Do not delete volumes, rotate credentials on existing databases, or recreate Chroma to change its persistence mount. If Mongo authentication fails on an existing volume, investigate credential custody and restore procedures before changing configuration. The shell regression is not evidence of physical Docker recovery or successful authenticated Mongo execution. All migration and release holds remain in force.
