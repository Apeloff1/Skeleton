"""Turn verified enemy weaknesses and genre history into original build recipes.

Recipes are deterministic, bounded, actionable game-development work with
engine-facing stages, controlled validation and original identity protection.
They never copy a rival's implementation or mistake a proposed change for
installed game code. Advancement requires *new* signed replay evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import canonical_digest
from .competitive_title_radar import PlannedOriginalTitle,ThreatAssessment,ThreatRadarError,_sha
from .competitive_deep_analysis import ScriptedProbe,FacetVerdict,ALL_FACETS
from .competitive_evolution_chain import RivalEvolutionChain

# Structured implementation recipes, not competitor-derived scripts. Each
# refers to an original technique and a verifiable acceptance signal.
REMEDIATIONS={
    "gameplay": (
        "Prototype new deterministic input-to-world state flow with scripted replay fixtures.",
        "Author original systems and NPC response state machines; record meaningful path changes.",
        "Run mirrored novice/expert encounters and negative/fault controls across hardware tiers.",
        "Profile response, agency, accessibility and stability on the named target platform.",
    ),
    "graphics": (
        "Create a new title-owned visual grammar, silhouettes, palette and scene hierarchy.",
        "Build adaptive LOD/animation/effects budget rules without imitating known rivals.",
        "Test low resolution, HDR/SDR, color-vision variants and motion/FX overload scenes.",
        "Measure real hardware frame pacing, legibility and controlled viewer recognition.",
    ),
    "sound": (
        "Compose original musical motifs and source-owned interactive sonic rules.",
        "Implement dynamic audio mixing, events, spatialization and caption parity.",
        "Stress simultaneous dialogue, effects and music with volume/mono/headphone controls.",
        "Measure cue comprehension, audio latency, loudness safety and emotional coherence.",
    ),
    "storyline": (
        "Author new character intent, causality and distinctive world-history constraints.",
        "Compile event-witness-memory-to-quest branches with deterministic state traces.",
        "Replay counterfactual choices, distant consequences, unresolved/postgame endings.",
        "Blind test story continuity, agency, localization and meaningful player decisions.",
    ),
}
AXIS_GUARDS={
    "gameplay": ("state_integrity","accessibility","rights_provenance_safety"),
    "graphics": ("accessibility","performance","rights_provenance_safety"),
    "sound": ("accessibility","performance","rights_provenance_safety"),
    "storyline": ("longform_consistency","originality","rights_provenance_safety"),
}


@dataclass(frozen=True,slots=True)
class OriginalCounterproposal:
    original_id: str
    rival_id: str
    facet: str
    domain: str
    analysis_digest: str
    evolution_digest: str
    starting_original_lower_bp: int|None
    rival_upper_bp: int|None
    target_lower_bp: int|None
    originality_pillars: tuple[str,...]
    lineage_chain_ids: tuple[str,...]
    delivery_priority: int
    work_scripts: tuple[str,...]
    adversarial_acceptance: tuple[str,...]
    protected_gates: tuple[str,...]
    needs_new_evidence: bool

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.rival_original_counterproposal.v1",
            original_id=self.original_id,rival_id=self.rival_id,
            facet=self.facet,domain=self.domain,
            analysis_digest=self.analysis_digest,
            evolution_digest=self.evolution_digest,
            starting_original_lower_bp=self.starting_original_lower_bp,
            rival_upper_bp=self.rival_upper_bp,
            target_lower_bp=self.target_lower_bp,
            originality_pillars=list(self.originality_pillars),
            lineage_chain_ids=list(self.lineage_chain_ids),
            delivery_priority=self.delivery_priority,
            work_scripts=list(self.work_scripts),
            adversarial_acceptance=list(self.adversarial_acceptance),
            protected_gates=list(self.protected_gates),
            needs_new_evidence=self.needs_new_evidence,
            actual_game_implementation_completed=False,
            release_approved=False,
            copy_competitor_expression=False)


def propose_original_outclassing(
    planned: PlannedOriginalTitle,
    threat: ThreatAssessment,
    chain: RivalEvolutionChain,
    scripts: tuple[ScriptedProbe,...],
    verdicts: tuple[FacetVerdict,...], *,
    authorized: bool, margin_bp: int=150,
    max_tasks: int=160,
)->tuple[OriginalCounterproposal,...]:
    if not authorized:
        raise PermissionError("competitive original development planning requires operator authority")
    if (not isinstance(planned,PlannedOriginalTitle)
            or not isinstance(threat,ThreatAssessment)
            or threat.original_id!=planned.title_id
            or threat.status!="enemy"
            or not isinstance(chain,RivalEvolutionChain)
            or chain.enemy_id!=threat.rival_id
            or type(scripts) is not tuple or type(verdicts) is not tuple
            or len(scripts)!=len(verdicts) or not 1<=len(scripts)<=256
            or len({x.digest for x in scripts})!=len(scripts)
            or any(not isinstance(x,ScriptedProbe) for x in scripts)
            or any(not isinstance(x,FacetVerdict) for x in verdicts)
            or type(margin_bp) is not int or not 50<=margin_bp<=2000
            or type(max_tasks) is not int or not 1<=max_tasks<=256):
        raise ThreatRadarError("full same-title analysis, evolution and quality verdicts required")
    script_map={s.digest:s for s in scripts}
    existing=set()
    proposed=[]
    for verdict in verdicts:
        script=script_map.get(verdict.script_digest)
        if (script is None or script.facet!=verdict.facet
                or script.axis!=verdict.axis
                or script.subject_id!=threat.rival_id
                or script.revision!=1
                or verdict.facet in existing):
            raise ThreatRadarError("analysis/evidence identity mismatch or duplicate facet")
        existing.add(verdict.facet)
        if verdict.status=="competitive_margin_met":
            continue
        if verdict.facet not in ALL_FACETS:
            raise ThreatRadarError("unknown analysis facet could become unbounded executable proposal")
        # Evidence gaps are research/experiment work, never claimed rival flaws.
        unexplained=(verdict.status=="insufficient_evidence" or
                     verdict.rival_conservative_upper_bp is None or
                     verdict.original_conservative_lower_bp is None)
        rival_upper=verdict.rival_conservative_upper_bp
        own_lower=verdict.original_conservative_lower_bp
        target=(min(10000,rival_upper+margin_bp)
                if rival_upper is not None else None)
        if target is not None and rival_upper+margin_bp>10000:
            unexplained=True
        if not chain.complete_competitor_coverage:
            # Research gaps remain visible but still produce original practice
            # and scripted evidence tasks without pretending verified ancestry.
            ancestry_goal=("Research missing comparable genre generations: "+
                           ", ".join(chain.unresolved_ancestry),)
        else:
            ancestry_goal=("Benchmark the same original design against every "
                           "reviewed comparable generation in the evidence chain.",)
        common=(
            "Do not incorporate a rival's copyrighted art, composition, dialogue, levels, code, branding or exact expressive layout.",
            "Derive candidate solutions from original identity pillars: "+
            ", ".join(planned.identity_pillars)+".",
            "Require independent blind original/rival game replay on the same protected experiment script.",
            "Fail if accessibility, IP similarity, reproducibility, platform budget or original identity regress.",
        )
        work=("Rebuild this facet using the title-owned signature: "+
              ", ".join(planned.identity_pillars)+".",)+(
            ("First gather independently reviewed source and original-game experiment evidence.",)
            if unexplained else (
                "Implement and test an original improvement to "+verdict.facet+
                " without borrowing competitor expression.",
            )
        )+REMEDIATIONS[script.axis]+ancestry_goal
        acceptance=(
            "Re-run exact protocol "+script.protocol_digest+
            " with frozen scenario "+script.scenario_digest+".",
            "Collect independently signed, repeated measurements from both titles plus an industry comparison cohort.",
            "Show the original game's conservative lower bound exceeds the rival's upper bound by the predeclared margin.",
            "Capture identical before/after original-game evidence and perform a blind adversarial reviewer pass.",
            "Retain all title-specific pillars and clearance of source and assets through the canonical RightsLedger.",
        )+common
        gap=(10000 if unexplained else
             max(0,(target or 10000)-(own_lower or 0)))
        urgency=min(100000,10*gap+
                    (20000 if verdict.status=="verified_weakspot" else 0)+
                    (10000 if script.axis in {"gameplay","storyline"} else 0))
        proposed.append(OriginalCounterproposal(
            planned.title_id,threat.rival_id,verdict.facet,script.axis,
            script.digest,chain.digest,own_lower,rival_upper,target,
            planned.identity_pillars,
            tuple(stage.title_id for stage in chain.stages),
            urgency,work,acceptance,AXIS_GUARDS[script.axis],
            unexplained))
    if len(proposed)>max_tasks:
        raise ThreatRadarError("full counterproposal workload exceeds one bounded batch; explicit partition required")
    return tuple(sorted(proposed,key=lambda p:(-p.delivery_priority,p.domain,p.facet)))


@dataclass(frozen=True,slots=True)
class OutclassingEvaluation:
    counterproposal_digest: str
    resulting_original_lower_bp: int|None
    verified_rival_upper_bp: int|None
    fulfilled: bool
    quality_gain_bp: int|None
    reasons: tuple[str,...]
    independently_measured: bool

    def payload(self):
        return dict(
            schema="skeleton.game_builder.outclassing_evaluation.v1",
            counterproposal_digest=self.counterproposal_digest,
            resulting_original_lower_bp=self.resulting_original_lower_bp,
            verified_rival_upper_bp=self.verified_rival_upper_bp,
            fulfilled=self.fulfilled,
            quality_gain_bp=self.quality_gain_bp,
            reasons=list(self.reasons),
            independently_measured=self.independently_measured,
            game_release_authorized=False,
            only_real_game_replay_can_prove_implementation=True)


def evaluate_original_counterproposal(
    proposal: OriginalCounterproposal,
    before: FacetVerdict,after: FacetVerdict,*,
    replay_implementation_digest: str|None,
    originality_review_passed: bool,
    protected_quality_gates_passed: bool,
    authorized: bool,minimum_gain_bp: int=50,
)->OutclassingEvaluation:
    if not authorized:
        raise PermissionError("outclassing candidate requires operator attestation")
    if (not isinstance(proposal,OriginalCounterproposal)
            or not isinstance(before,FacetVerdict)
            or not isinstance(after,FacetVerdict)
            or before.script_digest!=proposal.analysis_digest
            or after.script_digest!=proposal.analysis_digest
            or before.facet!=proposal.facet or after.facet!=proposal.facet
            or before.axis!=proposal.domain or after.axis!=proposal.domain
            or type(originality_review_passed) is not bool
            or type(protected_quality_gates_passed) is not bool
            or type(minimum_gain_bp) is not int
            or not 1<=minimum_gain_bp<=1000):
        raise ThreatRadarError("same-rubric before/after original-game evidence required")
    if replay_implementation_digest is not None:
        _sha(replay_implementation_digest,"actual new replayed build")
    reasons=[]
    if replay_implementation_digest is None:
        reasons.append("no_implemented_original_game_replay")
    if not originality_review_passed:
        reasons.append("independent_originality_gate_missing")
    if not protected_quality_gates_passed:
        reasons.append("protected_accessibility_security_or_rights_regression")
    if (after.status=="insufficient_evidence" or
            after.original_conservative_lower_bp is None or
            after.rival_conservative_upper_bp is None):
        reasons.append("new_signed_gameplay_evaluation_missing")
    if (before.original_conservative_lower_bp is None or
            before.rival_conservative_upper_bp is None):
        reasons.append("original_baseline_evaluation_missing")
    gain=(None if before.original_conservative_lower_bp is None
          or after.original_conservative_lower_bp is None else
          after.original_conservative_lower_bp-before.original_conservative_lower_bp)
    if gain is None or gain<minimum_gain_bp:
        reasons.append("no_measurable_original_game_optimization_gain")
    if (after.rival_conservative_upper_bp is not None
            and proposal.rival_upper_bp is not None
            and after.rival_conservative_upper_bp<proposal.rival_upper_bp):
        reasons.append("competitor_reference_regressed_or_changed")
    if (proposal.target_lower_bp is None or
            after.original_conservative_lower_bp is None or
            after.original_conservative_lower_bp<proposal.target_lower_bp):
        reasons.append("outclassing_margin_not_proved")
    return OutclassingEvaluation(
        proposal.digest,after.original_conservative_lower_bp,
        after.rival_conservative_upper_bp,not reasons,gain,
        tuple(sorted(set(reasons))),
        after.original_conservative_lower_bp is not None)


__all__=["REMEDIATIONS","OriginalCounterproposal",
         "OutclassingEvaluation","propose_original_outclassing",
         "evaluate_original_counterproposal"]
