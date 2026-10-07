# Autonomous Execution Manifest Contract

## Purpose

Define the evidence envelope produced by autonomous repository execution attempts.

The manifest is not authority. It is an immutable record of what was admitted, attempted, validated, and published.

## Required identity fields

- run_id
- repository
- base_sha
- execution_fingerprint
- snapshot_fingerprint
- worker_identity
- started_at
- completed_at

## Lifecycle states

Allowed terminal states:

- admitted
- suppressed
- executing
- validated
- published
- failed
- recovered

Every terminal state must include evidence.

## Failure classification

Failures must be categorized:

- stale_custody
- capacity_suppressed
- missing_authorization
- provider_failure
- worker_failure
- validation_failure
- publication_failure

Do not collapse operational failures into generic errors.

## Publication rules

A worker must not claim completion unless:

1. the resulting change is attached to the admitted execution identity;
2. validation results are recorded;
3. generated branches or PRs are deterministic and discoverable;
4. duplicate publication was checked.

## Recovery rules

Retries must preserve:

- original admission identity;
- original base SHA;
- bounded retry count;
- previous failure evidence.

Recovery creates additional evidence, not a replacement history.
