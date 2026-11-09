# Risk register — Skeleton FULL APP COMPLETION / ROLLOUT

Updated: **2026-10-10**. Owners are lanes, not individuals, unless a PR names one.

| ID | Severity | Risk | Evidence | Owner lane | Mitigation | Burn-down trigger |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | **P0** | `#3603` merges or is treated as ready while still stacked on `#3601` | [#3603](https://github.com/Apeloff1/Skeleton/pull/3603) base = `fix/dragon-ci-reliability-20261009`; body requires merge #3601 first | Production + Dragon | Hold `#3603` until `#3601` is on `main` and verified; then retarget | `#3601` merged + `#3603` base is `main` |
| R2 | **P0** | **Merge Readiness** exists but is **not required** on `main` — green Checks are not authorization | [#127](https://github.com/Apeloff1/Skeleton/issues/127) closed with keep-open admin items; `docs/CI_REQUIRED_CHECKS.md`; `required-checks.json` | Grenn (DevOps) | Run `scripts/configure_main_protection.sh --apply` then `--verify` | `--verify` reports protection enforcing **Merge Readiness** (app 15368) |
| R3 | **P0** | Draft-heavy queue creates false progress (`#3605` and siblings) | [#3605](https://github.com/Apeloff1/Skeleton/pull/3605) draft; Waves 4 in DEPENDENCY_BOARD | Production | Drafts stay Wave 4; no rollout claim from local Dragon greens | `#3605` (and peers) ready-for-review **and** Merge Readiness green on head |
| R4 | **P1** | Scope honesty: platform counts / ROM CI ≠ hardware-verified or shippable games | `#3603` / `#3604` bodies disclaim hardware-verified and legal clearance | Production + Game Director | Board forbids competitor-parity language until R2 + explicit acceptance gates | Written acceptance checklist signed off per platform class |
| R5 | **P1** | Parallel large packs (`#3604`, Dragon, offline AI) thrash `main` and burn CI | Open set `#3593`–`#3607` | Production | Enforce waves; one Wave-3 pack at a time after Wave 0/1 | Only one Wave-3 PR open against `main` at a time |
| R6 | **P1** | GHAS / security-agent quota failures mislabeled as product bugs | `#3603` acceptance: handle quota administratively; do not disable security checks | Grenn + Security | Quota = admin capacity issue; keep CodeQL/secret/malware gates | Quota restored or waived in writing without disabling checks |
| R7 | **P2** | Offline/AI PR cluster duplicates (`#3593`/`#3597`/`#3598`/`#3596`/`#3599`) | DEPENDENCY_BOARD Wave 3–4 | AI / Production | Designate one primary; close or rebase the rest | Single primary offline-app PR; others closed or stacked |
| R8 | **P2** | Combat/animation craft lands while Dragon visual play still draft | `#3606`, `#3607` vs `#3605` | Yosh / Snappo / Dragon | Prefer Wave 2 merges; rebase `#3605` after | `#3605` rebased on post-`#3606`/`#3607` `main` if still open |
| R9 | **P2** | Flaky quarantine used as a merge bypass | `docs/MERGE_READINESS.md` flaky policy; `.github/ci/flaky-quarantine.json` | Grenn + QA | Quarantine only with issue, owner, ≤30d expiry; never silent ignore | Expired entries fail Quarantine Policy (already enforced in workflow) |

## Schedule risk flag (2026-10-10)

**Immediate:** R1 + R2. Until `#3601` lands and Grenn enforces **Merge Readiness**, the completion program cannot honestly call any feature PR rollout-ready. Wave 2 (`#3606`, `#3607`) may still merge when their own Checks are green, but they are not a substitute for R2.
