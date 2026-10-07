"""Research semantic lenses for Jeeves.

This catalog extends the maximal semantic runtime with additional operators that
are useful across software systems, social reasoning, temporal analysis,
cognition, rhetoric, semiotics, narrative, cinema, and games.

The definitions remain hypothesis generators.  They do not create evidence and
must not be used as factual or causal authority without independent support.
Each lens therefore carries lineage, maturity, a falsifiable prediction, and a
transfer warning.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .semantic_extreme_lenses import LensMaturity, RareLensDefinition
from .semantic_lenses import LensFamily, SemanticLensRegistry, SemanticLensSpec, SemanticRole
from .types import AgentContractError, stable_fingerprint


CATALOG_VERSION = "research-v1"


def _r(
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


def research_semantic_definitions() -> tuple[RareLensDefinition, ...]:
    """Return additional high-value, cross-domain semantic operators."""
    return (
        # Systems, observability, and control.
        _r(
            "observability_gap", LensFamily.SYSTEM, SemanticRole.ADVERSARIAL_READING, 1960,
            "Distinguish hidden system state from what current telemetry can actually reveal.",
            ("observable", "telemetry", "metric", "trace", "hidden", "state"),
            ("Which state variables remain underdetermined by the available measurements?",),
            "Adding an independent observable should collapse at least one previously indistinguishable state hypothesis.",
            "Treating missing telemetry as proof that the underlying state is absent.",
            ("control theory", "observability", "distributed systems"), LensMaturity.FORMAL,
            "Do not infer unmeasured state without an explicit observation model.",
        ),
        _r(
            "control_loop_delay", LensFamily.SYSTEM, SemanticRole.CAUSAL_HINT, 1950,
            "Model delayed feedback as a source of overshoot, stale correction, or instability.",
            ("delay", "latency", "feedback", "overshoot", "controller", "lag"),
            ("Is the corrective action based on a state that is already stale?",),
            "Longer feedback delay predicts larger correction error when the controlled state changes quickly.",
            "Blaming delay for instability when the controller or plant model is the actual cause.",
            ("feedback control", "delay systems"), LensMaturity.FORMAL,
            "Treat delay as one candidate mechanism, not a complete causal explanation.",
            minimum=3, sequential=True,
        ),
        _r(
            "feedback_oscillation", LensFamily.SYSTEM, SemanticRole.STRUCTURE, 1940,
            "Detect alternating corrections that may indicate an underdamped or overreactive feedback loop.",
            ("oscillate", "flap", "toggle", "alternate", "retry", "revert"),
            ("Do corrective actions repeatedly cross the target instead of converging?",),
            "If the loop is underdamped, successive corrections should alternate around a stable target.",
            "Calling any repeated change an oscillation without a common controlled variable.",
            ("control theory", "stability analysis"), LensMaturity.FORMAL,
            "Require a shared state variable and ordered observations.",
            minimum=3, sequential=True,
        ),
        _r(
            "fault_containment_boundary", LensFamily.SYSTEM, SemanticRole.STRUCTURE, 1970,
            "Reason about whether failures remain isolated or propagate across subsystem boundaries.",
            ("fault", "isolate", "blast radius", "boundary", "cascade", "dependency"),
            ("Where should a local failure stop propagating if containment is working?",),
            "A valid containment boundary predicts downstream degradation without unrestricted state corruption.",
            "Assuming architectural boundaries imply runtime isolation.",
            ("fault tolerance", "reliability engineering"), LensMaturity.MIXED,
            "Verify actual failure propagation paths rather than trusting component diagrams.",
            minimum=2, pairwise=True,
        ),
        _r(
            "queue_backpressure", LensFamily.SYSTEM, SemanticRole.CAUSAL_HINT, 1961,
            "Interpret rising queue depth, blocked producers, and latency as a coupled flow-control problem.",
            ("queue", "backpressure", "throughput", "consumer", "producer", "lag"),
            ("Is arrival rate persistently exceeding effective service rate?",),
            "Sustained overload predicts rising wait time until demand drops, capacity rises, or admission is constrained.",
            "Diagnosing backpressure from a single queue snapshot.",
            ("queueing theory", "flow control", "reactive systems"), LensMaturity.FORMAL,
            "Estimate rates over time before assigning a queueing mechanism.",
            minimum=3, sequential=True,
        ),
        _r(
            "interface_contract_drift", LensFamily.SYSTEM, SemanticRole.ADVERSARIAL_READING, 1990,
            "Track gradual mismatch between producers and consumers that still share an interface name.",
            ("contract", "schema", "api", "version", "compatibility", "drift"),
            ("Which assumptions changed without a corresponding contract revision?",),
            "Contract drift predicts failures concentrated at integration boundaries despite locally valid components.",
            "Treating every integration failure as contract drift instead of implementation defect.",
            ("design by contract", "schema evolution", "software integration"), LensMaturity.MIXED,
            "Compare concrete preconditions, postconditions, and versions before inferring drift.",
            minimum=2, pairwise=True,
        ),

        # Social interaction and coordination.
        _r(
            "audience_design", LensFamily.SOCIAL, SemanticRole.PERSPECTIVE, 1984,
            "Treat expression choices as potentially adapted to an intended audience model.",
            ("audience", "explain", "jargon", "tone", "public", "private"),
            ("What knowledge or reaction does the speaker appear to assume from this audience?",),
            "A stable audience model predicts systematic changes in wording when the audience changes.",
            "Inferring identity or intent from style alone.",
            ("sociolinguistics", "audience design"), LensMaturity.EMPIRICAL,
            "Use observable register changes; do not infer protected traits or private motives.",
            minimum=2, pairwise=True,
        ),
        _r(
            "norm_signaling", LensFamily.SOCIAL, SemanticRole.INTERPRETATION, 1960,
            "Separate literal task content from behavior that may communicate adherence to a group norm.",
            ("norm", "acceptable", "expected", "proper", "signal", "reputation"),
            ("Would the behavior still make sense if nobody else could observe it?",),
            "If signaling matters, behavior should change with observability or reputational stakes.",
            "Assuming visible behavior is primarily performative.",
            ("social norms", "signaling theory"), LensMaturity.MIXED,
            "Treat signaling as a testable alternative to instrumental explanations.",
        ),
        _r(
            "pluralistic_ignorance", LensFamily.SOCIAL, SemanticRole.ADVERSARIAL_READING, 1931,
            "Model a group where private beliefs differ from perceived group consensus.",
            ("everyone", "nobody", "privately", "publicly", "consensus", "silence"),
            ("Do individual private reports diverge from what each person thinks others believe?",),
            "Anonymous elicitation predicts more variance than public behavior when pluralistic ignorance is present.",
            "Using silence as evidence that private disagreement exists.",
            ("social psychology", "pluralistic ignorance"), LensMaturity.EMPIRICAL,
            "Require separate evidence about private and perceived collective beliefs.",
            minimum=3,
        ),
        _r(
            "coordination_threshold", LensFamily.SOCIAL, SemanticRole.PREDICTION, 1969,
            "Model participation as conditional on how many others are expected to participate.",
            ("threshold", "join", "adopt", "critical mass", "others", "participate"),
            ("What expected participation level makes the action worthwhile for each actor?",),
            "Crossing a stable threshold predicts a discontinuous increase in participation.",
            "Fitting threshold dynamics to gradual adoption without individual conditionality.",
            ("collective behavior", "threshold models"), LensMaturity.MIXED,
            "Infer thresholds only from repeated choice under varying expected participation.",
            minimum=3, sequential=True,
        ),
        _r(
            "status_cascade", LensFamily.SOCIAL, SemanticRole.CAUSAL_HINT, 1950,
            "Consider whether deference to high-status actors amplifies otherwise weak signals.",
            ("status", "authority", "leader", "follow", "endorse", "prestige"),
            ("Would the same claim spread if emitted by a low-status source?",),
            "If status amplification matters, matched content from higher-status sources predicts faster or broader uptake.",
            "Reducing agreement to status effects while ignoring content quality or shared evidence.",
            ("social influence", "prestige bias"), LensMaturity.EMPIRICAL,
            "Compare matched messages and preserve independent-content explanations.",
            minimum=2, pairwise=True,
        ),
        _r(
            "coalition_realignment", LensFamily.SOCIAL, SemanticRole.STRUCTURE, 1950,
            "Track alliance structure as a changing graph rather than fixed actor labels.",
            ("alliance", "coalition", "side", "switch", "support", "oppose"),
            ("Which pairwise relations changed, and which higher-order coalition became possible?",),
            "Repeated pairwise shifts predict changes in coalition-level behavior before labels necessarily change.",
            "Inferring durable allegiance from a single joint action.",
            ("coalition theory", "social networks"), LensMaturity.MIXED,
            "Require repeated relational evidence before treating a coalition as stable.",
            minimum=3, sequential=True,
        ),

        # Temporal reasoning.
        _r(
            "event_time_processing_time", LensFamily.TEMPORAL, SemanticRole.STRUCTURE, 2010,
            "Separate when an event happened from when the system observed or processed it.",
            ("event time", "processing time", "late", "timestamp", "out of order", "watermark"),
            ("Is the apparent order an event order or merely an arrival order?",),
            "Late-arriving records should reorder conclusions that depend on event time but not those tied to processing time.",
            "Treating timestamp disagreement as corruption without checking clock and ingestion semantics.",
            ("stream processing", "event-time systems"), LensMaturity.FORMAL,
            "Preserve both event and processing clocks when chronology matters.",
            minimum=2, sequential=True,
        ),
        _r(
            "temporal_aliasing", LensFamily.TEMPORAL, SemanticRole.ADVERSARIAL_READING, 1960,
            "Detect when sparse sampling makes distinct temporal processes appear identical.",
            ("sample", "interval", "frequency", "alias", "periodic", "snapshot"),
            ("Could a faster process produce the same sampled observations?",),
            "Increasing sampling rate should distinguish hypotheses that were aliased at the original cadence.",
            "Attributing every ambiguous time series to undersampling.",
            ("signal processing", "sampling theory"), LensMaturity.FORMAL,
            "Test plausible sampling rates before interpreting apparent cycles.",
            minimum=3, sequential=True,
        ),
        _r(
            "hysteresis_memory", LensFamily.TEMPORAL, SemanticRole.CAUSAL_HINT, 1880,
            "Model state as depending on the path taken, not only the current input.",
            ("hysteresis", "history", "sticky", "path", "lag", "recovery"),
            ("Does the same input produce different states depending on prior trajectory?",),
            "Reversing the input predicts a different transition path when hysteresis is present.",
            "Calling any persistence effect hysteresis.",
            ("hysteresis", "dynamical systems"), LensMaturity.FORMAL,
            "Require matched current inputs with different histories.",
            minimum=3, sequential=True,
        ),
        _r(
            "path_dependence", LensFamily.TEMPORAL, SemanticRole.STRUCTURE, 1985,
            "Treat early contingent choices as constraints on later reachable states.",
            ("path", "lock-in", "legacy", "history", "irreversible", "compatibility"),
            ("Which later choices became costly or impossible because of an earlier branch?",),
            "Systems with path dependence should show different reachable states under counterfactual early choices.",
            "Using path dependence as a vague synonym for history matters.",
            ("increasing returns", "historical institutionalism", "complex systems"), LensMaturity.MIXED,
            "Name the specific state constraint or switching cost that carries history forward.",
            minimum=2, sequential=True,
        ),
        _r(
            "phase_transition_window", LensFamily.TEMPORAL, SemanticRole.PREDICTION, 1870,
            "Look for regime change near a threshold rather than extrapolating one linear trend.",
            ("threshold", "phase", "regime", "critical", "tipping", "transition"),
            ("Which observable changes discontinuously or changes slope near the candidate threshold?",),
            "Repeated crossings of the same control range predict a reproducible regime shift if a transition is real.",
            "Declaring a phase transition from one abrupt change.",
            ("statistical physics", "critical phenomena", "complex systems"), LensMaturity.MIXED,
            "Require repeated or mechanistically grounded threshold behavior.",
            minimum=3, sequential=True,
        ),
        _r(
            "deadline_pressure", LensFamily.TEMPORAL, SemanticRole.PLAYER_MODEL, 1950,
            "Model shrinking time horizon as a change in strategy, risk tolerance, and prioritization.",
            ("deadline", "time left", "urgent", "countdown", "late", "hurry"),
            ("Which actions become rational only because the remaining horizon is shorter?",),
            "As the deadline approaches, actors should shift toward options with faster payoff or lower completion latency.",
            "Explaining poor choices solely through time pressure.",
            ("bounded rationality", "deadline effects"), LensMaturity.EMPIRICAL,
            "Compare behavior across matched tasks with different remaining time.",
            minimum=2, sequential=True,
        ),

        # Cognitive and memory failure modes.
        _r(
            "change_blindness", LensFamily.COGNITIVE, SemanticRole.ADVERSARIAL_READING, 1990,
            "Consider whether a salient scene change went unnoticed because attention was disrupted.",
            ("changed", "didn't notice", "difference", "flicker", "scene", "attention"),
            ("Was attention interrupted at the moment the changed feature would need comparison?",),
            "Reducing the interruption should increase detection of the changed feature.",
            "Using inattentiveness as an explanation for any missed difference.",
            ("visual cognition", "change blindness"), LensMaturity.EMPIRICAL,
            "Apply only to detection behavior, not as evidence about internal awareness.",
            minimum=2, pairwise=True,
        ),
        _r(
            "inattentional_blindness", LensFamily.COGNITIVE, SemanticRole.ADVERSARIAL_READING, 1992,
            "Model failure to notice an unexpected stimulus while attention is occupied elsewhere.",
            ("unexpected", "missed", "attention", "task", "notice", "focus"),
            ("Was attention strongly allocated to a competing task when the stimulus appeared?",),
            "Reducing attentional load should increase detection of the unexpected stimulus.",
            "Treating all missed observations as attentional blindness.",
            ("attention research", "inattentional blindness"), LensMaturity.EMPIRICAL,
            "Distinguish absence of report from proof of absent perception.",
        ),
        _r(
            "fluency_misattribution", LensFamily.COGNITIVE, SemanticRole.META, 1980,
            "Separate ease of processing from truth, familiarity, or quality.",
            ("familiar", "easy", "smooth", "obvious", "fluent", "recognize"),
            ("Is confidence tracking processing ease rather than independent evidence?",),
            "Manipulating presentation fluency while holding content fixed should shift confidence more than accuracy.",
            "Assuming confidence is caused by fluency whenever content is familiar.",
            ("processing fluency", "metacognition"), LensMaturity.EMPIRICAL,
            "Treat fluency as a bias candidate and preserve content-based explanations.",
            minimum=2, pairwise=True,
        ),
        _r(
            "anchoring_adjustment", LensFamily.COGNITIVE, SemanticRole.META, 1974,
            "Test whether estimates remain too close to an initial value despite new evidence.",
            ("anchor", "initial", "estimate", "adjust", "starting", "reference"),
            ("Would a different arbitrary starting value pull the final estimate in a different direction?",),
            "Matched estimators exposed to different starting values should retain a measurable anchor effect.",
            "Calling any stable estimate anchored when the initial value was informative.",
            ("judgment under uncertainty", "anchoring"), LensMaturity.EMPIRICAL,
            "Use randomized or clearly irrelevant anchors to distinguish bias from rational updating.",
            minimum=2, pairwise=True,
        ),
        _r(
            "availability_sampling", LensFamily.COGNITIVE, SemanticRole.META, 1973,
            "Check whether easily retrieved examples are substituting for representative frequency data.",
            ("remember", "example", "recent", "common", "frequent", "available"),
            ("Is estimated frequency tracking retrievability rather than an explicit sample frame?",),
            "Providing balanced frequency data should reduce reliance on salient recalled examples.",
            "Dismissing vivid examples even when they are genuinely frequent.",
            ("availability heuristic", "memory retrieval"), LensMaturity.EMPIRICAL,
            "Compare recalled examples against a defined sampling frame.",
        ),
        _r(
            "memory_confidence_dissociation", LensFamily.COGNITIVE, SemanticRole.ADVERSARIAL_READING, 1970,
            "Keep subjective confidence in a memory separate from measured accuracy.",
            ("confident", "certain", "remember", "memory", "sure", "recall"),
            ("What independent evidence calibrates confidence against actual recall accuracy?",),
            "Across repeated trials, confidence and accuracy can diverge enough to require separate calibration curves.",
            "Treating confidence as useless rather than imperfectly calibrated.",
            ("metamemory", "confidence-accuracy calibration"), LensMaturity.EMPIRICAL,
            "Never convert high confidence directly into factual authority.",
            minimum=2,
        ),

        # Rhetoric and pragmatics.
        _r(
            "enthymeme_gap", LensFamily.RHETORIC, SemanticRole.INTERPRETATION, -350,
            "Recover the unstated premise required for an argument to connect its stated parts.",
            ("therefore", "so", "obviously", "because", "hence", "must"),
            ("Which missing premise makes the stated conclusion follow?",),
            "Making the missing premise explicit predicts whether disagreement targets the premise or the conclusion.",
            "Inventing a premise that makes a weak argument look stronger than intended.",
            ("Aristotelian rhetoric", "argumentation theory"), LensMaturity.CONCEPTUAL,
            "Offer multiple candidate premises when the gap is underdetermined.",
            pairwise=True,
        ),
        _r(
            "framing_by_omission", LensFamily.RHETORIC, SemanticRole.ADVERSARIAL_READING, 1970,
            "Inspect how excluding a relevant comparison class changes the apparent interpretation.",
            ("omit", "missing", "comparison", "context", "only", "selected"),
            ("Which plausible baseline or comparison would materially change the reading?",),
            "Restoring a withheld comparison should change evaluation if omission is doing rhetorical work.",
            "Assuming every absent fact was intentionally omitted.",
            ("framing", "selection effects", "rhetorical analysis"), LensMaturity.MIXED,
            "Distinguish demonstrable selection effects from claims about intent.",
            minimum=2, pairwise=True,
        ),
        _r(
            "burden_shift", LensFamily.RHETORIC, SemanticRole.ADVERSARIAL_READING, 1950,
            "Detect when a claim is defended mainly by demanding that others disprove it.",
            ("prove me wrong", "disprove", "unless", "show otherwise", "burden", "evidence"),
            ("Which party is making the positive claim, and what evidence would normally support it?",),
            "Clarifying evidential burden should separate unsupported assertion from legitimate rebuttal.",
            "Applying one burden convention to every conversational or legal context.",
            ("argumentation theory", "burden of proof"), LensMaturity.CONCEPTUAL,
            "Burden rules depend on context; do not treat this lens as a universal formal law.",
        ),
        _r(
            "equivocation_drift", LensFamily.RHETORIC, SemanticRole.ADVERSARIAL_READING, -350,
            "Track a key term whose operational meaning changes across an argument.",
            ("means", "definition", "same", "term", "actually", "sense"),
            ("Does the conclusion rely on a term having a different meaning than in an earlier premise?",),
            "Replacing the ambiguous term with explicit senses should expose any invalid transition.",
            "Mistaking legitimate polysemy or domain-specific refinement for fallacious drift.",
            ("classical logic", "lexical semantics"), LensMaturity.CONCEPTUAL,
            "Record each sense explicitly before labeling the transition problematic.",
            minimum=2, sequential=True,
        ),
        _r(
            "contrastive_focus", LensFamily.RHETORIC, SemanticRole.INTERPRETATION, 1970,
            "Use prosodic or textual emphasis to identify which alternatives are being contrasted.",
            ("only", "even", "actually", "emphasis", "rather", "instead"),
            ("Which alternative set makes the emphasized element informative?",),
            "Changing focus while holding words mostly fixed should alter which alternatives are excluded.",
            "Reading typographic emphasis as a complete semantic parse.",
            ("focus semantics", "pragmatics"), LensMaturity.FORMAL,
            "Treat focus as a constraint on alternatives, not as evidence of speaker motive.",
        ),
        _r(
            "speech_act_commitment", LensFamily.RHETORIC, SemanticRole.STRUCTURE, 1962,
            "Separate propositional content from the commitment created by asserting, promising, ordering, or requesting.",
            ("promise", "request", "order", "assert", "commit", "offer"),
            ("What normative or conversational commitment follows from the utterance type?",),
            "Different speech acts with similar propositional content predict different acceptable next moves.",
            "Inferring legal or moral obligation from linguistic form alone.",
            ("speech act theory", "pragmatics"), LensMaturity.MIXED,
            "Institutional force must be established separately from conversational force.",
        ),

        # Semiotics and multimodal meaning.
        _r(
            "markedness_contrast", LensFamily.SEMIOTIC, SemanticRole.CONTRAST, 1930,
            "Treat an asymmetry between ordinary and specially marked forms as a potential meaning-bearing contrast.",
            ("marked", "unmarked", "special", "default", "ordinary", "exception"),
            ("What feature makes one form marked relative to the local system?",),
            "Marked forms should cluster in contexts where the contrasted feature matters.",
            "Assuming the less frequent form is always the semantically marked one.",
            ("structural linguistics", "markedness theory"), LensMaturity.MIXED,
            "Define markedness relative to a specific system and contrast set.",
            minimum=2, pairwise=True,
        ),
        _r(
            "multimodal_redundancy", LensFamily.SEMIOTIC, SemanticRole.STRUCTURE, 1970,
            "Measure whether text, image, sound, or gesture repeat the same information or contribute distinct parts.",
            ("text", "image", "audio", "gesture", "same", "redundant"),
            ("Which message components survive if one modality is removed?",),
            "Redundant modalities predict graceful comprehension under single-channel loss.",
            "Calling correlated channels redundant when each contributes unique constraints.",
            ("multimodal communication", "information theory"), LensMaturity.MIXED,
            "Test ablation rather than inferring redundancy from surface similarity.",
            minimum=2, pairwise=True,
        ),
        _r(
            "symbol_grounding_gap", LensFamily.SEMIOTIC, SemanticRole.META, 1990,
            "Identify symbols whose interpretation depends on links to perception, action, or externally grounded conventions.",
            ("symbol", "ground", "meaning", "label", "token", "refer"),
            ("What observation or action anchors this symbol beyond other symbols?",),
            "Grounded symbols should support predictions that survive paraphrase or token substitution.",
            "Demanding sensorimotor grounding for every abstract symbolic system.",
            ("symbol grounding", "cognitive science"), LensMaturity.CONCEPTUAL,
            "Grounding can be social or operational; do not require one privileged modality.",
        ),
        _r(
            "iconicity_gradient", LensFamily.SEMIOTIC, SemanticRole.INTERPRETATION, 1930,
            "Model signs by degree and dimension of resemblance rather than a binary icon/non-icon split.",
            ("resembles", "icon", "shape", "sound", "looks like", "diagram"),
            ("Which structural property of the sign resembles its referent, and how strongly?",),
            "Greater task-relevant resemblance predicts easier mapping for observers who share the same perceptual basis.",
            "Treating resemblance as universal across cultures or tasks.",
            ("Peircean semiotics", "iconicity"), LensMaturity.MIXED,
            "Specify the resemblance dimension and observer context.",
        ),
        _r(
            "code_switch_signal", LensFamily.SEMIOTIC, SemanticRole.PERSPECTIVE, 1950,
            "Treat a switch between codes or registers as a contextual boundary cue without inferring identity.",
            ("switch", "language", "register", "code", "formal", "slang"),
            ("What interactional boundary coincides with the code switch?",),
            "Repeated switching at the same contextual boundary predicts a stable discourse function.",
            "Inferring ethnicity, ideology, or stable personality from a code switch.",
            ("code-switching", "sociolinguistics"), LensMaturity.EMPIRICAL,
            "Analyze local discourse function only; do not infer protected identity.",
            minimum=2, sequential=True,
        ),

        # Literature and narrative.
        _r(
            "narrative_speed", LensFamily.NARRATIVE, SemanticRole.TEMPORAL if hasattr(SemanticRole, "TEMPORAL") else SemanticRole.STRUCTURE, 1972,
            "Compare story-time duration with discourse space devoted to it.",
            ("summary", "scene", "pause", "years", "moment", "pages"),
            ("Where does narration accelerate, decelerate, pause, or omit story time?",),
            "Shifts in narrative speed predict redistribution of attention even when event importance is uncertain.",
            "Equating discourse duration with objective importance.",
            ("Genette", "narratology"), LensMaturity.CONCEPTUAL,
            "Treat duration as presentation structure, not factual importance.",
            minimum=2, sequential=True,
        ),
        _r(
            "narrative_frequency", LensFamily.NARRATIVE, SemanticRole.STRUCTURE, 1972,
            "Distinguish events that occur once but are narrated repeatedly from repeated events narrated once.",
            ("again", "every", "each time", "once", "repeated", "retell"),
            ("How many times did the event occur, and how many times is it narrated?",),
            "Repeated narration of one event predicts memory, emphasis, or perspective differences that can be tested across tellings.",
            "Confusing repeated mention with repeated occurrence.",
            ("Genette", "narrative frequency"), LensMaturity.CONCEPTUAL,
            "Track event identity separately from discourse instances.",
            minimum=2, sequential=True,
        ),
        _r(
            "epistolary_mediation", LensFamily.LITERATURE, SemanticRole.PERSPECTIVE, 1700,
            "Model letters, messages, logs, and documents as mediated records with their own audience and delay.",
            ("letter", "message", "diary", "log", "document", "entry"),
            ("Who produced the record, for whom, and how long after the event?",),
            "Different intended recipients or recording delays predict systematic changes in detail and stance.",
            "Treating documentary form as inherently more truthful than direct narration.",
            ("epistolary form", "documentary narration"), LensMaturity.CONCEPTUAL,
            "Keep document provenance separate from document truth.",
            minimum=2,
        ),
        _r(
            "unreliable_chronology", LensFamily.NARRATIVE, SemanticRole.ADVERSARIAL_READING, 1900,
            "Treat narrated order as potentially inconsistent with event order when temporal anchors conflict.",
            ("before", "after", "then", "later", "earlier", "timeline"),
            ("Which ordering constraints are explicit, and which come only from narration order?",),
            "Independent temporal anchors should resolve at least some conflicts if chronology rather than event identity is uncertain.",
            "Explaining every continuity error as deliberate temporal unreliability.",
            ("modernist narration", "temporal narratology"), LensMaturity.CONCEPTUAL,
            "Preserve an explicit constraint graph and distinguish contradiction from nonlinearity.",
            minimum=3, sequential=True,
        ),
        _r(
            "scene_boundary_cue", LensFamily.NARRATIVE, SemanticRole.STRUCTURE, 1900,
            "Detect transitions where place, time, participants, or goals change enough to form a new event unit.",
            ("scene", "later", "elsewhere", "meanwhile", "arrives", "leaves"),
            ("Which state dimensions changed together at the candidate boundary?",),
            "A real event boundary predicts a local drop in continuity features and reset of some predictive expectations.",
            "Segmenting on every paragraph or camera cut regardless of event continuity.",
            ("event segmentation", "narratology"), LensMaturity.MIXED,
            "Use multiple boundary cues instead of surface formatting alone.",
            minimum=2, sequential=True,
        ),

        # Cinema and audiovisual reasoning.
        _r(
            "motivated_lighting", LensFamily.FILM, SemanticRole.CONTEXTUALIZATION, 1940,
            "Separate lighting justified by an in-scene source from expressive lighting that exceeds that source.",
            ("light", "lamp", "shadow", "source", "glow", "dark"),
            ("Which visible source accounts for the direction and intensity of the light?",),
            "Changes to the visible source should predict corresponding lighting changes when illumination is strongly motivated.",
            "Treating every stylized light as a continuity error or hidden source.",
            ("cinematography", "motivated lighting"), LensMaturity.CONCEPTUAL,
            "Do not infer physical source geometry without image evidence.",
        ),
        _r(
            "depth_staging", LensFamily.FILM, SemanticRole.STRUCTURE, 1940,
            "Interpret foreground, midground, and background action as concurrently available relational structure.",
            ("foreground", "background", "depth", "near", "far", "frame"),
            ("Which relationships become visible only because multiple depth planes remain active?",),
            "Depth-staged relations should remain interpretable without relying on edit order.",
            "Assuming all visible depth planes carry equal narrative weight.",
            ("deep staging", "mise-en-scene"), LensMaturity.CONCEPTUAL,
            "Separate spatial co-presence from causal or narrative importance.",
            minimum=2,
        ),
        _r(
            "lens_distortion_perspective", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1920,
            "Treat focal-length and camera-distance effects as presentation geometry rather than literal object deformation.",
            ("wide", "telephoto", "distort", "perspective", "lens", "distance"),
            ("Could the apparent spatial relation be explained by camera geometry rather than world geometry?",),
            "Changing focal length and camera distance while preserving framing should alter apparent depth compression.",
            "Inferring exact optics from a single image without camera metadata.",
            ("photographic optics", "cinematography"), LensMaturity.FORMAL,
            "Use as a geometric alternative hypothesis, not as automatic metadata recovery.",
            pairwise=True,
        ),
        _r(
            "aspect_ratio_reframing", LensFamily.FILM, SemanticRole.META, 1950,
            "Treat changes in frame shape as presentation constraints that alter inclusion, emphasis, or comparison.",
            ("aspect ratio", "crop", "frame", "widescreen", "vertical", "square"),
            ("What becomes newly included, excluded, or spatially emphasized after reframing?",),
            "A changed frame shape predicts systematic composition changes even when underlying scene content is constant.",
            "Attributing compositional differences to narrative intent when delivery format alone changed.",
            ("film formats", "visual composition"), LensMaturity.CONCEPTUAL,
            "Separate source-format changes from authored within-work reframing.",
            minimum=2, pairwise=True,
        ),

        # Games and interactive systems.
        _r(
            "dominant_strategy_pressure", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1944,
            "Check whether one action is at least as good across relevant opponent responses, compressing meaningful choice.",
            ("dominant", "best", "always", "strategy", "choice", "optimal"),
            ("Does one action weakly or strictly dominate alternatives across the modeled response set?",),
            "If dominance is real, experienced players should converge on that action absent external constraints or preferences.",
            "Calling a popular strategy dominant without comparing counter-responses.",
            ("game theory", "dominance"), LensMaturity.FORMAL,
            "Define payoff assumptions and response set explicitly.",
            minimum=2,
        ),
        _r(
            "emergent_cooperation", LensFamily.GAME, SemanticRole.SOCIAL if hasattr(SemanticRole, "SOCIAL") else SemanticRole.INTERPRETATION, 1980,
            "Model cooperation that emerges from repeated incentives without a scripted alliance state.",
            ("cooperate", "team", "repeat", "trust", "reciprocal", "share"),
            ("Can repeated interaction support cooperation without a hard-coded coalition?",),
            "Longer expected interaction or stronger reciprocity should increase stable cooperation in suitable payoff regimes.",
            "Treating any coordinated action as emergent cooperation.",
            ("repeated games", "evolution of cooperation"), LensMaturity.FORMAL,
            "Verify incentive and repetition structure before inferring an emergent equilibrium.",
            minimum=3, sequential=True,
        ),
        _r(
            "resource_denial", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1970,
            "Interpret actions that reduce an opponent's options even when they do not directly increase own resources.",
            ("deny", "block", "resource", "starve", "control", "access"),
            ("Is value coming from own gain, opponent loss, or both?",),
            "When denial matters, players should contest resources whose opponent marginal value exceeds their own direct use value.",
            "Labeling ordinary competition as denial strategy.",
            ("zero-sum games", "strategy games"), LensMaturity.MIXED,
            "Estimate both own-use and denial value before classifying the move.",
            minimum=2, pairwise=True,
        ),
        _r(
            "skill_floor_ceiling", LensFamily.GAME, SemanticRole.META, 1990,
            "Separate how hard a mechanic is to use minimally from how much mastery it continues to reward.",
            ("skill floor", "skill ceiling", "easy", "master", "depth", "mechanic"),
            ("What competence is needed for basic value, and what additional performance remains available to experts?",),
            "A low floor/high ceiling mechanic predicts fast initial adoption with persistent expert differentiation.",
            "Equating complexity with skill ceiling or accessibility with low depth.",
            ("game design", "expertise research"), LensMaturity.HEURISTIC,
            "Measure performance distributions rather than relying on designer intuition alone.",
            minimum=2,
        ),
    )


def research_semantic_specs() -> tuple[SemanticLensSpec, ...]:
    return tuple(item.spec for item in research_semantic_definitions())


def register_research_lenses(
    registry: SemanticLensRegistry,
    *,
    ignore_existing: bool = True,
) -> SemanticLensRegistry:
    if not isinstance(registry, SemanticLensRegistry):
        raise TypeError("registry must be SemanticLensRegistry")
    existing = {item.key for item in registry.all()}
    for definition in research_semantic_definitions():
        if definition.spec.key in existing:
            if ignore_existing:
                continue
            raise AgentContractError(f"duplicate research semantic lens: {definition.spec.key}")
        registry.register(definition.spec)
        existing.add(definition.spec.key)
    return registry


def research_definitions_by_family(
    definitions: Iterable[RareLensDefinition] | None = None,
) -> dict[LensFamily, tuple[RareLensDefinition, ...]]:
    items = tuple(definitions or research_semantic_definitions())
    grouped: dict[LensFamily, list[RareLensDefinition]] = {}
    for item in items:
        grouped.setdefault(item.spec.family, []).append(item)
    return {
        family: tuple(sorted(values, key=lambda item: (item.spec.lineage_year, item.spec.key)))
        for family, values in grouped.items()
    }


def research_catalog_fingerprint() -> str:
    return stable_fingerprint(
        {
            "version": CATALOG_VERSION,
            "definitions": [
                {
                    "key": item.spec.key,
                    "family": item.spec.family.value,
                    "role": item.spec.role.value,
                    "year": item.spec.lineage_year,
                    "lineage": item.lineage,
                    "maturity": item.maturity.value,
                    "warning": item.transfer_warning,
                }
                for item in research_semantic_definitions()
            ],
        }
    )
