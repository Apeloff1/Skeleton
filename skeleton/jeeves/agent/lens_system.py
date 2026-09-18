"""High-dimensional semantic lens routing for Jeeves.

A lens is an interpretive operator, not a fact source.  The host can use lenses
to decide *how to inspect* evidence, memory, predictions, plans, narratives, or
games without allowing the lens itself to become evidence.

The catalog deliberately mixes mature scientific/statistical operators with
humanities/game-design heuristics.  Each definition carries an authority class
so downstream code can keep calibrated inference separate from interpretive
hypotheses.

The router is deterministic and cheap.  It is suitable for the first context
pass before expensive model calls.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .types import AgentContractError, bounded_text, json_safe, probability, stable_fingerprint, stable_id

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


class LensFamily(str, Enum):
    PROBABILITY = "probability"
    PREDICTIVE = "predictive"
    CAUSAL = "causal"
    INFORMATION = "information"
    MEMORY = "memory"
    SEMIOTIC = "semiotic"
    CINEMA = "cinema"
    LITERARY = "literary"
    LUDIC = "ludic"
    PRAGMATIC = "pragmatic"
    SOCIAL = "social"
    COMPUTATIONAL = "computational"
    METACOGNITIVE = "metacognitive"


class LensAuthority(str, Enum):
    """How strongly a lens may influence host decisions."""

    FORMAL = "formal"
    EMPIRICAL = "empirical"
    HEURISTIC = "heuristic"
    INTERPRETIVE = "interpretive"


@dataclass(frozen=True, slots=True)
class LensDefinition:
    lens_id: str
    name: str
    family: LensFamily
    authority: LensAuthority
    description: str
    cues: tuple[str, ...]
    outputs: tuple[str, ...]
    incompatible_with: tuple[str, ...] = ()
    preserves_source_truth: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lens_id", bounded_text("lens_id", self.lens_id, maximum=128))
        object.__setattr__(self, "name", bounded_text("lens name", self.name, maximum=256))
        if not isinstance(self.family, LensFamily):
            object.__setattr__(self, "family", LensFamily(str(self.family)))
        if not isinstance(self.authority, LensAuthority):
            object.__setattr__(self, "authority", LensAuthority(str(self.authority)))
        object.__setattr__(self, "description", bounded_text("lens description", self.description, maximum=4096))
        cues = tuple(sorted({str(value).casefold().strip() for value in self.cues if str(value).strip()}))
        outputs = tuple(str(value).strip() for value in self.outputs if str(value).strip())
        object.__setattr__(self, "cues", cues)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "incompatible_with", tuple(sorted({str(value) for value in self.incompatible_with})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class LensActivation:
    lens: LensDefinition
    score: float
    cue_score: float
    relation_score: float
    novelty_score: float
    matched_cues: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        for name in ("score", "cue_score", "relation_score", "novelty_score"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class LensBundle:
    query: str
    activations: tuple[LensActivation, ...]
    families: tuple[LensFamily, ...]
    fingerprint: str

    def ids(self) -> tuple[str, ...]:
        return tuple(value.lens.lens_id for value in self.activations)


@dataclass(frozen=True, slots=True)
class PerpendicularDirection:
    """A preserved side-direction that can be resumed after a restart."""

    direction_id: str
    parent_id: str | None
    axis: str
    hypothesis: str
    next_probe: str
    unresolved_questions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    priority: float = 0.5
    depth: int = 0
    status: str = "open"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction_id", bounded_text("direction_id", self.direction_id, maximum=256))
        if self.parent_id is not None:
            object.__setattr__(self, "parent_id", bounded_text("parent_id", self.parent_id, maximum=256))
        object.__setattr__(self, "axis", bounded_text("axis", self.axis, maximum=512))
        object.__setattr__(self, "hypothesis", bounded_text("hypothesis", self.hypothesis, maximum=8192))
        object.__setattr__(self, "next_probe", bounded_text("next_probe", self.next_probe, maximum=8192))
        object.__setattr__(self, "unresolved_questions", tuple(str(x)[:4096] for x in self.unresolved_questions))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x)[:256] for x in self.evidence_ids})))
        object.__setattr__(self, "priority", probability("priority", self.priority))
        if isinstance(self.depth, bool) or not isinstance(self.depth, int) or self.depth < 0:
            raise AgentContractError("depth must be a non-negative integer")
        object.__setattr__(self, "status", bounded_text("status", self.status, maximum=64))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class DirectionLedger:
    """Persistent-in-shape graph of mainline and orthogonal research directions."""

    def __init__(self, *, maximum: int = 4096) -> None:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise ValueError("maximum must be positive")
        self.maximum = maximum
        self._items: dict[str, PerpendicularDirection] = {}

    def add(
        self,
        *,
        axis: str,
        hypothesis: str,
        next_probe: str,
        parent_id: str | None = None,
        unresolved_questions: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        priority: float = 0.5,
        metadata: Mapping[str, Any] | None = None,
    ) -> PerpendicularDirection:
        depth = 0
        if parent_id is not None:
            parent = self._items.get(parent_id)
            if parent is None:
                raise KeyError(f"unknown direction parent: {parent_id}")
            depth = parent.depth + 1
        payload = {
            "parent": parent_id,
            "axis": axis,
            "hypothesis": hypothesis,
            "next_probe": next_probe,
            "questions": list(unresolved_questions),
            "evidence": sorted(str(x) for x in evidence_ids),
        }
        item = PerpendicularDirection(
            direction_id=stable_id("direction", payload, length=28),
            parent_id=parent_id,
            axis=axis,
            hypothesis=hypothesis,
            next_probe=next_probe,
            unresolved_questions=tuple(unresolved_questions),
            evidence_ids=tuple(evidence_ids),
            priority=priority,
            depth=depth,
            metadata=metadata or {},
        )
        if item.direction_id not in self._items and len(self._items) >= self.maximum:
            victim = min(
                self._items.values(),
                key=lambda value: (value.status != "closed", value.priority, -value.depth, value.direction_id),
            )
            self._items.pop(victim.direction_id, None)
        self._items[item.direction_id] = item
        return item

    def update_status(self, direction_id: str, status: str) -> PerpendicularDirection:
        prior = self._items[direction_id]
        updated = PerpendicularDirection(
            direction_id=prior.direction_id,
            parent_id=prior.parent_id,
            axis=prior.axis,
            hypothesis=prior.hypothesis,
            next_probe=prior.next_probe,
            unresolved_questions=prior.unresolved_questions,
            evidence_ids=prior.evidence_ids,
            priority=prior.priority,
            depth=prior.depth,
            status=status,
            metadata=prior.metadata,
        )
        self._items[direction_id] = updated
        return updated

    def resume_queue(self, *, limit: int = 16) -> tuple[PerpendicularDirection, ...]:
        values = [item for item in self._items.values() if item.status == "open"]
        values.sort(key=lambda item: (-item.priority, item.depth, item.direction_id))
        return tuple(values[: max(1, limit)])

    def children(self, direction_id: str) -> tuple[PerpendicularDirection, ...]:
        values = [item for item in self._items.values() if item.parent_id == direction_id]
        return tuple(sorted(values, key=lambda item: (-item.priority, item.direction_id)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            [
                (
                    item.direction_id,
                    item.parent_id,
                    item.axis,
                    item.hypothesis,
                    item.next_probe,
                    item.priority,
                    item.status,
                )
                for item in sorted(self._items.values(), key=lambda x: x.direction_id)
            ]
        )


def _spec(
    lens_id: str,
    family: LensFamily,
    authority: LensAuthority,
    description: str,
    cues: Sequence[str],
    outputs: Sequence[str],
    **metadata: Any,
) -> LensDefinition:
    return LensDefinition(
        lens_id=lens_id,
        name=lens_id.replace("_", " ").title(),
        family=family,
        authority=authority,
        description=description,
        cues=tuple(cues),
        outputs=tuple(outputs),
        metadata=metadata,
    )


def default_lenses() -> tuple[LensDefinition, ...]:
    F, E, H, I = LensAuthority.FORMAL, LensAuthority.EMPIRICAL, LensAuthority.HEURISTIC, LensAuthority.INTERPRETIVE
    P = LensFamily.PROBABILITY
    R = LensFamily.PREDICTIVE
    C = LensFamily.CAUSAL
    N = LensFamily.INFORMATION
    M = LensFamily.MEMORY
    Y = LensFamily.SEMIOTIC
    V = LensFamily.CINEMA
    L = LensFamily.LITERARY
    G = LensFamily.LUDIC
    Q = LensFamily.PRAGMATIC
    S = LensFamily.SOCIAL
    X = LensFamily.COMPUTATIONAL
    Z = LensFamily.METACOGNITIVE

    values = [
        # Probability and uncertainty: formal distinctions are kept explicit.
        _spec("classical_probability", P, F, "Equiprobable finite outcomes and exact counting.", ("dice","cards","coin","permutation","combination","fair"), ("event_probability","sample_space")),
        _spec("frequentist_probability", P, F, "Long-run frequency and sampling behavior.", ("frequency","trial","sample","repeat","rate"), ("estimate","sampling_error")),
        _spec("bayesian_probability", P, F, "Probability as uncertainty updated with evidence.", ("prior","posterior","bayes","belief","evidence"), ("posterior","credible_interval")),
        _spec("subjective_probability", P, H, "Explicit personal degree of belief, separated from empirical frequency.", ("belief","confidence","judgment","subjective"), ("stated_belief","calibration_need")),
        _spec("propensity_probability", P, H, "Chance as a physical/dispositional tendency of a process.", ("propensity","physical chance","randomizer","mechanism"), ("propensity_hypothesis",)),
        _spec("likelihood_lens", P, F, "Compare parameter support given observed data without treating likelihood as a probability distribution over parameters.", ("likelihood","mle","parameter","fit"), ("relative_support","likelihood_ratio")),
        _spec("posterior_predictive", P, F, "Integrate predictions across posterior parameter uncertainty.", ("predictive","posterior predictive","forecast"), ("predictive_distribution","predictive_interval")),
        _spec("hierarchical_bayes", P, F, "Share statistical strength across related groups while retaining partial pooling.", ("hierarchical","multilevel","group","pooling"), ("group_posterior","shrinkage")),
        _spec("survival_hazard", P, F, "Model time-to-event through survival and hazard.", ("hazard","survival","time to","failure time","churn"), ("survival","hazard")),
        _spec("markov_transition", P, F, "Condition future state on an explicit state representation.", ("transition","markov","state","next state"), ("transition_probability",)),
        _spec("hidden_state_probability", P, F, "Infer latent state from noisy observations.", ("hidden","latent","hmm","state space","filter"), ("state_belief","observation_likelihood")),
        _spec("calibration_probability", P, E, "Check whether stated probabilities match observed frequencies.", ("calibration","brier","reliability","ece"), ("calibration_error","reliability")),
        _spec("imprecise_probability", P, F, "Use lower/upper probability bounds when a single precise distribution is unjustified.", ("interval probability","imprecise","credal","lower probability"), ("lower_probability","upper_probability")),
        _spec("evidence_theory", P, F, "Represent belief mass and ignorance separately.", ("dempster","shafer","belief function","plausibility"), ("belief","plausibility","ignorance")),
        _spec("possibility_necessity", P, F, "Use possibility/necessity measures for ordinal uncertainty.", ("possibility","necessity","fuzzy uncertainty"), ("possibility","necessity")),
        _spec("conformal_coverage", P, F, "Finite-sample coverage sets under exchangeability assumptions.", ("conformal","coverage","prediction set"), ("prediction_set","coverage_target")),
        _spec("aleatoric_epistemic_split", P, E, "Separate irreducible outcome noise from model uncertainty.", ("aleatoric","epistemic","uncertainty","noise"), ("aleatoric","epistemic")),
        _spec("risk_sensitive_probability", P, F, "Evaluate downside tails rather than expectation alone.", ("cvar","tail risk","downside","worst case"), ("expected_value","tail_value")),
        _spec("information_gain_probability", P, F, "Value observations by expected posterior entropy reduction.", ("information gain","entropy","experiment","probe"), ("expected_information_gain",)),
        _spec("surprisal_probability", P, F, "Measure unexpectedness as negative log probability.", ("surprise","surprisal","unexpected"), ("surprisal",)),
        _spec("empirical_game_probability", P, E, "Estimate chance from repeated gameplay and compare to exact mechanics when known.", ("roll","draw","loot","drop rate","game probability"), ("empirical_rate","mechanic_gap")),
        _spec("memory_retrieval_probability", P, E, "Estimate recall probability from strength, spacing, interference, cue match and recency.", ("remember","recall","memory game","spacing","forget"), ("recall_probability","review_priority")),
        _spec("ensemble_model_probability", P, F, "Average across supported models while exposing model disagreement.", ("ensemble","model uncertainty","model average"), ("mixture_prediction","model_disagreement")),
        _spec("decision_probability", P, H, "Keep probability of outcomes distinct from utilities and decisions.", ("decision","utility","choice","expected utility"), ("outcome_probability","utility_separation")),
        _spec("martingale_evalue", P, F, "Use nonnegative test martingales/e-values for sequential evidence while preserving optional-stopping guarantees under their assumptions.", ("e-value","martingale","sequential test","optional stopping"), ("e_value","sequential_evidence")),
        _spec("proper_scoring_rule", P, F, "Evaluate probabilistic forecasts with proper scores so truthful probabilities are incentivized.", ("brier","log score","proper scoring","forecast score"), ("proper_score","calibration_sharpness")),
        _spec("multicalibration", P, E, "Audit calibration simultaneously across many overlapping subgroups instead of relying only on global calibration.", ("multicalibration","subgroup calibration","group reliability"), ("subgroup_calibration","worst_group_error")),
        _spec("selective_prediction", P, F, "Trade coverage against error by allowing abstention when uncertainty is too high.", ("selective prediction","coverage risk","abstain","reject option"), ("coverage","selective_risk")),
        _spec("extreme_value_tail", P, F, "Model rare extremes separately from the distribution body when tail risk drives the decision.", ("extreme value","gev","gpd","tail exceedance","rare extreme"), ("tail_index","return_level")),
        _spec("copula_dependence", P, F, "Separate marginal uncertainty from dependence structure for correlated risks.", ("copula","tail dependence","dependence structure"), ("marginals","dependence_parameter","joint_tail")),
        _spec("bayesian_nonparametric", P, F, "Permit model complexity to grow with evidence instead of fixing a finite parametric family in advance.", ("dirichlet process","gaussian process","nonparametric bayes"), ("posterior_process","adaptive_complexity")),
        _spec("importance_sampling_rare_event", P, F, "Estimate very rare probabilities by sampling from a proposal and correcting with likelihood ratios.", ("importance sampling","rare event","proposal distribution"), ("rare_event_probability","effective_sample_size")),
        _spec("distribution_shift_probability", P, E, "Separate in-distribution uncertainty from covariate, label, concept, and mechanism shift.", ("distribution shift","covariate shift","concept drift","ood"), ("shift_type","shift_score","recalibration_need")),
        _spec("forecast_combination", P, E, "Combine independently useful forecasts while measuring redundancy and disagreement.", ("forecast combination","pool forecasts","ensemble forecast"), ("combined_forecast","diversity_gain")),

        # Predictive / causal / information.
        _spec("base_rate", R, E, "Anchor forecasts in reference-class prevalence before case-specific adjustments.", ("base rate","prevalence","reference class"), ("base_rate","adjustment")),
        _spec("trend", R, E, "Inspect directional drift without assuming it persists.", ("trend","growth","decline","slope"), ("trend","trend_uncertainty")),
        _spec("seasonality", R, E, "Inspect periodic recurrence and calendar structure.", ("seasonal","cycle","weekly","monthly","yearly"), ("seasonal_component",)),
        _spec("change_point", R, F, "Detect regime boundaries where generating behavior changes.", ("change point","break","regime shift","structural break"), ("change_probability","regime")),
        _spec("state_space_forecast", R, F, "Separate latent dynamics from noisy observations.", ("state space","kalman","latent dynamics"), ("filtered_state","forecast")),
        _spec("sequence_prediction", R, E, "Use ordered event history rather than bag-of-events similarity.", ("sequence","next","after","before","history"), ("next_event","sequence_confidence")),
        _spec("scenario_tree", R, F, "Represent branching futures with explicit probabilities and consequences.", ("scenario","branch","future path"), ("branches","branch_weights")),
        _spec("ensemble_disagreement", R, E, "Use disagreement among independently plausible predictors as epistemic signal.", ("disagreement","ensemble","models"), ("dispersion","abstain_signal")),
        _spec("adversarial_forecast", R, H, "Search for plausible failure futures rather than only modal futures.", ("adversarial","failure mode","red team"), ("failure_scenarios",)),
        _spec("mechanism_drift", R, E, "Check whether learned transition mechanisms remain stable over time.", ("drift","mechanism change","nonstationary"), ("drift_score","relearn_signal")),
        _spec("causal_observation", C, F, "Treat observational association as distinct from intervention.", ("correlation","association","observe"), ("association",)),
        _spec("causal_intervention", C, F, "Estimate effects under do-style intervention semantics.", ("intervention","do(","treatment","cause"), ("interventional_effect",)),
        _spec("counterfactual", C, F, "Reason about alternate outcomes only under stated identification assumptions.", ("counterfactual","would have","had it not"), ("counterfactual_estimate","identification_status")),
        _spec("causal_transport", C, F, "Check whether a causal result can transport across populations/environments.", ("transport","domain shift","population","external validity"), ("transportability_conditions",)),
        _spec("mediation", C, F, "Separate total, direct and mediated pathways when identified.", ("mediator","mediation","pathway"), ("direct_effect","indirect_effect")),
        _spec("confounding", C, F, "Search for common causes that can explain an observed association.", ("confound","common cause","backdoor"), ("confounders","adjustment_set")),
        _spec("selection_bias", C, F, "Inspect conditioning/selection mechanisms that distort inference.", ("selection","collider","sample bias"), ("selection_path",)),
        _spec("entropy", N, F, "Quantify distributional uncertainty.", ("entropy","uncertainty"), ("entropy",)),
        _spec("mutual_information", N, F, "Quantify shared information while avoiding causal interpretation.", ("mutual information","dependence"), ("mutual_information",)),
        _spec("minimum_description_length", N, F, "Prefer concise explanatory encodings when predictive adequacy is comparable.", ("mdl","compression","description length"), ("description_length","complexity_penalty")),
        _spec("value_of_information", N, F, "Compare expected decision improvement from information to its cost.", ("value of information","voi","worth asking"), ("information_value","acquisition_cost")),

        # Memory and retrieval.
        _spec("episodic_reinstatement", M, E, "Retrieve concrete prior episodes before abstract summaries when cue overlap is strong.", ("episode","last time","previous interaction"), ("episode_hits","source_refs")),
        _spec("semantic_consolidation", M, E, "Retrieve generalized knowledge only after preserving source episodes.", ("general rule","semantic","learned"), ("semantic_hits","supporting_episodes")),
        _spec("spacing_effect", M, E, "Use retrieval spacing to schedule durable memory refresh.", ("spaced","review","practice","memory game"), ("next_review","retrieval_strength")),
        _spec("testing_effect", M, E, "Prefer active retrieval signals over passive re-exposure when measuring memory.", ("quiz","test","recall","retrieve"), ("retrieval_success","strength_update")),
        _spec("interference", M, E, "Inspect competition among similar memories.", ("interference","confuse","similar memories"), ("competitors","interference_penalty")),
        _spec("event_boundary", M, E, "Segment streams at meaningful event transitions before consolidation.", ("event boundary","scene change","transition"), ("segments","boundary_strength")),
        _spec("schema_script", M, E, "Use recurring event schemas while preserving exceptions.", ("schema","script","usually happens","routine"), ("schema","deviation")),
        _spec("associative_pair", M, E, "Use pair and triad associations for fast cue-based recall.", ("pair","association","next to","juxtapose"), ("associates","pair_strength")),
        _spec("source_monitoring", M, E, "Keep remembered content tied to where and how it was acquired.", ("source","where did","provenance"), ("source_refs","source_confidence")),

        # Semiotic / relational meaning lenses.  These never create source truth;
        # they expose relational hypotheses for retrieval, comparison and testing.
        _spec("semiotic_square", Y, I, "Expand a binary opposition into contradiction and implication relations to expose missing semantic quadrants.", ("semiotic square","opposition","contradiction","contrary"), ("opposition_graph","missing_quadrant")),
        _spec("icon_index_symbol", Y, I, "Distinguish resemblance, causal/contiguous indication, and conventional symbolism.", ("icon","index","symbol","semiotic"), ("sign_mode","referent_relation")),
        _spec("denotation_connotation", Y, I, "Keep literal reference separate from culturally or contextually associated meaning.", ("denotation","connotation","literal","associated meaning"), ("denotative_plane","connotative_plane")),
        _spec("syntagm_paradigm", Y, I, "Contrast meaning from sequence/combination with meaning from selectable alternatives.", ("syntagm","paradigm","sequence","alternative"), ("sequence_relation","alternative_set")),
        _spec("markedness", Y, I, "Detect asymmetric oppositions where one form is treated as default and the other explicitly marked.", ("marked","unmarked","default term","markedness"), ("default_pole","marked_pole")),
        _spec("figure_ground", Y, E, "Separate attended figure from contextual ground and test whether interpretation flips when attention is reassigned.", ("figure ground","foreground","background","salience"), ("figure","ground","attention_flip")),
        _spec("contrastive_semantics", Y, H, "Infer dimensions made salient by explicit juxtaposition while keeping each item's literal attributes separate.", ("contrast","juxtaposition","versus","side by side"), ("contrast_dimensions","relational_meaning")),
        _spec("absent_presence", Y, I, "Treat conspicuous omission as a hypothesis-generating cue without assuming what the missing element is.", ("absence","missing","omitted","not shown"), ("absence_hypotheses","expected_but_missing")),
        _spec("frame_boundary", Y, I, "Ask how inclusion/exclusion boundaries change the apparent meaning of the same material.", ("frame","crop","boundary","context window"), ("included_context","excluded_context","frame_effect")),
        _spec("semantic_inversion", Y, H, "Test whether swapping roles, order, polarity or foreground/background reveals a hidden dependency.", ("invert","swap roles","reverse","opposite framing"), ("invariant_features","order_sensitive_features")),

        # Cinema / editing lenses. These are interpretive unless supported by task evidence.
        _spec("kuleshov_juxtaposition", V, I, "Interpret meaning changes created by placing one shot/event beside another.", ("juxtaposition","kuleshov","shot","cut","reaction"), ("relational_meaning","contrast")),
        _spec("montage_collision", V, I, "Inspect conceptual meaning produced by collision/conflict between successive images.", ("montage","collision","conflict","edit"), ("emergent_concept","tension")),
        _spec("linkage_montage", V, I, "Inspect constructive linkage where successive shots build a larger action or idea.", ("montage","link","constructive","sequence"), ("constructed_whole",)),
        _spec("metric_montage", V, I, "Inspect effect of shot-duration regularity independent of content.", ("rhythm","duration","metric montage"), ("tempo_pattern",)),
        _spec("rhythmic_montage", V, I, "Inspect cut rhythm relative to movement within the frame.", ("rhythmic","movement","cut timing"), ("rhythmic_relation",)),
        _spec("tonal_montage", V, I, "Inspect affective tone formed across neighboring shots.", ("tone","mood","tonal montage"), ("affective_relation",)),
        _spec("overtonal_montage", V, I, "Inspect combined metric, rhythmic and tonal effects.", ("overtonal","layered montage"), ("combined_montage_effect",)),
        _spec("intellectual_montage", V, I, "Inspect abstract idea produced by juxtaposed concrete images.", ("intellectual montage","metaphor","conceptual edit"), ("abstract_relation",)),
        _spec("shot_reverse_shot", V, I, "Model conversational perspective alternation and inferred spatial/social relation.", ("shot reverse shot","conversation","reverse angle"), ("speaker_relation","perspective_balance")),
        _spec("pov_gaze", V, E, "Inspect gaze-to-target juxtaposition as a cue for shared attention and inferred intention.", ("pov","gaze","eyeline","look","target"), ("attention_target","perspective")),
        _spec("eyeline_match", V, I, "Infer spatial/intentional connection from gaze direction followed by a target shot.", ("eyeline","match","looking at"), ("spatial_relation","attention_relation")),
        _spec("match_cut", V, I, "Inspect continuity or analogy created by matching form/action across a cut.", ("match cut","graphic match","action match"), ("analogy","continuity")),
        _spec("jump_cut", V, I, "Inspect deliberate discontinuity, ellipsis or destabilization.", ("jump cut","discontinuity","skip"), ("discontinuity","ellipsis")),
        _spec("cross_cutting", V, I, "Track alternation among simultaneous or thematically linked event streams.", ("cross cut","parallel action","meanwhile"), ("parallel_threads","convergence")),
        _spec("temporal_ellipsis", V, I, "Infer omitted time from adjacent narrative states without inventing missing facts.", ("ellipsis","time jump","later","cut"), ("omitted_interval","uncertainty")),
        _spec("continuity_editing", V, I, "Inspect spatial/temporal coherence maintained across edits.", ("continuity","180 degree","screen direction"), ("continuity_constraints",)),
        _spec("mise_en_scene", V, I, "Inspect meaning carried by staging, setting, lighting, costume and composition.", ("mise en scene","staging","lighting","costume","composition"), ("scene_semantics",)),
        _spec("blocking", V, I, "Read spatial arrangement and movement of agents as relational information.", ("blocking","position","movement","stage"), ("spatial_power_relation","trajectory")),
        _spec("negative_space", V, I, "Treat conspicuous absence/empty frame regions as a possible semantic cue.", ("negative space","empty","absence","offscreen"), ("absence_hypothesis",)),
        _spec("frame_within_frame", V, I, "Inspect nested framing as a cue for separation, surveillance or constrained viewpoint.", ("frame within frame","window","doorway","screen within"), ("nested_perspective",)),
        _spec("sound_bridge", V, I, "Track audio continuity across visual boundaries.", ("sound bridge","audio carries","voice over cut"), ("cross_boundary_link",)),
        _spec("leitmotif_audio_visual", V, I, "Track recurring audiovisual motifs and changed meaning across repetitions.", ("leitmotif","recurring music","motif"), ("motif_instances","semantic_drift")),
        _spec("rack_focus_attention", V, I, "Treat focus shifts as explicit attention reallocation.", ("rack focus","focus shift","foreground","background"), ("attention_shift",)),
        _spec("reaction_shot", V, I, "Use a reaction shot as evidence about represented interpretation, not objective truth.", ("reaction shot","reaction","face"), ("character_interpretation",)),
        _spec("offscreen_space", V, I, "Represent causally relevant but unseen space as uncertain latent context.", ("offscreen","outside frame","heard not seen"), ("latent_space","uncertainty")),
        _spec("visual_foreshadowing", V, I, "Track planted visual details whose significance may emerge later.", ("foreshadow","plant","visual clue"), ("future_link_candidate",)),

        _spec("suture", V, I, "Track how shot/reverse-shot and off-screen absence position a viewer into an inferred viewpoint.", ("suture","viewer position","offscreen look"), ("viewpoint_position","missing_viewpoint")),
        _spec("diegetic_boundary", V, I, "Separate events/sounds inside the represented story world from extradiegetic presentation.", ("diegetic","nondiegetic","score","story world"), ("diegetic_plane","presentation_plane")),
        _spec("deep_focus_relation", V, I, "Treat simultaneous foreground/midground/background action as competing semantic evidence rather than a forced single focal path.", ("deep focus","foreground","midground","background"), ("simultaneous_planes","attention_options")),
        _spec("long_take_continuity", V, I, "Analyze meaning preserved by continuous duration where editing does not provide segmentation.", ("long take","oner","continuous shot","no cut"), ("continuous_dependencies","event_boundaries")),
        _spec("subjective_camera", V, I, "Model camera position/motion as aligned with a character or observer state without treating that alignment as objective truth.", ("subjective camera","first person camera","character viewpoint"), ("viewpoint_hypothesis","observer_state")),
        _spec("split_screen_parallelism", V, I, "Represent simultaneous visible streams and compare synchronization, contrast and causal independence.", ("split screen","simultaneous panels","parallel frame"), ("parallel_streams","synchrony","contrast")),
        _spec("graphic_rhyme", V, I, "Detect repeated visual geometry/color/motion across separated shots as a candidate semantic bridge.", ("graphic rhyme","visual rhyme","repeated composition"), ("visual_correspondence","bridge_candidate")),
        _spec("shot_scale_progression", V, I, "Track systematic changes in shot scale as a cue for attention, intimacy or information release.", ("close up","wide shot","shot scale","push in"), ("scale_sequence","attention_trajectory")),
        _spec("screen_direction_axis", V, I, "Track axis-of-action and screen direction so apparent pursuit, opposition or continuity is not inferred from cuts alone.", ("screen direction","axis of action","180 degree","left to right"), ("spatial_axis","continuity_break")),
        _spec("temporal_disjunction", V, I, "Treat non-contiguous cuts as possible time reordering rather than automatically continuous chronology.", ("nonlinear edit","temporal disjunction","out of order"), ("temporal_order_hypotheses","continuity_uncertainty")),

        # Literary / narratological lenses.
        _spec("focalization", L, I, "Separate who perceives from who narrates.", ("focalization","perspective","sees","perceives"), ("perceiver","narrator")),
        _spec("free_indirect_discourse", L, I, "Detect narrator language colored by a character's idiom or perspective.", ("free indirect","voice","thought style"), ("voice_blend",)),
        _spec("unreliable_narration", L, I, "Track discrepancies between a narrator's account and independently supported events.", ("unreliable narrator","contradiction","narrator"), ("reliability_hypothesis","conflicts")),
        _spec("dramatic_irony", L, I, "Represent differences between audience knowledge and character knowledge.", ("dramatic irony","audience knows","character doesn't"), ("knowledge_gap",)),
        _spec("defamiliarization", L, I, "Inspect unusual framing that makes a familiar object/process newly salient.", ("defamiliarize","strange","unfamiliar description"), ("reframing",)),
        _spec("intertextuality", L, I, "Track meaning imported by references to other texts or cultural artifacts.", ("reference","allusion","intertext","echo"), ("source_text_candidate","transferred_meaning")),
        _spec("motif", L, I, "Track repeated elements whose role changes with context.", ("motif","recurring","repeated image","refrain"), ("motif_instances","context_shift")),
        _spec("symbolic_reading", L, I, "Generate symbolic hypotheses while preserving literal reading separately.", ("symbol","symbolic","stands for"), ("literal_plane","symbolic_plane")),
        _spec("foil", L, I, "Compare contrasted entities to reveal dimensions that are less visible in isolation.", ("foil","contrast","opposite character"), ("contrast_dimensions",)),
        _spec("analepsis", L, I, "Track flashback and retrospective insertion.", ("flashback","earlier","analepsis"), ("temporal_backlink",)),
        _spec("prolepsis", L, I, "Track flashforward and anticipatory insertion.", ("flashforward","future glimpse","prolepsis"), ("temporal_forwardlink",)),
        _spec("narrative_ellipsis", L, I, "Represent omitted events/time without filling gaps as facts.", ("ellipsis","omitted","skip"), ("gap","possible_bridges")),
        _spec("parataxis", L, I, "Inspect meaning from adjacent units without explicit subordinating relation.", ("parataxis","side by side","juxtaposed clauses"), ("implicit_relation_candidates",)),
        _spec("hypotaxis", L, I, "Inspect explicit hierarchy/subordination among propositions.", ("because","although","while","subordinate"), ("relation_hierarchy",)),
        _spec("polyphony", L, I, "Preserve multiple voices/value systems without collapsing them into one narrator.", ("polyphony","many voices","dialogic"), ("voices","stance_map")),
        _spec("dialogism", L, I, "Inspect utterances as responses to prior/social discourse rather than isolated propositions.", ("dialogic","reply","voice","discourse"), ("inter_voice_relations",)),
        _spec("metonymy", L, I, "Inspect meaning by contiguity/association rather than similarity.", ("metonymy","associated with","contiguous"), ("association_mapping",)),
        _spec("synecdoche", L, I, "Inspect part-whole substitution.", ("part for whole","whole for part","synecdoche"), ("part_whole_mapping",)),
        _spec("chiasmus", L, I, "Detect mirrored ABBA structure and compare reversed relations.", ("chiasmus","abba","reversal","mirror"), ("structural_mirror",)),
        _spec("ring_composition", L, I, "Detect return-to-origin structures and symmetric narrative framing.", ("ring composition","returns to","circular narrative"), ("symmetry","closure")),
        _spec("frame_narrative", L, I, "Track nested narrators/stories with separate truth scopes.", ("story within story","frame narrative","nested narrator"), ("narrative_scopes",)),
        _spec("recursive_narrative", L, I, "Track self-similar or self-referential narrative levels.", ("recursive","story about story","self reference"), ("recursion_levels",)),
        _spec("narrative_distance", L, I, "Estimate distance between narration and immediate embodied event.", ("distance","close narration","detached"), ("distance_hypothesis",)),
        _spec("stream_of_consciousness", L, I, "Treat associative ordering as mental sequence rather than objective chronology.", ("stream of consciousness","associative thought","interior"), ("mental_sequence","chronology_separation")),
        _spec("constraint_poetics", L, I, "Inspect how explicit formal constraints generate structure and unexpected solutions.", ("constraint","oulipo","lipogram","formal rule"), ("constraint_effects",)),

        _spec("fabula_syuzhet", L, I, "Separate reconstructed chronological events from the order in which discourse presents them.", ("fabula","syuzhet","story order","plot order"), ("event_chronology","presentation_order")),
        _spec("metalepsis", L, I, "Detect crossings between narrative levels instead of collapsing nested worlds into one scope.", ("metalepsis","narrative level crossing","breaks into story"), ("level_crossing","scope_violation")),
        _spec("mise_en_abyme", L, I, "Track embedded miniature or mirrored versions of the containing narrative.", ("mise en abyme","story mirrors itself","embedded mirror"), ("self_mirroring_structure","nested_correspondence")),
        _spec("heteroglossia", L, I, "Preserve socially distinct registers and worldviews carried by different voices.", ("heteroglossia","register","social voice","many speech types"), ("voice_registers","ideological_contrast")),
        _spec("chronotope", L, I, "Analyze coupled time-space structures that constrain what actions and meanings are plausible.", ("chronotope","time space","setting and time"), ("time_space_regime","action_constraints")),
        _spec("aporia", L, I, "Mark irresolvable or structurally undecidable tensions instead of forcing premature synthesis.", ("aporia","undecidable","paradox","cannot resolve"), ("unresolved_tension","competing_readings")),
        _spec("ekphrasis", L, I, "Track transformations when one medium verbally represents another visual or material artifact.", ("ekphrasis","description of image","verbal painting"), ("cross_medium_mapping","representation_loss")),
        _spec("anagnorisis", L, I, "Detect recognition events that reclassify earlier evidence and relationships.", ("anagnorisis","recognition","revelation","realizes"), ("recognition_point","retroactive_reinterpretation")),
        _spec("peripeteia", L, I, "Detect reversals where the direction of action/outcome changes because prior assumptions fail.", ("peripeteia","reversal","turning point"), ("reversal_point","failed_expectation")),
        _spec("paratext", L, I, "Keep titles, framing notes, metadata and other threshold material distinct from the primary text while allowing them to guide interpretation.", ("paratext","title","preface","caption","metadata"), ("primary_text","framing_material")),
        _spec("negative_capability", L, H, "Preserve productive ambiguity when evidence does not justify collapsing multiple readings.", ("negative capability","ambiguity","uncertainty","multiple readings"), ("preserved_ambiguity","premature_closure_risk")),

        # Game / ludic lenses.
        _spec("mechanics_dynamics_aesthetics", G, H, "Separate rules/mechanics, emergent dynamics and player experience.", ("mechanic","dynamic","aesthetic","mda"), ("mechanics","dynamics","experience")),
        _spec("ludonarrative_relation", G, I, "Compare what rules reward with what narrative claims to value.", ("ludonarrative","story","mechanics","dissonance"), ("consonance","dissonance")),
        _spec("affordance", G, E, "Inspect actions the interface/world makes perceptually and mechanically available.", ("affordance","can do","interaction","button"), ("available_actions","discoverability")),
        _spec("feedback_loop", G, F, "Identify positive/negative feedback loops in state transitions.", ("feedback loop","snowball","rubber band"), ("loop_type","gain")),
        _spec("risk_reward", G, F, "Compare outcome distribution and utility under risky actions.", ("risk reward","gamble","stake","reward"), ("risk","reward","expected_utility")),
        _spec("dominant_strategy", G, F, "Check whether one action dominates alternatives across opponent states.", ("dominant strategy","always better","strategy"), ("dominance",)),
        _spec("mixed_strategy", G, F, "Represent randomized strategy when predictability can be exploited.", ("mixed strategy","randomize","probability strategy"), ("strategy_distribution",)),
        _spec("partial_observability", G, F, "Represent hidden state and information sets explicitly.", ("fog of war","hidden information","partial observability"), ("belief_state","information_set")),
        _spec("information_asymmetry", G, F, "Track who knows what and how that changes incentives.", ("information asymmetry","secret","private information"), ("knowledge_by_agent",)),
        _spec("bluff_deception", G, H, "Model strategic signaling where observed action may intentionally misrepresent private state.", ("bluff","deception","feint","signal"), ("signal_hypotheses",)),
        _spec("tempo_initiative", G, H, "Track who controls timing and forces responses.", ("tempo","initiative","forcing move"), ("initiative","tempo_cost")),
        _spec("zugzwang", G, F, "Detect states where every available move worsens the actor's position.", ("zugzwang","must move","all moves worse"), ("forced_loss_structure",)),
        _spec("resource_economy", G, F, "Track stocks, flows, sinks, faucets and opportunity cost.", ("resource","economy","mana","gold","energy","sink","faucet"), ("stocks","flows","opportunity_cost")),
        _spec("exploration_exploitation", G, F, "Balance information-seeking actions with currently valuable actions.", ("explore","exploit","bandit","uncertain option"), ("exploration_value","exploitation_value")),
        _spec("emergent_gameplay", G, H, "Look for behavior produced by interacting rules rather than authored scripts.", ("emergent","sandbox","interaction of systems"), ("emergent_pattern",)),
        _spec("procedural_rhetoric", G, I, "Treat rule systems as arguments/claims embodied in procedures.", ("procedural rhetoric","rules say","simulation claim"), ("procedural_claim",)),
        _spec("counterplay", G, H, "Check whether strong actions expose meaningful responses.", ("counterplay","counter","response option"), ("responses","fairness_hypothesis")),
        _spec("skill_floor_ceiling", G, E, "Separate entry difficulty from mastery depth.", ("skill floor","skill ceiling","mastery","beginner"), ("floor","ceiling")),
        _spec("difficulty_curve", G, E, "Track challenge progression relative to learned capability.", ("difficulty curve","challenge","learning curve"), ("challenge_trajectory",)),
        _spec("fail_forward", G, H, "Treat failure as state progression/information rather than pure reset.", ("fail forward","failure teaches","continue after failure"), ("failure_yield","recovery_path")),
        _spec("save_reload", G, H, "Model branching knowledge gained across reversible attempts without confusing player and character knowledge.", ("save","reload","checkpoint","retry"), ("attempt_knowledge","world_state")),
        _spec("metagame", G, H, "Track strategies shaped by population-level expectations outside the immediate rules state.", ("meta","metagame","popular strategy","counter meta"), ("population_strategy","adaptation")),
        _spec("state_abstraction", G, F, "Compress states by decision-relevant equivalence rather than surface similarity.", ("state abstraction","equivalent state","feature state"), ("abstract_state",)),
        _spec("quest_branching", G, H, "Track branch prerequisites, irreversible choices and convergence points.", ("quest","branch","choice","ending"), ("branch_graph","irreversibility")),
        _spec("pacing_loop", G, H, "Track tension/release and activity/rest cycles across play.", ("pacing","tension","downtime","loop"), ("pacing_state",)),
        _spec("memory_match_game", G, E, "Use cue-pair matching, interference and retrieval latency as measurable memory-game signals.", ("memory game","matching pairs","flip card","remember location"), ("match_probability","retrieval_latency","interference")),

        _spec("possibility_space", G, F, "Represent the reachable action/state space induced by rules instead of reasoning only from authored examples.", ("possibility space","reachable states","rules allow"), ("reachable_space","constraints")),
        _spec("magic_circle_boundary", G, H, "Track when rules, norms and meanings are local to the game frame versus imported from outside it.", ("magic circle","inside game","outside game","play frame"), ("frame_rules","boundary_crossing")),
        _spec("diegetic_interface", G, I, "Distinguish UI information that exists inside the game world from player-only overlays.", ("diegetic ui","hud","in world interface"), ("character_information","player_information")),
        _spec("environmental_storytelling", G, I, "Infer candidate past events from spatially arranged traces while keeping reconstruction uncertainty explicit.", ("environmental storytelling","scene tells story","environment clue"), ("trace_set","event_hypotheses")),
        _spec("emergent_narrative", G, H, "Track story structure produced by interacting simulation systems rather than only scripted beats.", ("emergent narrative","simulation story","systemic story"), ("event_chain","authored_vs_emergent")),
        _spec("exploitability", G, F, "Measure how much a strategy can lose to an informed best response.", ("exploitability","best response gap","nash gap"), ("exploitability_gap","best_response")),
        _spec("regret_minimization", G, F, "Evaluate strategies by cumulative counterfactual regret rather than only realized reward.", ("regret minimization","counterfactual regret","cfr"), ("regret","strategy_update")),
        _spec("signaling_game", G, F, "Model strategic messages/actions whose meaning depends on sender type, receiver belief and equilibrium incentives.", ("signaling game","sender receiver","signal type"), ("sender_type","receiver_belief","signal_equilibrium")),
        _spec("telegraphing", G, E, "Measure how clearly impending actions are signaled before they become costly to respond to.", ("telegraph","windup","warning cue","readable attack"), ("cue_lead_time","response_window")),
        _spec("player_modeling", G, E, "Maintain probabilistic hypotheses over player goals, skill and policy and update them from interaction.", ("player model","player behavior","skill estimate","preference model"), ("player_state_belief","behavior_prediction")),
        _spec("save_scumming_epistemics", G, H, "Separate knowledge accumulated across retries from knowledge available to the in-world agent.", ("save scum","retry knowledge","reload knowledge"), ("player_meta_knowledge","character_knowledge")),
        _spec("procedural_generation", G, F, "Analyze generator constraints, distributions and coverage rather than treating generated content as independent hand-authored samples.", ("procedural generation","pcg","generator","seed"), ("generator_distribution","coverage","constraint_violations")),
        _spec("speedrun_route", G, H, "Model route optimization under reset cost, execution variance, exploit availability and split dependencies.", ("speedrun","route","split","reset","world record"), ("route_graph","expected_time","variance")),
        _spec("systemic_storytelling", G, H, "Map narrative consequences onto simulation state transitions and persistent world variables.", ("systemic storytelling","world state story","simulation consequence"), ("story_state","systemic_consequence")),

        # Pragmatics/social/computational/metacognitive.
        _spec("gricean_implicature", Q, I, "Infer possible conversational implicature while preserving literal content.", ("imply","implicature","why say","conversational"), ("literal","implicature_hypothesis")),
        _spec("presupposition", Q, I, "Separate backgrounded presupposition from asserted content.", ("presuppose","again","stop","still"), ("assertion","presupposition")),
        _spec("speech_act", Q, I, "Classify utterance function: assertion, request, promise, warning, etc.", ("request","promise","warn","ask","order"), ("speech_act",)),
        _spec("common_ground", S, E, "Track mutually established context separately from private beliefs.", ("we know","as discussed","shared","common ground"), ("shared_context","private_context")),
        _spec("theory_of_mind", S, H, "Represent separate beliefs, goals and observations for different agents.", ("believes","thinks","knows","intends"), ("agent_beliefs","agent_goals")),
        _spec("social_signaling", S, H, "Inspect actions as both instrumental behavior and signals to observers.", ("signal","status","reputation","impression"), ("instrumental_effect","signal_effect")),
        _spec("abstract_interpretation", X, F, "Over-approximate program states to prove properties without enumerating executions.", ("abstract interpretation","static analysis","invariant"), ("abstract_state","property")),
        _spec("ssa_dataflow", X, F, "Reason over explicit definitions, uses and control/data dependencies.", ("ssa","dataflow","phi","definition use"), ("def_use","flow_fact")),
        _spec("translation_validation", X, F, "Validate semantics of a transformation rather than trusting the transform implementation.", ("translation validation","compiler pass","equivalence"), ("equivalence_result","counterexample")),
        _spec("decompilation_loss", X, F, "Track information irreversibly lost between source, binary/IR and reconstructed form.", ("decompile","reconstruct","lossy","symbol recovery"), ("loss_map","confidence")),
        _spec("value_of_computation", Z, F, "Estimate whether another reasoning step is worth its time/token/tool cost.", ("think more","compute","worth reasoning","stop"), ("expected_reasoning_value","cost")),
        _spec("loop_detection", Z, E, "Detect repeated cognitive states/actions without new evidence.", ("loop","repeat","stuck","same again"), ("loop_score","redirect_signal")),
        _spec("assumption_audit", Z, H, "Enumerate load-bearing assumptions and test the most decision-sensitive ones.", ("assume","assumption","depends on"), ("assumptions","sensitivity")),
        _spec("abstention", Z, F, "Prefer explicit uncertainty/deferral when support is insufficient.", ("uncertain","don't know","abstain","insufficient"), ("abstain_score","missing_support")),
    ]
    return tuple(values)


class LensCatalog:
    def __init__(self, definitions: Sequence[LensDefinition] | None = None) -> None:
        definitions = tuple(definitions or default_lenses())
        ids = [value.lens_id for value in definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate lens ids")
        self._definitions = {value.lens_id: value for value in definitions}

    def get(self, lens_id: str) -> LensDefinition | None:
        return self._definitions.get(str(lens_id))

    def all(self) -> tuple[LensDefinition, ...]:
        return tuple(sorted(self._definitions.values(), key=lambda value: value.lens_id))

    def by_family(self, family: LensFamily) -> tuple[LensDefinition, ...]:
        family = family if isinstance(family, LensFamily) else LensFamily(str(family))
        return tuple(value for value in self.all() if value.family is family)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            [
                (
                    value.lens_id,
                    value.family.value,
                    value.authority.value,
                    value.cues,
                    value.outputs,
                )
                for value in self.all()
            ]
        )


class SemanticLensRouter:
    """Cheap deterministic router for selecting diverse analysis operators.

    The router intentionally gives a diversity bonus to underrepresented
    families.  This is the "perpendicular" behavior: after choosing the best
    matching lens it seeks other high-scoring lenses from different axes rather
    than returning ten near-duplicates.
    """

    def __init__(self, catalog: LensCatalog | None = None) -> None:
        self.catalog = catalog or LensCatalog()

    def route(
        self,
        query: str,
        *,
        adjacent_text: Sequence[str] = (),
        prior_lens_ids: Sequence[str] = (),
        requested_families: Sequence[LensFamily] = (),
        limit: int = 12,
    ) -> LensBundle:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = self._tokens(query)
        adjacent_tokens = [self._tokens(value) for value in adjacent_text]
        family_filter = {
            value if isinstance(value, LensFamily) else LensFamily(str(value))
            for value in requested_families
        }
        prior = set(str(value) for value in prior_lens_ids)
        scored: list[tuple[float, LensActivation]] = []
        for lens in self.catalog.all():
            if family_filter and lens.family not in family_filter:
                continue
            cue_tokens = set()
            matched: list[str] = []
            for cue in lens.cues:
                tokens = self._tokens(cue)
                cue_tokens.update(tokens)
                if tokens and tokens.issubset(query_tokens):
                    matched.append(cue)
            overlap = len(query_tokens & cue_tokens) / max(1, len(query_tokens | cue_tokens))
            exact_bonus = min(1.0, len(matched) / 3.0)
            cue_score = min(1.0, overlap * 1.8 + exact_bonus * 0.55)

            relation = 0.0
            if adjacent_tokens:
                relation_hits = 0
                for left, right in zip(adjacent_tokens, adjacent_tokens[1:]):
                    left_hit = bool(left & cue_tokens)
                    right_hit = bool(right & cue_tokens)
                    if left_hit != right_hit or (left_hit and right_hit):
                        relation_hits += 1
                relation = min(1.0, relation_hits / max(1, len(adjacent_tokens) - 1))
                if lens.lens_id in {
                    "kuleshov_juxtaposition",
                    "montage_collision",
                    "cross_cutting",
                    "parataxis",
                    "foil",
                    "associative_pair",
                    "sequence_prediction",
                    "memory_match_game",
                    "contrastive_semantics",
                    "syntagm_paradigm",
                    "semiotic_square",
                    "split_screen_parallelism",
                    "graphic_rhyme",
                    "fabula_syuzhet",
                    "mise_en_abyme",
                    "environmental_storytelling",
                    "emergent_narrative",
                }:
                    relation = min(1.0, relation + 0.25)

            novelty = 0.15 if lens.lens_id not in prior else 0.0
            authority_prior = {
                LensAuthority.FORMAL: 0.14,
                LensAuthority.EMPIRICAL: 0.11,
                LensAuthority.HEURISTIC: 0.07,
                LensAuthority.INTERPRETIVE: 0.05,
            }[lens.authority]
            score = min(1.0, cue_score * 0.62 + relation * 0.18 + novelty + authority_prior)
            if score <= 0.05:
                continue
            rationale = (
                f"cue={cue_score:.3f}; relation={relation:.3f}; "
                f"novelty={novelty:.3f}; authority={lens.authority.value}"
            )
            activation = LensActivation(
                lens=lens,
                score=score,
                cue_score=cue_score,
                relation_score=relation,
                novelty_score=novelty,
                matched_cues=tuple(matched),
                rationale=rationale,
            )
            scored.append((score, activation))

        scored.sort(key=lambda item: (item[0], item[1].lens.authority.value, item[1].lens.lens_id), reverse=True)
        chosen: list[LensActivation] = []
        family_counts: dict[LensFamily, int] = {}
        pool = [value for _, value in scored]

        # First pass: maximize perpendicular family coverage.
        for value in pool:
            if len(chosen) >= limit:
                break
            if family_counts.get(value.lens.family, 0) == 0:
                chosen.append(value)
                family_counts[value.lens.family] = 1

        # Second pass: fill by score, limiting one family from flooding.
        for value in pool:
            if len(chosen) >= limit:
                break
            if value in chosen:
                continue
            family_count = family_counts.get(value.lens.family, 0)
            if family_count >= max(2, math.ceil(limit / 3)):
                continue
            chosen.append(value)
            family_counts[value.lens.family] = family_count + 1

        chosen.sort(key=lambda value: (-value.score, value.lens.lens_id))
        families = tuple(sorted({value.lens.family for value in chosen}, key=lambda family: family.value))
        fingerprint = stable_fingerprint(
            {
                "query": query,
                "adjacent": list(adjacent_text),
                "lenses": [(value.lens.lens_id, round(value.score, 8)) for value in chosen],
            }
        )
        return LensBundle(query=query, activations=tuple(chosen), families=families, fingerprint=fingerprint)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.casefold() for token in _TOKEN_RE.findall(text or "")}


__all__ = [
    "DirectionLedger",
    "LensActivation",
    "LensAuthority",
    "LensBundle",
    "LensCatalog",
    "LensDefinition",
    "LensFamily",
    "PerpendicularDirection",
    "SemanticLensRouter",
    "default_lenses",
]
