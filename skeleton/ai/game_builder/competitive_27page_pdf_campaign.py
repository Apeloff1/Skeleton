"""27-page exact three-round, three-AI system battle-plan publisher.

3 roles x 3 time-isolated rounds x 3 pages = 27 unique A4 pages. Exactly
three complete 9-page role PDFs are produced, plus nine individual
3-page part PDFs for stage-by-stage review. An exhaustive JSON Lines
annex contains ALL 4,080 probe definitions AND ALL 12,240 signed role
judgments; do not compress 12k statuses into a dishonest page-level
claim. Every ZIP entry is digest-bound to one immutable manifest.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from hashlib import sha256
import json
import os
import zipfile
from collections import Counter

from .contracts import canonical_digest,canonical_json
from .competitive_title_radar import ThreatRadarError,_sha
from .competitive_4080_scrutiny import (
    CampaignCatalog,SIZES,TIMES,STAGES,ROLE_NAMES,
)
from .competitive_4080_role_reviews import (
    AgentCampaignRoundReport,CampaignCouncilAudit,audit_council_scrutiny,
)
from .competitive_pdf_pack import _pdf_pages,_pdf_3_pages,ROLE_FOCUS
from .competitive_tri_council import ThreeRoundBattlePlan
from .competitive_user_critique import CurrentProjectCritique
from .competitive_delivery_gate import TrustedCompetitionJudge
from .game_project_workspace import GameWorkspace


ROUND_NARRATIVE=(
    ("R1 PROLOGUE / HISTORICAL GENRE BASELINES",
     "Prior-era comparative history: what each genre predecessor actually did, "
     "which apparent strengths survived platform constraints and which ideas were "
     "merely claimed by articles, blogs or gameplay-video peer commentary.",
     "Historical lineage is not automatically evidence of causal borrowing. "
     "Use two-source checks, older hardware fidelity, legal reference-only "
     "rights, independent experiments and explicit uncertain ancestry."),
    ("R2 MIDPOINT / CURRENT ENEMY BATTLE",
     "Current enemy-versus-original competition on the same game build "
     "scenario, player skill strata, platform budget, controlled faults and "
     "relevant accessibility modes.",
     "A real rival weakspot requires conservative signed intervals and an "
     "independent cohort. Dismantle weaknesses through YOUR original game "
     "design, never through copying an enemy's expression."),
    ("R3 EPILOGUE / FUTURE ORIGINAL OUTCLASSING",
     "Current-project constructive criticism extended to postgame, future "
     "world evolution, lineage nonregression, user safety and long-horizon "
     "original story/NPC/audio/graphics mastery.",
     "Double-size constructive scrutiny demands full test coverage, real "
     "source-owned builds and independently replayed improvements; an AI "
     "recommendation is NOT implemented work or a model-weight promotion."),
)
FOCUS_ACTION={
    "dragon":"Wiki/Dragon: Independently ingest source-specific facts, peer-video "
        "metadata and legally licensed research. Track corrections, rights revocation, "
        "separate train-permitted content and distill eligible ideas only after new "
        "facts survive independent verification.",
    "jeeves":"Jeeves: Compile original game-world changes in a dependency-aware "
        "plan. Detail NPC witness memory, causal quest graphs, audiovisual "
        "systems, era platform budgets and deterministic game build checkpoints; "
        "request a human design approval before application.",
    "adversarial":"Adversarial: Attack every claimed improvement with hidden "
        "counterfactual worlds, player cohorts, edge cases, distorted review "
        "metadata, near-clone detection, inaccessible interfaces and reproducible "
        "original-game regressions.",
}
DOMAIN_ACTIONS={
    "gameplay":"Retest control fairness, NPC epistemic state, save continuity, "
        "procedural solvability, world vibrancy, nonterminal simulation and "
        "player-driven quest consequence with instrumented repeated plays.",
    "graphics":"Profile source-owned silhouette, visual legibility, memory, "
        "animation transitions, FX, camera comfort and 99th percentile frame "
        "pacing on actual target hardware; no trailer-only marketing evidence.",
    "sound":"Compose original motifs, accessible captions and audio cues; "
        "evaluate spatial position, masking, dialogue, dynamic range, "
        "timing and platform mono/headphone fallbacks in blind listening trials.",
    "storyline":"Verify causal prologue-to-epilogue consistency, NPC witnessed "
        "events, agency, lore, contradictory rumors, irreversible choices, "
        "time paradox, endings and persistent playable postgame worlds.",
}
BARRIERS=(
    "Evidence gate: bind every finding to the exact reviewed research revision, "
    "source provenance, rights scope, timestamp, platform, build and trace digest.",
    "Originality gate: retain all immutable title identity pillars; exclude third-"
    "party artwork, code, audio, protected plots, character identities and maps.",
    "Statistical gate: independent heldout participants, fixed scenario, signed "
    "evaluator, uncertainty interval and negative-control replausibility.",
    "Release gate: require verified original-game code, player-facing quality "
    "gain, accessibility/nonregression, legal sign-off and real user approval.",
    "Learning gate: route verified facts into a versioned source-rights almanac; "
    "only separately train-licensed data may be admitted to any model optimizer.",
)


def _page(role,round_no,page_no,battle,critique,catalog,report,council):
    rnd=battle.rounds[round_no-1]
    base=ROUND_NARRATIVE[round_no-1]
    reviews=next(x for x in rnd.role_reviews if x.role==role)
    probes=[p for p in catalog.probes if p.round_number==round_no]
    report_by_digest={a.probe_digest:a for a in report.assessments}
    status=Counter(a.verdict for a in report.assessments)
    if page_no==1:
        rows=[
            ("heading",base[0]+" - 1/3: EVIDENCE-BOUND DIAGNOSIS"),
            ("body",f"ROLE: {role.upper()} / original project {battle.original_id} / "
                    f"round {round_no}/3 / epoch {battle.epoch}."),
            ("body",base[1]),
            ("heading","WHAT MUST BE EXAMINED WITHOUT FILLER"),
            ("body",f"This round owns {len(probes):,} unique probes in "
                    f"{TIMES[round_no-1]}. All 102 underlying design facets "
                    "receive distinct experimental lenses. Other time windows "
                    "are forbidden from claiming coverage of these experiments."),
            ("body",f"Signed role-probe judgments: {len(report.assessments):,}. "
                    f"Verified strengths {status.get('verified_strength',0)}; "
                    f"verified risks {status.get('verified_risk',0)}; "
                    f"unmeasured {status.get('not_yet_tested',0)}; "
                    f"inconclusive {status.get('inconclusive',0)}. "
                    "Unmeasured evidence cannot count as a game win."),
            ("body",f"Current user's game has {critique.missing_live_measurements}/"
                    f"{critique.all_facet_count} base facets without proven "
                    "instrumented project measurements. Never infer a real "
                    "game's quality from catalog size."),
            ("heading","INDEPENDENT FACET-BY-FACET ASSESSMENTS"),
        ]
        bydomain=Counter(p.domain for p in probes)
        for domain in ("gameplay","graphics","sound","storyline"):
            rows.append(("body",f"{domain.upper()} / {bydomain[domain]} experiments: "
                         f"{DOMAIN_ACTIONS[domain]}"))
        rows.extend([
            ("heading","ROLE SPECIFIC REALITY CHECK"),
            ("body",FOCUS_ACTION[role]),
            ("body","Full experiment text, scoring status, proposed correction and "
                    "source digests remain in the bundled machine annex, "
                    "not omitted because this human page is limited."),
        ])
    elif page_no==2:
        research=rnd.research
        rows=[
            ("heading",base[0]+" - 2/3: RESEARCH, DEBATE AND FAILURE ANALYSIS"),
            ("body",f"Round research scope {research.strategy}; actual reviewed "
                    f"sources: {len(research.source_ids)}; distinct publisher "
                    f"dependence groups: {len(research.independent_groups)}. "
                    f"Wiki revision root {research.wiki_root[:24]}... "
                    f"Rights root {research.rights_root[:24]}...."),
            ("heading","THREE-WAY PEER AND ADVERSARIAL ARGUMENT"),
            ("body",f"{role.upper()} challenge to {reviews.challenged_role}: "
                    f"{reviews.challenge[:330]}"),
            ("body",f"Response to prior objections: "
                    f"{reviews.answer_to_prior_objection[:330]}"),
            ("body",f"Declared role score {reviews.quantified_quality_bp}/10000, "
                    f"explicit hard vetoes {len(reviews.hard_vetoes)}. "
                    "No veto may be hidden by averaging other roles' scores."),
            ("body",base[2]),
            ("heading","RIGOROUS MULTISOURCE EVIDENCE CONTROL"),
        ]
        rows.extend(("body",str(i+1)+". "+line) for i,line in enumerate(BARRIERS))
        rows.extend([
            ("heading","MODEL WEIGHTS ARE NOT A PROXY FOR RESEARCH"),
            ("body","Dragon source discoveries and scholarly metadata must be "
                    "reviewed before entering Wiki. Jeeves proposes independent "
                    "original code changes. The Adversarial Mirror checks "
                    "counterfactual failures. Only after training licence, "
                    "heldout evaluation and approval may a separate model "
                    "promotion plane apply actual parameter or adapter updates."),
            ("body",f"Round evidence receipt {research.digest[:32]}; "
                    f"agent report {report.digest[:32]}. "
                    "No live model inference is asserted by generated prose."),
        ])
    else:
        rows=[
            ("heading",base[0]+" - 3/3: BATTLE PLAN / USER AUTHORITY"),
            ("body","Plan aim: surpass rival genre player value with first-principles "
                    "original play, not borrowed assets, mechanics' expressive "
                    "implementation or copied storyline."),
            ("heading","CONSTRUCTIVE AND MEASURABLE WORK SEQUENCE"),
            ("body","Stage A: Freeze the target original build, sources, research "
                    "rights, hardware tier, player cohort and original identity. "
                    "Do not invalidate historical source digests."),
            ("body","Stage B: Select the highest evidence-backed risk per domain "
                    "and create engine-native game code, art, audio and narrative "
                    "solutions in a reversible review branch."),
            ("body","Stage C: Instrument each new build and independently repeat "
                    "matched normal, fault, negative, accessibility, long-horizon "
                    "and platform-specific replay scenarios."),
            ("body","Stage D: Compare strongest verified historical ancestors, "
                    "current enemy and new original game under exact protocols. "
                    "Require original conservative lower > all rival conservative "
                    "upper bounds by the predeclared margin."),
            ("body","Stage E: Repeat blind red-team objections, fix every hard "
                    "failure, retain project identity and zero unlicensed "
                    "knowledge use. Record test evidence and QA signatures."),
            ("heading","ROLE-SPECIFIC IMPLEMENTATION DIRECTIVES"),
            ("body",FOCUS_ACTION[role]),
        ]
        for a in report.assessments:
            if a.verdict=="verified_risk":
                probe=next(p for p in probes if p.digest==a.probe_digest)
                rows.append(("body",f"Verified risk {probe.facet} / {probe.lens}: "
                             f"{a.improvement_direction[:230]}"))
                break
        rows.extend([
            ("heading","USER DELIVERY AND NONNEGOTIABLE REVIEW GATES"),
            ("body","This stage is not approved merely because nine AI rounds "
                    "pass signed review. Read all three 9-page role dossiers "
                    "and machine-annex research and scrutiny records."),
            ("body","[ ] Approve ALL 27 pages and the exact manifest digest. "
                    "[ ] Revise to trigger broader Dragon research and a new "
                    "three-round deliberation. [ ] Defer all automatic actions."),
            ("body","Passing a role review does not automatically edit your "
                    "game, scrape websites, merge a branch, publish a game "
                    "or modify the Dragon/Jeeves/Adversarial model weights."),
        ])
    return tuple(rows)


@dataclass(frozen=True,slots=True)
class CampaignPdf27Packet:
    digest: str
    folder: str
    role_document_sha: tuple[tuple[str,str],...]
    stage_document_sha: tuple[tuple[str,str],...]
    annex_sha: str
    zip_sha: str
    total_unique_pages: int=27

    def payload(self):
        return dict(schema="skeleton.game_builder.27page_campaign_pdf.v1",
                    digest=self.digest,folder=self.folder,
                    role_document_sha=list(map(list,self.role_document_sha)),
                    stage_document_sha=list(map(list,self.stage_document_sha)),
                    annex_sha=self.annex_sha,zip_sha=self.zip_sha,
                    total_unique_pages=self.total_unique_pages,
                    user_confirmation_not_yet_granted=True)


def publish_27page_campaign(
    root: str|Path,
    battle: ThreeRoundBattlePlan,
    critique: CurrentProjectCritique,
    catalog: CampaignCatalog,
    role_reports: tuple[AgentCampaignRoundReport,...],
    trusted_roles: tuple[tuple[str,TrustedCompetitionJudge],...], *,
    authorized: bool,
)->CampaignPdf27Packet:
    if not authorized:
        raise PermissionError("user three-system expanded scrutiny publisher needs authority")
    if (not isinstance(battle,ThreeRoundBattlePlan)
            or not isinstance(critique,CurrentProjectCritique)
            or not isinstance(catalog,CampaignCatalog)
            or battle.original_id!=critique.original_id
            or catalog.original_id!=battle.original_id
            or battle.critique_digest!=critique.digest
            or not battle.ready_for_pdf_review):
        raise ThreatRadarError("27 pages require approved research, full original and time-scoped scrutiny")
    audit=audit_council_scrutiny(
        catalog,battle,role_reports,trusted_roles,authorized=True)
    by_role_round={(x.role,x.round_number):x for x in role_reports}
    doc={}
    packet_root=canonical_digest([battle.digest,critique.digest,catalog.digest,
                                  audit.payload()])
    for role in ROLE_NAMES:
        combined=[]
        for rnd in (1,2,3):
            rows=tuple(_page(role,rnd,page,battle,critique,catalog,
                             by_role_round[(role,rnd)],audit)
                       for page in (1,2,3))
            doc[f"{role}_round_{rnd}.pdf"]=_pdf_3_pages(
                role,rows,battle,packet_root)
            combined.extend(rows)
        doc[f"{role}_full_9pages.pdf"]=_pdf_pages(
            role,tuple(combined),battle,packet_root)
    lines=[canonical_json(p.payload()) for p in catalog.probes]
    annex_catalog=("\n".join(lines)+"\n").encode()
    annex_role=("\n".join(
        canonical_json(dict(role=x.role,round_number=x.round_number,
                            signed_review_digest=x.digest,
                            judgment=y.payload()))
        for x in sorted(role_reports,key=lambda q:(q.round_number,q.role))
        for y in x.assessments)+"\n").encode()
    annex={"full_probe_catalog.jsonl":annex_catalog,
           "all_role_probe_judgments.jsonl":annex_role}
    manifest={
        "schema":"skeleton.game_builder.27page_campaign_manifest.v1",
        "original_id":battle.original_id,
        "battle_digest":battle.digest,
        "critique_digest":critique.digest,
        "catalog_digest":catalog.digest,
        "council_audit_digest":canonical_digest(audit.payload()),
        "research_roots":[round.research.digest for round in battle.rounds],
        "roles":list(ROLE_NAMES),
        "temporal_windows":list(TIMES),
        "per_round_unique_probes":list(SIZES),
        "review_obligations":audit.total_reviewed_obligations,
        "empirical_measurements_verified":audit.measured_obligations,
        "pdf_file_sha256":{n:sha256(d).hexdigest() for n,d in sorted(doc.items())},
        "machine_annex_sha256":{n:sha256(d).hexdigest() for n,d in sorted(annex.items())},
        "role_final_pdf_pages":{r:9 for r in ROLE_NAMES},
        "role_round_part_pdf_pages":{n:3 for n in sorted(doc) if "_round_" in n},
        "total_unique_pages":27,
        "approved_by_user":False,
        "models_must_supply_own_signed_reports":True,
        "source_reference_rights_not_training_rights":True,
    }
    manifest_bytes=(canonical_json(manifest)+"\n").encode()
    digest=sha256(manifest_bytes).hexdigest()
    workspace=GameWorkspace(root)
    parent=workspace.root/"competitive_intelligence"/"battle_pdf_27"
    folder=parent/digest
    if parent.is_symlink() or folder.is_symlink():
        raise ThreatRadarError("symlinked archive not allowed")
    parent.mkdir(exist_ok=True)
    folder.mkdir(exist_ok=True)
    archive=BytesIO()
    everything={**doc,**annex,"manifest.json":manifest_bytes}
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(everything.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    everything["complete_27page_campaign.zip"]=archive.getvalue()
    for name,data in everything.items():
        dest=folder/name
        if dest.is_symlink():
            raise ThreatRadarError("unsafe existing PDF packet destination")
        try:
            with dest.open("xb") as output:
                output.write(data);output.flush();os.fsync(output.fileno())
        except FileExistsError:
            if dest.is_symlink() or dest.read_bytes()!=data:
                raise ThreatRadarError("cannot overwrite authenticated complete 27-page review")
    return CampaignPdf27Packet(
        digest,str(folder),
        tuple((r,manifest["pdf_file_sha256"][f"{r}_full_9pages.pdf"])
              for r in ROLE_NAMES),
        tuple((n,manifest["pdf_file_sha256"][n]) for n in sorted(doc)
              if "_round_" in n),
        sha256(annex_catalog+annex_role).hexdigest(),
        sha256(archive.getvalue()).hexdigest(),27)


__all__=["CampaignPdf27Packet","publish_27page_campaign"]
