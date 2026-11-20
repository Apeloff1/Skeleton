# Standalone Jeeves Docker — independent real two-service Mongo journal audit

**Read-only physical prerequisite. Not writer enrollment. Not production
migration.** This operator action uses both actual running local Docker
application services, without starting containers, mounting volumes,
changing Mongo replica configuration or downloading models.

## Invoke

```sh
python scripts/local_ai_docker.py --mode cpu audit-real-writer-journal
```

The same command supports `--mode nvidia` or `--mode rocm` when that
canonical Compose profile has already passed independent device admission.
A successful command merely establishes that the two actual services can
read the same authenticated Mongo primary and its current majority journal
configuration. It cannot enable a Compose epoch overlay or alter user data.

## Source components

- `skeleton/persistence/docker_epoch_writer_policy.py` now exposes
  synchronous **and** asynchronous bounded five-command real Mongo policy
  checks against existing authenticated client handles.
- `skeleton/persistence/docker_epoch_writer_probe.py` runs in one existing
  service process via a separate `docker compose exec -T`. It reads a
  linearizable canonical epoch sentinel, the five-policy-command census,
  and a second linearizable epoch sentinel, refusing identity drift.
- `scripts/local_ai_real_journal_audit.py` drives engine and backend
  probes from the canonical local-only Compose definition and verifies
  strict allowlisted JSON receipts from both.
- `scripts/local_ai_docker.py` exposes `audit-real-writer-journal` as
  a read-only action. No additional credentials or operator tokens are
  accepted as command-line arguments.

## Exact physical proof sequence

1. Re-attest actual current running local Docker containers and their
   existing Compose boundary. The standard dual-service epoch capability
   gate must already prove both services can read the same Mongo primary.
2. Inside the **existing Jeeves engine** container, open an authenticated
   service-local Mongo client using `SKL_MONGO_URI` with exact internal
   `mongo:27017` hostname and administrative authSource.
3. Perform one primary-validated linearizable sentinel read; read `hello`,
   `replSetGetStatus`, `replSetGetConfig`, `getDefaultRWConcern`,
   and another `hello`. Require unique member IDs, exact live/config
   voter mapping, one current primary, ≥3 voting data-bearing nodes,
   healthy majority, explicit `w=majority` and majority-journal policy.
   Perform a second linearizable epoch read and compare process identity.
4. Perform the same independent read-only probe **inside the existing
   backend container**, using its distinct `MONGO_URL` environment.
5. Compare engine/backend replica set and primary process fingerprint,
   configured/voting-member counts, and the fingerprint originally
   attested by the canonical dual-service preflight.
6. Re-run the original dual-service epoch capability check and running
   Docker attestation. A changed primary identity or a malformed/extra
   field in any receipt fails closed.
7. Output only the shared SHA-256 fingerprint, non-sensitive replica
   name, aggregate member counts and a fixed set of proof/hold booleans.

The command cannot read environment secrets into the host response,
print URI values, start the model, enable epoch fencing, change a database
record, create a Mongo index or mutate Docker state. It runs two distinct
new Python inspection processes, **not** in-memory introspection of the
existing long-lived backend or engine workers.

## Production evidence boundaries

| Claim | Audit result |
|---|---|
| Current authenticated dual-service Mongo quorum policy | Read-only, physical if command passes |
| Shared current primary identity between both services | Read-only, physical if command passes |
| Linearizable sentinel reads and journal majority defaults | Read-only, physical if command passes |
| Long-running backend conversation epoch actually attached | Not proven |
| Long-running engine memory epoch actually attached | Not proven |
| Complete external writer registry / no mixed-version writers | Not proven |
| Existing actor migration and writer quiescence | Not proven |
| Power-loss durability on independent hosts | Not proven |
| Coherent Mongo + SQLite + optional Chroma snapshot/recovery | Not proven |
| Authenticated Jeeves local GGUF chat inference | Not proven |
| Merge, Windows/WSL2, GPU and signed release | Not authorized |

The default application Compose still uses a standalone Mongo deployment,
so **the expected result is denial** until an independently authorized
production replica set, credentials, topology and live services actually
exist. A green synthetic three-voter tmpfs test cannot substitute for
these actual application-service observations.

## Focused source tests

```sh
python -m compileall -q \
  skeleton/persistence/docker_epoch_writer_policy.py \
  skeleton/persistence/docker_epoch_writer_probe.py \
  scripts/local_ai_real_journal_audit.py \
  scripts/local_ai_docker.py \
  skeleton/testing/test_local_ai_real_journal_audit.py \
  skeleton/testing/test_docker_epoch_writer_policy.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_real_journal_audit.py \
  skeleton/testing/test_docker_epoch_writer_policy.py
```

Unit tests use fake source/service responses and cannot certify a
physical Docker execution. That requires independently running the
explicit command on an operator-owned installation and retaining the
exact receipt SHA and hardware/source provenance. No merge or release.
