"""Advanced Jeeves studio scenario laboratory and mirrored simulation observability.

A ranked game's sales are *commercial evidence*, never proof that a mechanic
works or that copying a game is legal. This catalog stores factual rank/title
references and original abstract test motifs only, never ROMs, maps, art,
dialogue, missions or unpublished assets.

All scenario lanes use the canonical emulator-style original-engine adapter.
Each thread owns one isolated environment. Result order is canonical,
progress is sampled from executed steps, and observability never modifies
production weights, active campaigns, player source or champion policies.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import math
import random

from skeleton.ai.game_builder.advanced_gameplay_runtime import ACTION_HELP, ENGINES
from skeleton.ai.game_builder.system_editors import editor_spec
from .game_studio_environment import make_studio_source, parse_studio_source, StudioGameEnvironment
from .game_studio_rule_curriculum import (
    PROPOSAL_SCHEMA, RuleCurriculumError, apply_rule_proposal,
    make_rule_curriculum, rule_authoring_contract, _sha as source_digest,
)

SCHEMA = "skeleton.game_builder.scenario_lab.v1"
MAX_LANES = 10
MAX_STEPS = 48
MAX_FRAMES = 3
ANGLES = (
    "explore", "progress", "safety", "economy", "adversary",
    "boundary", "temporal", "causal", "perturbation", "recovery",
)
MOTIFS = (
    # Publisher reported worldwide unit sales, 2026-06-30.
    {"reference":"Mario Kart 8 Deluxe","chart":"nintendo_switch_2026_06_30",
     "rank":1,"units_millions":71.53,"editor":"racing",
     "motif":"Original course decision-making under traction, risk and route choice"},
    {"reference":"Animal Crossing: New Horizons","chart":"nintendo_switch_2026_06_30",
     "rank":2,"units_millions":50.29,"editor":"ecosystem",
     "motif":"Independent small-world resource and seasonal feedback loops"},
    {"reference":"Super Smash Bros. Ultimate","chart":"nintendo_switch_2026_06_30",
     "rank":3,"units_millions":38.14,"editor":"fighting",
     "motif":"Original frame-window spacing and counterplay evaluation"},
    {"reference":"The Legend of Zelda: Breath of the Wild","chart":"nintendo_switch_2026_06_30",
     "rank":4,"units_millions":34.06,"editor":"metroidvania",
     "motif":"Original traversal, curiosity and systemic environmental puzzles"},
    {"reference":"Super Mario Odyssey","chart":"nintendo_switch_2026_06_30",
     "rank":5,"units_millions":30.80,"editor":"platformer",
     "motif":"Original movement mastery and branching optional challenge routes"},
    {"reference":"The Legend of Zelda: Tears of the Kingdom","chart":"nintendo_switch_2026_06_30",
     "rank":8,"units_millions":22.71,"editor":"sandbox",
     "motif":"Original composable player tools and multiple viable construction solutions"},
    # 2025 US dollar sales rank, not unit counts; NEVER compare to Nintendo units.
    {"reference":"Battlefield 6","chart":"circana_us_2025_dollars",
     "rank":1,"units_millions":None,"editor":"shooter",
     "motif":"Original squad objectives, cover choices and team coordination"},
    {"reference":"NBA 2K26","chart":"circana_us_2025_dollars",
     "rank":2,"units_millions":None,"editor":"sports",
     "motif":"Original possession, stamina, passing and score pacing"},
    {"reference":"Borderlands 4","chart":"circana_us_2025_dollars",
     "rank":3,"units_millions":None,"editor":"rpg",
     "motif":"Original resource-based gear progression and encounter variety"},
    {"reference":"Monster Hunter Wilds","chart":"circana_us_2025_dollars",
     "rank":4,"units_millions":None,"editor":"survival",
     "motif":"Original telegraphed encounters, crafting costs and ecology"},
    {"reference":"Call of Duty: Black Ops 7","chart":"circana_us_2025_dollars",
     "rank":5,"units_millions":None,"editor":"stealth",
     "motif":"Original line-of-sight, detection and recovery challenge"},
)
CHARTS = {
    "nintendo_switch_2026_06_30":{
        "type":"publisher_reported_lifetime_units",
        "as_of":"2026-06-30",
        "region":"worldwide",
        "source_url":"https://www.nintendo.co.jp/ir/en/finance/software/switch.html",
        "limitations":"Lifetime units include hardware bundles, not genre quality metrics",
    },
    "circana_us_2025_dollars":{
        "type":"annual_dollar_sales_rank",
        "as_of":"2025-12-31",
        "region":"United States",
        "source_url":"https://www.statista.com/statistics/1285658/top-ranked-video-games-sales-annual/",
        "limitations":"Annual dollars, not unit counts; no causal mechanics inference",
    },
}


class ScenarioLabError(ValueError):
    """Unapproved source, malformed probes or unbounded mirrored execution."""


def _plain(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False,
                   ensure_ascii=True).encode()
    if len(raw)>256000:
        raise ScenarioLabError("scenario laboratory JSON budget exceeded")
    return json.loads(raw)


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                              allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def sales_informed_catalog(editor: str | None = None) -> dict:
    if editor is not None and editor not in ENGINES:
        raise ScenarioLabError("catalog cannot claim unknown original-game engine")
    known=[_plain(row) for row in MOTIFS if editor is None or row["editor"]==editor]
    result={
        "schema_version":"skeleton.game_builder.sales_informed_motifs.v1",
        "sources":_plain(CHARTS),
        "entries":known,
        "source_rights":"factual_rank_and_abstract_original_design_heuristics_only",
        "evidence_use":"prioritize_questions_not_copy_content_or_certify_design_quality",
    }
    return {**result,"digest":_hash(result)}


def test_manifest(editor: str) -> dict:
    """Enumerate every exposed field/action and all risk dimensions.

    Exhaustive here means exhaustive *declared test categories* and registered
    controls, not the impossible Cartesian product of all game states.
    """
    if editor not in ENGINES:
        raise ScenarioLabError("unknown engine test manifest")
    spec=editor_spec(editor)
    axes=[]
    for field in spec["fields"]:
        values=(
            [field["minimum"],field["default"],field["maximum"]]
            if field["kind"]=="int" else
            [False,True] if field["kind"]=="bool" else
            field["options"] if field["kind"]=="enum" else
            [field["default"]]
        )
        axes.append({
            "name":field["key"],"type":field["kind"],
            "cases":[_plain(x) for x in values],
            "checks":["canonical_schema","source_digest","same_seed_replay",
                      "cross_field_invariants","invalid_value_rejection"],
        })
    actions=list(ACTION_HELP[editor])
    checks=[
        {"id":"source_schema","required":True},
        {"id":"scene_digest_tampering","required":True},
        {"id":"all_registered_actions","required":True,"count":len(actions)},
        {"id":"invalid_and_postterminal_actions","required":True},
        {"id":"replay_same_seed","required":True},
        {"id":"repeatable_cross_seed","required":True},
        {"id":"snapshot_restore_against_reexecution","required":True},
        {"id":"numeric_reward_finiteness","required":True},
        {"id":"resource_conservation_and_budget_guards","required":True},
        {"id":"episode_step_and_memory_limits","required":True},
        {"id":"source_rights_and_no_executable_content","required":True},
        {"id":"AI_rule_boundary_and_provenance","required":True},
        {"id":"candidate_vs_baseline_heldout","required":True},
        {"id":"training_data_separation","required":True},
        {"id":"concurrent_replay_isolation","required":True},
        {"id":"mirrored_angle_coverage","required":True},
        {"id":"ten_source_verified_multispectral_channels","required":True},
        {"id":"ten_pass_reverse_checkpoint_scrutiny","required":True},
        {"id":"telemetry_source_identity","required":True},
        {"id":"native_hardware_limitations_explicit","required":True},
    ]
    result={
        "schema_version":"skeleton.game_builder.engine_test_manifest.v1",
        "engine":editor,
        "registered_action_count":len(actions),
        "registered_actions":actions,
        "field_axes":axes,
        "mandatory_checks":checks,
        "angles":list(ANGLES),
        "declared_coverage":"all_registered_actions_fields_and_check_categories",
        "combinatorial_state_exhaustiveness_claimed":False,
        "verified_passes":0,"execution_status":"not_run",
    }
    return {**result,"digest":_hash(result)}


def all_engine_test_manifests() -> dict:
    entries=[test_manifest(editor) for editor in ENGINES]
    result={"schema_version":"skeleton.game_builder.all_engine_test_manifest.v1",
            "count":len(entries),"engines":entries,"passed":False}
    return {**result,"digest":_hash(result)}


def propose_scenarios(source: Mapping[str,object],
                      *, observations: Sequence[Mapping[str,object]]=(),
                      limit: int=4,
                      excluded_source_digests: Sequence[str]=()) -> dict:
    """Draft scenarios from actual measured evidence, not claimed game mastery."""
    base=parse_studio_source(_plain(source))
    if type(limit) is not int or not 1<=limit<=5 or (
            type(observations) not in (list,tuple) or len(observations)>64):
        raise ScenarioLabError("bounded observations and scenario budget required")
    if (type(excluded_source_digests) not in (list,tuple)
            or len(excluded_source_digests)>64
            or any(type(x) is not str or len(x)!=64
                   or any(char not in "0123456789abcdef" for char in x)
                   for x in excluded_source_digests)):
        raise ScenarioLabError("scenario novelty exclusions require bounded pinned sources")
    excluded=set(excluded_source_digests)
    for row in observations:
        if (type(row) is not dict or set(row)!={"mean_return","failure_rate","episodes"}
                or type(row["mean_return"]) not in (int,float)
                or not math.isfinite(row["mean_return"]) or
                type(row["failure_rate"]) not in (int,float)
                or not 0<=row["failure_rate"]<=1 or
                type(row["episodes"]) is not int or not 0<=row["episodes"]<=100000):
            raise ScenarioLabError("only measured finite training summaries are admitted")
    field_contract=rule_authoring_contract(base)
    fields=[f for f in field_contract["editable_settings"] if f["type"] in ("int","bool","enum")]
    proposals=[]
    # Actual negative returns and high recorded failure drive challenge order;
    # any zero-evidence proposal is explicitly hypothetical.
    evidence_count=sum(x["episodes"] for x in observations)
    needs_stress=any(x["failure_rate"]>0.35 or x["mean_return"]<0 for x in observations)
    sorted_fields=sorted(fields,key=lambda x:(x["type"]!="int",x["path"]))
    motifs=sales_informed_catalog(base["editor"])["entries"]
    revisited=0
    for field in sorted_fields:
        if len(proposals)>=limit:
            break
        old=field["current"]
        if field["type"]=="int":
            if field["minimum"]==field["maximum"]:
                continue
            # Avoid immediate extreme parameters; search local, playable
            # neighborhoods first and increase perturbation under failure.
            width=field["maximum"]-field["minimum"]
            increment=max(1,math.ceil(width/(6 if needs_stress else 12)))
            direction=(1 if sha256(
                (base["editor"]+":"+field["path"]).encode()
            ).digest()[0]%2 else -1)
            value=max(field["minimum"],min(field["maximum"],old+direction*increment))
            if value==old:
                value=max(field["minimum"],min(field["maximum"],old-direction*increment))
            if value==old:
                continue
        elif field["type"]=="bool":
            value=not old
        else:
            value=next((v for v in field["options"] if v!=old),None)
            if value is None:
                continue
        proposal={
            "schema_version":PROPOSAL_SCHEMA,
            "proposal_id":"auto-"+field["path"][:40],
            "base_digest":field_contract["base_digest"],
            "reason":"Study a source-validated mechanic under "
                     +("measured failure stress." if needs_stress
                       else "a distinct original-game circumstance."),
            "scene_seed":None if base["scene"] is None else base["scene"]["seed"],
            "operations":[{
                "scope":"settings","path":field["path"],"op":"set","value":value,
            }],
        }
        try:
            adjusted=apply_rule_proposal(base,proposal)
        except (RuleCurriculumError,ValueError):
            continue
        changed_digest=source_digest(adjusted)
        if changed_digest in excluded:
            revisited+=1
            continue
        excluded.add(changed_digest)
        proposals.append({"proposal":proposal,
                          "variant_source_digest":changed_digest,
                          "support":"measured_problem" if needs_stress else "untested_hypothesis",
                          "mechanics_inspiration":([m["motif"] for m in motifs[:1]]
                                                  or ["Original mechanics boundary stress"]),
                          "sales_rank_is_quality_evidence":False})
    result={"schema_version":"skeleton.game_builder.scenario_discovery.v1",
            "engine":base["editor"],"source_digest":source_digest(base),
            "measured_episode_count":evidence_count,
            "repeated_scenarios_skipped":revisited,
            "scenario_delta_strategy":"bounded_local_numeric_changes_not_extreme_defaults",
            "scenarios":proposals,"automatic_training_performed":False,
            "scenarios_verified_as_successful":False,
            "requires_rights_and_operator_training_admission":True}
    return {**result,"digest":_hash(result)}


def _choose(actions: tuple[str,...], angle: str, step: int, seed: int,
            last: Mapping[str,float]) -> str:
    rng=random.Random(int.from_bytes(sha256(
        f"{angle}:{seed}:{step}".encode()).digest()[:8],"big"))
    candidates={
        "explore": ("survey","observe","inspect","north","east","look","move"),
        "progress": ("attack","advance","move","trade","jump","right","tick"),
        "safety": ("guard","rest","heal","inspect","wait","defend"),
        "economy": ("sell:1","buy:1","collect","craft","harvest","survey"),
        "adversary": ("left","back","wait","inspect","down","retreat"),
        "boundary": ("inspect","tick","wait","end_turn","survey"),
        "temporal": ("tick","wait","advance","inspect","turn","end_turn"),
        "causal": ("buy:1","sell:1","produce","invest","craft","use","play"),
        "perturbation": ("jump","back","left","down","dodge","guard","inspect"),
        "recovery": ("rest","heal","repair","save:0","load:0","retreat","inspect"),
    }[angle]
    usable=[x for x in actions if any(x==p or x.startswith(p+":") for p in candidates)]
    if angle=="boundary" and step%3==0:
        return actions[-1]
    if angle=="adversary" and step%4==0:
        return actions[rng.randrange(len(actions))]
    if usable:
        return usable[(step+seed%len(usable))%len(usable)]
    return actions[rng.randrange(len(actions))]


def _lane(source: dict,angle: str,seed: int,steps: int) -> dict:
    env=StudioGameEnvironment(source,max_steps=steps)
    try:
        observation=dict(env.reset(seed))
        previews=[env.preview()]
        actions=[]
        rejected=0
        accepted_count=0
        productive_changes=0
        total=0.0
        digests=[]
        # The time coordinate increases even for no-op actions. Only actual
        # gameplay features count toward the novel-state evidence metric.
        features=tuple(key for key in sorted(observation) if key!="time")
        def state_key(state):
            return tuple(round(float(state[key]),6) for key in features)
        observed={state_key(observation)}
        gameplay_transition_states=[state_key(observation)]
        for i in range(steps):
            if env.done: break
            action=_choose(env.spec.actions,angle,i,seed,observation)
            measured=env.step(action)
            accepted=measured.info.get("evidence",{}).get("accepted",False)
            rejected+=int(accepted is not True)
            accepted_count+=int(accepted is True)
            total+=measured.reward
            digests.append(measured.transition_digest)
            next_observation=dict(measured.observation)
            if accepted is True and state_key(next_observation)!=state_key(observation):
                productive_changes+=1
            observed.add(state_key(next_observation))
            gameplay_transition_states.append(state_key(next_observation))
            observation=next_observation
            actions.append(action)
            if (i+1)%max(1,steps//(MAX_FRAMES-1))==0:
                previews.append(env.preview())
        final=env.snapshot()
        if not previews or previews[-1].get("step")!=len(actions):
            previews.append(env.preview())
        # Strictly bound previews, don't claim real game imagery.
        previews=previews[-MAX_FRAMES:]
        result={
            "angle":angle,"seed":seed,"steps":len(actions),
            "actions":actions,"rejected_actions":rejected,
            "accepted_actions":accepted_count,
            "productive_state_changes":productive_changes,
            "unique_gameplay_states":len(observed),
            "gameplay_transition_states_digest":_hash(gameplay_transition_states),
            "accepted_action_rate":round(accepted_count/max(1,len(actions)),6),
            "productive_action_rate":round(productive_changes/max(1,len(actions)),6),
            # The emulator-compatible reference replays the full action log
            # at each step. Count real replayed action applications as the
            # cost proxy, not just the visible number of requested steps.
            "replayed_action_applications":sum(range(1,len(actions)+1)),
            "total_reward":round(total,6),
            "source_digest":env.source_digest,
            "environment_digest":env.spec.environment_digest,
            "last_observation":observation,
            "snapshot_digest":final["digest"],
            "transition_digests":digests,
            "frames":previews,
            "native_frames":False,
        }
        # Every lane is independently replayed under all ten scrutiny gates,
        # with ten numeric analysis channels and reverse prefix checks.
        from .game_studio_multispectral import audit_simulation
        result["multispectral"]=audit_simulation(source,result,steps=steps)
        result["audit_passed"]=result["multispectral"]["passed_count"]==10
        return {**result,"digest":_hash(result)}
    finally:
        env.close()


def mirrored_simulations(source: Mapping[str,object], *,
                         seed: int=0, steps: int=12,
                         angles: Sequence[str]=ANGLES,
                         workers: int=4) -> dict:
    """Execute up to ten independently replayed, ten-pass-audited mirror runs."""
    original=parse_studio_source(_plain(source))
    if (type(seed) is not int or not 0<=seed<=2**31-MAX_LANES-1
            or type(steps) is not int or not 1<=steps<=MAX_STEPS
            or type(workers) is not int or not 1<=workers<=4
            or type(angles) not in (tuple,list)
            or not 1<=len(angles)<=MAX_LANES or len(set(angles))!=len(angles)
            or any(angle not in ANGLES for angle in angles)):
        raise ScenarioLabError("mirrored worker, seed, angle or step bounds exceeded")
    with ThreadPoolExecutor(max_workers=min(workers,len(angles)),
                            thread_name_prefix="jeeves-studio-mirror") as pool:
        results=list(pool.map(
            lambda item: _lane(original,item[1],seed+item[0],steps),
            enumerate(angles),
        ))
    record={
        "schema_version":SCHEMA,
        "engine":original["editor"],"source_digest":source_digest(original),
        "angles":list(angles),"lanes":results,
        "workers_requested":workers,"workers_used":min(workers,len(angles)),
        "concurrent_reference_simulations_executed":len(results),
        "scrutiny_checks_per_run":10,
        "scrutiny_checked_runs":sum(bool(row["audit_passed"]) for row in results),
        "multispectral_analysis_channels":list(
            results[0]["multispectral"]["spectral_channels"]
        ),
        "actual_spectral_sensor_hardware":False,
        "view_kind":"sampled_reference_telemetry_not_native_game_frames",
        "training_candidate_mutated":False,
        "learning_metrics_derived_from_actual_runtime":True,
    }
    return {**record,"digest":_hash(record)}



def mirrored_rule_comparison(baseline: Mapping[str,object],
                             candidate: Mapping[str,object],
                             *, seed: int=0, steps: int=12,
                             angles: Sequence[str]=ANGLES) -> dict:
    """Paired-seed, six-angle evidence for *hypothesized* original rules.

    This is held out from policy gradients, and does not certify subjective
    game design quality, sales success or hardware compatibility.
    """
    baseline=parse_studio_source(_plain(baseline))
    candidate=parse_studio_source(_plain(candidate))
    if baseline["editor"]!=candidate["editor"] or baseline["actions"]!=candidate["actions"]:
        raise ScenarioLabError("mirrors cannot compare foreign engines or differing action alphabets")
    first=mirrored_simulations(baseline,seed=seed,steps=steps,
                               angles=angles,workers=4)
    second=mirrored_simulations(candidate,seed=seed,steps=steps,
                                angles=angles,workers=4)
    observations=[]
    for a,b in zip(first["lanes"],second["lanes"],strict=True):
        observations.append({
            "angle":a["angle"],
            "seed":a["seed"],
            "baseline_return":a["total_reward"],
            "candidate_return":b["total_reward"],
            "return_difference":round(b["total_reward"]-a["total_reward"],6),
            "baseline_rejected_actions":a["rejected_actions"],
            "candidate_rejected_actions":b["rejected_actions"],
            "baseline_accepted_actions":a["accepted_actions"],
            "candidate_accepted_actions":b["accepted_actions"],
            "baseline_productive_state_changes":a["productive_state_changes"],
            "candidate_productive_state_changes":b["productive_state_changes"],
            "baseline_unique_gameplay_states":a["unique_gameplay_states"],
            "candidate_unique_gameplay_states":b["unique_gameplay_states"],
            "baseline_gameplay_transition_states_digest":a["gameplay_transition_states_digest"],
            "candidate_gameplay_transition_states_digest":b["gameplay_transition_states_digest"],
            "baseline_replayed_action_applications":a["replayed_action_applications"],
            "candidate_replayed_action_applications":b["replayed_action_applications"],
            "baseline_executed_steps":a["steps"],
            "candidate_executed_steps":b["steps"],
            "baseline_snapshot":a["snapshot_digest"],
            "candidate_snapshot":b["snapshot_digest"],
            "baseline_evidence_digest":a["digest"],
            "candidate_evidence_digest":b["digest"],
        })
    total_actions=sum(
        item["baseline_executed_steps"]+item["candidate_executed_steps"]
        for item in observations
    )
    total_replays=sum(
        item["baseline_replayed_action_applications"]
        +item["candidate_replayed_action_applications"]
        for item in observations
    )
    productive_pairs=sum(
        item["baseline_productive_state_changes"]
        +item["candidate_productive_state_changes"]
        for item in observations
    )
    measured_differences=sum(
        item["return_difference"]!=0
        or item["baseline_unique_gameplay_states"]!=item["candidate_unique_gameplay_states"]
        or item["baseline_productive_state_changes"]!=item["candidate_productive_state_changes"]
        or item["baseline_gameplay_transition_states_digest"]!=
           item["candidate_gameplay_transition_states_digest"]
        for item in observations
    )
    # Avoid promoting settings which do not have any measured influence
    # under sampled play. Short traces can only be inconclusive, never
    # a claimed game-design success or generalization proof.
    informative=(
        total_actions>=4 and productive_pairs>=2
        and measured_differences>=1
        and sum(item["candidate_accepted_actions"] for item in observations)>=2
    )
    result={
        "schema_version":"skeleton.game_builder.mirrored_rule_comparison.v1",
        "engine":baseline["editor"],
        "baseline_source_digest":source_digest(baseline),
        "candidate_source_digest":source_digest(candidate),
        "mirrors":observations,
        "total_executed_steps":total_actions,
        "total_replayed_action_applications":total_replays,
        "productive_state_changes":productive_pairs,
        "measured_behavior_differences":measured_differences,
        "novelty_per_100_replayed_actions":round(
            100*productive_pairs/max(1,total_replays),6,
        ),
        "informative_for_rule_selection":informative,
        "effectiveness_classification":(
            "measured_difference" if informative else "insufficient_behavioral_evidence"
        ),
        "mean_return_difference":round(sum(x["return_difference"] for x in observations)/len(observations),6),
        "worst_return_difference":min(x["return_difference"] for x in observations),
        "possibly_viable_under_bounded_mirror_checks":informative and all(
            x["return_difference"]>=-1 for x in observations
        ),
        "independent_human_review_required":True,
        "source_promotion_authorized":False,
        "claimed_exhaustive_game_state_coverage":False,
    }
    return {**result,"digest":_hash(result)}


__all__=["ANGLES","MAX_LANES","ScenarioLabError","mirrored_rule_comparison","sales_informed_catalog",
         "test_manifest","all_engine_test_manifests",
         "propose_scenarios","mirrored_simulations"]
