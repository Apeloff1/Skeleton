# AI Game Builder — Overengineering Constitution

Status: **active design authority**  
Machine authority: `machine/ai_game_builder_overengineering.json`  
Parent ladder: `machine/ai_game_builder_500_levels.json`  
Rival runtime: `machine/ai_game_builder_dual_rival_forge.json`

## Purpose

The 500 GBL levels define *what* must become excellent. This constitution defines the cross-cutting engineering laws that prevent a locally impressive result from becoming a globally bad game.

The system is deliberately overdesigned around one constraint: two creative AIs may compete aggressively, but neither may escape project truth, evidence, rights, reproducibility, or whole-game coherence.

## 48 mandatory cross-cutting planes

1. **Rival Isolation** — no hidden scratch-state sharing or side-channel collusion.
2. **Role Symmetry & Anti-Collusion** — builder/challenger authority rotates every round.
3. **Blind Candidate Evaluation** — anonymize candidate identity where practical to reduce evaluator anchoring.
4. **Pareto Promotion Constitution** — hard gates first, protected dimensions second, quality gains last.
5. **Anti-Goodhart & Metric Gaming** — held-out probes and play/replay evidence can veto pretty scores.
6. **Longform Canon Causality** — canon is a versioned causal graph, not a prose reminder.
7. **Character Epistemic State** — who knows/believes/suspects what, when, and why is explicit.
8. **Branch Universe & Temporal Integrity** — branch worlds, retcons, simulations, and saves never bleed silently.
9. **Pixel-to-Project Traceability** — every atom can be traced to its parent asset, scene, system, source, and release.
10. **Cross-Modal Coherence** — story, visuals, audio, UI, camera, mechanics, animation, and state agree.
11. **Rights Clean-Room Boundary** — source rights govern what may influence or be incorporated.
12. **Similarity-Risk Ensemble** — text/code/image/audio/name/layout risk screens remain non-legal signals.
13. **Source Quality, Freshness & Contradiction** — evidence is ranked, timestamped, and contradiction-preserving.
14. **Determinism, Replay & Counterfactuals** — important decisions can be replayed and compared against prior champions.
15. **Checkpoint, Event-Sourcing & Rollback** — the last known-good champion survives crashes and failed experiments.
16. **Bounded-Resource Infinite-Time Discipline** — no wall-clock deadline never means unbounded resources.
17. **Adversarial Playtest Swarm** — novice, expert, goal-driven, adversarial, and accessibility-oriented player policies attack the game.
18. **Property, Fuzz & Metamorphic Verification** — invariants are tested beyond canned examples.
19. **Independent Calibration & Appeal** — disputed decisions preserve evidence and can be independently reviewed.
20. **Adaptive Effort Escalation** — Forge-100, -1000, and -10000 are selected by risk/value while retaining exact round semantics.
21. **Project-Local Learning & Skill Consolidation** — verified lessons become sandboxed project skills only after evaluation.
22. **Artifact Bill of Materials & Lineage** — every derived code/media/content artifact carries dependency and transformation lineage.
23. **Cross-Platform Reproducibility** — target-specific behavior stays within declared compatibility tolerances.
24. **Whole-Game Release Arbitration** — no subsystem averages away a critical release failure.

