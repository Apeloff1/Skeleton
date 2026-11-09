# Massive E2E preparation and evidence runbook

**2026-10-13 preparation status: NOT an E2E completion certificate.**

This is an additional diagnostic control plane for the existing Stage-7
golden journeys, local-inference chat integration, Node-side browser stream
contracts, and frontend product journey contracts. Runtime tracing itself
continues to use the canonical system in [OBSERVABILITY.md](OBSERVABILITY.md).

## Disposable live E2E opt-in (2026-10-16)

The previously hazardous Galaxy Studio and playable-async test modules now
**skip at import time unless explicit approval is present**. Their target is
`SKELETON_DISPOSABLE_E2E_URL`, not the production, Expo or checked-in .env
backend URL. Only loopback http(s) with an explicit port is accepted. Keep a
separate disposable backend, database, dedicated provider/test account and
cleanup receipts. These controls do not make a production backend safe.

```bash
# Explicitly inspect a disposable local backend, read-only where possible:
SKELETON_DISPOSABLE_E2E_APPROVED=1 \
SKELETON_DISPOSABLE_E2E_URL=http://127.0.0.1:8001 \
python -m pytest -q backend/tests/test_iteration_79_galaxy_studio_full_e2e.py

# A missing completed Galaxy build is SKIPPED rather than silently
# creating a 48,000-file background build. That path additionally needs:
SKELETON_DESTRUCTIVE_E2E_APPROVED=1

# Live playable async creation may incur provider billing; it requires:
SKELETON_BILLED_E2E_APPROVED=1
```

The two extra approval variables are independent and must equal literal `1`.
Without them, the corresponding destructive/paid test is skipped. Normal
pytest collection will not make these calls, and even an Expo URL configured
elsewhere is insufficient authorization. Hermetic gate regressions live in
`skeleton/testing/test_live_service_gate.py`.

**These are safety controls, not completion evidence:** real deployed
browser/device, installed local checkpoint and full Stage-7 receipts remain
unverified. Record source SHA, target, budget, isolation and disposal before
approving any expensive tests.

## Execution boundaries

The PR workflow always runs **preflight only**:
- Parse the versioned machine/e2e_suites.json manifest.
- Check that prerequisite source files and work directories exist.
- Statically inspect tracked test files using AST for Python (without imports),
  inspect JavaScript tests and workflow evidence-retention surfaces, and
  classify network/process/database/mutation, skip and live-test candidates.
- Write exact-head run metadata, events, issue records, summary and gap report.

To run the bounded offline E2E shards, explicitly dispatch
**Pre-E2E Evidence and Massive Offline Journeys**, selecting
**run_offline=true**. Seven shards then run with independent verdicts,
30-minute job ceilings, suite-level timeouts, and max three parallel jobs.
The offline runner refuses any suite labeled live.

Live/deployed-service, provider-billed, destructive, Playwright and device
tests are NOT implicitly run or endorsed by this workflow. They require
disposable infrastructure, budget and identity controls, explicit approval,
and a separately defined integration environment.

## Evidence contract

- **report.json**: mode, UTC timestamps, exact checkout SHA, status, test
  inventory and per-shard duration/exit status.
- **events.jsonl**: chronological lifecycle events, issue creation events,
  and bounded redacted stdout/stderr lines correlated by run ID.
- **logs/SUITE.log**: timestamped diagnostic log, bounded in line count and
  size and sanitized by the existing observability redaction utility.
- **junit/SUITE.xml**: structured case-level pytest failure/error evidence
  parsed and sanitized before being uploaded. Missing/malformed XML is
  a failure rather than a green result. Empty receipts and skipped/expected-failure
  cases also become explicit unverified-test issues.
- **issues.json**, **issues.md** and **summary.md**: stable issue signature,
  phase, severity, failing testcase, evidence path and explicit open
  disposition. Success in one shard never hides another shard failure.
- **advanced-parse.json** and **advanced-parse.md**: test-source SHA-256,
  risk flags, estimated test counts, issue candidates, and categorized
  coverage. Static flags are candidates, not confirmed defects.

A final aggregator downloads the manifest-defined independent shard receipts, requires all
seven passes at one exact SHA, and emits aggregate.json and aggregate.md.
Missing, duplicate, malformed and failed shards become open issues rather
than disappearing from the status report.

Artifacts upload even when preflight or a shard fails and are retained
90 days in GitHub Actions. These logs are operational evidence, not
cryptographically signed release attestations. Never include provider
credentials, user data or production secrets in test fixtures.

## Concrete gaps identified before execution

| ID | Risk | Finding and required action |
| --- | --- | --- |
| PRE-E2E-01 | High | The current Stage-7 golden journey workflow has separate pytest and Node commands but no apparent persistent comprehensive JUnit + event + issue artifact collection. Preserve diagnostics for every failing step. |
| PRE-E2E-02 | High | backend/tests/test_iteration_79_galaxy_studio_full_e2e.py may start a 48,000-file build against localhost:8001 when no completed fixture exists. Keep excluded from offline/CI bulk runs; only execute on disposable server and data. |
| PRE-E2E-03 | High | backend/tests/test_playable_async_e2e.py expects a configured service URL, known playable ID and an LLM-backed long-running job; isolate and budget the remote/provider run. |
| PRE-E2E-04 | Medium | Backend CI excludes live_service markers via pytest selection, while legacy endpoint-style tests and the registry need explicit reconciliation before an expanded E2E wave. |
| PRE-E2E-05 | Medium | Node frontend contract tests do not substitute for real-browser screenshots, console/network diagnostics, real Expo/web/mobile navigation and keyboard/accessibility assertions. |
| PRE-E2E-06 | Medium | Local-model golden tests provide useful engine journeys but cannot by themselves prove installed desktop/mobile app + native checkpoint usability and recovery. |

