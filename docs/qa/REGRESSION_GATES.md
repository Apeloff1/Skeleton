# Skeleton Regression Gate List

Owner: QA Director (Carrol). Status: authoritative merge/ship gate reference for the standalone AI.

## Ship rule

- **Any red Sev1 or Sev2 gate = NO-SHIP.** No exceptions without an explicit, logged override from the QA Director and Production.
- **GameForge-only green is never sufficient.** A merge candidate must be green on every gate marked "Blocks merge: Yes".
- Gates fail closed: a skipped, cancelled, or missing required check counts as red.
- A docs-only change must not turn any gate red; if it does, that is a gate defect (Sev2) and is filed against the gate owner.

## Severity

| Sev | Meaning | Merge effect |
|---|---|---|
| Sev1 | Crash, data loss, security/trust break, AI core unusable, CI gate silently passing broken code | Blocks merge and ship |
| Sev2 | Major feature broken, CLI/cockpit command fails, deterministic test failure in a required job | Blocks merge and ship |
| Sev3 | Degraded behaviour with workaround, flaky non-required job, perf regression inside 10% | Ticket, does not block |
| Sev4 | Cosmetic, docs, log noise | Backlog |

## Gate table

| Gate ID | Enforcing CI job (workflow) | Sev on red | Owning lane | Blocks merge |
|---|---|---|---|---|
| G-GF | `Skeleton GameForge` (`ci.yml`, runs `tests/run_unit.py`) | Sev1 | Shirt 1 — GameForge cert | Yes |
| G-COCKPIT | `Cockpit Smoke` (`ci.yml`, runs `scripts/cockpit-smoke.sh`) | Sev2 | Shirt 6 — CLI/cockpit | Yes |
| G-BE-TEST | `Backend Test` (`ci.yml`) | Sev1 | Shirt 5 — AI core | Yes |
| G-BE-IMPORT | `Backend Import Smoke` (`ci.yml`) | Sev1 | Shirt 5 — AI core | Yes |
| G-BE-LINT | `Backend Lint` (`ci.yml`) | Sev2 | Shirt 5 — AI core | Yes |
| G-FE | `Frontend` (`ci.yml`) | Sev2 | Shirt 6 — CLI/cockpit (UI surface) | Yes |
| G-JAVA | `Java Batch Accelerators` (`ci.yml`) | Sev2 | Shirt 2 — performance | Yes |
| G-ASM | `Assembly Vector Accelerators` (`ci.yml`) | Sev3 | Shirt 2 — performance | No (advisory) |
| G-JEEVES | `Jeeves School Reasoning` (`ci.yml`) | Sev2 | Shirt 5 — AI core | Yes |
| G-DOCKER | `Docker Build` (`ci.yml`) | Sev2 | Shirt 3 — provenance | Yes |
| G-LTS | `Lint Type Security` (`merge-readiness.yml`) | Sev1 | Shirt 5 — AI core | Yes |
| G-MR-UNIT | `Unit` (`merge-readiness.yml`) | Sev1 | Shirt 5 — AI core | Yes |
| G-MR-INT | `Integration Smoke` (`merge-readiness.yml`) | Sev1 | Shirt 5 — AI core | Yes |
| G-MR-QUAR | `Quarantine Policy` (`merge-readiness.yml`) | Sev2 | QA Director | Yes |
| G-MR | `Merge Readiness` (`merge-readiness.yml`) | Sev1 | QA Director | Yes |
| G-AUTOMERGE | Auto-Merge Policy Validation (`automerge-control-plane.yml`) | Sev2 | QA Director | Yes |
| G-CODEQL | CodeQL / code scanning | Sev1 for high/critical alerts | Shirt 3 — provenance | Yes (high/critical) |
| G-SECRETS | Secret scanning (`secret-scanning.yml`) | Sev1 | Shirt 3 — provenance | Yes |
| G-PROV | Provenance policy (`provenance-policy.yml`) | Sev2 | Shirt 3 — provenance | Yes |
| G-E2E | Standalone-AI E2E suite (planned; see test plan) | Sev1 | Shirt 5 + Shirt 6 | Planned |
| G-PERF | Perf budget gate (planned: frame time, load, allocs) | Sev2 | Shirt 2 — performance | Planned |
| G-GODOT | Forge/Godot provenance gate (planned, `godot.pointer` integrity) | Sev2 | Shirt 3 — provenance | Planned |

## Known reds to track

Before certifying a candidate, check the current state of main with `gh run list --branch main` and the candidate's checks with `gh pr checks <n>`. Historically recurring reds that must be green before any SHIP call:

- `Backend Test` (boundary tests).
- `Java Batch Accelerators` (`ModuleNotFoundError: pydantic`).
- `Lint Type Security` (Merkle public-API exports, trust-snapshot signatures).
- `Merge Readiness` / Auto-Merge Policy Validation.

Pre-existing reds on main do not excuse a candidate; they keep the whole ship call at NO-SHIP until fixed.