25. **Epistemic Uncertainty & Calibration** — confidence is calibrated, ambiguity is explicit, and high-impact uncertainty can veto promotion.
26. **Evaluator Ensemble & Judge Diversity** — independent multi-method judge quorums replace single-judge authority.
27. **Novelty Reservoir & Mode-Collapse Defense** — preserve strong alternatives and actively resist repetitive local optima across long runs.
28. **Durable Dissent & Unresolved Objection Memory** — losing arguments and negative evidence persist until explicitly resolved.
29. **Predictive Blast-Radius & Causal Impact Analysis** — predict affected scenes/systems/assets/tests/saves before mutation and calibrate predictions afterward.
30. **Cross-Granularity Invariant Compiler** — compile project pillars into inherited machine-checkable constraints down to scene/asset/code/pixel/audio boundaries.
31. **Complexity & Design-Entropy Budget** — added mechanics, lore, UI, dependencies, and states must justify their complexity with player value.
32. **Counterfactual Player Policy Laboratory** — compare candidates across novice, expert, accessibility, exploratory, mistaken, and adversarial player policies.
33. **Exploit Economics & Degenerate Strategy Mining** — systematically search cross-system loopholes and dominant strategies over long horizons.
34. **Pacing, Tension & Cognitive-Load Control** — track rhythm, fatigue, tutorial density, and information burden across the whole game.
35. **Visual Style Manifold & Art-Bible Enforcement** — measure style drift across silhouette, palette, material, composition, motion, and lighting.
36. **Accessibility Equivalence Proof** — accessibility modes must preserve task solvability, information access, and meaningful challenge.
37. **Localization Semantic & Cultural Parity** — preserve gameplay meaning, voice, intent, terminology, timing, and layout across locales.
38. **Game Security, Cheat & Abuse Resistance** — threat-model gameplay, networking, generated scripts, economies, mods, and authority boundaries.
39. **Privacy & Telemetry Minimization** — purpose-bound collection, minimal retention, sensitive-data isolation, and governed deletion/export.
40. **Modding & Extensibility Sandbox** — extensions use capability-scoped APIs, quotas, versioned contracts, and reversible disable paths.
41. **LiveOps Evolution & World Migration** — seasonal/live changes preserve saves, canon, fairness, economy, and rollback.
42. **Corruption Detection, Repair & Self-Healing** — content-addressed integrity checks repair derived state from authoritative sources.
43. **Evaluator Poisoning & Prompt-Injection Containment** — retrieved sources, UGC, assets, and rival output remain untrusted data and cannot rewrite authority.
44. **Tool, Model & Transform Attestation** — every important artifact/verdict is bound to exact tool/model/config/source/policy identities.
45. **Canary, Soak & Progressive Release Control** — controlled exposure and abort thresholds precede full promotion, with automatic rollback.
46. **Cost, Energy & Thermal Efficiency Governance** — use long wall-clock time efficiently by maximizing quality gain per governed resource.
47. **Quality-Debt Ratchet & Non-Regression Baseline** — unresolved quality debt is typed, bounded, and its promotion ceiling can only tighten.
48. **Independent Gold-Master Tribunal** — terminal release requires a separate whole-game evidence authority beyond both rivals and routine evaluators.

## Non-compensable order of authority

Promotion order is intentionally lexicographic:

1. hard gates;
2. protected-dimension non-regression;
3. task-specific acceptance;
4. quality-vector dominance;
5. independent verdict.

A huge gain in visual beauty cannot compensate for broken rights provenance. Better combat cannot compensate for a corrupted save. A brilliant scene cannot compensate for an impossible character knowledge state. Better average frame time cannot compensate for catastrophic tail stalls if tails are protected.

## Anti-collusion and anti-bias

Rivals keep private working contexts. Only governed canon, evidence, source-rights state, champion artifacts, and explicit handoff receipts are shared. Candidate identity may be hidden from evaluation where practical. Candidate order is randomized for sampled blind re-evaluation. Challenge acceptance asymmetry is monitored so one rival cannot become a ceremonial critic.

The deterministic arbiter is not a third creative AI. It enforces state transitions and machine gates. Subjective evaluation may use independent evaluators or calibrated human evidence, but neither rival can be final authority for its own candidate.

## Infinite time, finite resources

Forge-100, Forge-1000, and Forge-10000 have no wall-clock deadline. Every run still has:

- per-round compute and tool budgets;
- memory/context limits;
- persistent-storage quotas;
- bounded branch counts;
- retry caps;
- concurrency limits;
- checkpoint cadence;
- explicit cancellation and hard-fault semantics.

