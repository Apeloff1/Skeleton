"""Original genre grammar with consequential episodic/multiera storytelling.

Games teach agency; cinema teaches visual staging and temporal juxtaposition;
literature teaches unreliable narrators, interiority and moral uncertainty.
Those are abstract design principles, not permission to copy recognizable
fictional worlds, cast, franchise titles, level geometry or story expression.

This grammar generates playable original world context, variable revelations,
reversible/irreversible commitments, choices that change faction relationships
and an optional ending followed by new exploration. It is not a trained
novelist, finished screenplay or cinematic rendering engine.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
import json

from .dragon_world_codex import CodexAddress,validate
from .dragon_world_codex_runtime import CodexState,start,step,codex_cell
from .dragon_living_world import _sha

SCHEMA="skeleton.ai.dragon.original_multimedia_world_grammar.v1"
WORLD_FAMILIES={
 "ecological_epic":(
   "migrating_woodlands","crystalline_tides","dormant_calderas",
   "wetland_archipelagos","glacial_frontiers","sunken_forest_roads",
   "skyward_meadows","underground_seed_vaults",
 ),
 "social_epic":(
   "canal_republics","pilgrim_market_towns","poststorm_communes",
   "nomad_crossings","rebuilding_metropolises","floating_councils",
   "subterranean_cities","river_delta_leagues",
 ),
 "speculative_science":(
   "orbital_greenhouses","ring_miner_colonies","signal_observatories",
   "relativistic_frontiers","generation_vessels","moonlit_laboratories",
   "dimensional_research_ports","forgotten_machine_biospheres",
 ),
 "original_fantasy":(
   "memory_mountains","singing_canyons","ritual_gardens",
   "dream_coastlines","seasonal_citadels","enchanted_drainage",
   "mirrored_deserts","timewoven_lighthouses",
 ),
 "mystery":(
   "clockwork_archives","abandoned_stations","vanishing_harbors",
   "forgotten_rooftops","flooded_libraries","midnight_canals",
   "buried_scriptoriums","shifting_borderlands",
 ),
 "survival":(
   "windward_islands","submerged_ruins","high_altitude_refuges",
   "dustfront_crossings","icebound_economies","radiant_caverns",
   "starved_farmlands","derelict_skylanes",
 ),
 "temporal":(
   "century_ferries","palimpsest_valleys","fragmented_empires",
   "aging_asteroid_towns","recursive_wilderness","future_fossils",
   "time_shutter_palaces","lost_season_orbits",
 ),
 "small_stories":(
   "family_workshops","stormy_bakeries","neighborhood_gardens",
   "rural_mail_routes","mountain_tea_houses","floating_greenhouses",
   "repair_cooperatives","seaside_observatories",
 ),
}
WORLD_ARCHETYPES=tuple(name for family in WORLD_FAMILIES.values() for name in family)
CONFLICTS=(
 "resources_vs_recovery","loyalty_vs_truth","memory_vs_evidence",
 "safety_vs_exploration","tradition_vs_change","community_vs_independence",
 "efficiency_vs_beauty","sacrifice_vs_self_preservation",
 "knowledge_vs_privacy","scarcity_vs_mutual_aid","ecology_vs_industry",
 "duty_vs_freedom","survival_vs_legacy","access_vs_exclusion",
 "time_vs_permanence","order_vs_emergence",
)
PERSPECTIVES=(
 "witness","outsider","restorer","cartographer",
 "chronicler","negotiator","wayfarer","caretaker",
)
TIMELINES=(
 "chronological","flashback","parallel_eras","in_media_res",
 "unreliable_history","generational","time_loop","fragmented_records",
)
STAGING=(
 "intimate","panoramic","quiet_observational","episodic",
 "intercut_regions","distant_history","subjective_memory","procedural_diary",
)
STORY_CHOICES=(
 "investigate","support_commune","support_wilderness",
 "negotiate","preserve_evidence","conceal_evidence","explore_elsewhere",
 "reconstruct","complete_chapter","choose_aftermath",
)
assert len(WORLD_ARCHETYPES)==64 and len(CONFLICTS)==16
assert len(PERSPECTIVES)==len(TIMELINES)==len(STAGING)==8


@dataclass(frozen=True)
class OriginalWorldBible:
    schema:str
    codex_digest:str
    setting:str
    world_family:str
    core_conflict:str
    perspective:str
    timeline:str
    staging:str
    delayed_revelation_steps:int
    choice_weight:int
    ending_replay_band:int
    era_count:int
    originality_boundary:str
    design_digest:str


@dataclass(frozen=True)
class StoryState:
    world:CodexState
    chapters:int=0
    observations:int=0
    evidence:int=0
    commune_support:int=0
    wilderness_support:int=0
    reliability:int=0
    commitments:tuple[str,...]=()
    revelations:tuple[str,...]=()
    endings:tuple[str,...]=()
    scene_log:tuple[str,...]=()
    story_digest:str=""


def bible(address:CodexAddress)->OriginalWorldBible:
    root,genes=validate(address)
    c=genes.level
    setting=WORLD_ARCHETYPES[(c("world_seam_complexity")+c("world_repopulation"))%64]
    family=next(
        key for key,variants in WORLD_FAMILIES.items()
        if setting in variants
    )
    conflict=CONFLICTS[(c("moral_ambiguity")+c("choice_permanence"))%16]
    perspective=PERSPECTIVES[c("memory_reliability")%8]
    timeline=TIMELINES[c("historical_drift")%8]
    staging=STAGING[c("future_visibility")%8]
    data={
        "schema":SCHEMA,"codex_digest":address.codex_digest,
        "setting":setting,"world_family":family,
        "core_conflict":conflict,"perspective":perspective,
        "timeline":timeline,"staging":staging,
        "delayed_revelation_steps":1+c("revelation_delay")//16,
        "choice_weight":1+c("choice_permanence")//16,
        "ending_replay_band":1+c("ending_multiplicity")//32,
        "era_count":1+c("generation_turnover")//32,
        "originality_boundary":"genre-level original composition only; "
            "no unlicensed character, dialogue, costume, location, source, "
            "trademark, film scene or expressive plot reproduction",
    }
    return OriginalWorldBible(**data,design_digest=_sha(data))


def open_story(address:CodexAddress)->StoryState:
    config=bible(address)
    root=start(address)
    return StoryState(
        world=root,
        reliability=128,
        story_digest=_sha([SCHEMA,config.design_digest,"beginning"]),
    )


def story_options(address:CodexAddress,state:StoryState)->dict[str,dict]:
    config=bible(address)
    if not isinstance(state,StoryState):
        raise ValueError("original world story state identity required")
    age=state.world.player.base.turn
    revealed=bool(state.revelations)
    possibilities={
        "investigate":(True,"real_information_gathering"),
        "support_commune":(True,"material_community_choice"),
        "support_wilderness":(True,"ecological_allegiance"),
        "negotiate":(state.commune_support+state.wilderness_support>=2,
                     "requires_actual_social_history"),
        "preserve_evidence":(state.evidence>=1,"needs_discovered_evidence"),
        "conceal_evidence":(state.evidence>=1,"needs_discovered_evidence"),
        "explore_elsewhere":(True,"leave_the_story_for_playable_world"),
        "reconstruct":(state.evidence>=2 and
                       state.commune_support+state.wilderness_support>=1,
                       "needs_evidence_and_actual_communal_support"),
        "complete_chapter":(age>=config.delayed_revelation_steps and
                            state.observations>=2,
                            "locked_until_revelation_and_study"),
        "choose_aftermath":(state.chapters>=1 and
                             state.commune_support+state.wilderness_support>=2,
                             "requires_experienced_chapter_and_relationships"),
    }
    return {
        name:{"available":allowed,
              "reason":"open" if allowed else reason,
              "world_win_required":False}
        for name,(allowed,reason) in possibilities.items()
    }


def choose(address:CodexAddress,state:StoryState,decision:str)->StoryState:
    if type(decision) is not str or decision not in STORY_CHOICES:
        raise ValueError("world story choice has no original authored mechanics")
    allowed=story_options(address,state)
    if not allowed[decision]["available"]:
        raise ValueError("narrative passage locked by actual time, knowledge or allies")
    if len(state.scene_log)>=96:
        raise ValueError("original story replay request exceeds its bound")
    config=bible(address)
    mapped={
        "investigate":"study_revelation_delay",
        "support_commune":"study_trust_dynamics",
        "support_wilderness":"study_ecosystem_recovery",
        "negotiate":"study_diplomatic_friction",
        "preserve_evidence":"study_memory_reliability",
        "conceal_evidence":"study_unreliable_history",
        "explore_elsewhere":"study_world_seam_complexity",
        "reconstruct":"study_reconstruction_rate",
        "complete_chapter":"study_story_branching",
        "choose_aftermath":"study_post_story_expansion",
    }
    world=step(address,state.world,mapped[decision])
    obs=state.observations+(decision in ("investigate","explore_elsewhere"))
    evidence=state.evidence+(decision=="investigate")
    civic=state.commune_support+(decision=="support_commune")
    wild=state.wilderness_support+(decision=="support_wilderness")
    reliability=max(0,min(255,state.reliability+
        (2 if decision=="preserve_evidence" else
         -3 if decision=="conceal_evidence" else 0)))
    revelations=list(state.revelations)
    if (obs>=2 and world.player.base.turn>=config.delayed_revelation_steps
            and "historical_record" not in revelations):
        revelations.append("historical_record")
    commitments=state.commitments
    if decision in ("preserve_evidence","conceal_evidence","negotiate",
                    "reconstruct") and decision not in commitments:
        commitments=commitments+(decision,)
    chapters=state.chapters+(decision=="complete_chapter")
    endings=state.endings
    if decision=="choose_aftermath":
        outcome=("communal_renewal" if civic>wild else
                 "rewilded_frontier" if wild>civic else
                 "cooperative_balance")
        if outcome not in endings:endings=endings+(outcome,)
    scene=state.scene_log+(decision,)
    changed=StoryState(
        world=world,chapters=chapters,observations=obs,evidence=evidence,
        commune_support=civic,wilderness_support=wild,
        reliability=reliability,commitments=commitments,
        revelations=tuple(revelations),endings=endings,
        scene_log=scene,
        story_digest=_sha([
            config.design_digest,state.story_digest,decision,
            world.history_digest,chapters,civic,wild,commitments,
            revelations,endings,reliability,
        ]),
    )
    return changed


def replay_story(address:CodexAddress,decisions:tuple[str,...])->StoryState:
    if (type(decisions) is not tuple or len(decisions)>96
        or any(type(x) is not str or x not in STORY_CHOICES for x in decisions)):
        raise ValueError("original world story decisions outside deterministic bound")
    state=open_story(address)
    for choice in decisions:state=choose(address,state,choice)
    return state


def story_report(address:CodexAddress,state:StoryState)->dict:
    config=bible(address)
    return {
        "schema":SCHEMA,"original_world_bible":asdict(config),
        "player":asdict(state),
        "choices":story_options(address,state),
        "ended_a_story":bool(state.endings),
        "ended_the_world":False,
        "playable_after_story":True,
        "timed_revelation_available":bool(state.revelations),
        "final_narrative_claim":"actual original bounded interactive story "
            "consequences with optional endings; not a copied work or "
            "machine-reviewed literary originality",
    }
