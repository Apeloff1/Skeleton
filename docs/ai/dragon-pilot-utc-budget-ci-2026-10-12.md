# Dragon research — durable attempt budgets and discoverable CI

**Authored:** 2026-10-12 UTC. **Scope:** controlled Dragon article pilots.

## Bounded research budgets
\`DragonPilotBudget\` adds a durable, SQLite-backed owner/host/day attempt ledger. The defaults are **8 attempts per owner per UTC day** and **2 per destination host per UTC day**. These conservative limits count **attempts**, not only successes, because failed crawls, denied robots checks and interrupted workers still consume time, bandwidth and source goodwill.

A source must already be selected by the permissioned, policy-ready queue and pass foreground/idle preflight before its attempt is debited. The cross-process operation is serialized with \`BEGIN IMMEDIATE\`, scopes the attempt to owner, host, source and exact signed permit digest, and refuses duplicate attempt IDs across all days. Every stored record is independently rechecked against its canonical digest and calendar date before more capacity is issued. An invalid or tampered ledger fails closed rather than resetting quota.

Quota is an **additional constraint**, never a grant to issue HTTP, retain text, approve Wiki knowledge, or modify model weights. Production deployments should also configure firewall/provider request budgets and HTTP byte caps; local SQLite cannot independently enforce limits across disconnected devices or multiple databases.

Read-only trusted-local command:
\`\`\`sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli pilot-budget \
  --database /approved/dragon.sqlite --owner studio \
  --now "$(date -u +%s)" --trusted-local-operator
\`\`\`

## Explicit Python validation on the Dragon branch
The \`Dragon Source Safety\` workflow compiles the source authority, external-rights verifier, pilot budget, runtime and controlled acquisition worker, and executes the source-operations and capture/acquisition suites with an explicit Python and \`cryptography>=50,<51\` environment. The existing broader Python job has the same cryptography dependency.

The compatibility module \`tests/test_ai_dragon_source_safety.py\` matches the test filename glob in the current **main** workflow and checks basic fail-closed imports, signature-key boundaries, external-stop issuance and lack of automatic pilot rights. This is designed to make the integration visible on older workflow discovery paths; successful GitHub execution **must** be observed separately.

Offline regression cases challenge cross-instance quota persistence, host limits, owner limits, daily rollover, replayed IDs, tenant isolation, corrupt ledger digests, no quota debit for an unscheduled source or a foreground interruption, and a successful consented source attempt. No browser, live source or training engine is invoked by tests.

## Remaining required production controls
Separately provisioned and identity-provider-backed independent rights signing service, actual trusted OS idle telemetry and process/grant reconciliation, permissioned destination-specific egress, redaction of sensitive source excerpts, executed Python tests and reviewed Wiki/HOAG admissions. The 248 atlas entries remain *candidate destinations* until approved individually.
