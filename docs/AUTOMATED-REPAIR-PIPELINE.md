# Automated repair pipeline

The repository uses a layered repair pipeline rather than direct writes to `main`.

```text
GitHub finding / failed gate
        |
        v
Repair Intake (durable, minimal metadata)
        |
        v
Backlog correlation + repository indexes
        |
        v
Deterministic policy + optional ChatGPT reasoning
        |
        v
Repair branch / PR
        |
        v
CodeQL + tests + malware + dependency + provenance gates
        |
        v
Merge Readiness
        |
        +--> automatic merge only for explicitly permitted low-risk classes
        |
        +--> human review for security/control-plane/trust-surface changes
```

## Intake boundary

`repair-intake.yml` observes trusted GitHub workflow metadata only. It does not checkout pull-request code, execute repository code, or copy workflow logs into an issue. This prevents secrets and attacker-controlled log payloads from becoming automatic model context.

Only failures from selected repository workflows are recorded, and failures from fork-owned heads are ignored. Open duplicate intake records are suppressed by workflow/head identity.

## Repair boundary

A repair proposal must retain the triggering commit SHA and finding/run identity. If the branch, base, finding, or relevant checks change, the proposal is stale and must be recomputed.

Model output is advisory. It cannot grant permissions, disable security gates, approve its own PR, or convert untrusted repository text into instructions.

## Automatic merge boundary

Automatic merge is limited to policy-approved low-risk changes. Changes to workflows, merge gates, security policy, authentication/authorization, sandbox/tool capabilities, secret boundaries, or other trust surfaces require human review even when all automated checks pass.

## Failure behavior

- API/model outage: retain durable intake state and continue deterministic processing.
- Duplicate failure: correlate rather than create another repair.
- Stale SHA: discard the old repair plan.
- Scanner disagreement: quarantine for review.
- Failing validation: no merge.
- Repeated unsuccessful repairs: stop retrying and quarantine.
- Secret-like material: redact before model context and never place it in an issue, artifact, or log.
