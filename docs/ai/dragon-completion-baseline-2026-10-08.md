# Dragon AI completion baseline — 2026-10-08

## Status vocabulary (mandatory)

- **Implemented:** source code exists in the repository.
- **Unit-verified:** automated tests executed successfully at the recorded commit SHA.
- **Integrated:** a real caller exercises the capability across its public boundary.
- **End-to-end verified:** real authorized inputs produce reviewable outputs in the running application.
- **Released:** reproducible build, security gates, rollback, and user acceptance evidence exist.

A file, stub, test definition, commit, or green unrelated CI job does **not** count as end-to-end completion.

## Snapshot

- Repository: `Apeloff1/Skeleton`
- Reference commit: `802b97a7d033838043b1f2bb8ebbf359d91524d5`
- CI observation at reference commit: zero returned combined statuses; zero returned associated PR-triggered workflow runs. This is **missing evidence**, not a passing or failing verdict.
- This snapshot is scoped to the Dragon research/gameplay-analysis work. It is not an audit of the entire Skeleton repository.
- No local pytest, TypeScript compilation, full app boot, or integration run has been verified in this baseline.

## Capability ledger

| Capability | Code | Tests authored | Execution evidence | Integration evidence |
| --- | --- | --- | --- | --- |
| Source reread scheduling | yes | yes | unknown | no |
| Probabilistic evidence distillation | yes | yes | unknown | no |
| Independence-group stress testing | yes | yes | unknown | no |
| Temporal feature segmentation | yes | yes | unknown | partial: callable worker |
| Temporal analysis worker | yes | yes | unknown | partial: chain receipt |
| Mechanic hypotheses and trial outcomes | yes | yes | unknown | no |
| 12-layer evidence chain | yes | yes | unknown | partial: execution planner |
| Quality measurements | yes | yes | unknown | no |
| Knowledge graph and retrieval | yes | yes | unknown | no |
| Promotion gate | yes | yes | unknown | no |
| Consent-based screen capture UI | yes | yes | unknown | not established |
| Animated dragon companion UI | yes | yes | unknown | not established |
| Playable prototype generator | yes | yes | unknown | not established |
| Two independently executing adversarial agents | no demonstrated runtime | no verified integration | none | no |
| Full application assembly and installer | unknown | unknown | none in this audit | unknown |

## Known critical correctness risks

1. **Uncalibrated probability:** the distiller maps confidence and reliability to heuristic log-likelihood increments. Without empirical likelihood estimates and held-out calibration, `Belief.probability` must not be presented as a statistically calibrated posterior. Promotion policy thresholds using it are provisional.
2. **Source independence:** `independence_group` is caller-provided. Multiple copies of the same source or dependent observations can inflate evidence. Build provenance-derived dependency clusters and adversarial duplicate-source tests.
3. **Receipt authenticity:** fingerprints are self-reported hashes, not signatures or attestations. A matching hash proves equality of declared strings, not that a worker actually ran or that a source was genuine.
4. **Quality measurements:** current quality gate accepts caller-provided numbers; no per-layer measurement worker is attested. Treat quality scores as unverified until calculated from evidence and independently validated.
5. **Consent and custody:** an `authorized=True` boolean does not constitute durable consent, retention policy, revocation propagation, or secure deletion.
6. **Causal claims:** a `randomized=True` field alone does not verify randomized assignment, blinding, compliance, or absence of interference. Require a trial protocol and stronger inference review.
7. **Execution:** most of the 12 layers have contracts or planners but no executable implementation.
8. **CI:** no successful exact-head regression run is recorded in this baseline.

## Deathmarch — strict completion gates

### P0 — establish reproducibility and stop false positives

- [ ] Pin an exact `main` SHA and enumerate Dragon tests and imports.
- [ ] Run `pytest` on the Dragon test modules and record failure tracebacks.
- [ ] Repair constructor/API mismatches and invalid assumptions before adding features.
- [ ] Run TypeScript typecheck for Dragon recorder/studio/companion.
- [ ] Add a focused GitHub Actions job that runs Dragon unit and integration tests on pull requests and main.
- [ ] Replace undocumented CI assumptions with exact-head run links and pass/fail evidence.

### P1 — operational ingestion and analysis

- [ ] Connect explicit screen-capture consent to bounded frame extraction.
- [ ] Bind source identity, capture timestamp, consent scope, and retention to each frame.
- [ ] Execute temporal segmentation from real recordings, with cancellation and backpressure.
- [ ] Implement object tracking, state inference, and measurable confidence intervals.
- [ ] Record falsifiable mechanic hypotheses before experiments; enforce experimental design and alternative explanations.
- [ ] Build replayable, signed or trusted-service-attested evidence receipts.

### P2 — calibrated knowledge and safe game generation

- [ ] Derive provenance-aware independence clusters, rather than trusting caller labels.
- [ ] Fit and evaluate probabilistic evidence likelihoods on held-out labeled examples.
- [ ] Implement source reread workers and cross-source contradiction analysis.
- [ ] Promote only traceable, reviewable, user-approved knowledge.
- [ ] Integrate retrieval, taste profiles, originality checks, and playable prototype output.
- [ ] Run two genuine model/agent execution paths with bounded competition budgets and independently scored results.

### P3 — application and release

- [ ] Mount recorder, companion, analysis review, and game studio in the actual app.
- [ ] Verify accessibility, offline behavior, crash recovery, deletion, and privacy controls.
- [ ] Run adversarial tests: prompt injection, source poisoning, replay tampering, privacy leakage, copyrighted-content similarity, and malicious recordings.
- [ ] Validate a reproducible app build and Windows installer with end-to-end acceptance scenarios.
- [ ] Sign completed masterplan volumes only after corresponding evidence links exist.

## Quantitative progress policy

Use **verified gates / total gates**, not lines of code or commits. There are 6 P0, 6 P1, 6 P2 and 4 P3 gates above (22 total). At baseline, **0/22 are evidenced complete in this audit**. This does **not** mean zero underlying implementation; it means no gate has yet been independently validated against its acceptance criteria. Update counts only after running and recording the checks.

## Next immediate command sequence

1. Run targeted Python tests and import smoke tests on the exact commit.
2. Triage the first reproducible failure and repair it.
3. Repeat until targeted tests pass, then run broader regression and TypeScript checks.
4. Capture exact SHA, test output, environment and CI run URL.
5. Only then mark P0 verification gates complete and advance to P1.
