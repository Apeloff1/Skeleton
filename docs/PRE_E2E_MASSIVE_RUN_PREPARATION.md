# Massive E2E preparation and evidence runbook

**2026-10-13 preparation status: NOT an E2E completion certificate.**

This is an additional diagnostic control plane for the existing Stage-7
golden journeys, local-inference chat integration, Node-side browser stream
contracts, and frontend product journey contracts. Runtime tracing itself
continues to use the canonical system in [OBSERVABILITY.md](OBSERVABILITY.md).

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
**run_offline=true**. Five shards then run with independent verdicts,
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
  a failure rather than a green result.
- **issues.json**, **issues.md** and **summary.md**: stable issue signature,
  phase, severity, failing testcase, evidence path and explicit open
  disposition. Success in one shard never hides another shard failure.
- **advanced-parse.json** and **advanced-parse.md**: test-source SHA-256,
  risk flags, estimated test counts, issue candidates, and categorized
  coverage. Static flags are candidates, not confirmed defects.

A final aggregator downloads the five independent shard receipts, requires all
five passes at one exact SHA, and emits aggregate.json and aggregate.md.
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

    python scripts/e2e_evidence.py --mode preflight --output-dir .e2e-evidence
    python scripts/e2e_advanced_parse.py --output-dir .e2e-evidence
    python -m unittest discover -s tests -p test_e2e_evidence_preflight.py -v

After installing dependencies and explicitly choosing an offline suite:

    python scripts/e2e_evidence.py --mode offline-e2e --suite stage7-browser --output-dir .e2e-evidence

The harness self-tests exercise only manifest parsing, evidence output,
redaction and non-execution contracts; they do not run product E2E.
