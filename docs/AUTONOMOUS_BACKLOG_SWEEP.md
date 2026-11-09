# Autonomous backlog sweep

## Current priority

The autonomous builder control plane is treated as the first unblocker because reliable execution reduces backlog risk.

## Control-plane hardening targets

- deterministic admission from immutable base SHA
- explicit custody fingerprints across Supervisor -> Secretary -> Worker
- bounded retry and recovery paths
- duplicate branch and PR convergence
- terminal evidence for success, suppression, failure, and no-op outcomes
- regression coverage for scheduled execution paths

## Operating rules

- No direct main mutation.
- No bypass of CI or security gates.
- Prefer focused repairs with evidence.
- Keep authority boundaries explicit.
