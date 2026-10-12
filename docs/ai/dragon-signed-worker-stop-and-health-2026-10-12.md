# Dragon research — signed crash recovery, health observability and exact Python gate

**Authored:** 2026-10-12 UTC  
**Feature branch:** `feat/dragon-wisdom-review-20261010` / PR #3605.

## Milestone 1: Independent signed worker-stop evidence

Previously, `DragonSourceOperations.confirm_recovered` accepted a 64-hex value alongside caller-supplied `worker_stopped=True` and `resources_reconciled=True`. A trusted caller could therefore clear a `quarantined` worker without a cryptographically verifiable link to the actual expired lease. This milestone removes that unsigned recovery path.

The new `DragonWorkerStopAuthority` signs an immutable `SignedWorkerStop` receipt, bound to owner, canonical source ID, host, exact **ticket digest**, exact **quarantine event digest**, process-stop evidence digest, global-resource reconciliation evidence digest, independent supervisor identity, issuer, random nonce and an expiry not more than **10 minutes** after issuance. A separate 256-bit signing key is required. A hatchling, site response or browser must not hold that key.

`confirm_recovered` now requires the typed signed receipt and verifier. Within the same SQLite immediate transaction, it checks the full append-only event head, verifies the signed source/host/ticket/quarantine identity against the **current** quarantine, checks expiry/signature, and commits the `acknowledged_stop` event containing the signed receipt digest and process/resource evidence references. A forged key, wrong source, old quarantine, expired receipt or repeated recovery fails before the state changes.

**Security boundary:** Cryptographic verification proves what the sealed OS/process supervisor signed, not that a remote machine actually stopped. The issuer must independently observe process termination and reconcile real global scheduler grants. Merely passing its `process_stopped=True` issuance argument without performing those checks is improper and defeats the external trust boundary. Keys, grant IDs and process evidence must remain outside web pages, hatchlings and model input.

## Milestone 2: Source health and operational alarms

`DragonSourceHealth` builds a **read-only**, owner-bound, 100-source-per-page snapshot using validated source-operations journal heads and the canonical editorial freshness/review ledger. It never executes crawling, changes queues, acknowledges recovery or releases resources.

The output provides per-page state counts, source-event digests, last-event clocks, lease expiry, retry-ready times, policy expiry, latest captured revision and operator alerts for:

- Expired leased workers requiring quarantine
- Quarantined workers requiring external stop/grant reconciliation
- Manual robots/rights policy holds
- Sources awaiting independent policy renewal
- Expired source permissions, reviewed-source revisits and pending captured-text review

Pagination uses a canonical last-source cursor, with `has_more` and `fleet_totals_complete` to prevent mistaking one page for the entire fleet. A journal mismatch fails closed, including forged event bodies and mismatched heads. Metrics are observations, not statements that the OS process has stopped or the source is lawful to crawl.

Trusted read-only operator example:

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli operations-health \
  --database /approved/dragon.sqlite --owner studio \
  --now "$(date -u +%s)" --limit 100 \
  --trusted-local-operator
```

Use `--after-source source-<sha256>` to continue at the next page.

## Milestone 3: Explicit Python source-safety CI

`.github/workflows/dragon-ai-verification.yml` has a separate **Dragon Source Safety** job, distinct from broad game/AI test suites. It compiles the critical new Dragon authorities and uses real Python 3.11 and pytest to execute the canonical source-operations, acquisition and capture regression modules on the exact source revision.

The job uses a credential-free checkout, pinned GitHub action references, bounded runtime, read-only contents permission and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. It has no secrets, live crawl, side-effecting permission grant or training step.

**Current validation constraint:** this workflow exists in the feature branch, but the PR run previously exposed only a successful CodeQL Actions check, not Python test execution. This implementation is **not certified** until an exact-head `Dragon Source Safety` job actually runs and completes successfully. A green CodeQL Actions analysis is not a substitute for pytest.

## Focused adversarial coverage

Additional tests check positive signed-stop recovery, wrong signing keys, forged quarantine digests, expired proofs, receipt replay, refusal of issuance without real stop assertions, operational alarms for crashed leases, read-only health snapshots, owner isolation, invalid cursors and corrupted operations custody.

## Outstanding real-world work

This batch does not deploy a privileged OS reconciler or an identity-provider-backed source-rights signer. A secure pilot still requires actual reviewer credentials and source permissions, a separate secured supervisor that observes processes and global grant reconciliation, trusted OS idle telemetry, permissioned destination-specific egress, and confirmed exact-head integration tests. No live crawling or weight-promotion is authorized by the code changes alone.
