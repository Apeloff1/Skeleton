"""Second-order semantic depth lenses for Jeeves.

These lenses deepen every semantic family already present in the unified plane.
They focus on diagnostic structure that becomes important after first-order lens
selection: hidden assumptions, failure modes, dynamic transitions, validation
leakage, dependence, delayed effects, and representation boundaries.

Like all semantic lenses, these operators generate questions, hypotheses and
falsifiable forecasts. They never create evidence or independently authorize
factual or causal claims.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .semantic_extreme_lenses import LensMaturity, RareLensDefinition
from .semantic_lenses import LensFamily, SemanticLensRegistry, SemanticLensSpec, SemanticRole
from .types import AgentContractError, stable_fingerprint


DEPTH_CATALOG_VERSION = "depth-v1"


def _d(
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


def depth_semantic_definitions() -> tuple[RareLensDefinition, ...]:
    """Return three second-order lenses for every semantic family."""
    return (
        # FILM
        _d(
            "continuity_space_graph", LensFamily.FILM, SemanticRole.STRUCTURE, 1910,
            "Reconstruct spatial continuity as a graph of viewpoints, entrances, exits, gaze and movement rather than assuming cuts preserve one geometry.",
            ("space", "continuity", "entrance", "exit", "gaze", "cut"),
            ("Which spatial adjacency constraints are actually established across shots?",),
            "A coherent continuity graph should predict later entrances, gaze targets or movement directions better than an unconstrained layout.",
            "Treating editing convention as proof of literal scene geometry.",
            ("continuity editing", "spatial cognition"), LensMaturity.MIXED,
            "Viewer-inferred space and physical shooting space are distinct.", minimum=3, sequential=True,
        ),
        _d(
            "color_motif_transition", LensFamily.FILM, SemanticRole.PREDICTION, 1940,
            "Treat recurring color structure as a state-linked motif only when transitions recur with independently identifiable narrative states.",
            ("color", "palette", "motif", "red", "blue", "transition"),
            ("Does the color pattern track a repeatable state transition rather than isolated production design?",),
            "If the motif is state-linked, the same transition should recur with similar color changes in later independent scenes.",
            "Assigning symbolic meaning to a single color appearance.",
            ("color dramaturgy", "visual motif"), LensMaturity.CONCEPTUAL,
            "Require repeated within-work structure before inferring a motif.", minimum=3, sequential=True,
        ),
        _d(
            "occlusion_reveal", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1920,
            "Model hidden and revealed visual regions as changes in audience access rather than changes in world state.",
            ("occluded", "hidden", "reveal", "behind", "frame", "visible"),
            ("What became newly observable, and was it newly created or merely newly revealed?",),
            "A pure reveal predicts continuity of the revealed object's state across the access transition.",
            "Treating newly visible information as newly occurring information.",
            ("cinematic staging", "visual attention"), LensMaturity.MIXED,
            "Separate presentation access from world-state change.", minimum=2, sequential=True,
        ),

        # LITERATURE
        _d(
            "narrative_distance", LensFamily.LITERATURE, SemanticRole.PERSPECTIVE, 1950,
            "Track shifts between close experiential access and distant summary as a discourse variable.",
            ("close", "distant", "interior", "summary", "thought", "narrator"),
            ("How much access does the discourse grant to perception, thought and evaluative language?",),
            "Stable distance shifts should correlate with changes in available mental-state detail and narrative compression.",
            "Equating grammatical person with a fixed degree of narrative distance.",
            ("narratology", "style"), LensMaturity.CONCEPTUAL,
            "Distance is multidimensional and should not be inferred from pronouns alone.", minimum=2, sequential=True,
        ),
        _d(
            "intertextual_dependency", LensFamily.LITERATURE, SemanticRole.CONTEXTUALIZATION, 1960,
            "Distinguish a reading that requires an external text from one recoverable from the local work itself.",
            ("reference", "allusion", "quote", "echo", "source text", "intertext"),
            ("Which inference disappears if the proposed source text is unknown?",),
            "A genuine dependency predicts systematic loss or change of interpretation when the referenced source is unavailable.",
            "Treating superficial phrase overlap as deliberate intertextual dependency.",
            ("intertextuality", "allusion studies"), LensMaturity.CONCEPTUAL,
            "Source dependence and authorial intent are separate hypotheses.", minimum=2, pairwise=True,
        ),
        _d(
            "motif_state_machine", LensFamily.LITERATURE, SemanticRole.STRUCTURE, 1920,
            "Track a recurring motif as a sequence of contextual states instead of a static symbol.",
            ("motif", "recurs", "again", "symbol", "changes", "returns"),
            ("What contextual state accompanies each recurrence, and how does that state change?",),
            "If the motif participates in a structured progression, later recurrences should occupy constrained successor states.",
            "Forcing a linear symbolic progression onto loosely repeated imagery.",
            ("motif analysis", "structuralism"), LensMaturity.CONCEPTUAL,
            "Preserve unmatched and contradictory recurrences instead of smoothing them away.", minimum=3, sequential=True,
        ),

        # GAME
        _d(
            "economy_sink_source", LensFamily.GAME, SemanticRole.STRUCTURE, 1980,
            "Model resource generation and removal as sources and sinks that determine long-run game-economy pressure.",
            ("source", "sink", "currency", "resource", "inflation", "economy"),
            ("Which mechanics create the resource, which destroy it, and at what state-dependent rates?",),
            "Persistent net source pressure predicts accumulation or inflation unless countered by adaptive sinks.",
            "Diagnosing inflation from nominal balances without measuring transaction or sink behavior.",
            ("game economy design", "flow systems"), LensMaturity.MIXED,
            "Player demand and velocity can matter as much as nominal supply.", minimum=3, sequential=True,
        ),
        _d(
            "counterplay_window", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1990,
            "Evaluate whether an opposing player has a perceivable and executable response window before an action becomes decisive.",
            ("counterplay", "window", "react", "telegraph", "response", "interrupt"),
            ("What information and time are available to the opponent before commitment becomes irreversible?",),
            "Wider readable response windows should increase successful counters for players with sufficient skill.",
            "Assuming every powerful action must expose symmetric counterplay.",
            ("competitive game design", "reaction windows"), LensMaturity.HEURISTIC,
            "Counterplay quality depends on goals, skill distribution and intended asymmetry.", minimum=2, sequential=True,
        ),
        _d(
            "progression_gate", LensFamily.GAME, SemanticRole.STRUCTURE, 1980,
            "Represent progression as prerequisites and gates that constrain reachable content or capabilities.",
            ("unlock", "gate", "level", "prerequisite", "progression", "require"),
            ("Which prerequisite relation prevents the next state from being reachable?",),
            "Removing a genuine gate should make previously unreachable states accessible without changing unrelated prerequisites.",
            "Calling mere difficulty a formal progression gate.",
            ("progression systems", "state graphs"), LensMaturity.MIXED,
            "Distinguish hard prerequisites from soft cost or skill barriers.", minimum=2, pairwise=True,
        ),

        # NARRATIVE
        _d(
            "causal_story_gap", LensFamily.NARRATIVE, SemanticRole.ADVERSARIAL_READING, 1980,
            "Identify places where narrative sequence encourages a causal inference that the presented events do not independently establish.",
            ("because", "therefore", "after", "caused", "led to", "story"),
            ("Which causal link is supplied by narrative coherence rather than direct evidence?",),
            "A genuine narrative gap should admit alternative causal models that preserve the same event order.",
            "Treating all narrative explanation as epistemically suspect.",
            ("narrative cognition", "causal attribution"), LensMaturity.MIXED,
            "Narrative order can suggest hypotheses but cannot substitute for causal identification.", minimum=2, sequential=True,
        ),
        _d(
            "setup_payoff_latency", LensFamily.NARRATIVE, SemanticRole.PREDICTION, 1900,
            "Track the distance between introduced narrative affordances and later resolution or reuse.",
            ("setup", "payoff", "later", "returns", "promise", "foreshadow"),
            ("Which earlier element creates an unresolved expectation, and how long does it remain active?",),
            "Repeated construction patterns should constrain the likely horizon and form of later payoff.",
            "Labeling any repeated detail a planned setup/payoff pair.",
            ("dramaturgy", "foreshadowing"), LensMaturity.HEURISTIC,
            "Retrospective coherence can overstate advance planning.", minimum=2, sequential=True,
        ),
        _d(
            "branch_merge", LensFamily.NARRATIVE, SemanticRole.STRUCTURE, 1980,
            "Model divergent narrative paths that later reconverge and identify which state differences survive the merge.",
            ("branch", "choice", "merge", "converge", "path", "ending"),
            ("Which branch-specific state variables remain distinct after reconvergence?",),
            "A strong merge should eliminate or reconcile most branch-specific dependencies before shared downstream events.",
            "Calling visually similar scenes a state-equivalent narrative merge.",
            ("interactive narrative", "branching structures"), LensMaturity.MIXED,
            "Track state, not only scene identity, when evaluating convergence.", minimum=3, sequential=True,
        ),

        # SEMIOTIC
        _d(
            "sign_chain_drift", LensFamily.SEMIOTIC, SemanticRole.META, 1960,
            "Track meaning drift across a chain where one sign is repeatedly interpreted through another.",
            ("sign", "meaning", "reinterpret", "chain", "drift", "translation"),
            ("At which link does the mapping cease to preserve the prior distinction?",),
            "Longer interpretive chains should accumulate detectable divergence unless mappings are explicitly constrained.",
            "Assuming every paraphrase changes meaning materially.",
            ("semiotics", "translation studies"), LensMaturity.CONCEPTUAL,
            "Define the preserved distinctions before measuring drift.", minimum=3, sequential=True,
        ),
        _d(
            "codebook_ambiguity", LensFamily.SEMIOTIC, SemanticRole.ADVERSARIAL_READING, 1948,
            "Test whether the same signal can be decoded under multiple plausible conventions or codebooks.",
            ("code", "decode", "symbol", "ambiguous", "convention", "mapping"),
            ("Which competing codebooks map the same sign to different interpretations?",),
            "Independent contextual constraints should reduce the set of viable decodings.",
            "Inventing arbitrary codebooks with no community or system support.",
            ("semiotics", "coding theory"), LensMaturity.MIXED,
            "A possible decoding is not a conventional decoding without evidence.", minimum=2, pairwise=True,
        ),
        _d(
            "multimodal_conflict", LensFamily.SEMIOTIC, SemanticRole.CONTRAST, 1970,
            "Preserve disagreement between modalities instead of averaging text, image, sound or gesture into one message.",
            ("text", "image", "sound", "gesture", "conflict", "contradict"),
            ("Which modality supports which proposition, and are their source roles comparable?",),
            "If conflict is systematic, later cases should reveal stable modality-specific reliability or framing differences.",
            "Assuming one modality is privileged without source-specific validation.",
            ("multimodal semiotics", "cross-modal integration"), LensMaturity.MIXED,
            "Keep modality provenance explicit.", minimum=2, pairwise=True,
        ),

        # COGNITIVE
        _d(
            "working_memory_load", LensFamily.COGNITIVE, SemanticRole.PREDICTION, 1956,
            "Model performance degradation when concurrent maintenance and manipulation exceed bounded working-memory resources.",
            ("working memory", "load", "remember", "simultaneous", "complex", "capacity"),
            ("Which information must remain actively available at the same time?",),
            "Reducing concurrent load should improve accuracy or latency when working-memory pressure is causal.",
            "Explaining every error on a complex task as capacity overload.",
            ("working memory", "cognitive load"), LensMaturity.EMPIRICAL,
            "Capacity and strategy vary by task and person; avoid fixed universal item limits."),
        _d(
            "retrieval_competition", LensFamily.COGNITIVE, SemanticRole.CAUSAL_HINT, 1970,
            "Treat recall failure as competition among related traces rather than simple absence.",
            ("recall", "compete", "interference", "similar", "memory", "retrieve"),
            ("Which alternative traces are activated by the same cue?",),
            "Increasing cue specificity should improve target retrieval when competition drives failure.",
            "Inferring a specific competing trace from retrieval difficulty alone.",
            ("memory interference", "cue-dependent retrieval"), LensMaturity.EMPIRICAL,
            "Use observed confusion or cue effects to support a competition account.", minimum=2, pairwise=True),
        _d(
            "belief_perseverance", LensFamily.COGNITIVE, SemanticRole.ADVERSARIAL_READING, 1975,
            "Test whether a belief persists after the evidence that originally supported it has been undermined.",
            ("still believe", "retracted", "debunked", "despite", "persevere", "update"),
            ("Did confidence fail to adjust after the original evidence was explicitly invalidated?",),
            "Directly explaining why the original evidence failed should reduce persistence more than mere retraction in affected cases.",
            "Calling rational residual belief perseverance when independent evidence remains.",
            ("belief perseverance", "belief revision"), LensMaturity.EMPIRICAL,
            "Audit all remaining evidence before labeling under-updating."),

        # RHETORIC
        _d(
            "implicature_cancellation", LensFamily.RHETORIC, SemanticRole.ADVERSARIAL_READING, 1975,
            "Test a pragmatic inference by checking whether it can be explicitly cancelled without contradiction.",
            ("some", "but not", "in fact", "actually", "cancel", "imply"),
            ("Can the suspected implication be denied while the literal utterance remains coherent?",),
            "Defeasible implicatures should permit cancellation in at least some compatible contexts.",
            "Treating cancellability as sufficient proof that a specific implicature was intended.",
            ("Gricean pragmatics", "implicature"), LensMaturity.MIXED,
            "Cancellation distinguishes entailment from defeasible inference, not speaker intent.", minimum=2, pairwise=True),
        _d(
            "presupposition_failure", LensFamily.RHETORIC, SemanticRole.ADVERSARIAL_READING, 1970,
            "Detect when an utterance backgrounds a proposition that is absent, disputed or incompatible with common ground.",
            ("again", "stop", "realize", "presuppose", "assume", "background"),
            ("Does the trigger require background content that the discourse participants have not accepted?",),
            "Explicit denial or repair should occur more often when a critical presupposition is unsupported.",
            "Treating every unfamiliar background assumption as pragmatic failure.",
            ("presupposition", "common ground"), LensMaturity.MIXED,
            "Accommodation may legitimately repair missing common ground."),
        _d(
            "framing_baseline_shift", LensFamily.RHETORIC, SemanticRole.CONTRAST, 1980,
            "Compare equivalent claims expressed against different reference baselines.",
            ("baseline", "relative", "gain", "loss", "compared with", "frame"),
            ("Which reference point makes the same outcome appear favorable or unfavorable?",),
            "Holding outcomes fixed while changing baselines should alter evaluation when framing is influential.",
            "Calling any comparison a framing manipulation.",
            ("framing effects", "reference dependence"), LensMaturity.EMPIRICAL,
            "Separate numerical reference changes from broader semantic reframing.", minimum=2, pairwise=True),

        # SOCIAL
        _d(
            "common_knowledge_gap", LensFamily.SOCIAL, SemanticRole.PERSPECTIVE, 1970,
            "Distinguish everyone knowing a fact from everyone knowing that everyone knows it.",
            ("everyone knows", "common knowledge", "public", "announce", "coordination", "shared"),
            ("Which higher-order belief level is actually established?",),
            "A public announcement should enable coordination unavailable under equivalent private information when common knowledge matters.",
            "Assuming shared information is automatically common knowledge.",
            ("epistemic game theory", "common knowledge"), LensMaturity.FORMAL,
            "Higher-order belief structure must be represented explicitly.", minimum=2, pairwise=True),
        _d(
            "network_diffusion", LensFamily.SOCIAL, SemanticRole.PREDICTION, 1950,
            "Model spread through network exposure and topology rather than treating adoption events as independent.",
            ("network", "spread", "neighbor", "viral", "diffuse", "cascade"),
            ("Which edges transmit exposure, and how concentrated is influence in the topology?",),
            "Network-local exposure should predict adoption better than global frequency when diffusion is edge-mediated.",
            "Inferring contagion from correlated behavior among connected actors.",
            ("diffusion models", "social networks"), LensMaturity.MIXED,
            "Homophily and shared environment are competing explanations.", minimum=3, sequential=True),
        _d(
            "reputation_feedback", LensFamily.SOCIAL, SemanticRole.CAUSAL_HINT, 1980,
            "Model actions and observed reputation as a feedback loop in which each can alter the other.",
            ("reputation", "rating", "trust", "feedback", "status", "behavior"),
            ("Does reputation alter future opportunity while behavior simultaneously alters reputation?",),
            "Exogenous reputation changes should shift later opportunities if the feedback link is operational.",
            "Treating correlation between reputation and behavior as one-way causation.",
            ("reputation systems", "social feedback"), LensMaturity.MIXED,
            "Bidirectional mechanisms and selection effects must remain explicit.", minimum=3, sequential=True),

        # TEMPORAL
        _d(
            "lag_structure", LensFamily.TEMPORAL, SemanticRole.STRUCTURE, 1950,
            "Represent multiple candidate delays between related processes instead of assuming immediate response.",
            ("lag", "delay", "after", "lead", "response time", "offset"),
            ("At which lag is the relationship stable, and does that lag match a plausible mechanism?",),
            "A stable delayed mechanism should concentrate predictive association around a repeatable lag.",
            "Choosing the lag that maximizes correlation after broad unconstrained search.",
            ("time-series analysis", "distributed lag models"), LensMaturity.FORMAL,
            "Lag selection requires out-of-sample validation or correction for search.", minimum=3, sequential=True),
        _d(
            "seasonality_alias", LensFamily.TEMPORAL, SemanticRole.ADVERSARIAL_READING, 1960,
            "Test whether apparent relationships are induced by shared periodic structure.",
            ("seasonal", "cycle", "weekly", "daily", "monthly", "periodic"),
            ("Does the relationship persist after accounting for each series' periodic components?",),
            "Removing shared seasonality should weaken associations that were primarily calendar-driven.",
            "Removing real causal periodic effects as nuisance seasonality.",
            ("seasonal time series", "signal processing"), LensMaturity.FORMAL,
            "Seasonal adjustment can remove signal as well as confounding structure.", minimum=3, sequential=True),
        _d(
            "delayed_effect_window", LensFamily.TEMPORAL, SemanticRole.PREDICTION, 1950,
            "Represent effects that begin, peak and decay over a time window rather than at one instant.",
            ("delayed effect", "onset", "peak", "decay", "window", "later"),
            ("What onset and decay window is mechanistically plausible?",),
            "Repeated exposures should show outcome changes concentrated within a similar lag window if the delayed effect is stable.",
            "Selecting the window post hoc around the observed outcome.",
            ("distributed effects", "event studies"), LensMaturity.MIXED,
            "Pre-specify or cross-validate time windows where possible.", minimum=3, sequential=True),

        # SYSTEM
        _d(
            "circuit_breaker_state", LensFamily.SYSTEM, SemanticRole.STRUCTURE, 2010,
            "Model closed, open and half-open circuit-breaker states as explicit control state.",
            ("circuit breaker", "open", "half-open", "failure threshold", "trip", "recover"),
            ("Which transition rule moves the system between service and rejection states?",),
            "Repeated failures should trigger rejection until the recovery condition permits a bounded probe.",
            "Calling generic retry suppression a circuit breaker.",
            ("resilience engineering", "distributed systems"), LensMaturity.FORMAL,
            "Validate actual state transitions and thresholds.", minimum=3, sequential=True),
        _d(
            "retry_storm", LensFamily.SYSTEM, SemanticRole.CAUSAL_HINT, 2010,
            "Treat uncoordinated retries as load amplification that can worsen the failure they respond to.",
            ("retry", "storm", "backoff", "timeout", "thundering herd", "load"),
            ("Does each failure generate enough retry traffic to raise effective arrival rate above recovery capacity?",),
            "Adding jitter, backoff or retry budgets should reduce synchronized load if retry amplification is causal.",
            "Blaming retries when baseline demand already exceeds capacity.",
            ("distributed systems", "reliability engineering"), LensMaturity.MIXED,
            "Measure original and retry traffic separately.", minimum=3, sequential=True),
        _d(
            "cascading_failure_path", LensFamily.SYSTEM, SemanticRole.PREDICTION, 1960,
            "Trace ordered dependency failures to identify paths along which local degradation becomes systemic.",
            ("cascade", "dependency", "failure", "downstream", "propagate", "blast radius"),
            ("Which dependency edge transfers load, bad state or unavailability to the next component?",),
            "Breaking a true propagation edge should reduce downstream failure probability under matched upstream faults.",
            "Reading temporal co-failure as a dependency path.",
            ("reliability engineering", "network failures"), LensMaturity.MIXED,
            "Propagation edges need mechanism or intervention support.", minimum=3, sequential=True),

        # CAUSAL
        _d(
            "frontdoor_identification", LensFamily.CAUSAL, SemanticRole.CAUSAL_HINT, 1995,
            "Test whether a fully mediating observed pathway can identify an effect despite unobserved treatment-outcome confounding.",
            ("front-door", "mediator", "unobserved confounding", "indirect", "identify", "path"),
            ("Do the front-door assumptions hold for treatment-to-mediator and mediator-to-outcome paths?",),
            "When assumptions hold, mediator-based adjustment should recover a stable effect despite treatment-outcome confounding.",
            "Using front-door adjustment without full mediation or valid mediator-outcome control.",
            ("Pearl", "front-door criterion"), LensMaturity.FORMAL,
            "Front-door identification requires strong graphical assumptions.", minimum=3, sequential=True),
        _d(
            "instrumental_variable_probe", LensFamily.CAUSAL, SemanticRole.ADVERSARIAL_READING, 1928,
            "Evaluate a proposed instrument for relevance, exclusion and independence rather than treating correlation with treatment as sufficient.",
            ("instrument", "iv", "relevance", "exclusion", "encouragement", "endogenous"),
            ("What path could let the instrument affect the outcome outside the treatment channel?",),
            "A valid instrument should shift treatment while showing no supported direct outcome pathway under the assumed model.",
            "Accepting an instrument because it strongly predicts treatment.",
            ("instrumental variables", "causal inference"), LensMaturity.FORMAL,
            "Exclusion is often untestable and must be defended substantively.", minimum=2, pairwise=True),
        _d(
            "interference_spillover", LensFamily.CAUSAL, SemanticRole.STRUCTURE, 1960,
            "Relax no-interference assumptions when one unit's treatment can alter another unit's outcome.",
            ("spillover", "interference", "neighbor", "network", "treatment", "contagion"),
            ("Whose treatment assignment can plausibly affect this unit's outcome?",),
            "Cluster- or network-aware estimands should differ from individual-only estimates when spillovers are material.",
            "Calling correlated peer outcomes treatment interference without a treatment pathway.",
            ("SUTVA", "causal interference"), LensMaturity.FORMAL,
            "Specify the interference graph or exposure mapping.", minimum=2, pairwise=True),

        # INFORMATION
        _d(
            "active_query_value", LensFamily.INFORMATION, SemanticRole.PLAYER_MODEL, 1950,
            "Choose the next observation by expected reduction of decision-relevant uncertainty per acquisition cost.",
            ("query", "ask", "probe", "information gain", "cost", "next observation"),
            ("Which affordable observation most changes the posterior over decision-relevant states?",),
            "Higher-ranked probes should produce larger expected decision-relevant posterior changes on average.",
            "Optimizing abstract entropy reduction when the decision does not depend on that uncertainty.",
            ("active learning", "value of information"), LensMaturity.FORMAL,
            "Query value is conditional on the current model and utility target."),
        _d(
            "lossy_summary_budget", LensFamily.INFORMATION, SemanticRole.META, 1959,
            "Audit which distinctions are intentionally discarded when compressing context into a bounded summary.",
            ("summary", "compress", "token budget", "lossy", "omit", "context"),
            ("Which future queries become unanswerable after this compression?",),
            "A summary that discards task-relevant distinctions should cause predictable downstream retrieval or reasoning failures.",
            "Treating every omitted detail as harmful information loss.",
            ("rate-distortion", "information bottleneck"), LensMaturity.MIXED,
            "Loss must be evaluated against downstream tasks, not source length."),
        _d(
            "uncertainty_budget", LensFamily.INFORMATION, SemanticRole.META, 2020,
            "Allocate limited verification effort toward uncertainties with the largest expected downstream consequence.",
            ("uncertainty", "budget", "verify", "priority", "unknown", "risk"),
            ("Which uncertainty contributes most to decision sensitivity per unit verification cost?",),
            "Targeted verification should reduce decision instability more than equal effort on low-impact uncertainty.",
            "Converting subjective importance into a precise information-theoretic quantity.",
            ("value of information", "risk-based verification"), LensMaturity.HEURISTIC,
            "Use as a resource-allocation heuristic unless utilities are explicitly modeled."),

        # COMPUTATIONAL
        _d(
            "memoization_tradeoff", LensFamily.COMPUTATIONAL, SemanticRole.META, 1960,
            "Compare recomputation cost with cache memory, invalidation and key-correctness cost.",
            ("memoize", "cache", "recompute", "memory", "key", "invalidate"),
            ("Which subproblem repeats with stable semantics, and what makes a cached answer stale?",),
            "Memoization should improve repeated-work latency when hit rate exceeds lookup and invalidation overhead.",
            "Caching nondeterministic or context-dependent computations under incomplete keys.",
            ("dynamic programming", "memoization"), LensMaturity.FORMAL,
            "Correctness depends on cache-key completeness and invalidation semantics."),
        _d(
            "consistency_latency_tradeoff", LensFamily.COMPUTATIONAL, SemanticRole.STRUCTURE, 2000,
            "Expose the operational tradeoff between coordination strength and response latency under partition or distance.",
            ("consistency", "latency", "replica", "quorum", "partition", "coordination"),
            ("Which reads or writes wait for which remote acknowledgements?",),
            "Stronger synchronous coordination should increase tail latency under network delay relative to weaker consistency modes.",
            "Treating CAP as a universal latency theorem for all operating conditions.",
            ("distributed systems", "consistency models"), LensMaturity.FORMAL,
            "State the failure and network model explicitly.", minimum=2, pairwise=True),
        _d(
            "scheduler_fairness", LensFamily.COMPUTATIONAL, SemanticRole.ADVERSARIAL_READING, 1960,
            "Inspect whether resource scheduling systematically starves tasks despite global throughput.",
            ("scheduler", "fair", "starve", "priority", "queue", "share"),
            ("Which runnable task waits unboundedly or receives persistently lower service than policy promises?",),
            "A fairness defect should appear as sustained service imbalance under matched demand classes.",
            "Calling intentional priority differentiation unfairness.",
            ("scheduling theory", "operating systems"), LensMaturity.FORMAL,
            "Evaluate against the scheduler's declared fairness contract.", minimum=3, sequential=True),

        # METACOGNITIVE
        _d(
            "confidence_resolution_curve", LensFamily.METACOGNITIVE, SemanticRole.META, 1980,
            "Separate calibration from resolution: predictions can be calibrated yet insufficiently discriminate easy from hard cases.",
            ("confidence", "resolution", "calibration", "discriminate", "sharpness", "forecast"),
            ("Do higher-confidence bins actually correspond to meaningfully different empirical outcome rates?",),
            "A useful confidence system should show both acceptable calibration and nontrivial separation across bins.",
            "Treating sharp but miscalibrated predictions as high-quality resolution.",
            ("probabilistic forecasting", "calibration-resolution decomposition"), LensMaturity.FORMAL,
            "Calibration and resolution are distinct properties.", minimum=3, sequential=True),
        _d(
            "search_diversity_audit", LensFamily.METACOGNITIVE, SemanticRole.ADVERSARIAL_READING, 2020,
            "Measure whether generated hypotheses differ structurally rather than only lexically.",
            ("alternatives", "diverse", "hypotheses", "same idea", "search", "different"),
            ("Do alternatives imply different evidence, mechanisms or falsifiers?",),
            "Structurally diverse hypotheses should yield more distinct discriminating tests than paraphrase-heavy sets.",
            "Rewarding novelty that is irrelevant to the target problem.",
            ("metareasoning", "diversity search"), LensMaturity.HEURISTIC,
            "Diversity is useful only when hypotheses remain plausible and testable."),
        _d(
            "evidence_saturation", LensFamily.METACOGNITIVE, SemanticRole.META, 2020,
            "Detect diminishing marginal value from repeatedly collecting highly redundant evidence.",
            ("more evidence", "same source", "redundant", "saturation", "confirm", "again"),
            ("How much does the next evidence item change the posterior or decision compared with its cost?",),
            "As evidence becomes redundant, marginal belief change should fall while independent evidence retains higher value.",
            "Stopping evidence collection merely because the conclusion feels stable.",
            ("Bayesian updating", "information gain"), LensMaturity.MIXED,
            "Redundancy must be measured through dependence, not source count alone.", minimum=3, sequential=True),

        # PROBABILITY
        _d(
            "calibration_drift", LensFamily.PROBABILITY, SemanticRole.PREDICTION, 2000,
            "Track whether probability calibration changes over time or domain even when headline accuracy appears stable.",
            ("calibration", "drift", "probability", "over time", "domain", "reliability"),
            ("Do empirical outcome rates within probability bins change across time or population slices?",),
            "True calibration drift should produce persistent bin-level reliability changes in later windows.",
            "Calling random bin noise drift in small samples.",
            ("forecast calibration", "dataset shift"), LensMaturity.EMPIRICAL,
            "Use uncertainty intervals and minimum sample sizes for sliced calibration.", minimum=3, sequential=True),
        _d(
            "exchangeability_break", LensFamily.PROBABILITY, SemanticRole.ADVERSARIAL_READING, 1990,
            "Audit whether a method relying on exchangeable observations is exposed to order, cluster or distribution dependence.",
            ("exchangeable", "iid", "order", "cluster", "dependence", "conformal"),
            ("Which permutation or resampling symmetry does the method require, and what process violates it?",),
            "Methods relying on exchangeability should lose nominal guarantees under systematic nonexchangeable shifts.",
            "Declaring exchangeability false merely because observations are temporally ordered.",
            ("exchangeability", "conformal inference"), LensMaturity.FORMAL,
            "Some dependent processes admit weaker valid symmetry assumptions.", minimum=3, sequential=True),
        _d(
            "partial_identification_bounds", LensFamily.PROBABILITY, SemanticRole.META, 1990,
            "Return a set or interval of compatible quantities when assumptions do not point-identify one value.",
            ("bound", "interval", "partially identified", "unknown dependence", "range", "compatible"),
            ("What extrema remain compatible with observed constraints and stated assumptions?",),
            "Adding a valid identifying restriction should narrow, never widen, the feasible identified set.",
            "Reporting an arbitrary midpoint of a wide identified set as the estimate.",
            ("partial identification", "Fréchet bounds"), LensMaturity.FORMAL,
            "Bounds are conditional on the constraint set and should remain visible."),

        # PREDICTIVE
        _d(
            "target_leakage", LensFamily.PREDICTIVE, SemanticRole.ADVERSARIAL_READING, 2000,
            "Detect features containing direct or proxy information unavailable at the intended prediction time.",
            ("leakage", "target", "future", "feature", "post-outcome", "validation"),
            ("Could this feature only exist after or because of the target outcome?",),
            "Removing leaked features should reduce apparently exceptional validation performance toward deployable levels.",
            "Calling a legitimate contemporaneous predictor leakage.",
            ("machine learning validation", "data leakage"), LensMaturity.FORMAL,
            "Prediction-time availability must be defined precisely.", minimum=2, pairwise=True),
        _d(
            "temporal_validation_leak", LensFamily.PREDICTIVE, SemanticRole.ADVERSARIAL_READING, 2000,
            "Audit train/test construction for future-to-past information flow in temporal prediction tasks.",
            ("time split", "future", "validation", "shuffle", "leak", "train"),
            ("Can any preprocessing statistic, label-derived feature or future record influence an earlier validation case?",),
            "Strict forward-chaining validation should reduce performance inflated by temporal leakage.",
            "Assuming random split is always invalid for temporally indexed data.",
            ("time-series validation", "machine learning"), LensMaturity.FORMAL,
            "The split must match the intended deployment information set.", minimum=2, pairwise=True),
        _d(
            "residual_autocorrelation", LensFamily.PREDICTIVE, SemanticRole.ADVERSARIAL_READING, 1920,
            "Treat predictable structure remaining in forecast errors as evidence of model misspecification or omitted dynamics.",
            ("residual", "autocorrelation", "error", "lag", "pattern", "forecast"),
            ("Do residuals retain stable lagged structure after conditioning on the model?",),
            "Adding the missing temporal structure should reduce out-of-sample residual autocorrelation if it is genuinely predictive.",
            "Overfitting residual noise until diagnostics appear white.",
            ("time-series diagnostics", "forecast evaluation"), LensMaturity.FORMAL,
            "Residual whiteness is not sufficient for overall model validity.", minimum=3, sequential=True),
    )


def depth_semantic_specs() -> tuple[SemanticLensSpec, ...]:
    return tuple(item.spec for item in depth_semantic_definitions())


def register_depth_lenses(
    registry: SemanticLensRegistry,
    *,
    ignore_existing: bool = True,
) -> SemanticLensRegistry:
    if not isinstance(registry, SemanticLensRegistry):
        raise TypeError("registry must be SemanticLensRegistry")
    existing = {item.key for item in registry.all()}
    for definition in depth_semantic_definitions():
        if definition.spec.key in existing:
            if ignore_existing:
                continue
            raise AgentContractError(f"duplicate depth semantic lens: {definition.spec.key}")
        registry.register(definition.spec)
        existing.add(definition.spec.key)
    return registry


def depth_definitions_by_family(
    definitions: Iterable[RareLensDefinition] | None = None,
) -> dict[LensFamily, tuple[RareLensDefinition, ...]]:
    items = tuple(definitions or depth_semantic_definitions())
    grouped: dict[LensFamily, list[RareLensDefinition]] = {}
    for item in items:
        grouped.setdefault(item.spec.family, []).append(item)
    return {
        family: tuple(sorted(values, key=lambda item: (item.spec.lineage_year, item.spec.key)))
        for family, values in grouped.items()
    }


def depth_catalog_fingerprint() -> str:
    return stable_fingerprint(
        {
            "version": DEPTH_CATALOG_VERSION,
            "definitions": [
                (
                    item.spec.key,
                    item.spec.family.value,
                    item.spec.role.value,
                    item.spec.lineage_year,
                    item.maturity.value,
                    item.lineage,
                )
                for item in depth_semantic_definitions()
            ],
        }
    )
