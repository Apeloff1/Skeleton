# Operational native AI acceptance — 2026-11-03

## Dependency order
1. Owner-safe filesystem and trusted checkpoint SHA-256
2. Valid operator-reviewed model license and native tokenizer compatibility
3. Existing model admission and principal-bound persistent stores
4. Real offline model activation with cross-process session fence
5. Canonical 480-case / 20-domain original test inventory
6. Actual native generation, one committed receipt per step
7. Deterministic checks and model-identity corroboration
8. Private result publication with no-clobber + fsync
9. Independent report verification, optional HMAC custody ledger
10. Exact-head merge, backend, E2E, security, device, recovery and rights gates

## Commands
Inventory is safe without model weights:
`python -m skeleton.ai.runtime.operational_ai.native_qualification.cli --inventory`.

Focused source tests (no model claims):
`python -m unittest discover -s skeleton/testing -p 'test_native_qualification*.py' -v`.

Real model qualification:
`python -m skeleton.ai.runtime.operational_ai.native_qualification.cli --run-native --checkpoint <operator-approved-checkpoint> --sha256 <verified-digest> --license operator_reviewed --database <state>/chat.sqlite3 --memory-db <state>/memory.sqlite3 --journal-db <state>/audit.sqlite3 --output-directory <state>/qualification_reports`.

This tool is deliberately CLI-only and uses existing native model authority.
No synthetic weight packages, game systems, hosted services, or public proxy.

## Evidence severity
Critical: injection, privacy, citations, grounding, abstention and continuity.
High: arithmetic, structured records, transformations, reasoning, multilingual,
summarization and constrained formatting.

Every critical failure holds policy-threshold success. An incomplete or
altered corpus cannot be called complete. A device or checkpoint failure
cannot be marked successful by static unit tests. All unknown values are
denials or explicit unverified holds.

## Failure handling
Preserve the checkpoint manifest and source Git SHA. Do not retry a committed
request as new inference without the original stable request ID. Never
publish raw private prompts, request bodies, bearer tokens or model output.
Diagnose by bounded error code and hashed receipt identifiers. Reconcile
ambiguous effects separately through authoritative custody; this runner
does not authorize any side-effect tools.

## Release and merge holds
The parent AI ecosystem drafts are not qualified by this package. Require
fresh successful exact-head Merge Readiness, Backend Quality, App E2E, Workflow
Input Security, Sealed Context Guard, Artifact Policy, Malware Gate,
Repository Hygiene, Secret Scanning, Dependency Review, model rights and
independent clean-install/device acceptance before promotion or merge.
