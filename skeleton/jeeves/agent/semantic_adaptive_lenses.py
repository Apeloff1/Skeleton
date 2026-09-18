"""Adaptive third-order semantic lenses for Jeeves.

This layer targets failure detection, boundary conditions, update dynamics, and
validation breakdowns that become important after first- and second-order lens
analysis. Every family receives exactly two lenses.

These operators remain hypothesis generators. They may select observations,
propose tests, and create forecasts, but they never create evidence or grant
standalone factual or causal authority.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .semantic_extreme_lenses import LensMaturity, RareLensDefinition
from .semantic_lenses import LensFamily, SemanticLensRegistry, SemanticLensSpec, SemanticRole
from .types import AgentContractError, stable_fingerprint


ADAPTIVE_CATALOG_VERSION = "adaptive-v1"


def _a(
    key: str,
    family: LensFamily,
    role: SemanticRole,
    year: int,
    description: str,
    cues: Sequence[str],
    asks: Sequence[str],
    predicts: str,
    failure: str,
    lineage: Sequence[str],
    maturity: LensMaturity,
    warning: str,
    *,
    minimum: int = 1,
    pairwise: bool = False,
    sequential: bool = False,
) -> RareLensDefinition:
    return RareLensDefinition(
        SemanticLensSpec(
            key=key,
            family=family,
            role=role,
            lineage_year=year,
            description=description,
            activation_cues=tuple(cues),
            asks=tuple(asks),
            predicts=predicts,
            failure_mode=failure,
            minimum_observations=minimum,
            pairwise=pairwise,
            sequential=sequential,
            rare=True,
        ),
        tuple(lineage),
        maturity,
        warning,
    )


def adaptive_semantic_definitions() -> tuple[RareLensDefinition, ...]:
    return (
        # FILM
        _a(
            "shot_scale_transition",
            LensFamily.FILM,
            SemanticRole.PERSPECTIVE,
            1920,
            "Track changes in shot scale as changes in available visual detail and relational context.",
            ("close-up", "wide", "medium", "shot scale", "detail", "distance"),
            ("What information becomes newly available or unavailable when shot scale changes?",),
            "Repeated scale changes should predict systematic shifts in visible detail and contextual access.",
            "Treating scale change as proof of emotional importance.",
            ("cinematography", "visual attention"),
            LensMaturity.MIXED,
            "Shot scale constrains presentation access, not objective importance.",
            minimum=2,
            sequential=True,
        ),
        _a(
            "sound_perspective_mismatch",
            LensFamily.FILM,
            SemanticRole.ADVERSARIAL_READING,
            1970,
            "Test whether auditory perspective and visual viewpoint imply different observer positions.",
            ("sound", "muffled", "distant", "camera", "viewpoint", "perspective"),
            ("Do sound and image imply the same observer location or different access models?",),
            "Persistent mismatch should predict later clarification of subjective or nonlocal sound perspective.",
            "Assuming every audiovisual mismatch is intentional subjectivity.",
            ("film sound", "audiovisual perception"),
            LensMaturity.MIXED,
            "Keep technical mixing and stylistic alternatives open.",
            minimum=2,
            pairwise=True,
        ),

        # LITERATURE
        _a(
            "narrator_knowledge_boundary",
            LensFamily.LITERATURE,
            SemanticRole.PERSPECTIVE,
            1950,
            "Map what the narrator can know, infer, report, or conceal at each point in the discourse.",
            ("narrator", "knows", "could not know", "secret", "thought", "omniscient"),
            ("Which statement crosses the narrator's previously established knowledge boundary?",),
            "Boundary violations should cluster around explicit viewpoint shifts, later revelation, or unreliability cues.",
            "Calling every unexplained detail an impossible knowledge violation.",
            ("narratology", "focalization"),
            LensMaturity.CONCEPTUAL,
            "Narrative convention can legitimately change knowledge access.",
            minimum=2,
            sequential=True,
        ),
        _a(
            "lexical_register_drift",
            LensFamily.LITERATURE,
            SemanticRole.STRUCTURE,
            1930,
            "Track gradual shifts in vocabulary and register that may mark voice, time, audience, or state change.",
            ("register", "vocabulary", "formal", "slang", "voice", "word choice"),
            ("Does lexical change coincide with a stable contextual or speaker-state transition?",),
            "A genuine register transition should recur with independently identifiable discourse-state changes.",
            "Inferring identity or psychology from vocabulary alone.",
            ("stylistics", "sociolinguistics"),
            LensMaturity.MIXED,
            "Do not infer protected identity or stable personality from register.",
            minimum=3,
            sequential=True,
        ),

        # GAME
        _a(
            "equilibrium_break",
            LensFamily.GAME,
            SemanticRole.PREDICTION,
            1944,
            "Detect when a rule, payoff, information, or population change invalidates a previously stable strategic equilibrium.",
            ("meta changed", "balance", "equilibrium", "patch", "counter", "strategy"),
            ("Which payoff or information relation changed enough to alter best responses?",),
            "Players should migrate away from the prior equilibrium after the relevant strategic relation changes.",
            "Calling ordinary exploration an equilibrium break.",
            ("game theory", "metagame analysis"),
            LensMaturity.FORMAL,
            "Equilibrium conclusions remain conditional on modeled payoffs and information.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "exploit_patch_cycle",
            LensFamily.GAME,
            SemanticRole.STRUCTURE,
            2000,
            "Model repeated discovery, exploitation, patching, and rediscovery as an adaptive game-system cycle.",
            ("exploit", "patch", "nerf", "abuse", "fix", "meta"),
            ("Does each intervention remove the mechanism or only one observed manifestation?",),
            "Surface-only fixes should predict recurrence through nearby strategy variants.",
            "Treating every balance update as an exploit response.",
            ("live game operations", "adversarial adaptation"),
            LensMaturity.HEURISTIC,
            "Separate intentional optimization from policy-violating exploitation.",
            minimum=3,
            sequential=True,
        ),

        # NARRATIVE
        _a(
            "unresolved_thread_pressure",
            LensFamily.NARRATIVE,
            SemanticRole.PREDICTION,
            1900,
            "Track unresolved promises, goals, mysteries, and conflicts as active narrative obligations.",
            ("unresolved", "mystery", "promise", "goal", "thread", "return"),
            ("Which open thread still constrains plausible future events?",),
            "High-salience unresolved threads should be more likely to receive later resolution or explicit abandonment.",
            "Assuming every introduced detail requires payoff.",
            ("dramaturgy", "narrative expectation"),
            LensMaturity.HEURISTIC,
            "Open threads can remain intentionally unresolved.",
            minimum=2,
            sequential=True,
        ),
        _a(
            "perspective_handoff",
            LensFamily.NARRATIVE,
            SemanticRole.PERSPECTIVE,
            1900,
            "Model transfer of informational and experiential access from one focal perspective to another.",
            ("perspective", "viewpoint", "handoff", "meanwhile", "switch", "focal"),
            ("Which knowledge becomes available or unavailable after the focal handoff?",),
            "A true perspective handoff should change the accessible evidence set while preserving shared world-state constraints.",
            "Treating any scene change as a viewpoint transfer.",
            ("focalization", "narrative perspective"),
            LensMaturity.CONCEPTUAL,
            "Track access changes separately from world-state changes.",
            minimum=2,
            sequential=True,
        ),

        # SEMIOTIC
        _a(
            "sign_referent_decoupling",
            LensFamily.SEMIOTIC,
            SemanticRole.ADVERSARIAL_READING,
            1900,
            "Detect when a familiar sign remains stable while its actual referent or operational target changes.",
            ("label", "name", "symbol", "referent", "same sign", "changed meaning"),
            ("Does the same sign still point to the same object, state, or convention?",),
            "Independent grounding should reveal divergence when stable labels mask referent change.",
            "Calling ordinary contextual polysemy referent drift.",
            ("semiotics", "reference"),
            LensMaturity.MIXED,
            "Verify the grounding relation rather than assuming one canonical referent.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "convention_shift",
            LensFamily.SEMIOTIC,
            SemanticRole.STRUCTURE,
            1950,
            "Model community or system changes in the convention that maps signs to meanings or actions.",
            ("convention", "new meaning", "usage changed", "code", "norm", "symbol"),
            ("Did the mapping change across time, group, or system version?",),
            "A genuine convention shift should produce cohort- or time-specific decoding differences.",
            "Treating individual misuse as community-level convention change.",
            ("semiotics", "language change"),
            LensMaturity.EMPIRICAL,
            "Require repeated group-level evidence before declaring convention change.",
            minimum=3,
            sequential=True,
        ),

        # COGNITIVE
        _a(
            "attentional_switch_cost",
            LensFamily.COGNITIVE,
            SemanticRole.PREDICTION,
            1990,
            "Model transient performance loss after switching tasks, rules, or attentional sets.",
            ("switch", "task", "context", "attention", "cost", "interrupt"),
            ("Does performance degrade immediately after a rule or task-set switch?",),
            "Switch trials should show higher latency or error than matched repeat trials when switch cost is present.",
            "Attributing all post-interruption errors to cognitive switching.",
            ("task switching", "attention"),
            LensMaturity.EMPIRICAL,
            "Separate switch cost from task difficulty and interruption recovery.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "source_confusion",
            LensFamily.COGNITIVE,
            SemanticRole.ADVERSARIAL_READING,
            1970,
            "Detect correct content recalled with incorrect provenance, speaker, context, or acquisition route.",
            ("source", "who said", "where heard", "remember", "origin", "confuse"),
            ("Is the content memory separable from the memory of where it came from?",),
            "Source-specific cues should improve provenance accuracy more than content accuracy when source confusion is present.",
            "Treating disagreement about provenance as proof of memory unreliability generally.",
            ("source monitoring", "episodic memory"),
            LensMaturity.EMPIRICAL,
            "Content and source memory should be scored separately.",
            minimum=2,
            pairwise=True,
        ),

        # RHETORIC
        _a(
            "modal_force_shift",
            LensFamily.RHETORIC,
            SemanticRole.INTERPRETATION,
            1950,
            "Track changes in modal strength such as possible, likely, should, must, and certain across restatements.",
            ("may", "might", "likely", "should", "must", "certain"),
            ("Did the evidential or normative force become stronger or weaker without new support?",),
            "Unsupported modal strengthening should correlate with larger gaps between source claim and restatement.",
            "Treating all modal variation as distortion.",
            ("modality", "pragmatics"),
            LensMaturity.FORMAL,
            "Distinguish epistemic, deontic, and dynamic modality.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "quotation_context_loss",
            LensFamily.RHETORIC,
            SemanticRole.ADVERSARIAL_READING,
            1900,
            "Test whether extracted wording changes interpretation after surrounding qualifications or referents are removed.",
            ("quote", "context", "excerpt", "before", "after", "qualification"),
            ("Which nearby qualifier, referent, or scope restriction changes the quoted meaning?",),
            "Restoring relevant context should materially change interpretations caused by truncation.",
            "Assuming every short quotation is misleading.",
            ("quotation", "discourse context"),
            LensMaturity.MIXED,
            "Identify the specific omitted context that changes semantics.",
            minimum=2,
            pairwise=True,
        ),

        # SOCIAL
        _a(
            "coordination_failure_mode",
            LensFamily.SOCIAL,
            SemanticRole.STRUCTURE,
            1950,
            "Classify failed coordination by information, incentive, timing, trust, or role mismatch.",
            ("coordination", "failed", "misaligned", "timing", "role", "trust"),
            ("Which necessary coordination condition failed first?",),
            "Repairing the true limiting condition should improve coordination without requiring unrelated changes.",
            "Explaining every group failure through one favored social mechanism.",
            ("coordination theory", "organizational behavior"),
            LensMaturity.MIXED,
            "Preserve multiple failure hypotheses until a repair discriminates them.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "information_cascade",
            LensFamily.SOCIAL,
            SemanticRole.PREDICTION,
            1990,
            "Model actors ignoring private signals after observing sufficiently strong prior public choices.",
            ("cascade", "follow others", "private signal", "herd", "public choice", "copy"),
            ("Would the actor choose differently if prior public choices were hidden?",),
            "Removing public-choice visibility should increase sensitivity to private information if a cascade is active.",
            "Calling any popular choice herding.",
            ("information cascades", "social learning"),
            LensMaturity.FORMAL,
            "Requires an explicit information and action-order model.",
            minimum=3,
            sequential=True,
        ),

        # TEMPORAL
        _a(
            "regime_duration",
            LensFamily.TEMPORAL,
            SemanticRole.PREDICTION,
            1950,
            "Model how long a state or regime persists instead of only modeling transitions between states.",
            ("duration", "how long", "persist", "regime", "state", "dwell"),
            ("Does transition probability depend on time already spent in the current state?",),
            "Duration-dependent regimes should show non-memoryless exit hazards.",
            "Inferring duration dependence from a few long episodes.",
            ("survival analysis", "semi-Markov models"),
            LensMaturity.FORMAL,
            "Estimate dwell-time effects with adequate event counts.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "event_order_uncertainty",
            LensFamily.TEMPORAL,
            SemanticRole.META,
            1900,
            "Represent partial orders when timestamps or reports do not establish a unique sequence.",
            ("order", "before", "after", "uncertain", "timestamp", "simultaneous"),
            ("Which precedence constraints are known, and which event pairs remain unordered?",),
            "New temporal anchors should reduce the set of valid linearizations without contradicting established constraints.",
            "Forcing one total order when only a partial order is justified.",
            ("temporal logic", "partial orders"),
            LensMaturity.FORMAL,
            "Keep unresolved orderings explicit rather than selecting one arbitrarily.",
            minimum=2,
            pairwise=True,
        ),

        # SYSTEM
        _a(
            "graceful_degradation",
            LensFamily.SYSTEM,
            SemanticRole.PREDICTION,
            1970,
            "Test whether reduced capacity preserves core service rather than causing abrupt total failure.",
            ("degrade", "fallback", "reduced", "partial service", "capacity", "essential"),
            ("Which capabilities are intentionally preserved under resource loss?",),
            "Controlled resource reduction should degrade optional functions before protected core functions.",
            "Calling accidental partial failure graceful degradation.",
            ("fault tolerance", "resilience engineering"),
            LensMaturity.MIXED,
            "Gracefulness is defined relative to explicit service priorities.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "load_shedding",
            LensFamily.SYSTEM,
            SemanticRole.STRUCTURE,
            2000,
            "Model deliberate rejection or deferral of work to protect bounded service capacity.",
            ("shed", "drop", "reject", "overload", "admission", "capacity"),
            ("Which requests are rejected, and what protected resource or latency objective does that preserve?",),
            "Effective load shedding should cap protected-resource saturation while increasing controlled rejection.",
            "Confusing uncontrolled loss with deliberate admission control.",
            ("queueing systems", "overload control"),
            LensMaturity.FORMAL,
            "Evaluate both protection benefit and rejected-work cost.",
            minimum=3,
            sequential=True,
        ),

        # CAUSAL
        _a(
            "negative_control_probe",
            LensFamily.CAUSAL,
            SemanticRole.ADVERSARIAL_READING,
            1980,
            "Use an exposure or outcome expected to have no causal effect to probe residual confounding or bias.",
            ("negative control", "placebo", "should not affect", "bias", "confounding", "null"),
            ("What variable shares bias pathways but lacks the target causal pathway?",),
            "A nonzero negative-control association should raise suspicion of uncontrolled bias under the control assumptions.",
            "Treating every negative-control signal as proof of one specific confounder.",
            ("negative controls", "causal inference"),
            LensMaturity.FORMAL,
            "Control validity requires substantive justification.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "positivity_overlap",
            LensFamily.CAUSAL,
            SemanticRole.META,
            1970,
            "Audit whether every relevant covariate stratum has support for the treatment or action comparisons required by the estimand.",
            ("overlap", "positivity", "support", "treated", "control", "propensity"),
            ("Where does the data lack comparable treatment alternatives?",),
            "Severe support gaps should make estimates more sensitive to extrapolation and weighting choices.",
            "Treating low-frequency strata as automatic positivity violations.",
            ("positivity", "causal identification"),
            LensMaturity.FORMAL,
            "Overlap must be assessed relative to the target population and estimand.",
            minimum=2,
            pairwise=True,
        ),

        # INFORMATION
        _a(
            "conditional_entropy_residual",
            LensFamily.INFORMATION,
            SemanticRole.META,
            1948,
            "Measure uncertainty remaining after conditioning on the currently available evidence set.",
            ("conditional entropy", "remaining uncertainty", "given", "residual", "information", "unknown"),
            ("Which uncertainty remains after all currently available variables are conditioned on?",),
            "Adding genuinely informative variables should reduce conditional uncertainty in held-out data.",
            "Equating low conditional entropy with causal understanding.",
            ("information theory", "conditional entropy"),
            LensMaturity.FORMAL,
            "Results depend on the modeled distribution and conditioning set.",
        ),
        _a(
            "compression_invariance",
            LensFamily.INFORMATION,
            SemanticRole.STRUCTURE,
            1960,
            "Test whether a compressed representation preserves decision-relevant relationships under paraphrase or encoding changes.",
            ("compress", "summary", "invariant", "representation", "preserve", "encoding"),
            ("Which downstream relation must survive compression for the representation to remain useful?",),
            "Equivalent source representations should yield equivalent compressed task outputs when invariance is preserved.",
            "Assuming shorter representations are semantically equivalent.",
            ("sufficient statistics", "information bottleneck"),
            LensMaturity.MIXED,
            "Define the downstream task before claiming sufficient preservation.",
            minimum=2,
            pairwise=True,
        ),

        # COMPUTATIONAL
        _a(
            "algorithmic_nondeterminism",
            LensFamily.COMPUTATIONAL,
            SemanticRole.ADVERSARIAL_READING,
            1960,
            "Distinguish intended nondeterministic choice from hidden environmental, concurrency, or random-state dependence.",
            ("nondeterministic", "random", "different result", "seed", "race", "order"),
            ("Which uncontrolled state determines the divergent execution path?",),
            "Fixing the relevant scheduler, seed, or environment should reduce unexplained output variance.",
            "Calling floating-point or external-input variation algorithmic nondeterminism.",
            ("nondeterministic computation", "reproducibility"),
            LensMaturity.FORMAL,
            "Enumerate allowed nondeterminism separately from implementation noise.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "serialization_boundary",
            LensFamily.COMPUTATIONAL,
            SemanticRole.STRUCTURE,
            1980,
            "Audit what type, ordering, precision, identity, or version information is lost when state crosses a serialization boundary.",
            ("serialize", "json", "wire", "schema", "precision", "version"),
            ("Which semantic distinction exists in memory but not in the serialized representation?",),
            "Round-trip failures should concentrate on distinctions omitted or normalized by the serialization format.",
            "Blaming serialization when the producer or consumer already changed semantics.",
            ("data representation", "protocol design"),
            LensMaturity.FORMAL,
            "Compare canonical pre- and post-serialization semantics.",
            minimum=2,
            pairwise=True,
        ),

        # METACOGNITIVE
        _a(
            "uncertainty_miscalibration",
            LensFamily.METACOGNITIVE,
            SemanticRole.META,
            1980,
            "Audit whether uncertainty estimates respond appropriately to evidence quality, novelty, and domain shift.",
            ("uncertain", "confidence", "calibration", "novel", "shift", "evidence quality"),
            ("Does reported uncertainty increase when the evidence basis weakens or the domain moves out of support?",),
            "A calibrated uncertainty mechanism should widen uncertainty under demonstrably weaker support.",
            "Assuming more uncertainty is always more honest or useful.",
            ("metacognition", "uncertainty calibration"),
            LensMaturity.EMPIRICAL,
            "Evaluate uncertainty against outcomes and support conditions.",
            minimum=3,
            sequential=True,
        ),
        _a(
            "adversarial_self_check",
            LensFamily.METACOGNITIVE,
            SemanticRole.ADVERSARIAL_READING,
            2020,
            "Generate a targeted internal counterargument against the strongest current conclusion and demand a discriminating test.",
            ("counterargument", "challenge", "wrong", "falsify", "adversarial", "self-check"),
            ("What strongest plausible alternative explains the same evidence?",),
            "A useful self-check should produce a test whose outcomes would change relative support among live hypotheses.",
            "Generating implausible objections merely to appear balanced.",
            ("falsification", "adversarial reasoning"),
            LensMaturity.HEURISTIC,
            "Counterarguments must remain plausible and evidence-sensitive.",
        ),

        # PROBABILITY
        _a(
            "prior_sensitivity",
            LensFamily.PROBABILITY,
            SemanticRole.META,
            1950,
            "Measure how posterior or decision conclusions change across a justified range of prior assumptions.",
            ("prior", "sensitivity", "bayesian", "posterior", "assumption", "robust"),
            ("Which prior choices materially change the posterior or decision threshold?",),
            "Data-dominated conclusions should remain stable across a reasonable prior family.",
            "Using implausibly extreme priors to manufacture sensitivity.",
            ("Bayesian robustness", "sensitivity analysis"),
            LensMaturity.FORMAL,
            "The prior family itself must be justified and visible.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "multiplicity_correction",
            LensFamily.PROBABILITY,
            SemanticRole.ADVERSARIAL_READING,
            1930,
            "Account for increased false-positive opportunity when many hypotheses, metrics, groups, or windows are searched.",
            ("multiple tests", "many metrics", "significant", "search", "p-hacking", "correction"),
            ("How many effective opportunities existed to discover the reported extreme result?",),
            "Proper multiplicity control should reduce apparent significance of discoveries produced by broad search.",
            "Applying overly conservative correction to a single prespecified hypothesis.",
            ("multiple comparisons", "family-wise error"),
            LensMaturity.FORMAL,
            "Correction depends on the testing family and dependence structure.",
            minimum=2,
            pairwise=True,
        ),

        # PREDICTIVE
        _a(
            "out_of_distribution",
            LensFamily.PREDICTIVE,
            SemanticRole.ADVERSARIAL_READING,
            2010,
            "Detect inputs outside the support or structural conditions represented by training or calibration data.",
            ("out of distribution", "ood", "unseen", "novel", "support", "training"),
            ("Which feature or relation lies outside the validated support region?",),
            "Predictive error or uncertainty should worsen in unsupported regions unless the model has validated extrapolation behavior.",
            "Calling every rare input out-of-distribution.",
            ("distribution shift", "machine learning"),
            LensMaturity.MIXED,
            "OOD depends on the representation and task-relevant support notion.",
            minimum=2,
            pairwise=True,
        ),
        _a(
            "forecast_combination_diversity",
            LensFamily.PREDICTIVE,
            SemanticRole.META,
            1969,
            "Evaluate whether an ensemble gains from genuinely diverse error structure rather than many correlated forecasts.",
            ("ensemble", "combine", "diverse", "forecast", "correlated", "models"),
            ("Do component forecast errors differ enough that combination reduces expected loss?",),
            "Combination should improve most when component errors are informative and imperfectly correlated.",
            "Counting model names as diversity when they share data, features, or failure modes.",
            ("forecast combination", "ensemble methods"),
            LensMaturity.FORMAL,
            "Dependence among component errors must remain explicit.",
            minimum=2,
            pairwise=True,
        ),
    )


def adaptive_semantic_specs() -> tuple[SemanticLensSpec, ...]:
    return tuple(item.spec for item in adaptive_semantic_definitions())


def register_adaptive_lenses(
    registry: SemanticLensRegistry,
    *,
    ignore_existing: bool = True,
) -> SemanticLensRegistry:
    if not isinstance(registry, SemanticLensRegistry):
        raise TypeError("registry must be SemanticLensRegistry")
    existing = {item.key for item in registry.all()}
    for definition in adaptive_semantic_definitions():
        if definition.spec.key in existing:
            if ignore_existing:
                continue
            raise AgentContractError(f"duplicate adaptive semantic lens: {definition.spec.key}")
        registry.register(definition.spec)
        existing.add(definition.spec.key)
    return registry


def adaptive_definitions_by_family(
    definitions: Iterable[RareLensDefinition] | None = None,
) -> dict[LensFamily, tuple[RareLensDefinition, ...]]:
    items = tuple(definitions or adaptive_semantic_definitions())
    grouped: dict[LensFamily, list[RareLensDefinition]] = {}
    for item in items:
        grouped.setdefault(item.spec.family, []).append(item)
    return {
        family: tuple(sorted(values, key=lambda item: (item.spec.lineage_year, item.spec.key)))
        for family, values in grouped.items()
    }


def adaptive_catalog_fingerprint() -> str:
    return stable_fingerprint(
        {
            "version": ADAPTIVE_CATALOG_VERSION,
            "definitions": [
                (
                    item.spec.key,
                    item.spec.family.value,
                    item.spec.role.value,
                    item.spec.lineage_year,
                    item.maturity.value,
                    item.lineage,
                )
                for item in adaptive_semantic_definitions()
            ],
        }
    )
