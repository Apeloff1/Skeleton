# Autonomous Validation Orchestration Contract

## Purpose
Define the contract between execution, validation, remediation, and evidence collection layers.

## Validation lifecycle

1. Admission
- Verify execution identity.
- Verify scope and ownership.
- Reject ambiguous work units.

2. Execution
- Run bounded actions.
- Emit structured progress evidence.
- Preserve deterministic state transitions.

3. Validation
- Collect checks.
- Classify failures.
- Attach evidence to the work unit.

4. Remediation
- Apply focused correction.
- Prevent duplicate fixes.
- Re-enter validation.

## Required signals

- work identity
- execution identity
- validation result
- failure category
- remediation reference
- final evidence package

## Design constraints

- Fail closed on missing evidence.
- Keep worker scope bounded.
- Preserve traceability across retries.
- Prefer deterministic recovery over repeated execution.
