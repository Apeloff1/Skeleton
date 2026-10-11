"""Deep competitor analysis: scripted gameplay, visuals, audio and storytelling.

Every facet gets a typed *reproducible experiment script*, not a generic
sentiment score. Reviewed Wiki/Dragon research supplies claims and provenance;
signed, independently replayed observations supply measurements. Absent data
never becomes a claimed weakness. Rival IP never enters the generated design.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import (
    PlannedOriginalTitle, ThreatAssessment, RivalSourceLink, ThreatRadarError,
    _id, _sha, _date, _tags,
)
from .competitive_delivery_gate import TrustedCompetitionJudge, _mac
from .reviewed_knowledge import KnowledgeBrief, ReviewedKnowledgeStore
from .knowledge_rights_bridge import ClearedResearchPacket, require_cleared_research_current
from .rights import RightsLedger

# Each dimension has an explicit experimental protocol. More nuanced facets
# can be added with reviewed rubric versions; never rewrite an old script ID.
# Format: (facet_id, question, input condition, observable, adverse control).
FACETS = {
    "gameplay": (
        ("input_latency", "How consistently do inputs produce responsive action?", "repeat identical controller commands at cold and warm starts", "95th percentile press-to-effect latency", "latency spikes under simultaneous NPC/FX load"),
        ("control_precision", "Can expert and novice players reliably execute intent?", "repeat navigation/combat with identical input envelopes", "action-error rate and success spread", "dead zones, dropped inputs and ambiguous responses"),
        ("combat_readability", "Are threats, counters and damage states legible?", "blind randomized encounter telegraphs", "recognition, reaction and unfair-hit rate", "occluded or indistinguishable telegraph variants"),
        ("mechanical_depth", "Can players discover meaningful alternative tactics?", "counterbalanced multi-solution objective trials", "distinct viable strategy success", "dominant trivial tactic and no-choice ablation"),
        ("progression_curve", "Does mastery increase without grinding or dead zones?", "novice/expert progression milestones", "time-to-mastery and engagement plateau", "early power spike and late impossible bottleneck"),
        ("encounter_variety", "Are encounters mechanically differentiated?", "seeded repeated encounters across world zones", "distinct decision classes", "reskin-only or repeated-pattern baselines"),
        ("difficulty_fairness", "Are losses explainable and recoverable?", "randomized state-equivalent trials across player skill", "avoidable failures and perceived fairness", "unavoidable loss and information starvation"),
        ("exploration_reward", "Is exploration paid off with original discovery?", "blind world navigation and optional detours", "optional discovery value per traversal", "empty traversal and map marker saturation"),
        ("world_consistency", "Do interactions preserve state and physical laws?", "replayed cross-zone persistence, combat and save/load", "invariant pass rate", "desync, broken save and impossible state injection"),
        ("npc_agency", "Do NPC decisions adapt to witnessed events and memory?", "repeat first-hand/rumor/absent witness permutations", "correct contextual NPC action", "omniscient response and irrelevant quest triggers"),
        ("quest_consequence", "Do player decisions produce causal lasting changes?", "replay mutually exclusive decision branches", "causal consequences and path distinction", "branch convergence disguised as agency"),
        ("replayability", "Does a second run offer distinct valid play?", "counterbalanced independent seeds/builds/endings", "novel decisions and persistent player value", "procedural repetition with no meaningful variance"),
        ("tutorial_friction", "Can novices learn without needless interruption?", "first-session blind onboarding", "time to independent first success", "information overload and forced tutorial loops"),
        ("accessibility_controls", "Can different mobility needs play equivalently?", "alternate input and assist-mode blind trials", "task completion parity", "assist options that silently disable progress"),
    ),
    "graphics": (
        ("art_direction", "Is the visual identity internally distinctive?", "blind cross-scene composition classification", "style consistency and original identity recall", "competitor visual motif similarity check"),
        ("silhouette_clarity", "Are characters, interactables and threats distinct?", "grayscale low-resolution perception trials", "object recognition", "overlapping silhouettes and clutter"),
        ("animation_weight", "Does movement convey timing, intent and impact?", "frame-by-frame input/action/impact playback", "timing consistency and anticipation clarity", "broken contact and erratic animation transitions"),
        ("lighting_legibility", "Can players navigate varied lighting safely?", "fixed HDR/SDR, dark/bright combat variants", "navigation accuracy and hazard detection", "black crush, blown highlights and invisible interactables"),
        ("composition", "Do scene framing and focal hierarchy communicate intent?", "blind viewpoint/attention heatmap testing", "primary objective discovery", "attention stolen by irrelevant spectacle"),
        ("motion_stability", "Is motion comfortable and stable under stress?", "camera pans, FPS jitter and accessibility variants", "camera judder and comfort incidents", "rapid flashes and uncontrolled FOV transitions"),
        ("texture_readability", "Are materials clear at intended display sizes?", "target-resolution downsampling and zoom", "material identity and contrast", "asset noise or repeating tile seams"),
        ("color_language", "Is color signaling coherent and accessible?", "normal and color-vision deficiency simulations", "status recognition and palette distinction", "color-only mandatory information"),
        ("fx_budget", "Do particles and postprocessing help gameplay?", "identical fights at FX low/high settings", "hazard visibility and rendering cost", "occlusion, overdraw and eye strain"),
        ("lod_pop", "Does asset streaming preserve perceptual coherence?", "path replay and abrupt camera turns", "LOD transition salience", "texture pop-in and temporal shimmer"),
        ("ui_visuals", "Is information hierarchy readable across display sizes?", "small/large screen task finding", "task completion and menu search time", "text clipping and inaccessible HUD scaling"),
        ("platform_fidelity", "Does each device respect its performance/visual budget?", "native target-hardware baseline runs", "frame pacing and memory bounds", "thermal throttling and broken platform fallback"),
    ),
    "sound": (
        ("spatial_audio", "Does acoustic location match actual game sources?", "blind rotating-source and occlusion replay", "auditory direction error", "wrong occlusion, distance or front/back inversion"),
        ("mix_intelligibility", "Can important sounds survive dense mixes?", "combat/dialogue/weather loudness-balanced scenarios", "critical signal detection", "speech masking and indiscriminate loudness"),
        ("music_identity", "Does the score establish an original world identity?", "blind theme and motif recognition sessions", "original motif discrimination", "generic motif or known-track resemblance"),
        ("adaptive_music", "Does music follow player agency and tension?", "state-transition replay with event markers", "music-state alignment and transition latency", "late cues or stuck battle loops"),
        ("feedback_sounds", "Are actions audibly differentiated?", "blind action-without-video identification", "action recognition", "reused indistinguishable cues"),
        ("dialogue_performance", "Are lines intelligible and emotionally coherent?", "dialogue accessibility and emotion blind rating", "line intelligibility and context fit", "misaligned delivery or clipping"),
        ("dynamic_range", "Can listeners hear vital cues at safe volume?", "headphone/speaker low-volume sessions", "loudness-safe cue recognition", "sudden peaks and buried narration"),
        ("audio_latency", "Is input/impact sound synchronized with visuals?", "replayed controller, animation and cue timestamp", "audio-visual offset distribution", "buffer drop and jitter spikes"),
        ("silence_design", "Is silence used intentionally in exploration?", "quiet-versus-scored equivalent atmosphere", "tension clarity and listening fatigue", "continuous noise and no contrast"),
        ("hearing_access", "Can deaf/hard-of-hearing users perceive cues?", "subtitles, direction indicators and alternate cues", "cue comprehension parity", "offscreen audio-only objectives"),
        ("audio_platform_fit", "Does audio behave on target audio hardware?", "stereo, mono, handheld and headphones", "mix translation and sample budget", "missing channels and encoder artifacts"),
    ),
    "storyline": (
        ("narrative_causality", "Do events follow understandable causes?", "event-order reconstruction from independent play", "causal comprehension", "unmotivated twists and broken chronology"),
        ("player_agency", "Do choices matter beyond dialogue cosmetics?", "save-state fork with distinct intent decisions", "persistent downstream divergence", "branches with identical unacknowledged outcomes"),
        ("character_consistency", "Do characters retain beliefs and motivations?", "long-horizon dialogue and witness-memory replay", "stable character-model agreement", "unearned personality reversal"),
        ("story_pacing", "Are tension and rest distributed appropriately?", "time-coded story beat analysis", "pacing satisfaction and completion drop-off", "mandatory exposition wall and dead stretch"),
        ("world_lore", "Is lore discoverable, coherent and non-contradictory?", "replay lore clues and optional secrets", "consistent inference and discovery value", "contradictory world rules"),
        ("dialogue_subtext", "Does dialogue support non-literal character intent?", "blind context/subtext interpretation", "understood motivations", "repetitive exposition and missing subtext"),
        ("witness_to_quest", "Do NPC observations initialize plausible quests?", "vary spatial witness, memory, credibility and delay", "correctly justified story/quest triggers", "omniscient quest and rumor treated as fact"),
        ("branch_coverage", "Are all reachable paths narratively complete?", "bounded exhaustive branch traversal", "reachable beat coverage and orphan rate", "dead branch and blocked quest"),
        ("consequence_memory", "Do decisions continue to matter after chapters?", "save/load and distant NPC re-encounter", "persistent event acknowledgment", "memory erased without story reason"),
        ("mystery_fairness", "Can mystery be solved through seeded evidence?", "blind clue acquisition and counterfactual replay", "fair inference and ambiguity control", "unseeded reveal and involuntary spoilers"),
        ("theme_expression", "Are themes dramatized rather than merely stated?", "playtests compare mechanics with thematic claims", "theme comprehension through actions", "lore assertion contradicted by mechanics"),
        ("ending_integrity", "Are ending, endless and postgame modes intentional?", "all terminal and nonterminal world modes", "state consistency and closure fit", "forced victory in inherently endless world"),
        ("emotional_payoff", "Do arcs earn emotional and character stakes?", "blind narrative beat and relationship analysis", "earned emotion and arc continuity", "unearned tragedy or unsupported reward"),
        ("localization_narrative", "Do branches preserve intent across languages?", "cross-locale story choices and UI stress replay", "semantic parity and branching stability", "missing strings and changed choice semantics"),
    ),
}
ALL_FACETS = {name:axis for axis,rows in FACETS.items() for name,*_ in rows}
if len(ALL_FACETS)!=sum(map(len,FACETS.values())):
    raise RuntimeError("facet taxonomy contains duplicate IDs")


@dataclass(frozen=True, slots=True)
class ScriptedProbe:
    subject_id: str
    facet: str
    axis: str
    revision: int
    platform: str
    scenario_digest: str
    protocol_digest: str
    evidence_root: str
    research_receipt: str
    research_status: str
    independent_publishers: int
    questions: tuple[str,...]
    steps: tuple[str,...]
    measurement: str
    adverse_controls: tuple[str,...]
    measurement_is_verified: bool = False

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.rival_scripted_probe.v1",
                    subject_id=self.subject_id,facet=self.facet,axis=self.axis,
                    revision=self.revision,platform=self.platform,
                    scenario_digest=self.scenario_digest,
                    protocol_digest=self.protocol_digest,
                    evidence_root=self.evidence_root,
                    research_receipt=self.research_receipt,
                    research_status=self.research_status,
                    independent_publishers=self.independent_publishers,
                    questions=list(self.questions),steps=list(self.steps),
                    measurement=self.measurement,
                    adverse_controls=list(self.adverse_controls),
                    measurement_is_verified=self.measurement_is_verified,
                    source_copyright_or_media_embedded=False,
                    scripts_are_declarative_not_executed=True)


def compose_deep_probe_scripts(
    original: PlannedOriginalTitle,
    threat: ThreatAssessment,
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    wiki: ReviewedKnowledgeStore,
    rights: RightsLedger,
    links: tuple[RivalSourceLink,...], *,
    platform: str, authorized: bool,
    min_independent_groups: int=2,
)->tuple[ScriptedProbe,...]:
    """Generate the complete nontruncated four-domain analysis script library.

    Source support is a *research assertion*, not a verified playtest score.
    Coverage is explicit: unknown facets still get scripts with a blocker.
    """
    if not authorized:
        raise PermissionError("deep competitor analysis requires reviewed operator scope")
    if (not isinstance(original,PlannedOriginalTitle)
            or not isinstance(threat,ThreatAssessment)
            or threat.original_id!=original.title_id
            or threat.status not in {"enemy","watch"}
            or platform not in original.platforms
            or type(min_independent_groups) is not int
            or not 2<=min_independent_groups<=8
            or type(links) is not tuple
            or any(not isinstance(x,RivalSourceLink) for x in links)):
        raise ThreatRadarError("current typed competitor/authoring plan required")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (brief.scope!="design_reference"
            or brief.owner!=packet.owner
            or brief.knowledge_root!=packet.knowledge_root
            or brief.to_payload()["brief_digest"]!=packet.research_brief_digest
            or canonical_digest([x.to_payload() for x in brief.citations])!=
               canonical_digest([x.to_payload() for x in packet.citations])):
        raise ThreatRadarError("deep analysis Wiki research/rights mismatch")
    mapped={x.source_id:x for x in links}
    if (len(mapped)!=len(links)
            or any(x.source_id not in mapped for x in brief.citations)
            or any(mapped[x.source_id].revision_digest!=x.revision_digest
                   for x in brief.citations)):
        raise ThreatRadarError("deep analysis source lineage missing or stale")
    groups=defaultdict(set)
    traces=defaultdict(set)
    for hit in brief.citations:
        if mapped[hit.source_id].rival_id!=threat.rival_id:
            continue
        if hit.mechanic not in ALL_FACETS or hit.stance!="supports":
            continue
        if hit.confidence_ppm<600000:
            continue
        groups[hit.mechanic].add(hit.dependence_group)
        traces[hit.mechanic].add((hit.source_id,hit.revision_digest,hit.note_id))
    scripts=[]
    for axis,catalog in FACETS.items():
        for facet,question,stimulus,measurement,attack in catalog:
            relevant=tuple(sorted(traces[facet]))
            independent=len(groups[facet])
            status="grounded_hypothesis" if independent>=min_independent_groups else "await_independent_research"
            scenario=canonical_digest({
                "original_design":original.design_digest,
                "rival_id":threat.rival_id,
                "domain":axis,"facet":facet,"platform":platform,
                "revision":1,"test_type":"original_cross_game_controlled_replay"})
            protocol=canonical_digest({
                "facet":facet,"stimulus":stimulus,"measurement":measurement,
                "adverse_control":attack,"version":1,
                "same_scenario_required_on_original_and_rival":True})
            steps=(
                "Freeze exact build/platform, controller, camera, performance budget and player cohort.",
                "Acquire operator-approved lawful gameplay observations without copying protected source assets.",
                "Run a seeded normal-case independent replay: "+stimulus+".",
                "Run the negative/fault control: "+attack+".",
                "Collect timestamped/per-frame/participant raw measurements with anonymized consent.",
                "Blind score both games under one declared protocol with separate evaluators and uncertainty intervals.",
                "Red-team suspected weakness with a matched control; label unknown until actually measured.",
                "Record critical accessibility, rights and originality vetoes before suggesting improvements.",
            )
            scripts.append(ScriptedProbe(
                threat.rival_id,facet,axis,1,platform,scenario,protocol,
                brief.knowledge_root,
                canonical_digest([packet.to_payload()["packet_digest"],relevant]),
                status,independent,(question,),steps,measurement,
                (attack,"test source-agnostic counterfactual metadata",
                 "compare independently authored original alternatives")))
    return tuple(scripts)


@dataclass(frozen=True,slots=True)
class FacetMeasurement:
    """An HMAC-verified measurement; signing keys are operator-issued.

    The evaluator's cryptographic key proves possession, not independent human
    identity, truth of footage, or a scientifically calibrated confidence CI.
    """
    script_digest: str
    subject_id: str
    evaluator_id: str
    score_bp: int
    lower_bp: int
    upper_bp: int
    participant_count: int
    replay_receipt_digest: str
    observed_at: str
    signature: str

    def __post_init__(self):
        for name in ("script_digest","replay_receipt_digest","signature"):
            _sha(getattr(self,name),name)
        _id(self.subject_id,"measured title")
        _id(self.evaluator_id,"evaluator")
        _date(self.observed_at)
        for name in ("score_bp","lower_bp","upper_bp"):
            val=getattr(self,name)
            if type(val) is not int or not 0<=val<=10000:
                raise ThreatRadarError("score confidence interval must be 0..10000 basis points")
        if not self.lower_bp<=self.score_bp<=self.upper_bp:
            raise ThreatRadarError("score outside claimed confidence interval")
        if type(self.participant_count) is not int or not 10<=self.participant_count<=100000:
            raise ThreatRadarError("real repeated participants/replays required")

    def body(self):
        return dict(schema="skeleton.game_builder.facet_measurement.v1",
                    script_digest=self.script_digest,subject_id=self.subject_id,
                    evaluator_id=self.evaluator_id,score_bp=self.score_bp,
                    lower_bp=self.lower_bp,upper_bp=self.upper_bp,
                    participant_count=self.participant_count,
                    replay_receipt_digest=self.replay_receipt_digest,
                    observed_at=self.observed_at)

    def payload(self):
        return dict(self.body(),signature=self.signature)


def sign_facet_measurement(row: FacetMeasurement,
                           signer: TrustedCompetitionJudge)->FacetMeasurement:
    from dataclasses import replace
    if (not isinstance(row,FacetMeasurement) or
            not isinstance(signer,TrustedCompetitionJudge)
            or signer.judge_id!=row.evaluator_id):
        raise ThreatRadarError("measured facet signer does not own evaluation identity")
    return replace(row,signature=_mac(row.body(),signer.key))


@dataclass(frozen=True,slots=True)
class FacetVerdict:
    script_digest: str
    facet: str
    axis: str
    status: str
    rival_conservative_upper_bp: int|None
    original_conservative_lower_bp: int|None
    cohort_groups: int
    signed_measurements: int
    gap_to_outperform_bp: int|None
    blockers: tuple[str,...]

    def payload(self):
        return dict(schema="skeleton.game_builder.facet_verdict.v1",
                    script_digest=self.script_digest,facet=self.facet,axis=self.axis,
                    status=self.status,
                    rival_conservative_upper_bp=self.rival_conservative_upper_bp,
                    original_conservative_lower_bp=self.original_conservative_lower_bp,
                    cohort_groups=self.cohort_groups,
                    signed_measurements=self.signed_measurements,
                    gap_to_outperform_bp=self.gap_to_outperform_bp,
                    blockers=list(self.blockers),
                    reported_weakness_verified=self.status=="verified_weakspot",
                    cannot_infer_absent_measurements_as_failure=True)


def score_deep_scripts(
    scripts: tuple[ScriptedProbe,...],
    rival: str,
    original: str,
    measurements: tuple[FacetMeasurement,...],
    judges: tuple[TrustedCompetitionJudge,...], *,
    as_of: str, authorized: bool, margin_bp: int=150,
    independent_judges: int=2,
    max_age_days: int=180,
    industry_floors: dict[str,int]|None=None,
)->tuple[FacetVerdict,...]:
    """Full-coverage fail-closed scoring, no truncation or made-up superiority.

    Verified weakspot means rival's conservative upper CI is below an
    independently predeclared *industry benchmark floor*, not that a reviewer
    disliked its art. An unverified self-declared floor cannot be supplied
    silently: without explicit benchmark levels, only 'gap' is reported.
    """
    if not authorized:
        raise PermissionError("scored competitor scripts require operator authority")
    if (type(scripts) is not tuple or not scripts or
            len({x.digest for x in scripts})!=len(scripts)
            or any(not isinstance(x,ScriptedProbe) for x in scripts)
            or type(measurements) is not tuple or len(measurements)>10000
            or any(not isinstance(x,FacetMeasurement) for x in measurements)
            or type(judges) is not tuple or
            any(not isinstance(x,TrustedCompetitionJudge) for x in judges)
            or len({x.judge_id for x in judges})!=len(judges)
            or type(margin_bp) is not int or not 50<=margin_bp<=2000
            or type(independent_judges) is not int or not 2<=independent_judges<=8
            or type(max_age_days) is not int or not 1<=max_age_days<=365):
        raise ThreatRadarError("typed bounded full-coverage facet evaluation required")
    _id(rival,"rival title");_id(original,"original title")
    stamp=_date(as_of)
    trusted={x.judge_id:x for x in judges}
    scripts_by_digest={x.digest:x for x in scripts}
    by_script=defaultdict(lambda:defaultdict(list))
    seen=set()
    for row in measurements:
        if row.script_digest not in scripts_by_digest or row.subject_id not in {rival,original}:
            raise ThreatRadarError("facet score attempts cross-title or cross-script injection")
        signer=trusted.get(row.evaluator_id)
        if signer is None or not hmac.compare_digest(
                row.signature,_mac(row.body(),signer.key)):
            raise ThreatRadarError("forged, unsigned or unknown facet evaluator")
        when=_date(row.observed_at)
        if when>stamp or (stamp-when).days>max_age_days:
            raise ThreatRadarError("facet measurement stale or from future")
        identity=(row.script_digest,row.subject_id,row.evaluator_id)
        if identity in seen:
            raise ThreatRadarError("duplicate evaluator replay cannot inflate independent coverage")
        seen.add(identity)
        by_script[row.script_digest][row.subject_id].append(row)
    if industry_floors is not None and (
            type(industry_floors) is not dict or
            set(industry_floors)-{x.facet for x in scripts} or
            any(type(v) is not int or not 0<=v<=10000
                for v in industry_floors.values())):
        raise ThreatRadarError("predeclared bounded external industry facet floors required")
    results=[]
    for script in scripts:
        ours=by_script[script.digest][original]
        theirs=by_script[script.digest][rival]
        blockers=[]
        if script.research_status!="grounded_hypothesis":
            blockers.append("missing_independent_source_context")
        if len(ours)<independent_judges or len(theirs)<independent_judges:
            blockers.append("insufficient_independent_measured_replays")
        if len({r.evaluator_id for r in ours})<independent_judges or len({
                r.evaluator_id for r in theirs})<independent_judges:
            blockers.append("independent_evaluator_requirement_not_met")
        our_lower=min((row.lower_bp for row in ours),default=None)
        rival_upper=max((row.upper_bp for row in theirs),default=None)
        shortfall=(None if our_lower is None or rival_upper is None
                   else max(0,rival_upper+margin_bp-our_lower))
        # Absolute weakness needs a separately provided industry bar; caller
        # is responsible for provenance, and verdict never attests its accuracy.
        floor=(industry_floors or {}).get(script.facet)
        weakspot=(not blockers and floor is not None
                  and rival_upper is not None and rival_upper<floor)
        if blockers:
            status="insufficient_evidence"
        elif weakspot:
            status="verified_weakspot"
        elif shortfall and shortfall>0:
            status="outwork_required"
        else:
            status="competitive_margin_met"
        results.append(FacetVerdict(
            script.digest,script.facet,script.axis,status,rival_upper,our_lower,
            script.independent_publishers,len(ours)+len(theirs),
            shortfall,tuple(sorted(set(blockers)))))
    return tuple(results)


__all__=["FACETS","ALL_FACETS","ScriptedProbe","FacetMeasurement",
         "FacetVerdict","compose_deep_probe_scripts",
         "sign_facet_measurement","score_deep_scripts"]
