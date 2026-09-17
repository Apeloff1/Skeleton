# Automated repair pipeline

Skeleton's repair automation is intentionally layered. Findings and failed gates may create bounded intake records, but they do not authorize code changes or direct writes to `main`.

```text
trusted workflow metadata / repository finding
        |
        v
Repair Intake (durable identity, minimal metadata)
        |
        v
Backlog correlation + repository indexes
        |
        v
Deterministic policy + optional advisory reasoning
        |
        v
Repair branch / pull request
        |
        v
Tests + security + dependency + provenance gates
        |
        v
Merge Readiness / human review boundary
```

## Intake boundary

`.github/workflows/repair-intake.yml` is a privileged `workflow_run` consumer, so it follows a strict rule: **never checkout or execute the triggering head**. It reads only event metadata, records the workflow/run/head identity, and never copies workflow logs or repository-file contents into the issue.

Only selected failed workflows whose `head_repository.full_name` equals the current repository are eligible. Fork-owned heads are ignored.

The durable SHA fingerprint is based on normalized workflow name, conclusion, and head SHA. The run ID is retained as metadata but deliberately excluded from the fingerprint, so reruns of the same failing workflow at the same commit do not create duplicate issues. Deduplication searches both open and closed intake records.

Intake is pre-emptive about merge storms. Before opening a new issue the trusted workflow:

1. Looks up the current same-repo branch tip through the GitHub API. It never checks out the triggering head.
2. Skips superseded SHAs whose branch tip has already moved, and skips deleted branches.
3. Skips when the branch tip cannot be read unambiguously. Creating another issue is the privileged mutation, so uncertainty does not open a record.
4. Groups remaining current-head failures by a workflow + branch family fingerprint. One open family record is enough; later current-head failures on that same live branch correlate instead of multiplying.

Branch names and all later repository/issue text remain untrusted data even when the head repository is the same repository. Branch names are hashed for family identity and percent-encoded for the branches API. Control characters and oversized refs fail closed.

## Repair policy boundary

`repair_policy.py` is fail closed. Proposed paths are canonicalized as repository-relative POSIX paths; traversal, absolute, empty, NUL-bearing, and non-canonical paths are classified high risk rather than normalized into a lower-risk path.

Changes touching workflow/action control planes, security/authentication/sandbox/secret/provenance surfaces, dependency manifests, or security findings require human review. The only current automatic-merge allowlist is a small ordinary documentation-only change of at most three `.md`, `.mdx`, or `.rst` files that does not cross a trust boundary.

Model output is advisory. It cannot grant permissions, change the deterministic risk classification, disable validation, approve its own PR, or convert untrusted repository text into policy.

## Freshness boundary

A repair proposal must retain the triggering commit SHA and relevant finding/run identity. If the base, head, finding, or validation state changes, the proposal must be recomputed against current evidence rather than assuming the old decision remains valid.

## Failure behavior

- Duplicate workflow/head failure: correlate to the existing intake record.
- Superseded SHA, deleted branch, or unreadable branch tip: skip intake rather than opening a storm of stale records.
- Open workflow+branch family record already exists: correlate; do not open a second issue.
- Stale SHA or changed base: discard/recompute the old repair plan.
- Invalid or non-canonical path: classify high risk and require review.
- Scanner disagreement or ambiguous scope: quarantine for review.
- Failing validation: no merge.
- Repeated unsuccessful repairs: stop retrying automatically and escalate for review.
- Secret-like material: do not place raw values in issues, artifacts, or model context.
