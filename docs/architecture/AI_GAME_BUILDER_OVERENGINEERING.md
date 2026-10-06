# AI Game Builder — Overengineering Constitution

Status: **active design authority**  
Machine authority: `machine/ai_game_builder_overengineering.json`  
Parent ladder: `machine/ai_game_builder_500_levels.json`  
Rival runtime: `machine/ai_game_builder_dual_rival_forge.json`

## Purpose

The 500 GBL levels define *what* must become excellent. This constitution defines the cross-cutting engineering laws that prevent a locally impressive result from becoming a globally bad game.

The system is deliberately overdesigned around one constraint: two creative AIs may compete aggressively, but neither may escape project truth, evidence, rights, reproducibility, or whole-game coherence.

## 24 mandatory cross-cutting planes

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

The branch now contains a deterministic control-plane kernel:

- `skeleton/ai/game_builder/contracts.py`
- `skeleton/ai/game_builder/dual_rival_forge.py`
- `skeleton/testing/test_ai_game_builder_contracts.py`

The kernel enforces exact effort budgets, exact three-stage order, alternating roles, independent evaluator identity, non-compensable gate vetoes, Pareto-safe quality promotion, explicit synthesis ancestry, tamper-evident checkpoint digests, and exact completion only when the selected round count is reached.

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