Time is an ally because the system may continue careful iteration, not because it may leak resources forever.

## Runtime kernel

The branch now contains a deterministic control-plane kernel and three governed project-state foundations:

- `skeleton/ai/game_builder/contracts.py`
- `skeleton/ai/game_builder/dual_rival_forge.py`
- `skeleton/ai/game_builder/canon.py`
- `skeleton/ai/game_builder/rights.py`
- `skeleton/ai/game_builder/atomizer.py`
- `tests/test_ai_game_builder_runtime.py`
- `tests/test_ai_game_builder_governance.py`

The forge kernel enforces exact effort budgets, exact three-stage order, alternating roles, independent evaluator identity, non-compensable gate vetoes, Pareto-safe quality promotion, explicit synthesis ancestry, tamper-evident checkpoint digests, and exact completion only when the selected round count is reached.

The canon ledger implements branch-aware assertions, temporal validity and explicit character knowledge events so accidental contradictions and epistemic leaks fail closed. The rights ledger implements source-rights states, explicit incorporation decisions, unknown-rights quarantine and unresolved-high-similarity release blocking. The atom graph implements stable pixel/content atoms, parent context, dependency closure and deterministic change blast radius.

It intentionally does **not** call model providers. Model execution must plug into this control plane rather than becoming the control plane.

## Copyright, originality, and clean-room design

The target is to minimize infringement and provenance risk, not claim impossible universal legal certainty. Unknown incorporated rights fail closed. Reference-only sources may contribute facts, techniques, constraints, or abstract ideas but may not be copied as protected expression.

Similarity checks are an ensemble of risk screens across text, code, image, audio/music, names/marks, layouts, characters, and world elements. A score is never a legal conclusion. Unresolved high-risk cases are quarantined and escalated for human/legal review.

## Family coverage

All 50 game-builder capability families inherit the 11 critical planes:

`OP01 OP02 OP04 OP05 OP06 OP11 OP14 OP15 OP16 OP22 OP24`

Each family also receives domain-specific planes. The machine authority requires at least 11 planes per family, so no GBL family can exist outside the shared governance spine.

## Evidence rule

Every overengineering plane starts planned and unsigned. A plane becomes complete only when implementation plus its declared evidence exists at exact head. A GBL level cannot use a plane's prose as completion evidence, and a plane cannot weaken a GBL hard gate.


## Second-generation runtime controls

The constitution is now partially executable through four additional deterministic primitives:

- `skeleton/ai/game_builder/evaluation.py` — independent evaluator quorum, robust median aggregation, confidence floors, method diversity, disagreement-driven appeal, and blind candidate tokens.
- `skeleton/ai/game_builder/resource_governor.py` — atomic token/tool/artifact/retry/branch/concurrency accounting with checkpoint cadence and deliberately **no wall-clock budget field**.
- `skeleton/ai/game_builder/quality_debt.py` — typed unresolved debt, zero-tolerance protected debt by default, critical-debt vetoes, and ceilings that may only tighten.
- `skeleton/ai/game_builder/control_plane.py` — integrates the duel, evaluator panel, resource governor, and debt ratchet. Panel medians—not candidate self-scores—are used for promotion comparison, and a material declared-vs-adjudicated score gap becomes a hard gate.
- `skeleton/ai/game_builder/resilience.py` — executes critical novelty/mode-collapse defense, durable dissent, transitive blast-radius prediction, and cross-granularity invariant inheritance.
- `skeleton/ai/game_builder/release.py` — terminal 50-family gold-master evidence bundle plus an independent tribunal; failed family qualification or tribunal dissent blocks release.

The integrated control plane recomputes the canonical panel decision from the bound panel before promotion. A caller cannot fabricate a favorable `PanelDecision` and bypass the judge quorum.

No runtime primitive grants completion by existing. The 48 planes remain individually unsigned until their own exact-head evidence is produced.