These are preparedness findings, **not observed runtime test failures**.

## Massive run readiness gates

1. Freeze exact commit SHA, Linux/Windows/macOS build identities, container
   digests, dependency lockfiles, model checkpoint hash and test data revision.
2. Run the preflight and triage high-severity static findings, missing paths,
   live-service registry/marker mismatches and skipped tests.
3. Provision isolated Mongo, Skeleton engine, backend, frontend and disposable
   tenants; record startup health, exit codes and service-side correlation IDs.
4. Define run strata: offline; disposable-service integration; browser/device;
   provider and paid external integrations; destructive recovery and migration.
   No fallback from a safe stratum into a dangerous one.
5. Capture browser console/network failures, frontend stack traces, screenshot
   and trace on failure; server and worker logs, DB fault state, resource
   pressure, request/run/task IDs and deterministic fixture/seed identifiers.
   Strip credentials before exporting any evidence.
6. Record issues for assertions, collection failures, skips, missing receipts,
   timeouts, crashes and cleanup failures. Each issue requires a reproducible
   head SHA, artifact link, owner, reproduction recipe, root-cause note, fix
   commit and revalidation.
7. Re-run failed shards at the original exact head and the fixing head, then
   re-run the full isolated matrix before release. Never claim readiness
   from an unexecuted, skipped or inconclusive journey.

## Local operator commands

### Resume the disposable assembled campaign

Install the repository Python requirements and locked frontend dependencies,
and select a local MongoDB executable. Commit the candidate before starting:

    python scripts/e2e_assembled_system.py --mongod /absolute/path/to/mongod --output-dir .e2e-evidence/assembled

The campaign clones the exact candidate into a temporary checkout, builds its
Expo export, trains a small credential-free model fixture, and starts isolated
Mongo, engine, backend and browser services. `--backend-port`, `--engine-port`
and `--web-port` select distinct loopback ports when another campaign is active.
Installed frontend dependencies may be selected with `--node-modules`.

The evidence binds every exported asset, the frontend lockfile, the candidate
commit and fixture model build. It exercises authenticated provider status,
cross-principal conversation denial, concurrent idempotent replay, two-turn
lineage, an immutable edit branch, browser refresh, project-loaded world/design
views, mobile companion controls, process restart, governed conversation
deletion, and engine-outage degradation. Seeded project artifacts verify view
wiring; they do not certify game generation. Unreached journeys are recorded
explicitly. Forced shutdown or incomplete cleanup fails the campaign, while
uvicorn's final SIGTERM exit requires a shutdown-completion marker from that
specific process generation.

The optional `--web-export` accepts only an export with a sibling
`NAME.receipt.json` containing the exact `head_sha`, `assets_sha256`,
`backend_url` and `engine_url`. Building directly from the candidate is the
default. A selected local Godot binary is forwarded only to `app-cli-forge`:

    SKELETON_GODOT_BIN=/absolute/path/to/godot python scripts/e2e_evidence.py --mode offline-e2e --suite app-cli-forge --output-dir .e2e-evidence/forge

The selected executable is checked and its digest recorded. Provider secrets
remain excluded. Skipped tests, unexpected passes and missing structured test
receipts fail evidence qualification. Fixture-model execution, Chromium mobile
viewports and headless Godot runs do not qualify model quality, installed mobile
devices, desktop installers, live providers or enterprise readiness.

    python scripts/e2e_evidence.py --mode preflight --output-dir .e2e-evidence
    python scripts/e2e_advanced_parse.py --output-dir .e2e-evidence
    python -m unittest discover -s tests -p test_e2e_evidence_preflight.py -v

After installing dependencies and explicitly choosing an offline suite:

    python scripts/e2e_evidence.py --mode offline-e2e --suite stage7-browser --output-dir .e2e-evidence

The harness self-tests exercise only manifest parsing, evidence output,
redaction and non-execution contracts; they do not run product E2E.

## Disposable assembled system run

`scripts/e2e_assembled_system.py` clones the committed candidate into a temporary
checkout and runs a private Mongo replica set, canonical engine, backend and
Expo static export. It exercises authenticated conversation writes, principal
isolation, desktop/mobile navigation and local-model chat, restart replay without
duplicate commits, engine outage reporting and graceful cleanup.

Install the backend requirements plus Playwright and its Chromium browser. Build
the Expo web export with API URLs `http://127.0.0.1:38001` and
`http://127.0.0.1:38010`, then run:

    python scripts/e2e_assembled_system.py --mongod /absolute/path/to/mongod --web-export /absolute/path/to/web-export --output-dir .e2e-evidence/assembled-system

Ports 33000, 38001 and 38010 must be free. The runner creates disposable
credentials, sanitizes traces/logs and removes temporary state. Forced shutdown
is a failed cleanup result. Its tiny trained native model verifies execution
and service assembly; it does not certify answer quality, a release model,
installed device behavior or live providers. The expanded `app-cli-forge` shard
reports a missing Godot binary as an unverified playtest rather than silently
certifying that journey. Set `SKELETON_GODOT_BIN` to a real supported executable
when qualifying the headless game playtest.

The CI forge shard installs Godot 4.4.1 from the official download service and
checks its pinned archive SHA-256 before executing that playtest.

For production-style ingress qualification, build the web export without
explicit backend or engine URL overrides and add `--nginx /absolute/path/to/nginx`.
The runner uses the repository's ingress configuration with loopback fixture
upstreams. `--audit-all-routes` opens every exported public route, including a
concrete dynamic gate URL; `--audit-route /path` reproduces selected routes.
The route audit checks initial rendering and HTTP 5xx responses. It does not
certify every feature or complete every workflow behind each page.
