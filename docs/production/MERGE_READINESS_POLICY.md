# Merge-readiness policy (operational)

Historical tracker: [#127](https://github.com/Apeloff1/Skeleton/issues/127) (**closed** 2026-10-03).

This page is the Production operational pointer. It does **not** replace the
enforced policy documents. Do not edit `.github/ci/required-checks.json`
`documentation` / lane names without updating those docs in the same change
(the Quarantine Policy lane fails closed on drift).

## Source of truth

| Artifact | Role |
| --- | --- |
| [`.github/ci/required-checks.json`](../../.github/ci/required-checks.json) | Machine-readable required check + lanes |
| [`.github/workflows/merge-readiness.yml`](../../.github/workflows/merge-readiness.yml) | Publishes **Merge Readiness** |
| [docs/CI_REQUIRED_CHECKS.md](../CI_REQUIRED_CHECKS.md) | Human required-check guide |
| [docs/MERGE_READINESS.md](../MERGE_READINESS.md) | Full readiness contract, flaky policy, security-sensitive rules |
| `scripts/check_required_checks_policy.py` | Drift guard (runs in Quarantine Policy) |
| `scripts/merge_readiness_status.py` | Local READY / NOT_READY / PENDING reporter |
| `scripts/configure_main_protection.sh` | Owner-side apply/verify of `main` protection |

## Required aggregate

**Merge Readiness** (GitHub Actions app id `15368`) fails unless all of these
succeed for the **same** head SHA:

1. **Quarantine Policy**
2. **Unit**
3. **Integration Smoke**
4. **Lint Type Security**
5. **PR Automation Tests**

Draft PRs skip those lanes (`if` on non-draft). Converting to draft or closing
cancels the obligation for that event; a later ready-for-review re-runs.

## Green definition (Production)

A PR is merge-ready for Production only when:

1. Head is current (no newer push pending Checks).
2. **Merge Readiness** is **success** on that head (not an older SHA).
3. Mergeability is clean (no conflicts).
4. If the change is security-sensitive, [docs/MERGE_READINESS.md](../MERGE_READINESS.md) security section is satisfied.
5. Stacked PRs have their base already on the intended target (`main` for Wave 0+).

## Overrides

- **No silent ignore** of red or pending required lanes.
- Emergency / manual merge requires a follow-up issue and restoring enforcement
  before routine work (`docs/MERGE_READINESS.md`).
- Flaky quarantine only via `.github/ci/flaky-quarantine.json` with issue, owner,
  and ≤30-day expiry — never by disabling Checks.

## Grenn enforcement follow-ups (not done by this docs PR)

Repository administration must still:

1. Protect `main` and **require** the stable check **Merge Readiness** (app 15368).
2. Prefer `scripts/configure_main_protection.sh --apply` then `--verify`.
3. Keep defence-in-depth workflows (CodeQL, secret scanning, malware, artifact
   policy) running; do not promote a second job to the same required name.

Until step 1–2 succeed, Production treats Checks as **advisory** and will not
call the app rollout-ready.

## Related

- [#540](https://github.com/Apeloff1/Skeleton/issues/540) — repository-wide hardening / merge gate (security)
- [#784](https://github.com/Apeloff1/Skeleton/issues/784) — protect main / fail-closed production CORS (security)
- [#127](https://github.com/Apeloff1/Skeleton/issues/127) — original required-checks tracker (closed)
