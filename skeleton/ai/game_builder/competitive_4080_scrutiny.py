"""Evidence-first, nonoverlapping 4,080-probe scrutiny program.

102 independent game facets x (10 historical foundation probes + 10 live
rival probes + 20 future original-design probes) = exactly 4,080 authored
experiment INSTANCES, each with its own condition, observable, adversarial
control, source authority, privacy boundary and acceptance criterion.

The 40 experimental *lenses* are authored here. Resulting 4,080 scenarios
are a systematic matrix, not 4,080 independently hand-written papers or
4,080 completed game tests. No probe gains a measured status without
externally authenticated trace and research evidence. Research is separated
by narrative time window and cannot be laundered between rounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter,defaultdict

from .contracts import canonical_digest
from .competitive_deep_analysis import FACETS,ALL_FACETS
from .competitive_title_radar import ThreatRadarError,_sha,_date,_id
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
import hmac

TIMES=("historical_prologue","contemporary_conflict","future_epilogue")
STAGES=("ancestral_foundations","enemy_confrontation","constructive_transformation")
SIZES=(1020,1020,2040)
ROLE_NAMES=("dragon","jeeves","adversarial")
# lens ID, independent falsification axis, perturbation, comparison,
# observable quantitative measure, nondegradation/information control.
FOUNDATIONS=(
 ("origin_dependency","which prior genre constraint created this limitation","remove one dependency from the predecessor baseline","matched earlier-era original controls","unexplained dependency incidence","no unsupported causal ancestry"),
 ("archival_fidelity","which historical build/platform version exhibits this behavior","repeat source-published reference states across hardware generations","stable archived version versus emulated target","hardware-specific trace disagreements","separate historical rights from modern gameplay"),
 ("genre_invariant","which game genre requirement survives across generations","change a nonessential rule while holding genre premise constant","minimal genre rule versus era-era adaptations","mechanic invariants broken","no genre tag substitutes for play evidence"),
 ("historical_accessibility","who could perceive or control the original convention","replay with remapped inputs and assistive-mode reconstruction","era-era input/access needs","parity of completion","distinguish era hardware constraints from defects"),
 ("legacy_failure","which older design shortcut introduced repeated player failures","inject known historical failure with deterministic seed","baseline and prior-patch states","avoidable error incidence","separate anecdote from reproducible bug"),
 ("retained_strength","what made the prior implementation worthwhile","ablate one valuable player choice or cue","original predecessor and intentionally simplified control","player-value effect with confidence bounds","do not indiscriminately destroy beloved style"),
 ("era_resource_budget","what memory, render and audio resources were genuinely available","apply authentic per-platform CPU/GPU/RAM/storage envelopes","original-era and modern target budgets","sustained quality versus resource cost","do not confuse hardware inability with poor design"),
 ("published_peer_claim","does independent commentary match observed play","blind recode an independently published claim and evidence","source claim versus observed authentic build","verified reproduction fraction","repost clusters count as one evidence group"),
 ("creative_signature","which expressive features were unique to predecessor","remove all protected art/characters/arrangements from reference features","abstract mechanics versus specific expression","similarity risk and identity separation","reuse insights only if legally permitted"),
 ("early_failure_repair","did the next comparable title measurably fix the same gap","replay issue before and after published change when lawful","historical predecessor versus documented successor","verified improvement and regression","no influence assertion without explicit evidence"),
)
CONFRONTATION=(
 ("matched_skill","does apparent rival advantage survive skill matching","counterbalance novice/intermediate/expert player groups","same task, players and skill strata","stratified success difference","no player selection advantage"),
 ("challenge_load","does rival performance persist at worst-case state complexity","stress NPCs, sound, physics and rendering with equivalent scene intent","normal and worst-case equivalent replay","tail failures and user-visible stutter","exclude unrelated load effects"),
 ("input_variation","is opponent success contingent on a specific controller","swap legally usable input accessibility profiles","game-native and remapped control methods","precision/completion parity","no proprietary peripheral dependency"),
 ("gameplay_counterfactual","does removal of one purported strength change outcome","ablate one user-visible game mechanic in original controlled prototype","paired with/without mechanic game state","attributable player value delta","do not copy rival exact mechanics"),
 ("perception_blind","does nonbranded game presentation retain the claimed benefit","blind-score equivalent tasks without title identity and marketing","blinded visual/audio/story labels","perception gain with uncertainty","no publisher reputation proxy"),
 ("genre_neighbor","is the weakness rival-specific or shared genre constraint","compare two lawful independent similar-era titles and target","same genre matched representative game cohort","within-genre variation","never label a weakness as fact from metadata"),
 ("stress_failure","can an adversarial state falsify the rival strength","inject player/NPC interruption, disconnect or asset load fault","equivalent normal/stress controls","recovery failures and lasting damage","protect real player data and privacy"),
 ("cross_platform_parity","does claimed advantage survive destination platform","repeat task on supported device and display budgets","desktop/console/handheld matched capability tier","frame/cue/story parity","different features must be reported, not hidden"),
 ("consequence_horizon","does quality survive beyond one flashy encounter","replay result after chapter, save/load and world-state evolution","immediate result versus delayed consequence","persistent acknowledgment fraction","never infer storyline from trailer"),
 ("verified_enemy_weakness","does measured weakness exceed an independent quality baseline","validate adverse outcome with repeat source-neutral tester cohorts","rival, original, industry cohort, same script","nonoverlapping conservative intervals","requires qualified signed source and player evidence"),
)
TRANSFORMATION=(
 ("original_mechanic","can a new original system surpass the abstract quality objective","create source-owned mechanic with at least two alternate tactics","original build versus abstraction-only baseline","meaningful strategy diversity improvement","no direct competitor expression"),
 ("player_agency","do new game choices have causally distinct long-term effects","fork identical save with mutually exclusive user choices","branch A/B original-game consequence","persistent divergence without inconsistency","cannot force winning story mode"),
 ("npc_witness","do NPCs only respond to witnessed or credibly learned events","hide/reveal events across sight, rumor, delay, deception","present/absent/rumor NPC memory","epistemic decision accuracy","no omniscient NPC quest initiation"),
 ("resource_efficiency","can the new original idea meet consumer-grade hardware","profile LOD, streaming, CPU, memory and audio budget under stress","before/after equivalent hardware scene","tail latency and feature quality gain","no fake benchmark optimizations"),
 ("visual_grammar","does original art improve legibility and remain recognizably own","author new silhouettes, lighting, material language and composition","blind original/new and competitor-dissimilarity assessment","readability gain and originality retention","no protected asset imitation"),
 ("audio_identity","does original music and feedback convey meaning accessibly","compose new motifs, spatial feedback, ducking, captions and silence","mono/headphone/loud-scene matched tasks","cue accuracy, latency and discomfort","no imported melody or arrangement"),
 ("story_architecture","does plot stay causal under unsolved and postgame worlds","replay original factions, lore, endings and no-ending state rules","initial/mid/postgame world states","contradiction-free narrative reachability","no copied character or plot"),
 ("quest_recovery","can divergent quests recover from NPC loss, rewinds and save changes","fault-inject death/relocation/cancel at every story checkpoint","normal/fault story loops","reachable resolution and no orphan quests","loss is sometimes an intentional consequence"),
 ("accessibility_parity","can assistive settings retain comparable game agency","run impairment-representative controls and perception alternatives","default/assist matched player tasks","completion parity and retained satisfaction","not just contrast screenshot tests"),
 ("performance_regression","does feature quality remain after stress and content growth","cross-batch benchmark with deterministic seeded scale growth","earlier/new candidate on equal target hardware","99th percentile latency and memory","new feature must not destroy responsiveness"),
 ("legal_originality","does every deliverable preserve title identity and source rights","separate historical idea, protected expression and training-use permission","signed copyright and design identity review","unresolved similarity risk","do not train from reference-only rights"),
 ("security_privacy","does research or telemetry reveal personal or secret information","fuzz logs, player profiles, crawler URL handling and exports","safeguarded and attacker-modified inputs","privacy/secret leak count","rights/adversarial may veto"),
 ("localization","do story and sound choices remain faithful across locales","replay 5 locale input/voice/text variants and branch decisions","source locale versus localized gameplay","semantic/equality parity","no untranslated mandatory cues"),
 ("regime_change","does AI adapt to new player/meta behavior without catastrophic drift","rotate skill, genre style, seed and hardware regimes","frozen model baseline versus staged candidate","worst-regime quality delta","no self-promotion without heldout evaluation"),
 ("training_provenance","can distilled source knowledge be proved legal, fresh and independent","revoke one paper/video/blog and recompute downstream approvals","old and revoked source snapshots","unlearning/revocation propagation","facts-reference is not training permission"),
 ("multi_agent_contestation","can three distinct evaluators overturn fragile conclusions","introduce counterevidence and blind counter-arguments","Dragon/Jeeves/Adversarial separate signed claims","resolved objections and residual uncertainty","same LLM prompts do not create independent truth"),
 ("continuous_world","does the game remain meaningful without terminal win conditions","repeat world changes across seasonal/cyclic/nonterminal arcs","completion/never-ending sandbox baselines","ongoing agency and causal history","do not force a scripted victory"),
 ("player_learning","does system enhance discoverability, not arbitrary difficulty","longitudinal randomized player onboarding and mastery trials","before/after independent cohort study","skill retention and friction reduction","respect privacy and statistical validity"),
 ("counterproposal_ablation","which original proposed change produced actual value","remove a single new capability after independent implementation","new build versus ablated candidate","effect size and confounding control","avoid backfilled success metrics"),
 ("epilogue_audit","does the final candidate survive cumulative regression and peer review","replay all prior validated failure modes with fresh holdout cohort","original, rival, ancestry and independent postgame worlds","complete protected-axis nonregression","no release/weight promotion without user approval"),
)
LENSES=(FOUNDATIONS,CONFRONTATION,TRANSFORMATION)
if tuple(len(x) for x in LENSES)!=(10,10,20):
    raise RuntimeError("4,080 probe matrix must use 10/10/20 independently authored lenses")
if len({t[0] for level in LENSES for t in level})!=40:
    raise RuntimeError("scrutiny lenses must be wholly disjoint across times")


@dataclass(frozen=True,slots=True)
class CampaignProbe:
    probe_id: str
    round_number: int
    time_window: str
    stage: str
    domain: str
    facet: str
    lens: str
    hypothesis: str
    intervention: str
    comparison: str
    measurement: str
    integrity_rule: str
    scenario_digest: str
    protocol_digest: str
    research_receipt: str
    tested: bool=False

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.scrutiny_campaign_probe.v1",
            probe_id=self.probe_id,round_number=self.round_number,
            time_window=self.time_window,stage=self.stage,
            domain=self.domain,facet=self.facet,lens=self.lens,
            hypothesis=self.hypothesis,intervention=self.intervention,
            comparison=self.comparison,measurement=self.measurement,
            integrity_rule=self.integrity_rule,
            scenario_digest=self.scenario_digest,
            protocol_digest=self.protocol_digest,
            research_receipt=self.research_receipt,tested=self.tested,
            actual_playtest_performed=False,
            independent_peer_identity_not_inferred=True)


@dataclass(frozen=True,slots=True)
class CampaignCatalog:
    original_id: str
    design_digest: str
    probes: tuple[CampaignProbe,...]
    role_obligations: tuple[str,...]=ROLE_NAMES

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.4080_scrutiny_catalog.v1",
                    original_id=self.original_id,
                    design_digest=self.design_digest,
                    probe_ids=[p.probe_id for p in self.probes],
                    per_round=[sum(p.round_number==i for p in self.probes)
                               for i in (1,2,3)],
                    role_obligations=list(self.role_obligations),
                    tested_count=sum(p.tested for p in self.probes),
                    total_role_probe_obligations=len(self.probes)*3,
                    source_promotion_from_generation=False)


def build_scrutiny_campaign(original_id: str,design_digest: str,
                            research_receipts: tuple[str,str,str],*,
                            authorized: bool)->CampaignCatalog:
    if not authorized:
        raise PermissionError("large game scrutiny campaign requires studio permission")
    _id(original_id,"original project ID")
    _sha(design_digest,"original design")
    if (type(research_receipts) is not tuple or len(research_receipts)!=3
            or len(set(research_receipts))!=3):
        raise ThreatRadarError("three nonoverlapping source-evidence roots required")
    for receipt in research_receipts:
        _sha(receipt,"separate reviewed research receipt")
    if len(ALL_FACETS)!=102:
        raise ThreatRadarError("game scrutiny must include exactly 102 real foundational facets")
    catalog=[]
    for level,(stage,time,lenses,receipt) in enumerate(
        zip(STAGES,TIMES,LENSES,research_receipts),1):
        for domain,facets in FACETS.items():
            for facet,question,stimulus,measurement,attack in facets:
                for lens_id,question_lens,mutation,control,observable,guard in lenses:
                    scenario=canonical_digest([
                        original_id,design_digest,level,time,domain,
                        facet,lens_id,receipt])
                    protocol=canonical_digest([
                        "game_studio_scrutiny_2026_10_v1",level,domain,
                        facet,question,stimulus,measurement,attack,
                        lens_id,question_lens,mutation,control,observable,guard])
                    catalog.append(CampaignProbe(
                        f"r{level}_{domain}_{facet}_{lens_id}",
                        level,time,stage,domain,facet,lens_id,
                        f"{question} Determine {question_lens} for '{facet}' "
                        f"under the {time} evidence window.",
                        f"Baseline controlled trial: {stimulus}. "
                        f"Independent experimental mutation: {mutation}. "
                        f"Adversarial failure: {attack}.",
                        f"{control}; use identical frozen task intent, player "
                        "population and declared hardware limitations.",
                        f"{measurement}; independently also quantify {observable} "
                        "with a predeclared direction, units, confidence and sample budget.",
                        f"{guard}; preserve title-owned creative identity, source "
                        "consent, accessibility and legally permitted comparisons.",
                        scenario,protocol,receipt,False))
    ids=[p.probe_id for p in catalog]
    if (len(ids)!=4080 or len(set(ids))!=4080
            or tuple(sum(p.round_number==r for p in catalog) for r in (1,2,3))!=SIZES
            or len({(p.facet,p.lens) for p in catalog})!=4080):
        raise ThreatRadarError("every scrutiny must be unique with exact full-coverage counts")
    return CampaignCatalog(original_id,design_digest,tuple(catalog))


@dataclass(frozen=True,slots=True)
class ProbeEvidenceReceipt:
    probe_digest: str
    experiment_result_digest: str
    source_packet_digest: str
    signers: tuple[str,...]
    signed_at: str
    empirical_status: str
    failure_codes: tuple[str,...]

    def __post_init__(self):
        _sha(self.probe_digest,"experiment identity")
        _sha(self.experiment_result_digest,"experiment results")
        _sha(self.source_packet_digest,"licensed research packet")
        if (type(self.signers) is not tuple or len(self.signers)<2
                or len(set(self.signers))!=len(self.signers)
                or self.empirical_status not in {"measured","refuted","inconclusive"}
                or type(self.failure_codes) is not tuple):
            raise ThreatRadarError("two independent experiment witnesses and honest status required")
        for signer in self.signers:
            _id(signer,"replay evaluator ID")
        _date(self.signed_at)

    def payload(self):
        return dict(schema="skeleton.game_builder.4080_probe_evidence.v1",
                    probe_digest=self.probe_digest,
                    experiment_result_digest=self.experiment_result_digest,
                    source_packet_digest=self.source_packet_digest,
                    signers=list(self.signers),signed_at=self.signed_at,
                    empirical_status=self.empirical_status,
                    failure_codes=list(self.failure_codes),
                    actual_training_weights_changed=False)


@dataclass(frozen=True,slots=True)
class ProbeCoverageReport:
    original_id: str
    catalog_digest: str
    per_round_tested: tuple[int,int,int]
    per_round_missing: tuple[int,int,int]
    independent_role_obligations: int
    verified_passes: int
    unresolved_failures: int
    promotion_eligible: bool

    def payload(self):
        return dict(schema="skeleton.game_builder.scrutiny_coverage.v1",
                    original_id=self.original_id,catalog_digest=self.catalog_digest,
                    per_round_tested=list(self.per_round_tested),
                    per_round_missing=list(self.per_round_missing),
                    independent_role_obligations=self.independent_role_obligations,
                    verified_passes=self.verified_passes,
                    unresolved_failures=self.unresolved_failures,
                    promotion_eligible=self.promotion_eligible,
                    complete_evidence_not_implied_by_catalog_generation=True)


def audit_scrutiny_campaign(
    catalog: CampaignCatalog,
    evidence: tuple[ProbeEvidenceReceipt,...],*,
    authorized: bool,
)->ProbeCoverageReport:
    if not authorized:
        raise PermissionError("full-catalog promotion audit needs oversight authority")
    if (not isinstance(catalog,CampaignCatalog)
            or type(evidence) is not tuple or len(evidence)>4080
            or any(not isinstance(x,ProbeEvidenceReceipt) for x in evidence)):
        raise ThreatRadarError("bounded exact 4,080 probe evidence required")
    mapping={p.digest:p for p in catalog.probes}
    if len(mapping)!=4080:
        raise ThreatRadarError("cannot qualify incomplete scrutiny catalog")
    seen=set()
    counts=Counter()
    failures=0
    passed=0
    for receipt in evidence:
        if receipt.probe_digest not in mapping or receipt.probe_digest in seen:
            raise ThreatRadarError("replayed/unknown probe cannot contaminate promotion")
        seen.add(receipt.probe_digest)
        probe=mapping[receipt.probe_digest]
        if receipt.source_packet_digest!=probe.research_receipt:
            raise ThreatRadarError("wrong research round source rights packet")
        counts[probe.round_number]+=1
        if receipt.empirical_status!="measured" or receipt.failure_codes:
            failures+=1
        else:
            passed+=1
    done=tuple(counts[r] for r in (1,2,3))
    missing=tuple(SIZES[i]-done[i] for i in range(3))
    eligible=not any(missing) and not failures and passed==4080
    return ProbeCoverageReport(catalog.original_id,catalog.digest,done,missing,
                               3*len(catalog.probes),passed,failures,eligible)


__all__=["TIMES","STAGES","SIZES","ROLE_NAMES","LENSES",
         "CampaignProbe","CampaignCatalog","build_scrutiny_campaign",
         "ProbeEvidenceReceipt","ProbeCoverageReport",
         "audit_scrutiny_campaign"]
