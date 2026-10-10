"""Authored research questions for gaming niches, not acquired factual claims.

Each entry specifies mechanics to investigate, a proposed measurement and a
failure case. The catalog is deliberately overlapping and open-ended.
"""
from dataclasses import asdict, dataclass

from .contracts import canonical_digest


@dataclass(frozen=True, slots=True)
class GamingNiche:
    niche_id: str
    family: str
    mechanics: tuple[str, ...]
    proposed_measurement: str
    failure_probe: str
    original_design_prompt: str


# Author-created design/research prompts. None of these rows asserts that a
# mechanic improves enjoyment, accessibility, commercial success or legality.
_DATA = """
precision_platformer|platform|input buffering;variable jump;checkpoint placement|missed-input rate and retry duration by device|frame drops at landing boundaries|restore signals across moving mountain observatories
momentum_platformer|platform|acceleration;slopes;air steering|velocity conservation and route completion by input|slope transitions eject players|deliver weather instruments through a shifting cloud city
cinematic_platformer|platform|animation commitment;context actions;camera framing|action recognition and recovery time|camera hides a required landing|repair a traveling theater during its final migration
exploration_platformer|platform|movement upgrades;secret routes;backtracking|route discovery and revisit time|upgrades create unreachable save states|map root tunnels of an itinerant forest
character_action|combat|combo branching;cancel windows;style incentives|input-to-action latency and viable move diversity|one safe loop dominates every encounter|conduct a kinetic rescue troupe in living machinery
dueling_fighter|combat|spacing;frame advantage;resource reads|matchup outcomes with skill and latency controls|defensive option covers every response|settle fictional guild disputes through ceremonial instruments
arena_brawler|combat|crowd control;hazard positioning;pickup economy|threat readability and offscreen damage rate|opponents chain unavoidable stuns|guide sanitation robots through storm-damaged plazas
cooperative_brawler|combat|revival;shared resources;friendly interaction|participation distribution and revival failures|one player repeatedly locks out partners|coordinate harbor crews protecting migrating lanterns
arena_shooter|shooting|map control;movement tech;weapon timing|spawn fairness and item-control concentration|spawn locations permit immediate repeated kills|compete with remote survey drones inside shifting ruins
tactical_shooter|shooting|information control;team utility;round economy|communication dependence and comeback opportunities|audio-only cues reveal mandatory information|coordinate nonlethal containment in unstable research habitats
twin_stick|shooting|independent aim;crowd steering;cooldown routing|aim accuracy across sticks mouse and alternative controls|camera shake masks incoming threats|clear invasive debris around fragile orbital farms
bullet_hell|shooting|pattern reading;hitbox clarity;resource recovery|collision visibility and survival by pattern speed|projectiles merge into indistinguishable backgrounds|navigate luminous pollen currents as a mechanical pollinator
real_time_strategy|strategy|resource allocation;scouting;production timing|decision load and strategy diversity by skill|early advantage makes later choices irrelevant|manage competing restoration teams on a flooded world
turn_based_tactics|strategy|action economy;cover;initiative|outcome predictability and effective tactical options|hidden rules invalidate displayed previews|escort a mobile museum through changing terrain
grand_strategy|strategy|diplomacy;institution change;logistics|long-horizon causality comprehension|opaque modifiers overwhelm strategic intent|guide a federation of migrating islands over centuries
operational_wargame|strategy|supply lines;fog of war;order delays|supply-model consistency and order explanation|simulation hides decisive logistical failures|plan fictional disaster-response campaigns without combat copying
city_builder|management|zoning;service coverage;traffic|service deficits and congestion recovery|feedback loops trap an otherwise solvent city|build settlements that move with seasonal tides
colony_sim|management|agent needs;task priorities;emergent events|task starvation and recovery after resource shocks|priority inversion leaves critical work undone|support a research colony inside a slowly rotating cavern
logistics_factory|management|throughput;buffers;transport routing|bottleneck attribution and queue stability|minor delays cause unrecoverable deadlocks|process reclaimed materials across modular floating workshops
business_tycoon|management|pricing;capacity;customer demand|profit sensitivity with transparent demand assumptions|unexplained customer behavior defeats planning|run a network of community repair festivals
party_rpg|role_playing|party roles;resource attrition;dialogue checks|role usefulness and encounter resource variance|one build removes meaningful party decisions|follow archivists negotiating with newly awakened landscapes
dungeon_crawler|role_playing|grid navigation;mapping;resource pressure|navigation errors and recoverable expedition losses|required cues rely solely on memorized orientation|survey subterranean libraries rearranged by mineral growth
action_rpg|role_playing|build crafting;enemy tells;equipment tradeoffs|build viability and tell recognition|visual effects obscure damage-critical signals|restore damaged constellations using modular astronomical tools
creature_collecting|role_playing|collection;team synergy;care systems|team diversity and collection-friction distribution|progress requires repetitive compulsory acquisition|catalog synthetic symbionts with ecology-based cooperation
traditional_roguelike|run_based|turn economy;identification;permadeath|seed-conditioned survival and explainable failure|unavoidable early randomness dominates outcomes|lead temporary expeditions through abandoned weather engines
action_roguelite|run_based|real-time encounters;run upgrades;meta progression|skill improvement separated from permanent upgrades|grind disguises unchanged player learning|rebuild a roaming observatory after each storm season
deckbuilder_roguelike|run_based|deck thinning;draw probability;path choices|seed-controlled strategy diversity and draw risk|one early card makes all later choices automatic|assemble ritual instructions for cooperative landscape repair
survival_autobattler|run_based|positioning;upgrade selection;wave pacing|meaningful decision frequency and threat readability|passive upgrades eliminate all player agency|steer an autonomous salvage fleet through magnetic reefs
push_block_puzzle|puzzle|irreversible pushes;goal ordering;undo|solvability and accidental deadlock frequency|hidden one-way move forces complete restart|arrange tidal gates in a hand-drawn estuary
nonogram_logic|puzzle|constraint propagation;marking;hint steps|unique-solution rate and explainable hint quality|ambiguous puzzle is presented as uniquely solvable|reconstruct star charts from damaged expedition records
deduction_mystery|puzzle|evidence links;hypothesis testing;contradictions|false-positive accusation and clue sufficiency|solution depends on an unstated external fact|investigate competing accounts of a vanished public garden
physics_puzzle|puzzle|force transfer;materials;timing|solution reproducibility across timestep settings|frame-rate changes alter whether a solution works|design gentle transport for fragile living sculptures
parser_fiction|narrative|language affordances;world state;discovery|command acceptance and unhelpful response rate|valid intent fails because of a hidden exact verb|negotiate an expedition through a city of literal promises
point_and_click|narrative|inventory reasoning;environment clues;dialogue|puzzle inference and accidental item-combination burden|progress requires an arbitrary unexplained combination|repair social rituals aboard a drifting market town
visual_novel|narrative|branching choices;relationship state;scene pacing|choice comprehension and route-state consistency|cosmetic choices are misrepresented as consequential|mediate an intergenerational archive during an evacuation
interactive_drama|narrative|timed choices;consequence tracking;perspective shifts|consequence recall and decision-window accessibility|late input yields an outcome the UI did not communicate|coordinate witnesses rebuilding a disputed community history
survival_horror|horror|scarcity;safe spaces;enemy avoidance|resource pressure and escape-route readability|failure recovery erases excessive unrelated progress|maintain remote lighthouses during impossible geological events
psychological_horror|horror|uncertainty;environment change;unreliable accounts|orientation recovery and content-warning effectiveness|confusion is indistinguishable from broken state|explore an archive whose rooms reflect conflicting testimony
folk_horror|horror|ritual systems;community rules;landscape clues|rule inference without external cultural assumptions|borrowed cultural imagery becomes a shallow stereotype|invent an original seasonal belief system with reviewed influences
asymmetric_horror|horror|unequal roles;pursuit;team rescue|role-specific agency and matchmaking fairness|one role has prolonged periods without meaningful action|guide couriers and wardens through a transforming dream station
life_simulation|simulation|routines;relationships;self-directed goals|player-defined goal support and schedule friction|mandatory chores overwhelm chosen activities|support a rotating neighborhood aboard a traveling habitat
ecosystem_simulation|simulation|food webs;population dynamics;habitat change|stability and uncertainty under parameter variation|plausible graphics imply unvalidated ecological accuracy|rebuild an explicitly fictional biome from documented abstractions
farming_simulation|simulation|crop cycles;tool use;season planning|repetition burden and viable seasonal strategies|missed calendar event blocks a long progression chain|cultivate rooftop gardens on a migrating industrial vessel
profession_simulation|simulation|procedures;tool handling;diagnosis|procedure fidelity and error-recovery clarity|game simplification is mistaken for professional training|operate fictional meteorological maintenance equipment
rally_racing|vehicles|surface grip;pace information;damage management|handling consistency and cue timing by device|essential navigation depends on audio alone|race survey vehicles along procedurally shifting riverbeds
circuit_sim_racing|vehicles|tire behavior;braking;race strategy|lap variance separated from control-device differences|assist settings silently change competitive comparisons|develop original low-impact racing machinery and circuits
flight_simulation|vehicles|lift control;navigation;landing procedures|control response and instrument readability|unvalidated simulation is presented as flight instruction|pilot fictional buoyant craft through layered weather systems
spaceflight_simulation|vehicles|orbital planning;fuel budgets;relative motion|trajectory reproducibility and model-error disclosure|simplified physics is mistaken for scientific prediction|service rotating scientific habitats with transparent simulation limits
skating_sport|sports|momentum;trick linking;landing control|input consistency and route expression diversity|animation hides when landing correction is possible|traverse repurposed industrial gardens with original equipment
fishing_sim|sports|habitat reading;line tension;equipment choice|feedback comprehension and session pacing|random reward schedules overpower learnable technique|study fictional aquatic organisms using non-extractive observation
climbing_game|sports|route reading;stamina;grip selection|route accessibility and failure recoverability|camera occlusion conceals necessary grips|ascend mobile geological research towers
team_sport|sports|positioning;passing;role coordination|role contribution and possession balance by team skill|single dominant role removes cooperative decisions|invent a team game based on shifting spatial goals
key_rhythm|rhythm|timing windows;chart readability;calibration|timing error after device-specific latency calibration|display lag is scored as player error|perform original compositions to stabilize a fictional signal network
dance_rhythm|rhythm|step patterns;movement sequencing;physical pacing|input recognition and fatigue-aware session recovery|required motions cannot be independently remapped|choreograph an original festival using configurable movement vocabulary
music_construction|rhythm|loop layering;harmonic constraints;interactive mixing|creative option diversity and audible-feedback latency|automatic correction prevents intended musical expression|build sound gardens from original synthesized instruments
rhythm_combat|rhythm|beat synchronization;attack tells;tempo changes|dual-task load and timing-assist effectiveness|beat cues and combat cues become mutually unreadable|conduct animated machines through original percussive rituals
ability_gated_exploration|exploration|ability locks;world topology;return routes|reachable-state coverage and backtracking burden|new ability strands the player behind irreversible terrain|explore a folded observatory with reconfigurable instruments
archaeology_exploration|exploration|artifact context;inference;environment reading|inference traceability and contextual understanding|speculation is displayed as settled historical fact|study an invented civilization through contradictory artifacts
underwater_exploration|exploration|buoyancy;oxygen planning;three-dimensional navigation|orientation loss and resource-pressure recovery|depth cues disappear for particular display settings|survey luminous fictional reef structures with original tools
cartography_game|exploration|landmark inference;map annotation;route planning|map accuracy and navigation without color-only cues|annotations become unusable on small screens|chart islands that slowly exchange positions
social_deduction|social|hidden roles;discussion;information asymmetry|role win rates and participation under group-size changes|players can identify roles from out-of-band technical leaks|debate resource anomalies aboard an original expedition
party_minigames|social|rapid onboarding;short rounds;shared attention|instruction comprehension and waiting-time distribution|eliminated players spend most of a session inactive|stage cooperative competitions in a traveling workshop fair
cooperative_puzzle|social|distributed information;communication;shared state|communication load and equitable agency|one player can solve everything while others watch|restore bridges using complementary abstract sensing tools
asymmetric_cooperation|social|different interfaces;role transfer;coordination|cross-role workload and interruption recovery|role mismatch traps a player without useful actions|pair a navigator with a habitat engineer in an original rescue mission
voxel_sandbox|creative|terrain editing;resource rules;spatial construction|edit latency and recoverability of accidental changes|small mistakes destroy large amounts of authored work|build floating gardens with invented material behavior
structural_builder|creative|load paths;connections;failure visualization|simulation consistency and explainable structural failure|approximate physics is marketed as engineering certification|design fictional modular shelters under declared simplified loads
programming_game|creative|instruction sequencing;debugging;execution traces|concept transfer and diagnostic usefulness|puzzles reward memorizing undocumented implementation quirks|program tiny maintenance agents for an invented archive
automation_puzzle|creative|routing;state machines;parallel tasks|throughput and determinism under scheduling changes|solution depends on accidental execution order|coordinate reversible material-processing contraptions
idle_incremental|experimental|growth curves;offline progress;reset choices|decision relevance and time-cost transparency|progress incentives become compulsive obligation|model fictional habitat renewal with bounded optional sessions
document_game|experimental|classification;cross-referencing;rule exceptions|rule comprehension and error explanation|dense text is the only channel for critical instructions|reconcile fictional expedition manifests with humane exception policies
audio_navigation|experimental|spatial sound;landmarks;orientation|localization accuracy across headphones and alternatives|essential spatial information has no adjustable fallback|explore original resonant architecture with multimodal guidance
experimental_time|experimental|rewind;branching timelines;causal puzzles|causal-model comprehension and replay consistency|state rewinds leave contradictory persistent consequences|maintain a fictional observatory across reversible weather cycles
vector_arcade|historical|line geometry;score loops;limited display load|vector workload and shape recognition on target hardware|busy scenes exceed display timing constraints|guide original surveying shapes through abstract mineral fields
attribute_graphics|historical|tile constraints;palette allocation;readability|constraint violations and sprite-background distinction|visual indicators disappear under attribute restrictions|compose original low-resolution botanical expeditions
text_mode_game|historical|glyph semantics;keyboard input;screen updates|glyph readability and input consistency across terminals|terminal behavior changes the interpretation of game state|manage an original expedition through a navigable text map
persistent_text_world|historical|shared commands;world persistence;community rules|recovery consistency and moderation workload|state or permissions leak across player boundaries|build a small consent-based fictional research settlement
speedrun_design|community|route optimization;timing;replay verification|deterministic timing and route diversity|hardware differences silently alter leaderboard eligibility|create an original courier circuit with transparent timing categories
challenge_run|community|self-imposed rules;constraint tracking;proof playback|rule-verification reliability and viable restricted strategies|hidden exceptions make challenge completion unverifiable|design optional expedition protocols for original mechanics
randomizer_design|community|seed generation;logic solving;progression shuffle|seed solvability and spoiler-safe hint behavior|generated seed requires an item locked behind itself|shuffle original world modules with declared logic constraints
level_maker|community|user tools;sharing;validation|creator task completion and invalid-content containment|shared content executes untrusted code or breaks saves|provide an original puzzle workshop with bounded expressive tools
roomscale_vr|interfaces|embodied interaction;reach;spatial locomotion|comfort and task success across seated and standing configurations|required reach excludes seated or limited-mobility players|maintain a miniature fictional weather workshop
mixed_reality_tabletop|interfaces|surface anchoring;physical occlusion;shared perspective|tracking loss recovery and anchor consistency|real-world boundaries are mistaken for safe gameplay space|coordinate an original tabletop ecosystem with explicit boundaries
one_button_mobile|interfaces|timing;state cycling;context actions|accidental activation and one-handed task completion|ambiguous context makes one button perform an unintended action|operate a small fictional signal station in short optional sessions
dual_screen_handheld|interfaces|split information;touch input;attention switching|cross-screen attention cost and stylus-free alternatives|mandatory information is split beyond comfortable attention|pair an original field notebook with a navigable miniature world
"""

NICHES = tuple(GamingNiche(parts[0], parts[1], tuple(parts[2].split(";")), *parts[3:])
               for line in _DATA.strip().splitlines() if (parts := line.split("|")))
BY_ID = {n.niche_id: n for n in NICHES}
if len(BY_ID) != len(NICHES) or any(len(n.mechanics) != 3 for n in NICHES):
    raise RuntimeError("invalid niche research catalog")


def niche_catalog() -> dict:
    body = {"schema": "skeleton.game_builder.niche_catalog.v1",
            "profiles": [asdict(n) for n in NICHES],
            "families": sorted({n.family for n in NICHES}),
            "coverage": "authored_research_agenda_not_exhaustive_taxonomy",
            "empirically_validated": False}
    return {**body, "catalog_digest": canonical_digest(body)}
