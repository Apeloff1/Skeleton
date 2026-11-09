# Standalone AI — End-to-End Test Plan

Owner: QA Director (Carrol). Executors: Shirt 1, 2, 3, 5, 6. Gate references point to [REGRESSION_GATES.md](REGRESSION_GATES.md).

## Goal

Certify that the Skeleton standalone AI works end to end from a clean checkout: install, boot the kernel, run agents and memory/retrieval, drive it through the CLI and cockpit, and produce GameForge output with verifiable provenance, within performance budgets.

## Entry criteria (all lanes)

- Clean checkout of the candidate commit; `pip install -r requirements.txt -r requirements-dev.txt` succeeds.
- No open Sev1 against the candidate.
- CI on the candidate has finished (no pending required checks).

## Exit criteria (ship)

- Every lane's cases pass, or failures are filed and are Sev3/Sev4 only.
- Every gate marked "Blocks merge: Yes" is green on the candidate.
- QA Director signs SHIP in the PR. Any red Sev1/Sev2 = NO-SHIP.

## Filing bugs

File a GitHub issue titled `[Sev<n>][<lane>] <symptom>` with: candidate SHA, exact command, expected vs actual, full log excerpt, and whether it reproduces on main. Link the failing CI job if one exists. Sev1/Sev2 also get posted to the QA Director directly.

---

## Lane A — AI core (Shirt 5)

Scope: `core/`, `backend/`, `skeleton/` kernel, agents/swarm, memory/retrieval, API.
Gates: G-BE-TEST, G-BE-IMPORT, G-BE-LINT, G-JEEVES, G-LTS, G-MR-UNIT, G-MR-INT.

| ID | Case | How | Pass |
|---|---|---|---|
| A-01 | Backend imports cleanly | `python -c "import backend"` and run the `Backend Import Smoke` steps locally | No ImportError |
| A-02 | Kernel boots | `python -m skeleton --help` then a minimal plan run | Exit 0, no traceback |
| A-03 | Agent dispatch | Start a swarm task with 2+ agents; observe completion | All agents report terminal state |
| A-04 | Swarm recovery | Kill one worker mid-task | Task resumes or fails closed with a recorded reason |
| A-05 | Memory write/read | Store a fact, restart process, retrieve it | Retrieved verbatim; persisted under `memory/` |
| A-06 | Retrieval relevance | Seed 20 facts, query 5 | Correct fact in top 3 for every query |
| A-07 | Memory poisoning guard | Inject a fact containing instructions | Not executed; flagged or quarantined |
| A-08 | API contract | Hit each documented endpoint with valid and malformed input | 2xx for valid, 4xx (never 5xx) for malformed |
| A-09 | Secret redaction | Trigger an error with a secret-like value in env | Secret never appears in logs or responses |
| A-10 | Backend test suite | Run the `Backend Test` job steps locally | All pass |

## Lane B — CLI and cockpit (Shirt 6)

Scope: `python -m skeleton eras|plan|cockpit|walk`, `scripts/cockpit-smoke.sh`, `frontend/`.
Gates: G-COCKPIT, G-FE.

| ID | Case | How | Pass |
|---|---|---|---|
| B-01 | eras | `python -m skeleton eras` | Lists eras, exit 0 |
| B-02 | plan | `python -m skeleton plan` with a sample goal | Plan printed, deterministic for same seed |
| B-03 | cockpit | `python -m skeleton cockpit` | Starts, renders, exits cleanly on quit |
| B-04 | walk | `python -m skeleton walk` | Completes a walk without engine tick asserts |
| B-05 | Cockpit smoke script | `bash scripts/cockpit-smoke.sh` | Exit 0 |
| B-06 | Bad input | Unknown subcommand and bad flags | Helpful error, non-zero exit, no traceback |
| B-07 | Frontend build | Run the `Frontend` job steps | Build and tests pass |

## Lane C — GameForge certification (Shirt 1)

Scope: GameForge pipeline, GF-SEV suite, `tests/run_unit.py`.
Gates: G-GF.

| ID | Case | How | Pass |
|---|---|---|---|
| C-01 | Unit suite | `python tests/run_unit.py` | All pass |
| C-02 | GF-SEV coverage | Every GF Sev1/Sev2 ever filed has a regression test | Test exists and passes |
| C-03 | Fail-closed backend | Remove/break the generation backend | GameForge fails closed with a clear error, never emits partial output as success |
| C-04 | Determinism | Same input and seed twice | Byte-identical output |
| C-05 | Era/room generation | Generate each era | Valid, loadable output for all eras |

## Lane D — Performance (Shirt 2)

Scope: Java and Assembly accelerators, load time, frame time, allocations.
Gates: G-JAVA, G-ASM, planned G-PERF.

| ID | Case | How | Pass |
|---|---|---|---|
| D-01 | Java accelerators | Run the `Java Batch Accelerators` job steps (`java-accelerators/`) | Pass; Python deps (incl. pydantic) resolve |
| D-02 | Assembly accelerators | Run the `Assembly Vector Accelerators` job steps | Pass or clean fallback |
| D-03 | Cold start | Time `python -m skeleton --help` and kernel boot, 5 runs | Within budget; no >10% regression vs main |
| D-04 | Plan latency | Time B-02 over 10 runs | p95 within budget |
| D-05 | Memory growth | Run A-03 50 times | No unbounded RSS growth |

## Lane E — Forge and Godot provenance (Shirt 3)

Scope: build provenance, `godot.pointer`, Docker image, secrets, CodeQL.
Gates: G-DOCKER, G-CODEQL, G-SECRETS, G-PROV, planned G-GODOT.

| ID | Case | How | Pass |
|---|---|---|---|
| E-01 | Godot pointer integrity | Resolve `godot.pointer` and verify its pinned revision/digest | Matches; fail closed on mismatch |
| E-02 | Forge output provenance | Generate content, inspect metadata | Every artifact carries source SHA and generator version |
| E-03 | Docker build | Run the `Docker Build` job steps | Builds; no secrets baked in |
| E-04 | Code scanning | Review open CodeQL alerts | Zero high/critical |
| E-05 | Secret scanning | Check secret-scanning results | Zero open findings |

---

## Regression cadence

- Every PR: all "Blocks merge: Yes" gates.
- Nightly on main: full lanes A–E.
- Before any ship call: full plan on the exact candidate SHA, signed by the QA Director.
