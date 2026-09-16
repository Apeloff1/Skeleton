# Backlog Bot State Machine

The bot persists lifecycle state independently of model availability. State transitions are deterministic and tied to immutable evidence.

| State | Meaning | Allowed next states |
|---|---|---|
| `observed` | A new or changed report was ingested | `correlated`, `quarantined` |
| `correlated` | Duplicate sources were grouped without losing evidence | `retrieving`, `quarantined` |
| `retrieving` | Focused repository evidence is being assembled | `planned`, `quarantined` |
| `planned` | A repair proposal exists but is not trusted as authorization | `validating`, `quarantined` |
| `validating` | Deterministic policy and security checks are evaluating the proposal | `ready_for_change`, `quarantined` |
| `ready_for_change` | Policy permits a bounded repository change | `changed`, `quarantined` |
| `changed` | A change was created on a controlled branch/PR | `verifying`, `quarantined` |
| `verifying` | CI, security scans and repository gates are being observed | `merge_ready`, `changed`, `quarantined` |
| `merge_ready` | All configured merge gates report the required state | `completed`, `quarantined` |
| `completed` | Work was merged/closed and post-change evidence recorded | terminal |
| `quarantined` | Automation stopped because evidence or policy is insufficient | `observed` only after fresh evidence |

## Transition invariants

- A model response never performs a transition by itself.
- Every transition records the triggering evidence fingerprint and repository SHA.
- A changed PR head, base, merge conflict, or relevant finding update invalidates `planned`, `validating`, and later cached conclusions.
- Security findings cannot transition to a less restrictive state solely because a model recommends it.
- Retries are bounded per transition and per work key.
- Concurrent workers must acquire the same deterministic work key before mutating state.
- Quarantined work does not silently retry forever.
- Missing ChatGPT credentials may skip reasoning but cannot erase or advance durable state without deterministic evidence.

## Work key

Use a stable key derived from repository identity, normalized finding identity and affected source scope. Do not use a transient workflow run ID as the primary identity; run IDs are evidence attached to a work item.
