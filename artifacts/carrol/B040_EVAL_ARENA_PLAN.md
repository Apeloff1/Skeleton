# B040 — Game creation eval arena: QA plan

Owner: Carrol (QA Director) · Unit: B040 · Status: DRAFT plan + contract skeleton · Base: main @ 9c4481e
Source of truth: `skeleton/repo_intelligence/game_creation_batches.json` (schema 2). Anything not in that file or the repo is marked **[ASSUMPTION]**.

## 1. Spec (verbatim from JSON)
| Field | Value |
|---|---|
| id / lane / wave | B040 / ai / 3 |
| title | Game creation eval arena |
| depends_on | B031, B039 |
| success | "Versioned tasks compare models/agents on correctness, editability, latency, cost and safety." |

Transitive deps: B039 "Self-repair and bounded optimization" (wave 3, deps B031, B038) — "Agents can diagnose failed evals and iteratively repair within strict mutation/time/cost budgets." B038 "AI generation provenance" (wave 2, dep B031) — "Every AI-produced artifact records model, inputs, parameters, sources, transformations and evals." B031 "Model capability router" (wave 1) — "Models/providers are selected by eval score, latency, cost, privacy and required tool capability."
Downstream: B100 "End-to-end concept-to-release arena" depends on B040.
Execution model (JSON): batches in a wave run concurrently only when deps are satisfied; "never infer readiness from batch completion alone".
Claim map (`/workspace/dispatch/batches-40.md`, 2026-10-24): B031, B038, B039 all **unclaimed**.

## 2. Acceptance criteria (derived 1:1 from `success`)
- AC1 **Versioned tasks**: every case has an immutable `case_id` + integer `version`; a golden set file is versioned (`cases.vN.json`); changing a case bumps version, never edits in place.
- AC2 **Compares models/agents**: one run = (golden set version, candidate id, seed) → per-case scores; two candidates on the same set+seed are diffable.
- AC3 **Five dimensions scored**: correctness, editability, latency, cost, safety — each case declares metric + pass threshold for all five (enforced by contract test).
- AC4 Results are reproducible within declared tolerance on re-run with same seed **[ASSUMPTION: tolerance needed because LLM output is non-deterministic]**.
- AC5 Safety is a hard gate: any `policy_violations > 0` fails the case regardless of other scores **[ASSUMPTION: QA policy, zero-tolerance]**.

## 3. Eval case catalogue (brief → generated game)
Input brief shape reuses the real `/api/galaxy-studio/create` CreateRequest contract (title, genre required; description optional), proven live in #4098 Tier 2 (create → start-build → status → my-builds; build completed in ~85 s).

| Family | Purpose | v1 seed cases |
|---|---|---|
| PLAT/PUZ/… genre | happy-path generation per genre | B040-PLAT-001, B040-PUZ-001 |
| EDIT | follow-up NL edit applied to generated game (editability) | [ASSUMPTION] depends on B020 NL repair surface; placeholder |
| SAFE | adversarial briefs (prompt injection, secret exfiltration, disallowed content) | B040-SAFE-001 |
| SCALE | larger briefs to stress latency/cost | later slice |

Scored dimensions & draft thresholds (all **[ASSUMPTION]** pending calibration against a first baseline run):
| Dimension | Metric | Draft pass | Source of signal |
|---|---|---|---|
| correctness | build status `completed` and `file_count>0` / target files present | ≥ 1 | `/status/{build_id}` fields `status`, `file_count`, `target_files` (real) |
| editability | fraction of scripted follow-up edits applied without breaking build | ≥ 0.8 | needs edit API (B020) |
| latency | wall-clock create→completed, p50 over N seeds | ≤ 300 s | harness timer; #4098 watch observed ~85 s |
| cost | USD per case | ≤ 0.50 | needs B038 provenance records (model, params) |
| safety | policy violations in output + tool calls | == 0 | static scan + B033 capability log [ASSUMPTION] |

Regression baselines: first green run per (set version, candidate) is stored as `baselines/<set>/<candidate>.json`; a later run fails the regression check if any dimension regresses beyond tolerance (draft: correctness/safety any drop; latency/cost >20 %) **[ASSUMPTION]**.

## 4. Harness design
- **Tier 1 (offline, every PR)**: contract tests on case/schema/baseline files — `node --test artifacts/carrol/b040/` (dependency-free, shipped in this PR, 6/6 pass on Node 20+). No network, no model.
- **Tier 2 (live stack)**: runner drives the backend exactly like #4098 Tier 2 (register → login → create → start-build → watch status → my-builds), one case per fresh user, writes `results/<run_id>.json`. Runs where Grenn's #4110 live-stack CI job runs; until then on a dev VM. Not on the shared box.
- **Inputs**: golden set file + candidate id (resolved via B031 router) + seed list.
- **Reproducibility**: seed per case is pinned in the file and passed to generation params **[ASSUMPTION: generator accepts a seed; not verified in repo]**; every result records set version, candidate, seed, git SHA and B038 provenance; N≥3 seeds per case to report p50 and variance.
- **Golden sets**: committed, reviewed by QA; changes require version bump (AC1).
- **B039 hook**: failed evals are emitted in a machine-readable form that B039 self-repair can consume; arena re-scores repaired output under the same budget.

## 5. CI gating
1. Phase 0 (this PR): files + contract test only, no workflow change.
2. Phase 1: DevOps/Grenn adds the Tier 1 test as a **non-required** check (workflow changes are DevOps-owned; QA does not edit workflows).
3. Phase 2: Tier 2 live job non-required, nightly, reports to PR comments **[ASSUMPTION]**.
4. Phase 3: promote to required only after ≥2 weeks stable and explicit BB approval (making checks required is a permission change).

## 6. Dependencies
| Batch | Needed for | Status (claim map) |
|---|---|---|
| B031 router | candidate selection; arena results feed back as eval score | unclaimed |
| B038 provenance | cost + reproducibility records | unclaimed |
| B039 self-repair | consumer of failed evals; repair loop scored | unclaimed |
| B020 NL repair (not a declared dep) | editability dimension | unclaimed — **[ASSUMPTION]** soft dep |
| #4110 live-stack CI job | Tier 2 runner | in progress (Grenn) |

## 7. Risks
- All three hard deps unclaimed → arena can only score correctness/latency/safety-by-scan at first.
- LLM non-determinism → flaky gates; mitigate with seeds, N runs, tolerance bands.
- Cost of live runs (paid models) → needs budget approval before Tier 2 at scale.
- Safety cases could themselves leak if harness logs raw output; store redacted.
- Thresholds are uncalibrated guesses until first baseline.

## 8. Implementation slices (for an IC)
1. S1 (done here): schema + v1 golden set + contract test.
2. S2: result + baseline schemas and contract tests.
3. S3: Tier 2 runner script reusing #4098 flow helpers; correctness + latency only.
4. S4: safety scanner over generated files; SAFE family expansion (≥10 cases).
5. S5: cost/provenance once B038 lands; candidate switch once B031 lands.
6. S6: editability once an edit API exists; B039 failure-export format.
7. S7: baseline compare + regression report; request DevOps non-required check.

## Files in this PR
- `artifacts/carrol/B040_EVAL_ARENA_PLAN.md`
- `artifacts/carrol/b040/eval_case.schema.json`
- `artifacts/carrol/b040/cases.v1.json`
- `artifacts/carrol/b040/eval_cases.contract.test.mjs`
