"""Frontier semantic lenses and cross-lens composition for Jeeves.

This module extends :mod:`semantic_lenses` with rarer but useful interpretive
operators from cinema/editing, narratology/rhetoric, and game studies.  These
operators are *hypothesis generators*, never evidence generators.

Scientific boundary
-------------------
A lens may:
* select observations worth comparing;
* propose an interpretation or counter-reading;
* generate a falsifiable prediction;
* create a tangent for later investigation.

A lens may not:
* manufacture an observation;
* increase source trust merely because a reading is coherent;
* turn an aesthetic/semantic interpretation into causal evidence;
* collapse genuinely incompatible readings by averaging them.

Cross-lens composition is explicit.  Interactions state whether two lenses
reinforce, condition, reframe, conflict, remain orthogonal, or create a new
research tangent.  This keeps nuance visible to planning and prediction while
preserving epistemic provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .semantic_deep_lenses import deep_semantic_lenses
from .semantic_lenses import (
    LensFamily,
    LensSelection,
    ReadingStatus,
    SemanticFinding,
    SemanticLensRegistry,
    SemanticLensRouter,
    SemanticLensSpec,
    SemanticObservation,
    SemanticRole,
    TangentSeed,
)
from .types import AgentContractError, bounded_text, json_safe, positive_int, probability, stable_fingerprint, stable_id


class LensInteractionKind(str, Enum):
    REINFORCES = "reinforces"
    CONFLICTS = "conflicts"
    CONDITIONS = "conditions"
    REFRAMES = "reframes"
    ORTHOGONAL = "orthogonal"
    GENERATES_TANGENT = "generates_tangent"


@dataclass(frozen=True, slots=True)
class LensInteractionRule:
    left_key: str
    right_key: str
    kind: LensInteractionKind
    rationale: str
    question: str
    predictive_effect: str
    symmetric: bool = True
    tangent_axis_hint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "left_key", str(self.left_key).strip().casefold())
        object.__setattr__(self, "right_key", str(self.right_key).strip().casefold())
        if not self.left_key or not self.right_key or self.left_key == self.right_key:
            raise AgentContractError("lens interaction requires two distinct keys")
        if not isinstance(self.kind, LensInteractionKind):
            object.__setattr__(self, "kind", LensInteractionKind(str(self.kind)))
        object.__setattr__(self, "rationale", bounded_text("interaction rationale", self.rationale, maximum=4096))
        object.__setattr__(self, "question", bounded_text("interaction question", self.question, maximum=4096))
        object.__setattr__(self, "predictive_effect", bounded_text("predictive effect", self.predictive_effect, maximum=4096))
        if self.tangent_axis_hint is not None:
            object.__setattr__(self, "tangent_axis_hint", str(self.tangent_axis_hint).strip().casefold())

    @property
    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_key, self.right_key))) if self.symmetric else (self.left_key, self.right_key)


@dataclass(frozen=True, slots=True)
class LensInteraction:
    interaction_id: str
    rule: LensInteractionRule
    left_finding_id: str
    right_finding_id: str
    observation_ids: tuple[str, ...]
    confidence: float
    ambiguity: float
    evidence_ids: tuple[str, ...]
    hypothesis: str
    counter_hypothesis: str
    tangent: TangentSeed | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "interaction_id", str(self.interaction_id).strip())
        if not self.interaction_id:
            raise AgentContractError("interaction_id is required")
        object.__setattr__(self, "confidence", probability("interaction confidence", self.confidence))
        object.__setattr__(self, "ambiguity", probability("interaction ambiguity", self.ambiguity))
        object.__setattr__(self, "observation_ids", tuple(sorted({str(x) for x in self.observation_ids if str(x)})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "hypothesis", bounded_text("interaction hypothesis", self.hypothesis, maximum=8192))
        object.__setattr__(self, "counter_hypothesis", bounded_text("counter hypothesis", self.counter_hypothesis, maximum=8192, allow_empty=True))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "rule": self.rule.key,
                "kind": self.rule.kind.value,
                "left": self.left_finding_id,
                "right": self.right_finding_id,
                "observations": self.observation_ids,
                "evidence": self.evidence_ids,
                "hypothesis": self.hypothesis,
                "counter": self.counter_hypothesis,
            }
        )


@dataclass(frozen=True, slots=True)
class SemanticComposition:
    finding_ids: tuple[str, ...]
    interactions: tuple[LensInteraction, ...]
    unresolved_conflicts: tuple[str, ...]
    tangent_seeds: tuple[TangentSeed, ...]
    families: tuple[LensFamily, ...]
    fingerprint: str


def _lens(
    key: str,
    family: LensFamily,
    role: SemanticRole,
    year: int,
    description: str,
    cues: Sequence[str],
    asks: Sequence[str],
    predicts: str,
    failure: str,
    *,
    minimum: int = 1,
    pairwise: bool = False,
    sequential: bool = False,
    rare: bool = True,
) -> SemanticLensSpec:
    return SemanticLensSpec(
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
        rare=rare,
    )


def frontier_semantic_lenses() -> tuple[SemanticLensSpec, ...]:
    """Additional rare lenses deliberately orthogonal to the base catalog.

    ``lineage_year`` is an orientation marker, not an assertion that a modern
    formalization was invented in exactly that year.
    """

    return (
        # --- Cinema: montage, continuity, staging, sound and viewpoint ---
        _lens("metric_montage", LensFamily.FILM, SemanticRole.STRUCTURE, 1929,
              "Read cut duration itself as a structural variable independent of depicted content.",
              ("cut", "duration", "pace", "tempo", "shot", "length"),
              ("Does changing shot length alone alter perceived pressure or emphasis?",),
              "Regular shortening or lengthening of cuts predicts a change in perceived intensity.",
              "Inferring emotion from duration without controlling content.", minimum=3, sequential=True),
        _lens("rhythmic_montage", LensFamily.FILM, SemanticRole.STRUCTURE, 1929,
              "Combine cut timing with movement inside the frame to model audiovisual rhythm.",
              ("rhythm", "movement", "motion", "cut", "pace", "beat"),
              ("Do internal motion and edit timing reinforce or resist each other?",),
              "Alignment of motion and cuts predicts stronger temporal grouping than either cue alone.",
              "Treating any repeated timing as meaningful rhythm.", minimum=3, sequential=True),
        _lens("tonal_montage", LensFamily.FILM, SemanticRole.CONTEXTUALIZATION, 1929,
              "Track the dominant affective or perceptual tone distributed across a sequence.",
              ("tone", "mood", "light", "texture", "affect", "atmosphere"),
              ("Which properties jointly create the sequence's dominant tone?",),
              "A stable tonal field changes priors over how an ambiguous adjacent shot is read.",
              "Projecting an assumed mood onto neutral evidence.", minimum=2, sequential=True),
        _lens("overtonal_montage", LensFamily.FILM, SemanticRole.META, 1929,
              "Model emergent meaning from the interaction of metric, rhythmic and tonal structure.",
              ("overtonal", "combined", "layered", "rhythm", "tone", "pace"),
              ("Does the interaction of timing, motion, and tone explain more than any one layer?",),
              "Converging edit layers predict a stronger contextual effect than isolated cues.",
              "Calling a vague accumulation of cues an emergent effect without comparison.", minimum=3, sequential=True),
        _lens("intellectual_montage", LensFamily.FILM, SemanticRole.INTERPRETATION, 1929,
              "Juxtaposed concrete images can propose an abstract relation, metaphor, or argument.",
              ("metaphor", "idea", "abstract", "collision", "juxtaposition", "argument"),
              ("What abstract relation is only available from A beside B?", "What observation would falsify that relation?"),
              "Repeated use of the same image relation predicts a stable abstract association.",
              "Treating a critic's metaphor as an objective property of either image.", minimum=2, pairwise=True),
        _lens("montage_of_attractions", LensFamily.FILM, SemanticRole.PREDICTION, 1923,
              "Treat salient shocks or attractions as deliberately sequenced attention interventions.",
              ("shock", "attraction", "spectacle", "interrupt", "attention", "impact"),
              ("Which element is designed to redirect attention or response?",),
              "A salient interruption predicts a short-horizon shift in attention or interpretation.",
              "Equating salience with authorial intention.", minimum=2, sequential=True),
        _lens("eyeline_inference", LensFamily.FILM, SemanticRole.CAUSAL_HINT, 1910,
              "Infer candidate gaze targets from ordered look/object shots while retaining ambiguity.",
              ("look", "gaze", "eyeline", "sees", "object", "pov"),
              ("Is the second shot actually licensed as the gaze target?",),
              "Stable look-target ordering predicts a relational interpretation between shots.",
              "Converting editing grammar into proof that a character literally saw the object.", minimum=2, pairwise=True),
        _lens("reaction_shot_inference", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1910,
              "Use a reaction shot as evidence about interpretation of an event, not the event itself.",
              ("reaction", "face", "response", "after", "sees", "hears"),
              ("Does the reaction constrain the event, the character belief, or merely audience framing?",),
              "Repeated reaction patterns predict a character-specific response model.",
              "Using a reaction as direct evidence for the hidden cause.", minimum=2, pairwise=True),
        _lens("match_on_action", LensFamily.FILM, SemanticRole.STRUCTURE, 1910,
              "Continuity can be constructed by preserving an action trajectory across a cut.",
              ("action", "cut", "continues", "motion", "match", "continuity"),
              ("Which state variable persists across the edit?",),
              "Matched action predicts continuity of event identity despite viewpoint change.",
              "Assuming continuity when a deceptive match hides a state change.", minimum=2, pairwise=True),
        _lens("long_take_counterlens", LensFamily.FILM, SemanticRole.ADVERSARIAL_READING, 1940,
              "Counter montage-based readings by testing what continuous duration preserves without cuts.",
              ("long take", "continuous", "uncut", "duration", "staging", "real time"),
              ("Would the interpretation survive if no juxtaposing cut supplied it?",),
              "Meaning that persists through continuous observation is less dependent on edit adjacency.",
              "Treating long takes as unmediated reality.", minimum=2, sequential=True),
        _lens("deep_focus_relations", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1941,
              "Treat simultaneous foreground/background information as competing or co-present semantic channels.",
              ("foreground", "background", "depth", "focus", "simultaneous", "frame"),
              ("What relation is visible because multiple depth planes remain legible together?",),
              "Co-present actions predict interpretations that need not depend on edit order.",
              "Assuming equal perceptual importance for every depth plane.", minimum=2),
        _lens("blocking_proxemics", LensFamily.FILM, SemanticRole.SOCIAL if hasattr(SemanticRole, "SOCIAL") else SemanticRole.INTERPRETATION, 1950,
              "Use spatial arrangement, distance and movement as hypotheses about social relation.",
              ("distance", "near", "far", "blocking", "position", "space"),
              ("Does spatial relation change systematically with interaction state?",),
              "Stable changes in distance or position predict changes in relational stance.",
              "Equating physical distance with emotion across cultures and contexts."),
        _lens("rack_focus_attention", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1930,
              "Treat a focus shift as an attention transition between co-present candidates.",
              ("focus", "blur", "sharp", "attention", "shift", "foreground"),
              ("What becomes newly relevant when focus transfers?",),
              "Focus transfer predicts a change in narrative attention, not necessarily causal importance.",
              "Treating focus priority as factual importance.", minimum=2, sequential=True),
        _lens("sound_bridge", LensFamily.FILM, SemanticRole.STRUCTURE, 1930,
              "A sound crossing an edit can connect otherwise discontinuous visual segments.",
              ("sound", "continues", "bridge", "audio", "cut", "transition"),
              ("Does audio continuity imply temporal, spatial, thematic, or merely editorial linkage?",),
              "Persistent audio increases the prior for a meaningful relation across the visual transition.",
              "Assuming shared sound proves shared time or place.", minimum=2, pairwise=True),
        _lens("acousmatic_source", LensFamily.FILM, SemanticRole.PREDICTION, 1950,
              "An audible but unseen source creates a hidden-source inference problem.",
              ("unseen", "voice", "sound", "source", "offscreen", "heard"),
              ("Which candidate hidden source best explains the sound?",),
              "Subsequent reveal should discriminate among hidden-source hypotheses.",
              "Inventing a source without preserving alternatives.", rare=True),
        _lens("leitmotif_association", LensFamily.FILM, SemanticRole.PREDICTION, 1876,
              "Repeated audiovisual motifs can become probabilistic cues for entities, states or themes.",
              ("motif", "theme", "music", "returns", "cue", "associated"),
              ("Does the motif predict an entity/state beyond chance recurrence?",),
              "A learned motif increases the prior of its associated state when it recurs.",
              "Treating one co-occurrence as a stable motif.", minimum=3, sequential=True),
        _lens("subjective_camera", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1920,
              "Model image content as potentially filtered by an embodied or unreliable viewpoint.",
              ("subjective", "pov", "vision", "dream", "hallucination", "camera"),
              ("Is this a world-state observation or a viewpoint-conditioned presentation?",),
              "Viewpoint-conditioned anomalies predict disagreement with independent observations.",
              "Dismissing inconvenient visual evidence as subjective without cues.", rare=True),
        _lens("frame_within_frame", LensFamily.FILM, SemanticRole.META, 1940,
              "Nested visual frames can mark observation, mediation, surveillance, or constrained access.",
              ("frame", "window", "screen", "mirror", "within", "surveillance"),
              ("Who observes whom through which mediating boundary?",),
              "Nested framing predicts an information-access asymmetry or reflexive relation.",
              "Assigning symbolic intent to ordinary architecture.", rare=True),

        # --- Literature / narratology / rhetoric ---
        _lens("vertical_metalepsis", LensFamily.NARRATIVE, SemanticRole.META, 1972,
              "Detect transgression between the level of telling and the world being told.",
              ("narrator", "story", "enters", "addresses", "author", "character", "level"),
              ("Which narrative boundary is crossed, and in which direction?",),
              "Boundary-crossing cues predict altered rules of reference or agency across narrative levels.",
              "Treating ordinary address or quotation as an ontological boundary crossing.", minimum=2, rare=True),
        _lens("descending_metalepsis", LensFamily.NARRATIVE, SemanticRole.META, 1972,
              "Model a teller/author-level entity entering or acting inside the represented story world.",
              ("author", "narrator", "enters", "story", "world", "character"),
              ("Did an entity from the telling level acquire agency in the told level?",),
              "If genuine, later events may violate previously stable narrative-level constraints.",
              "Confusing figurative authorial presence with diegetic agency.", minimum=2, rare=True),
        _lens("ascending_metalepsis", LensFamily.NARRATIVE, SemanticRole.META, 1972,
              "Model a story-level entity addressing or affecting the telling/reader level.",
              ("reader", "audience", "narrator", "character", "breaks", "fourth wall"),
              ("Did a diegetic entity gain access to an outer narrative level?",),
              "If genuine, reference and agency rules should differ from ordinary intradiegetic action.",
              "Calling every direct address a literal boundary crossing.", minimum=2, rare=True),
        _lens("fabula_syuzhet", LensFamily.NARRATIVE, SemanticRole.TEMPORAL if hasattr(SemanticRole, "TEMPORAL") else SemanticRole.STRUCTURE, 1925,
              "Separate inferred event chronology from presentation order.",
              ("order", "chronology", "reveal", "flashback", "sequence", "event"),
              ("What is the minimal event order consistent with the presented order?",),
              "Reconstructed event order should improve causal consistency without erasing uncertainty.",
              "Forcing one chronology when multiple event orders remain possible.", minimum=3, sequential=True),
        _lens("chronotope", LensFamily.LITERATURE, SemanticRole.CONTEXTUALIZATION, 1937,
              "Treat recurrent configurations of time and space as constraints on action and meaning.",
              ("place", "time", "road", "threshold", "home", "journey", "setting"),
              ("Which time-space configuration repeatedly enables the same class of events?",),
              "Returning to a stable chronotope predicts a similar affordance/constraint structure.",
              "Reducing every setting to a symbolic template.", minimum=2, sequential=True),
        _lens("heteroglossia", LensFamily.LITERATURE, SemanticRole.INTERPRETATION, 1934,
              "Track socially distinct registers or voices without collapsing them into one semantic authority.",
              ("register", "voice", "dialect", "jargon", "official", "slang", "speech"),
              ("Which social perspective is carried by each register?",),
              "Register shifts predict changes in stance, audience, or authority.",
              "Inferring identity or intent from dialect alone.", minimum=2, rare=True),
        _lens("paratext_frame", LensFamily.LITERATURE, SemanticRole.CONTEXTUALIZATION, 1987,
              "Titles, epigraphs, labels, metadata and framing material can alter priors before core content is read.",
              ("title", "subtitle", "epigraph", "preface", "caption", "label", "metadata"),
              ("Which expectation is supplied by the frame rather than the body?",),
              "Changing the paratext should change interpretation priors while leaving body evidence unchanged.",
              "Treating framing as proof of the framed claim.", pairwise=True, rare=True),
        _lens("mise_en_abyme", LensFamily.LITERATURE, SemanticRole.META, 1893,
              "A work or structure nested within itself can expose recursive or self-modeling relations.",
              ("story within", "nested", "mirror", "self", "recursive", "miniature"),
              ("Does the inner structure model, distort, or comment on the outer structure?",),
              "Inner/outer correspondences predict recursive themes or control relations.",
              "Calling any nested content a meaningful self-model.", minimum=2, rare=True),
        _lens("ekphrasis_cross_modal", LensFamily.LITERATURE, SemanticRole.INTERPRETATION, 1700,
              "Treat verbal description of another medium as a transformation with possible information loss or reframing.",
              ("describes", "painting", "image", "music", "scene", "picture"),
              ("What survives, disappears, or is added in the cross-modal description?",),
              "Systematic additions/omissions predict the describer's interpretive priorities.",
              "Assuming verbal description faithfully reconstructs the source.", rare=True),
        _lens("implied_reader", LensFamily.LITERATURE, SemanticRole.PERSPECTIVE, 1974,
              "Infer the competencies and expectations presupposed by a text, without equating them with an actual user.",
              ("assumes", "reader", "you", "obvious", "reference", "expects"),
              ("What knowledge or norm must a reader possess for this move to work?",),
              "Repeated presuppositions predict what later explanations will be omitted or foregrounded.",
              "Projecting the inferred reader model onto the real user.", rare=True),
        _lens("unreliable_memory", LensFamily.LITERATURE, SemanticRole.ADVERSARIAL_READING, 1900,
              "Separate source sincerity from memory reliability when a report is retrospective.",
              ("remember", "recall", "forgot", "years ago", "memory", "uncertain"),
              ("Could the source be sincere yet wrong because memory was reconstructed?",),
              "Independent records may diverge systematically from retrospective detail while broad gist survives.",
              "Treating all remembered details as suspect merely because they are old."),
        _lens("apophasis", LensFamily.RHETORIC, SemanticRole.META, 100,
              "Mentioning something while claiming not to mention it can make the omitted topic salient.",
              ("not mention", "needless to say", "won't discuss", "without saying", "not to mention"),
              ("What information is introduced through ostensible omission?",),
              "The ostensibly excluded topic predicts subsequent attention or framing.",
              "Assuming every disclaimer is strategic insinuation.", rare=True),
        _lens("aposiopesis", LensFamily.RHETORIC, SemanticRole.PREDICTION, 100,
              "A deliberately broken-off utterance can leave a constrained but unresolved completion set.",
              ("...", "stops", "trails off", "if you", "or else", "unfinished"),
              ("Which completions are licensed, and which remain unsupported?",),
              "Later context may select among a small set of implied completions.",
              "Filling the omission with the most dramatic completion.", rare=True),
        _lens("chiasmus_reversal", LensFamily.RHETORIC, SemanticRole.STRUCTURE, -400,
              "AB/BA reversal can expose contrast, reciprocity, or conceptual inversion.",
              ("reverse", "inversion", "rather", "not", "but", "order"),
              ("Does structural reversal encode a semantic reversal or only style?",),
              "Repeated AB/BA structure predicts deliberate contrast between paired concepts.",
              "Treating syntactic symmetry as logical equivalence.", pairwise=True, rare=True),
        _lens("parataxis_hypotaxis", LensFamily.RHETORIC, SemanticRole.CAUSAL_HINT, 1900,
              "Distinguish mere adjacency from explicitly subordinated causal/temporal relation.",
              ("and", "because", "therefore", "while", "then", "since"),
              ("Is relation asserted grammatically, merely sequenced, or inferred by the reader?",),
              "Explicit subordination warrants a stronger relational prior than bare adjacency.",
              "Reading causal force into paratactic sequence.", minimum=2, pairwise=True),
        _lens("isotopy_recurrence", LensFamily.SEMIOTIC, SemanticRole.INTERPRETATION, 1966,
              "Repeated semantic features across different expressions can establish a coherent reading path.",
              ("semantic", "recurs", "field", "theme", "pattern", "same meaning"),
              ("Which semantic feature recurs despite lexical variation?",),
              "A stable semantic recurrence predicts interpretation of later ambiguous terms in the same field.",
              "Manufacturing a semantic field from generic vocabulary.", minimum=3, sequential=True, rare=True),

        # --- Games: formal system, enacted play, information and incentives ---
        _lens("procedural_rhetoric", LensFamily.GAME, SemanticRole.INTERPRETATION, 2007,
              "Treat rules and executable processes as possible arguments about how a modeled system works.",
              ("rule", "process", "simulation", "procedure", "system", "message"),
              ("What claim is implied by what the rules permit, reward, or forbid?",),
              "Changing a rule should change the implied procedural claim if that claim is genuinely rule-borne.",
              "Assuming formal rules exhaust a game's meaning.", minimum=2),
        _lens("player_enactment_counterlens", LensFamily.GAME, SemanticRole.ADVERSARIAL_READING, 2011,
              "Counter formalist readings by modeling player appropriation, creative play and social enactment.",
              ("player", "appropriation", "creative", "breaks", "social", "play", "improvised"),
              ("What meaning or practice appears in actual play that is not encoded by the intended procedure?",),
              "Observed player practices can diverge from designer-intended procedural meaning.",
              "Treating any rule-breaking as evidence against the rule system.", minimum=2),
        _lens("possibility_space", LensFamily.GAME, SemanticRole.SYSTEM, 2007,
              "Represent the reachable configurations and actions induced by rules rather than only the chosen path.",
              ("possible", "reachable", "rules", "actions", "space", "configuration"),
              ("What can be done, what cannot, and which possibilities are merely undiscovered?",),
              "Changes to constraints alter the reachable state/action set even before behavior changes.",
              "Equating formal possibility with perceived or practically achievable action."),
        _lens("simulation_gap", LensFamily.GAME, SemanticRole.ADVERSARIAL_READING, 2003,
              "Compare source-world assumptions with what a simulation includes, excludes, or simplifies.",
              ("simulation", "model", "omits", "simplifies", "real", "representation"),
              ("Which causal variables or actions are absent from the simulation?",),
              "Behavior depending on omitted variables will fail to transport from simulation to target domain.",
              "Demanding perfect realism from a deliberately abstract model.", minimum=2),
        _lens("meaningful_play_feedback", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 2004,
              "Test whether action-outcome relations are discernible and integrated into the larger system.",
              ("feedback", "outcome", "action", "response", "consequence", "legible"),
              ("Can the player infer which action caused which consequence?",),
              "More legible feedback predicts faster policy adaptation and fewer mistaken causal attributions.",
              "Assuming immediate feedback is always desirable or truthful.", minimum=2, sequential=True),
        _lens("diegetic_interface", LensFamily.GAME, SemanticRole.PERSPECTIVE, 2000,
              "Distinguish information available inside the game world from interface-only information available to the player.",
              ("hud", "interface", "diegetic", "character", "player knows", "map"),
              ("Who has access to this information: avatar, player, both, or neither?",),
              "Behavior can diverge when player information exceeds character information.",
              "Assuming UI information is available to in-world agents."),
        _lens("sequence_break", LensFamily.GAME, SemanticRole.ADVERSARIAL_READING, 1990,
              "Detect player routes that bypass the intended progression graph while remaining mechanically valid.",
              ("skip", "sequence break", "speedrun", "bypass", "route", "exploit"),
              ("Which dependency was assumed by design but not enforced by mechanics?",),
              "A reproducible bypass predicts other reachable states outside intended progression order.",
              "Calling every alternate route an exploit.", minimum=2, sequential=True, rare=True),
        _lens("hidden_role_epistemics", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1986,
              "Maintain beliefs over hidden roles using claims, actions and strategically generated misinformation.",
              ("role", "traitor", "hidden", "claim", "vote", "suspect", "deceive"),
              ("Which observations are endogenous to strategic deception?",),
              "Role posterior should update on behavior while discounting strategically manipulable signals.",
              "Treating statements as independent observations.", minimum=2, rare=True),
        _lens("signaling_game", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1973,
              "Separate actor type, chosen signal, receiver belief and receiver response.",
              ("signal", "type", "bluff", "credible", "costly", "response"),
              ("Would different hidden types rationally choose different signals?",),
              "Costly or type-dependent signals can shift receiver beliefs more than cheap talk.",
              "Assuming observed signals are honest or equilibrated.", minimum=2, pairwise=True),
        _lens("information_set", LensFamily.GAME, SemanticRole.PERSPECTIVE, 1944,
              "Evaluate an action using states the actor could distinguish at decision time, not hindsight state.",
              ("information", "hidden", "decision", "knew", "state", "choice"),
              ("Which world states were observationally equivalent to the actor then?",),
              "A policy should map an information set, not privileged true state, to action.",
              "Judging a decision with information unavailable when it was made."),
        _lens("counterfactual_regret", LensFamily.GAME, SemanticRole.META, 2000,
              "Track regret for actions at information sets under counterfactual reach, useful for imperfect-information strategy analysis.",
              ("regret", "counterfactual", "strategy", "information set", "policy", "reach"),
              ("Which local action would have improved value if this information set were reached?",),
              "Persistent positive counterfactual regret predicts strategy mass shifting toward that action.",
              "Applying CFR semantics to non-strategic or nonstationary data without a game model.", rare=True),
        _lens("mechanism_design_incentives", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 1960,
              "Ask whether rules make truthful/cooperative behavior individually rational under modeled incentives.",
              ("incentive", "truthful", "mechanism", "reward", "strategy", "auction", "cooperate"),
              ("Can an actor profitably misreport, defect, or manipulate the rule?",),
              "If a profitable deviation exists and is discoverable, observed play should eventually exploit it.",
              "Assuming agents are perfectly rational or share the modeled utility."),
        _lens("common_knowledge_coordination", LensFamily.GAME, SemanticRole.SOCIAL if hasattr(SemanticRole, "SOCIAL") else SemanticRole.PERSPECTIVE, 1976,
              "Distinguish private knowledge, shared knowledge and common knowledge in coordination problems.",
              ("everyone knows", "common", "coordinate", "signal", "team", "shared"),
              ("Is the fact merely shared, or does each actor know that others know it?",),
              "Public signals can unlock coordination unavailable under equivalent private observations.",
              "Treating identical private information as common knowledge.", minimum=2, rare=True),
        _lens("rubber_band_dynamics", LensFamily.GAME, SemanticRole.SYSTEM, 1990,
              "Detect state-dependent assistance or penalties that compress performance differences.",
              ("catch up", "rubber band", "behind", "leader", "boost", "balancing"),
              ("Does transition/reward behavior depend on relative rank rather than absolute state?",),
              "Conditional assistance predicts mean reversion in performance gaps beyond baseline dynamics.",
              "Mistaking ordinary regression to the mean for a designed catch-up mechanism.", minimum=3, sequential=True, rare=True),
        _lens("roguelike_run_meta", LensFamily.GAME, SemanticRole.STRUCTURE, 1980,
              "Separate transient run state from persistent meta-progression across repeated runs.",
              ("run", "reset", "meta", "unlock", "persistent", "seed", "roguelike"),
              ("Which variables reset, which persist, and which alter future transition distributions?",),
              "Persistent unlocks predict nonstationarity across nominally fresh runs.",
              "Pooling runs as IID when meta-state changes between them.", minimum=2, sequential=True),
        _lens("procedural_seed_regime", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 1980,
              "Treat generation seed and generator version as latent regime variables for procedural worlds.",
              ("seed", "generated", "procedural", "version", "map", "random"),
              ("Are repeated outcomes conditionally dependent on a shared seed/regime?",),
              "Holding seed/version fixed should reproduce structural regularities more strongly than marginal sampling.",
              "Attributing all recurrence to the seed when generator state has other inputs.", rare=True),
        _lens("constraint_propagation_puzzle", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 1970,
              "Model puzzle progress as propagation of constraints across a candidate state space.",
              ("constraint", "puzzle", "candidate", "eliminate", "must", "cannot"),
              ("Which assignment removes the most inconsistent candidate states?",),
              "High-information constraints should sharply reduce the feasible set.",
              "Treating heuristic plausibility as a hard constraint."),
        _lens("false_affordance", LensFamily.GAME, SemanticRole.ADVERSARIAL_READING, 2000,
              "Detect actions suggested by representation but unavailable or nonfunctional in the actual mechanics.",
              ("looks", "should", "can't", "button", "door", "interaction", "affordance"),
              ("Is the perceived action actually represented in the transition model?",),
              "Repeated false affordances predict systematic user errors or frustration at the same cue class.",
              "Assuming every unavailable action is a design defect."),
        _lens("griefing_adversarial_play", LensFamily.GAME, SemanticRole.ADVERSARIAL_READING, 1990,
              "Model actors optimizing for disruption, attention or others' loss rather than nominal game reward.",
              ("grief", "troll", "disrupt", "sabotage", "harass", "ruin"),
              ("Does behavior make sense under a utility that includes others' loss or disruption?",),
              "Nominally irrational moves become predictable under an adversarial social utility model.",
              "Pathologizing unconventional play without evidence of adversarial intent.", rare=True),
    )


class FrontierSemanticRegistry(SemanticLensRegistry):
    """Base semantic catalog plus rare frontier lenses."""

    def __init__(self, extra: Iterable[SemanticLensSpec] = ()) -> None:
        super().__init__()
        for spec in frontier_semantic_lenses():
            self.register(spec)
        for spec in deep_semantic_lenses():
            self.register(spec)
        for spec in extra:
            self.register(spec)


class FrontierLensRouter(SemanticLensRouter):
    """Diversity-preserving router with bounded rare-lens representation."""

    def __init__(self, registry: FrontierSemanticRegistry | None = None) -> None:
        super().__init__(registry or FrontierSemanticRegistry())

    def select_frontier(
        self,
        observations: Sequence[SemanticObservation],
        *,
        requested: Sequence[str] = (),
        max_lenses: int = 18,
        max_per_family: int = 4,
        minimum_rare_when_supported: int = 2,
    ) -> LensSelection:
        maximum = positive_int("max_lenses", max_lenses, maximum=100)
        rare_min = positive_int("minimum_rare_when_supported", minimum_rare_when_supported, maximum=20)
        base = self.select(
            observations,
            requested=requested,
            max_lenses=maximum,
            max_per_family=max_per_family,
            perpendicular=True,
        )
        selected = list(base.lenses)
        selected_keys = {spec.key for spec in selected}
        rare_count = sum(spec.rare for spec in selected)
        if rare_count >= rare_min or len(selected) >= maximum:
            return base

        # Only promote rare lenses that have nontrivial lexical/cue support.  Do
        # not force exotic interpretations merely to hit a quota.
        text = " ".join(obs.content + " " + " ".join(obs.tags) for obs in observations).casefold()
        candidates: list[tuple[float, SemanticLensSpec]] = []
        for spec in self.registry.all():
            if not spec.rare or spec.key in selected_keys or len(observations) < spec.minimum_observations:
                continue
            matched = sum(1 for cue in spec.activation_cues if cue in text)
            if matched <= 0:
                continue
            support = matched / max(1, len(spec.activation_cues))
            candidates.append((support, spec))
        candidates.sort(key=lambda item: (-item[0], item[1].family.value, item[1].key))
        for score, spec in candidates:
            if len(selected) >= maximum or rare_count >= rare_min:
                break
            selected.append(spec)
            selected_keys.add(spec.key)
            rare_count += 1
        scores = dict(base.activation_scores)
        for score, spec in candidates:
            if spec.key in selected_keys:
                scores.setdefault(spec.key, min(1.0, 0.25 + score))
        return LensSelection(
            lenses=tuple(selected),
            activation_scores=scores,
            families=tuple(sorted({spec.family for spec in selected}, key=lambda family: family.value)),
            perpendicular=True,
        )


def default_interaction_rules() -> tuple[LensInteractionRule, ...]:
    return (
        LensInteractionRule(
            "kuleshov_context", "unreliable_narrator", LensInteractionKind.CONDITIONS,
            "Context can alter interpretation while source reliability independently controls whether the report is trusted.",
            "Is the changed reading caused by adjacent context, source unreliability, or both?",
            "Predict context-sensitive judgments without upgrading narrator claims to facts.",
            tangent_axis_hint="semantic",
        ),
        LensInteractionRule(
            "montage_collision", "intellectual_montage", LensInteractionKind.REINFORCES,
            "Both lenses test meaning that emerges from juxtaposition rather than either item alone.",
            "Does the proposed abstract relation recur across independent juxtapositions?",
            "Repeated pair structure should improve prediction of the same abstract reading.",
            tangent_axis_hint="cinematic",
        ),
        LensInteractionRule(
            "procedural_rhetoric", "player_enactment_counterlens", LensInteractionKind.CONFLICTS,
            "Formal procedure and enacted play are distinct sources of meaning and can diverge.",
            "Do observed player practices reproduce, reinterpret, or reject the rule-implied message?",
            "A persistent rules/play gap predicts failure of purely procedural behavioral forecasts.",
            tangent_axis_hint="ludic",
        ),
        LensInteractionRule(
            "focalization", "fog_of_war_partial_observability", LensInteractionKind.REINFORCES,
            "Narrative focalization and game partial observability both constrain what an actor can know.",
            "Do the represented viewpoint and formal observation function expose the same information?",
            "Aligned access models should improve actor-policy prediction; mismatches predict dramatic/player irony.",
            tangent_axis_hint="semantic",
        ),
        LensInteractionRule(
            "genre_expectation", "defamiliarization", LensInteractionKind.CONFLICTS,
            "Genre supplies a prior while defamiliarization deliberately disrupts familiar expectations.",
            "Which prior is being violated, and is the violation stable enough to warrant updating the genre model?",
            "Early prediction error should rise, then fall if a new local convention becomes learnable.",
            tangent_axis_hint="probabilistic",
        ),
        LensInteractionRule(
            "vertical_metalepsis", "frame_within_frame", LensInteractionKind.REFRAMES,
            "Narrative-level transgression and visual nesting both mark boundaries, but only the former changes ontological level.",
            "Is the nested frame merely representational, or does agency/reference cross the boundary?",
            "True metalepsis predicts downstream rule changes that pure framing does not.",
            tangent_axis_hint="semantic",
        ),
        LensInteractionRule(
            "possibility_space", "affordance_action", LensInteractionKind.CONDITIONS,
            "Formal possibility and perceived/actionable affordance are not the same set.",
            "Which formally legal actions are invisible or impractical, and which perceived actions are false affordances?",
            "Behavior is better predicted by perceived feasible actions than by the full formal action set.",
            tangent_axis_hint="ludic",
        ),
        LensInteractionRule(
            "possibility_space", "false_affordance", LensInteractionKind.CONFLICTS,
            "A presented affordance may suggest an action that the formal transition system does not permit.",
            "Is the mismatch representational, implementation-specific, or intentionally deceptive?",
            "Repeated mismatch predicts user action errors at similar cues.",
            tangent_axis_hint="ludic",
        ),
        LensInteractionRule(
            "information_set", "dramatic_irony", LensInteractionKind.REINFORCES,
            "Both require evaluating action with actor-local information instead of observer hindsight.",
            "Which facts are available to the observer but absent from the actor's information set?",
            "Actor choices should track local beliefs even when an external observer knows they are mistaken.",
            tangent_axis_hint="probabilistic",
        ),
        LensInteractionRule(
            "simulation_gap", "causal_interventional" if False else "save_load_counterfactual", LensInteractionKind.CONDITIONS,
            "Controlled replay can estimate simulator effects, while a simulation gap limits transport to an external target.",
            "Does the counterfactual answer a within-simulator question or an external-world question?",
            "Within-simulator estimates may be precise while transport uncertainty remains high.",
            tangent_axis_hint="causal",
        ),
        LensInteractionRule(
            "paratext_frame", "kuleshov_context", LensInteractionKind.REINFORCES,
            "Both model context supplied outside the target content as a prior over interpretation.",
            "Does replacing the frame while holding content fixed alter the reading?",
            "A controlled frame swap should change interpretation if contextual framing is active.",
            tangent_axis_hint="semantic",
        ),
        LensInteractionRule(
            "unreliable_memory", "unreliable_narrator", LensInteractionKind.CONDITIONS,
            "A report can be inaccurate because memory reconstruction failed even when the narrator is sincere.",
            "Is divergence better explained by deception/bias, memory reconstruction, or independent source error?",
            "Error patterns tied to retention interval favor memory unreliability over stable deceptive intent.",
            tangent_axis_hint="memory",
        ),
        LensInteractionRule(
            "sequence_break", "possibility_space", LensInteractionKind.REINFORCES,
            "A sequence break demonstrates a reachable path omitted from the intended progression model.",
            "Which supposed dependency was conventional rather than mechanically enforced?",
            "Verified bypasses expand the learned reachable-state graph.",
            tangent_axis_hint="ludic",
        ),
        LensInteractionRule(
            "procedural_seed_regime", "roguelike_run_meta", LensInteractionKind.CONDITIONS,
            "Run outcomes may depend jointly on generated seed and persistent meta-state.",
            "Which variation is attributable to seed, generator version, or meta-progression?",
            "Conditioning on both seed regime and meta-state should reduce unexplained run variance.",
            tangent_axis_hint="probabilistic",
        ),
        LensInteractionRule(
            "parataxis_hypotaxis", "montage_collision", LensInteractionKind.ORTHOGONAL,
            "Linguistic subordination and visual juxtaposition encode relation through different channels.",
            "Do both channels support the same relation or does one merely invite it?",
            "Cross-channel agreement raises robustness of a relation hypothesis without making it causal proof.",
            tangent_axis_hint="semantic",
        ),
    )


class LensCompositionEngine:
    """Compose semantic findings without converting interpretations to evidence."""

    def __init__(self, rules: Iterable[LensInteractionRule] = ()) -> None:
        merged = [*default_interaction_rules(), *tuple(rules)]
        index: dict[tuple[str, str], LensInteractionRule] = {}
        directed: dict[tuple[str, str], LensInteractionRule] = {}
        for rule in merged:
            destination = index if rule.symmetric else directed
            if rule.key in destination:
                raise AgentContractError(f"duplicate lens interaction rule: {rule.key}")
            destination[rule.key] = rule
        self._symmetric = index
        self._directed = directed

    def rule_for(self, left_key: str, right_key: str) -> LensInteractionRule | None:
        left = str(left_key).casefold()
        right = str(right_key).casefold()
        return self._directed.get((left, right)) or self._symmetric.get(tuple(sorted((left, right))))

    def compose(self, findings: Sequence[SemanticFinding]) -> SemanticComposition:
        findings = tuple(findings)
        if any(not isinstance(item, SemanticFinding) for item in findings):
            raise TypeError("compose requires SemanticFinding values")
        interactions: list[LensInteraction] = []
        conflicts: list[str] = []
        tangent_seeds: list[TangentSeed] = []
        for i, left in enumerate(findings):
            for right in findings[i + 1 :]:
                rule = self.rule_for(left.lens_key, right.lens_key)
                if rule is None:
                    continue
                observations = tuple(sorted(set(left.observation_ids) | set(right.observation_ids)))
                evidence = tuple(sorted(set(left.evidence_ids) | set(right.evidence_ids)))
                confidence = min(left.confidence, right.confidence)
                ambiguity = max(left.ambiguity, right.ambiguity)
                hypothesis = (
                    f"{rule.kind.value}: {rule.rationale} Test: {rule.question} "
                    f"Prediction: {rule.predictive_effect}"
                )
                counter = ""
                if rule.kind is LensInteractionKind.CONFLICTS:
                    counter = (
                        "Preserve both readings until a discriminating observation resolves the conflict; "
                        "coherence alone is not evidence."
                    )
                interaction_id = stable_id(
                    "lens-interaction",
                    {
                        "rule": rule.key,
                        "kind": rule.kind.value,
                        "left": left.fingerprint,
                        "right": right.fingerprint,
                        "observations": observations,
                    },
                    length=28,
                )
                tangent = None
                if rule.kind in {LensInteractionKind.CONFLICTS, LensInteractionKind.GENERATES_TANGENT, LensInteractionKind.REFRAMES}:
                    tangent = TangentSeed(
                        seed_id=stable_id("semantic-tangent", {"interaction": interaction_id}, length=28),
                        parent_fingerprint=stable_fingerprint((left.fingerprint, right.fingerprint)),
                        lens_key=f"{left.lens_key}+{right.lens_key}",
                        direction=rule.question,
                        rationale=rule.rationale,
                        novelty=max(left.novelty, right.novelty),
                        expected_value=max(0.1, confidence * (1.0 - 0.5 * ambiguity)),
                        evidence_ids=evidence,
                        tags=("semantic-composition", rule.kind.value, rule.tangent_axis_hint or "semantic"),
                    )
                    tangent_seeds.append(tangent)
                interaction = LensInteraction(
                    interaction_id=interaction_id,
                    rule=rule,
                    left_finding_id=left.finding_id,
                    right_finding_id=right.finding_id,
                    observation_ids=observations,
                    confidence=confidence,
                    ambiguity=ambiguity,
                    evidence_ids=evidence,
                    hypothesis=hypothesis,
                    counter_hypothesis=counter,
                    tangent=tangent,
                    metadata={
                        "interpretive_only": True,
                        "may_promote_to_evidence": False,
                        "left_status": left.status.value,
                        "right_status": right.status.value,
                    },
                )
                interactions.append(interaction)
                if rule.kind is LensInteractionKind.CONFLICTS:
                    conflicts.append(interaction.interaction_id)

        families = tuple(sorted({item.family for item in findings}, key=lambda family: family.value))
        fingerprint = stable_fingerprint(
            {
                "findings": sorted(item.fingerprint for item in findings),
                "interactions": sorted(item.fingerprint for item in interactions),
                "conflicts": sorted(conflicts),
                "tangents": sorted(seed.seed_id for seed in tangent_seeds),
            }
        )
        return SemanticComposition(
            finding_ids=tuple(sorted(item.finding_id for item in findings)),
            interactions=tuple(interactions),
            unresolved_conflicts=tuple(sorted(conflicts)),
            tangent_seeds=tuple(tangent_seeds),
            families=families,
            fingerprint=fingerprint,
        )
