"""Typed multi-factor original-game scenario design and measurable Q-parameter learning.

Factor values are *only* registered original game settings and commands.
A requested modality without executable controls is listed as unsupported,
not invented as synthetic audio, music, facial expressions, cameras or AI.
Greedy pair/three-way covering selects legal joint perturbations within a
fixed budget, followed by source-replayed ablations and optional actual local
Q-policy weight updates. Every variant is independent, source pinned and
heldout seed separated; no global Jeeves neural weights are modified.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import combinations, product
import json
import math

from skeleton.ai.game_builder.system_editors import editor_spec
from .game_studio_environment import make_studio_source, parse_studio_source, studio_request_tree
from .game_studio_scenario_lab import _lane
from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest

SCHEMA="skeleton.game_builder.multifactor_training.v1"
MAX_AXES=8
MAX_SCENARIOS=24
MAX_EXECUTED=8
MAX_FACTOR_CANDIDATES=512
# Name matching is a capability *heuristic* over real declared knobs; no
# category promises physical simulation outside its registered source API.
CATEGORIES={
    "items":("item","inventory","loot","pickup","bag","goods","collect","drop"),
    "abilities":("ability","skill","spell","mana","cast","power","cooldown","buff","dash"),
    "weapons":("weapon","gun","ammo","bullet","projectile","attack","fire","damage","bow"),
    "tools":("tool","craft","build","repair","harvest","mine","equip","upgrade"),
    "style":("style","genre","visual","perspective","palette","theme","skin"),
    "movement":("move","speed","jump","walk","sprint","run","climb","dodge","velocity","steer","accelerat","north","south","east","west"),
    "expression":("express","emotion","face","gesture","emote","mood"),
    "reaction":("react","counter","guard","defend","block","parry","retaliat"),
    "consequence":("consequence","karma","reputation","penalty","reward","outcome","branch","ending"),
    "actions":("action","interact","use","inspect","survey","wait","tick","turn"),
    "environment":("weather","terrain","map","world","hazard","water","wind","climate","biome","gravity","topology","light"),
    "ambience":("ambience","ambient","atmosphere","fog","rain","night","day","soundscape"),
    "music":("music","tempo","bpm","beat","rhythm","melody","note","song","instrument"),
    "apparel":("apparel","armor","armour","cloth","outfit","wear","equipment"),
    "status_effects":("poison","stun","burn","freeze","bleed","heal","health","fatigue","stamina"),
    "npc_behavior":("npc","enemy","ally","social","faction","population","dialogue"),
    "quests":("quest","mission","objective","contract","goal","victory"),
    "physics":("physics","mass","friction","force","collision","gravity","traction"),
    "economy":("market","price","trade","tax","credit","gold","sell","buy"),
    "camera":("camera","angle","focus","zoom","pan","shot","cutscene"),
    "time":("time","duration","day","turn","tick","window","cycle"),
    "accessibility":("accessib","contrast","caption","subtitl","input_assist"),
    "localization":("locale","language","translation","subtitle"),
    "network":("network","latency","packet","client","server","sync"),
    "save_load":("save","load","checkpoint","persist","rollback"),
}
KINDS=("source_field","registered_action")


class MultiFactorError(ValueError):
    """Unknown source, unbounded factorial design or unverified training."""


def _json(value,maximum=3000000):
    try:
        data=json.dumps(value,sort_keys=True,separators=(",",":"),
                        ensure_ascii=True,allow_nan=False).encode()
    except (ValueError,TypeError,RecursionError) as exc:
        raise MultiFactorError("finite bounded factor evidence required") from exc
    if len(data)>maximum:
        raise MultiFactorError("factor result exceeds bounded evidence transport")
    return data


def _sha(value):
    return sha256(_json(value)).hexdigest()


def _category(key:str)->str|None:
    name=key.lower()
    for category, fragments in CATEGORIES.items():
        if any(fragment in name for fragment in fragments):
            return category
    return None


def _field_variants(source:dict, field:dict)->list[object]:
    old=source["settings"][field["key"]]
    if field["kind"]=="bool":
        candidates=[old,not old]
    elif field["kind"]=="enum":
        candidates=[old]+[v for v in field["options"] if v!=old][:2]
    elif field["kind"]=="int":
        lo,hi=field["minimum"],field["maximum"]
        amount=max(1,math.ceil((hi-lo)/12))
        candidates=[old,max(lo,min(hi,old+amount)),
                    max(lo,min(hi,old-amount)),lo,hi]
    else:
        return []
    out=[]
    for value in candidates:
        if value in out:continue
        cfg=dict(source["settings"]);cfg[field["key"]]=value
        try:
            make_studio_source(source["editor"],cfg,scene=source["scene"],
                               actions=source["actions"])
        except (TypeError,ValueError):
            continue
        out.append(value)
        if len(out)==3:break
    return out if len(out)>=2 else []


def multifactor_capabilities(raw_source:Mapping[str,object])->dict:
    source=parse_studio_source(dict(raw_source))
    catalog=editor_spec(source["editor"])
    groups={name:[] for name in CATEGORIES}
    for field in catalog["fields"]:
        category=_category(field["key"])
        if category is None:continue
        variants=_field_variants(source,field)
        if len(variants)>1:
            groups[category].append({
                "id":"setting:"+field["key"],"category":category,
                "kind":"source_field","field":field["key"],
                "levels":variants,"origin":"canonical_editor_validated_value",
            })
    for action in source["actions"]:
        category=_category(action)
        if category is not None:
            groups[category].append({
                "id":"action:"+action,"category":category,"kind":"registered_action",
                "field":None,"levels":[None,action],
                "origin":"original_engine_registered_action",
            })
    # Keep category dimensions separately visible, even if a game cannot
    # simulate them. Action modes do not imply a physically rendered scene.
    manifest=[]
    axes=[]
    for category, choices in groups.items():
        available=bool(choices)
        manifest.append({
            "category":category,
            "status":"executable_logic" if available else "unimplemented_for_this_engine",
            "registered_controls":[row["id"] for row in choices],
            "real_physical_modality_certified":False,
        })
        if choices:
            # Round-robin across distinct requested factors; only one
            # representative per category before any repeated dimension.
            axes.append(choices[0])
    # The first bank spans distinct categories; subsequent banks can
    # include additional controls from the same family (multi-item/tool).
    for category,choices in groups.items():
        axes.extend(choices[1:3])
    axes=axes[:64]
    data={
        "schema_version":"skeleton.game_builder.multifactor_capabilities.v1",
        "editor":source["editor"],"source_digest":_sha(source),
        "categories":manifest,
        "available_axes":axes,"selected_axes":axes[:MAX_AXES],
        "total_executable_axes":len(axes),
        "maximum_simultaneous_axes":MAX_AXES,
        "joint_modality_claim":"canonical_settings_and_real_action_sequences_only",
        "native_music_audio_expression_rendering_assumed":False,
        "max_interaction_order":3,
        "unsupported_category_count":sum(x["status"]!="executable_logic" for x in manifest),
    }
    return {**data,"digest":_sha(data)}


def _variant_source(source:dict, axes:list[dict], levels:tuple[int,...]):
    settings=dict(source["settings"])
    used_actions=[]
    for axis,index in zip(axes,levels):
        if axis["kind"]=="source_field":
            settings[axis["field"]]=axis["levels"][index]
        elif index:
            used_actions.append(axis["levels"][index])
    try:
        updated=make_studio_source(
            source["editor"],settings,scene=source["scene"],
            actions=source["actions"],
        )
    except (TypeError,ValueError):
        return None
    if updated==source and not used_actions:return None
    return updated,tuple(dict.fromkeys(used_actions))


def _coverage(levels:tuple[int,...],order:int)->set[tuple]:
    return {
        tuple((i,levels[i]) for i in indexes)
        for degree in range(1,min(order,len(levels))+1)
        for indexes in combinations(range(len(levels)),degree)
    }


def plan_multifactor_scenarios(
    raw_source:Mapping[str,object], *,
    interaction_order:int=3, max_scenarios:int=16,
    axis_offset:int=0,
)->dict:
    source=parse_studio_source(dict(raw_source))
    if (type(interaction_order) is not int or interaction_order not in (2,3)
            or type(max_scenarios) is not int
            or not 2<=max_scenarios<=MAX_SCENARIOS
            or type(axis_offset) is not int or axis_offset<0
            or axis_offset>63):
        raise MultiFactorError("finite pair/three-way test-budget controls required")
    capacity=multifactor_capabilities(source)
    axes=capacity["available_axes"][axis_offset:axis_offset+MAX_AXES]
    if not axes:
        raise MultiFactorError("source has no variable executable factor axes")
    # An 8-axis ternary Cartesian grid contains 6,561 worlds. Build a
    # deterministic bounded covering candidate pool from one-, two- and
    # three-factor perturbations instead of blindly allocating all worlds.
    candidates=set()
    n=len(axes)
    zero=(0,)*n
    candidates.add(zero)
    for degree in (1,2,3):
        for inds in combinations(range(n),degree):
            for values in product(*(range(1,len(axes[i]["levels"])) for i in inds)):
                vector=list(zero)
                for i,value in zip(inds,values):
                    vector[i]=value
                candidates.add(tuple(vector))
                if len(candidates)>=MAX_FACTOR_CANDIDATES:
                    break
            if len(candidates)>=MAX_FACTOR_CANDIDATES:
                break
        if len(candidates)>=MAX_FACTOR_CANDIDATES:
            break
    candidates.add(tuple(
        min(1,len(axis["levels"])-1) for axis in axes
    ))
    pairs=[]
    for levels in sorted(candidates):
        candidate=_variant_source(source,axes,levels)
        if candidate is not None:
            edited,extra_actions=candidate
            pairs.append((tuple(levels),edited,extra_actions))
    if not pairs:
        raise MultiFactorError("no multi-axis world changes satisfy original game invariants")
    seen=set()
    selected=[]
    # Pair/triple interaction selection: set-cover greedily; all offered
    # tuples are already validated by the canonical world constructor.
    while pairs and len(selected)<max_scenarios:
        ranked=sorted(pairs,key=lambda entry:(
            -len(_coverage(entry[0],interaction_order)-seen),
            sum(bool(v) for v in entry[0]),
            entry[0],
        ))
        winner=ranked[0]
        gain=_coverage(winner[0],interaction_order)-seen
        if not gain:
            break
        seen.update(gain)
        levels,edited,extra=winner
        plan={
            "index":len(selected),
            "levels":list(levels),
            "source":edited,
            "source_digest":_sha(edited),
            "selected_registered_actions":list(extra),
            "changed_axes":[axes[i]["id"] for i,x in enumerate(levels) if x],
            "new_coverage_witnesses":len(gain),
            "coverage_custody_digest":_sha(sorted([repr(x) for x in gain])),
        }
        selected.append(plan)
        pairs=[entry for entry in pairs if entry[0]!=levels]
    total=set()
    for levels,_,_ in pairs+[(tuple(row["levels"]),row["source"],()) for row in selected]:
        total.update(_coverage(levels,interaction_order))
    out={
        "schema_version":"skeleton.game_builder.multifactor_plan.v1",
        "editor":source["editor"],"base_source_digest":_sha(source),
        "interaction_order":interaction_order,
        "axis_offset":axis_offset,
        "total_executable_axes":capacity["total_executable_axes"],
        "axes":axes,"capabilities_digest":capacity["digest"],
        "scenarios":selected,
        "covered_interactions":len(seen),
        "valid_interaction_opportunities":len(total),
        "bounded_candidate_worlds_considered":len(candidates),
        "full_cross_product_enumerated":False,
        "coverage_fraction":round(len(seen)/max(1,len(total)),6),
        "maximum_possible_variants_executed_claimed":False,
        "all_original_scenes_and_assets_preserved":True,
        "media_modes_not_in_source_are_not_executed":True,
    }
    return {**out,"digest":_sha(out)}


def _action_script(source:dict, selected:list[str],steps:int,seed:int)->tuple[str,...]:
    palette=source["actions"]
    if not palette:
        raise MultiFactorError("source game has no executable commands")
    mandatory=list(dict.fromkeys(selected))
    # Chosen combination actions MUST actually execute early in a short
    # scenario; seed jitter must never hide an item/ability/tool intervention.
    # Other registered controls fill the remaining bounded horizon.
    fallback=[x for x in palette if x not in mandatory]
    if not fallback:
        fallback=mandatory or list(palette)
    tail=[fallback[(seed+i)%len(fallback)] for i in range(max(0,steps-len(mandatory)))]
    queue=mandatory+tail
    return tuple(queue[:steps])


def _gain(before:dict,after:dict)->dict:
    left={tuple(item["state"]):item for item in before["q_table"]}
    right={tuple(item["state"]):item for item in after["q_table"]}
    added=0;changed=0;maximum=0.0;total=0.0;details=[]
    for state,row in sorted(right.items()):
        previous=left.get(state)
        old_q=previous["values"] if previous else [0.0]*len(row["values"])
        old_n=previous["visits"] if previous else [0]*len(row["visits"])
        for i,(old,new,prior,visits) in enumerate(zip(
            old_q,row["values"],old_n,row["visits"]
        )):
            delta=round(float(new)-float(old),9)
            if abs(delta)>1e-10:
                changed+=1;total+=abs(delta);maximum=max(maximum,abs(delta))
                if len(details)<96:
                    details.append({
                        "state":list(state),"action_index":i,
                        "before":round(float(old),9),
                        "after":round(float(new),9),
                        "delta":delta,
                        "visits_before":prior,"visits_after":visits,
                    })
            added+=int(prior==0 and visits>0)
    return {
        "newly_visited_state_action_parameters":added,
        "changed_q_parameters":changed,
        "sum_absolute_q_weight_change":round(total,9),
        "max_absolute_q_weight_change":round(maximum,9),
        "sample_parameter_updates":details,
        "complete_q_diff_digest":_sha({
            "before":before["snapshot_digest"],"after":after["snapshot_digest"],
            "q_table":after["q_table"],
        }),
        "model_kind":"local_tabular_Q_not_neural_transformer",
        "production_neural_parameters_updated":0,
    }


def execute_multifactor_scenarios(
    source:Mapping[str,object], *,
    interaction_order:int=3,
    max_scenarios:int=8,steps:int=4,seed:int=1,axis_offset:int=0,
    train:bool=False,authorized:bool=False,rights_cleared:bool=False,
)->dict:
    original=parse_studio_source(dict(source))
    if (type(max_scenarios) is not int or not 2<=max_scenarios<=MAX_EXECUTED
            or type(steps) is not int or not 1<=steps<=12
            or type(seed) is not int or not 0<=seed<=2**31-20000
            or type(train) is not bool):
        raise MultiFactorError("real game and candidate training resource ceiling exceeded")
    if train and (authorized is not True or rights_cleared is not True):
        raise PermissionError("local weight gains require explicit operator and source rights")
    plan=plan_multifactor_scenarios(
        original,interaction_order=interaction_order,max_scenarios=max_scenarios,
        axis_offset=axis_offset,
    )
    experiments=[]
    seen_seed=set()
    for row in plan["scenarios"]:
        trial_seed=seed+row["index"]*5
        if trial_seed in seen_seed:raise MultiFactorError("simulated split contamination")
        seen_seed.add(trial_seed)
        modified=row["source"]
        script=_action_script(modified,row["selected_registered_actions"],steps,trial_seed)
        control=_lane(original,"causal",trial_seed,steps,scripted_actions=script)
        changed=_lane(modified,"causal",trial_seed,steps,scripted_actions=script)
        if not control["audit_passed"] or not changed["audit_passed"]:
            raise MultiFactorError("unverified combined world cannot supply weight data")
        selected_actions=row["selected_registered_actions"]
        action_receipts=[
            {
                "action":name,
                "attempted":any(event["action"]==name for event in changed["step_receipts"]),
                "accepted":any(
                    event["action"]==name and event["accepted"] is True
                    for event in changed["step_receipts"]
                ),
            }
            for name in selected_actions
        ]
        # An attempted but rejected action is never proof an item, ability,
        # weapon, tool, animation or media behavior was actually exercised.
        all_selected_exercised=all(item["accepted"] for item in action_receipts)
        if (control["source_digest"]!=_sha(original)
                or changed["source_digest"]!=row["source_digest"]):
            raise MultiFactorError("game source custody differs from original design")
        # One-factor removals reveal whether joint changes still affect
        # measured behavior. A two-way difference-of-differences tests a
        # particular interaction rather than ascribing all gain to one item.
        changed_indices=[
            i for i,value in enumerate(row["levels"]) if value
        ][:4]
        counterfactuals=[]
        def controlled_intervention(removed):
            adjusted=list(row["levels"])
            for index in removed:
                adjusted[index]=0
            alternative=_variant_source(original,plan["axes"],tuple(adjusted))
            if alternative is None:
                return None
            candidate_source,chosen=alternative
            action_sequence=_action_script(
                candidate_source,list(chosen),steps,trial_seed,
            )
            probe=_lane(
                candidate_source,"causal",trial_seed,steps,
                scripted_actions=action_sequence,
            )
            if not probe["audit_passed"]:
                raise MultiFactorError("counterfactual game source was not independently audited")
            return {
                "removed_axes":[plan["axes"][i]["id"] for i in removed],
                "source_digest":_sha(candidate_source),
                "trace_digest":probe["digest"],
                "audit_digest":probe["multispectral"]["digest"],
                "accepted_actions":probe["accepted_actions"],
                "productive_state_changes":probe["productive_state_changes"],
                "reward":probe["total_reward"],
                "reward_difference_to_joint":round(
                    changed["total_reward"]-probe["total_reward"],6,
                ),
                "joint_gameplay_trace_differs":(
                    changed["gameplay_transition_states_digest"]!=
                    probe["gameplay_transition_states_digest"]
                ),
                "source_verified":True,
            }
        for idx in changed_indices:
            counter=controlled_intervention((idx,))
            if counter is not None:
                counterfactuals.append(counter)
        pair_interaction=None
        if len(changed_indices)>=2:
            a,b=changed_indices[:2]
            removed_a=next((x for x in counterfactuals
                            if x["removed_axes"]==[plan["axes"][a]["id"]]),None)
            removed_b=next((x for x in counterfactuals
                            if x["removed_axes"]==[plan["axes"][b]["id"]]),None)
            removed_both=controlled_intervention((a,b))
            if removed_a and removed_b and removed_both:
                interaction=(
                    changed["total_reward"]-removed_a["reward"]
                    -removed_b["reward"]+removed_both["reward"]
                )
                pair_interaction={
                    "axes":[plan["axes"][a]["id"],plan["axes"][b]["id"]],
                    "pair_removed_trace_digest":removed_both["trace_digest"],
                    "difference_of_differences":round(interaction,6),
                    "measured_on_same_seed":trial_seed,
                    "mechanical_causal_generalization_proven":False,
                }
        learned=None
        if train:
            req=GameEnvironmentRequest(
                "studio:"+modified["editor"],kind="studio",
                tree=studio_request_tree(modified),max_steps=steps,
            )
            env=req.build()
            try:spec=env.spec
            finally:env.close()
            learner=GamePolicyLearner(
                spec,GameLearningConfig(
                    seed=trial_seed,max_episodes=3,max_updates=3*steps,
                ),
                policy_id="multifactor:"+modified["editor"]+":"+str(trial_seed),
                source_lineage={
                    "origin":"source_verified_multifactor_original_game",
                    "rights_acknowledged":True,
                    "factor_plan_digest":plan["digest"],
                    "factor_source_digest":row["source_digest"],
                    "no_live_neural_promotion":True,
                },
            )
            before=learner.snapshot()
            observed=learner.train(
                req.build,episodes=3,
                seeds=[trial_seed+9000+i for i in range(3)],
            )
            after=learner.snapshot()
            heldout=learner.evaluate(
                req.build,heldout_seeds=[
                    trial_seed+14000+i for i in range(2)
                ],baseline_snapshot=before,
            ).as_dict()
            gain=_gain(before,after)
            valid_steps=0
            changed_states=0
            for trace in observed.traces:
                for transition in trace["transitions"]:
                    accepted=(transition.get("info") or {}).get("evidence",{}).get("accepted") is True
                    valid_steps+=int(accepted)
                    old=transition["observation"]
                    new=transition["next_observation"]
                    changed_states+=int(accepted and any(
                        abs(float(new[key])-float(old[key]))>1e-8
                        for key in old if key!="time"
                    ))
            useful={
                "actual_q_updates":observed.updates,
                "accepted_game_actions":valid_steps,
                "productive_non_time_transitions":changed_states,
                "new_q_state_actions_per_100_updates":round(
                    100*gain["newly_visited_state_action_parameters"]/max(1,observed.updates),6,
                ),
                "changed_q_parameters_per_100_updates":round(
                    100*gain["changed_q_parameters"]/max(1,observed.updates),6,
                ),
                "absolute_q_weight_change_per_update":round(
                    gain["sum_absolute_q_weight_change"]/max(1,observed.updates),9,
                ),
                "heldout_mean_return_difference":heldout["mean_return_difference"],
                "heldout_regression_observed":heldout["mean_return_difference"]<0,
                "neural_parameter_updates_observed":0,
                "claimed_converged_or_SOTA":False,
            }
            learned={
                "policy_before_digest":before["snapshot_digest"],
                "policy_after_digest":after["snapshot_digest"],
                "parameter_gain":gain,
                "measured_learning_efficiency":useful,
                "actual_training_updates":observed.updates,
                "training_trace_digests":[t["trace_digest"] for t in observed.traces],
                "training_episode_actions":[{
                    "seed":trace["seed"],
                    "actions":[event["action"] for event in trace["transitions"]],
                    "trace_digest":trace["trace_digest"],
                } for trace in observed.traces],
                "heldout_evaluation":heldout,
                "heldout_seeds":[trial_seed+14000+i for i in range(2)],
                "candidate_policy_snapshot":after,
                "promoted_to_production":False,
            }
        run={
            "index":row["index"],
            "axes":row["changed_axes"],
            "source_digest":row["source_digest"],
            "original_digest":_sha(original),
            "seed":trial_seed,"scripted_actions":list(script),
            "control_audit_digest":control["multispectral"]["digest"],
            "variant_audit_digest":changed["multispectral"]["digest"],
            "control_trace_digest":control["digest"],
            "variant_trace_digest":changed["digest"],
            "control_accepted":control["accepted_actions"],
            "variant_accepted":changed["accepted_actions"],
            "control_productive_changes":control["productive_state_changes"],
            "variant_productive_changes":changed["productive_state_changes"],
            "reward_delta":round(changed["total_reward"]-control["total_reward"],6),
            "source_behavior_differs":(
                changed["gameplay_transition_states_digest"]!=
                control["gameplay_transition_states_digest"]
                or changed["total_reward"]!=control["total_reward"]
            ),
            "variant_source_verified":True,
            "selected_action_receipts":action_receipts,
            "all_selected_actions_accepted":all_selected_exercised,
            "unexecuted_action_categories":[
                item["action"] for item in action_receipts if not item["accepted"]
            ],
            "factor_ablation_receipts":counterfactuals,
            "pairwise_interaction_witness":pair_interaction,
            "actual_weight_training":learned,
            "native_audio_or_visual_content_created":False,
        }
        experiments.append({**run,"digest":_sha(run)})
    result={
        "schema_version":SCHEMA,
        "plan_digest":plan["digest"],
        "plan":plan,
        "editor":original["editor"],
        "scenarios_executed":len(experiments),
        "measured_interactions_not_causal_proof":True,
        "actual_q_weight_updates":sum(
            (x["actual_weight_training"] or {}).get("actual_training_updates",0)
            for x in experiments
        ),
        "newly_visited_q_parameters":sum(
            (x["actual_weight_training"] or {}).get("parameter_gain",{}).get(
                "newly_visited_state_action_parameters",0)
            for x in experiments
        ),
        "different_gameplay_observed_count":sum(x["source_behavior_differs"] for x in experiments),
        "scenarios_with_all_selected_actions_actually_accepted":sum(
            x["all_selected_actions_accepted"] for x in experiments
        ),
        "scenarios_with_rejected_or_unexecuted_factor_actions":sum(
            not x["all_selected_actions_accepted"] for x in experiments
        ),
        "experiments":experiments,
        "independently_heldout_from_training":True,
        "production_neural_weights_modified":False,
        "automatic_promotion":False,
    }
    _json(result)
    return {**result,"digest":_sha(result)}


__all__=[
    "CATEGORIES","MultiFactorError","multifactor_capabilities",
    "plan_multifactor_scenarios","execute_multifactor_scenarios",
]
