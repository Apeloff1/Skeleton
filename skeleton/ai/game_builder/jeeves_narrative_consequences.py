"""Original story and NPC consequence matrix for genuinely played campaign routes.

Reads only approved, full-history-verified story scenes, a committed campaign
lore map and verified finite player action portfolios. Links real observed
game nodes to original character, region, event and social affiliation
changes without claiming these authored changes were mechanically applied
in a game engine. The distinction is part of every evidence receipt.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .game_project_workspace import GameWorkspace,_json
from .contracts import canonical_json,canonical_digest
from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_campaign_lore import rebuild_campaign_lore_document
from .jeeves_campaign_outcomes import rebuild_outcome_portfolio
from .story_workspace import load_story_workspace
from .story_canon_fabric import scene_path,FIELDS

SCHEMA="skeleton.ai.jeeves_narrative_consequences.v1"
DOCUMENT="skeleton.game_builder.reviewed_narrative_consequence_matrix.v1"
IDENT=re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
EMPTY_SHA=sha256(b"").hexdigest()
MAX_SOURCE_BYTES=220000
MAX_CAUSAL_CHANGES=800
MAX_PATH_EVENTS=2500


def compile_narrative_consequences(workspace,project,campaign_id):
    """Rebuild every actual scenario outcome against full source-signed story."""
    if (not isinstance(workspace,GameWorkspace)
            or type(project) is not str or project!=workspace.active()
            or type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
        raise JeevesAppwideError("selected original approved game campaign required")
    prefix="game/campaigns/"+campaign_id
    lore_version=workspace.read("current",project,prefix+"_lore.json")
    portfolio_version=workspace.read("current",project,prefix+"_outcomes.json")
    lore=_json(lore_version["content"])
    portfolio=_json(portfolio_version["content"])
    if (rebuild_campaign_lore_document(workspace,project,lore)!=lore or
            rebuild_outcome_portfolio(workspace,project,portfolio)!=portfolio):
        raise JeevesAppwideError("reviewed story, campaign or gameplay source drifted")
    if lore["campaign_id"]!=campaign_id or portfolio["campaign_id"]!=campaign_id:
        raise JeevesAppwideError("gameplay and narrative belong to different campaigns")
    if lore["campaign_source_sha256"]!=portfolio["approved_campaign_source_sha256"]:
        raise JeevesAppwideError("gameplay outcomes must match linked original campaign")
    bible,history,index=load_story_workspace(workspace,project)
    if bible is None or index is None or index["digest"]!=lore["full_history_digest"]:
        raise JeevesAppwideError("full original cast and event source history changed")
    by_path={scene_path(item):item for item in history}
    binding={item["game_node"]:item for item in lore["narrative_sources"]}
    if set(binding)!={node["id"] for node in
                         _json(workspace.read(
                             "current",project,prefix+".json")["content"])["nodes"]}:
        raise JeevesAppwideError("narrative game nodes not fully linked")
    scenarios=[]
    all_ids=set()
    all_paths=set()
    all_actor_ids=set()
    all_regions=set()
    all_fields=set()
    for recorded in portfolio["executed_scenarios"]:
        witnessed_events=[]
        witnessed_states=[]
        actor_ids=set()
        regions=set()
        route=[]
        for step in recorded["real_path"]:
            node=step["node"]
            if node not in binding:
                raise JeevesAppwideError("observed original game node has no story source")
            linked=binding[node]
            path=linked["approved_story_path"]
            story=by_path.get(path)
            if story is None or story["digest"]!=linked["signed_story_digest"]:
                raise JeevesAppwideError("unreviewed or historically changed original story scene")
            route.append({
                "game_node":node,"source_story_path":path,
                "signed_story_digest":story["digest"],
                "scene_sequence":story["sequence"],
                "original_authored_ending_event_count":len(story["events"]),
            })
            regions.add(story["region"])
            actor_ids.update(story["cast"])
            for event in story["events"]:
                witnessed_events.append({
                    "event_id":event["id"],
                    "story_source_sha256":linked["approved_story_sha256"],
                    "authored_scene_sequence":story["sequence"],
                    "event_actor":event["actor"],
                    "event_kind":event["kind"],
                    "prior_causal_references":list(event["references"]),
                })
                for change in event["changes"]:
                    if change["field"] not in FIELDS:
                        raise JeevesAppwideError("unexpected original cast state transition")
                    witnessed_states.append({
                        "source_event":event["id"],
                        "character":change["character"],
                        "field":change["field"],
                        "original_previous":change["previous"],
                        "authored_new":change["value"],
                        "narrative_reason":change["reason"],
                        "story_sequence":story["sequence"],
                    })
        if len(witnessed_events)>MAX_PATH_EVENTS or len(witnessed_states)>MAX_CAUSAL_CHANGES:
            raise JeevesAppwideError("original character consequence recording over budget")
        path_events={event["event_id"] for event in witnessed_events}
        all_ids.update(path_events)
        all_paths.add(tuple(x["game_node"] for x in route))
        all_actor_ids.update(actor_ids)
        all_regions.update(regions)
        all_fields.update(x["field"] for x in witnessed_states)
        scenarios.append({
            "scenario_id":recorded["scenario_id"],
            "gameplay_compiler_output_digest":recorded["compiler_output_digest"],
            "real_reached_ending_node":recorded["real_reached_ending_node"],
            "real_reached_ending_category":recorded["real_reached_ending_category"],
            "original_authored_game_story_route":route,
            "observed_canonical_character_ids":sorted(actor_ids),
            "observed_canonical_region_ids":sorted(regions),
            "signed_causal_events_on_real_route":witnessed_events,
            "authored_social_character_transitions_on_real_route":witnessed_states,
            "observed_gameplay_execution":True,
            "character_state_transition_mechanically_executed_in_game":False,
        })
    signatures={
        item["scenario_id"]:tuple(
            x["event_id"] for x in item["signed_causal_events_on_real_route"])
        for item in scenarios
    }
    matrix=[]
    for left in scenarios:
        left_events=set(signatures[left["scenario_id"]])
        comparisons=[]
        for right in scenarios:
            if left["scenario_id"]==right["scenario_id"]:
                continue
            right_events=set(signatures[right["scenario_id"]])
            comparisons.append({
                "other_scenario_id":right["scenario_id"],
                "different_gameplay_ending":
                    left["real_reached_ending_node"]!=right["real_reached_ending_node"],
                "source_events_only_on_this_route":sorted(left_events-right_events),
                "source_events_only_on_other_route":sorted(right_events-left_events),
            })
        matrix.append({
            "scenario_id":left["scenario_id"],
            "compared_to":comparisons,
        })
    body={
        "schema":DOCUMENT,"project":project,"campaign_id":campaign_id,
        "current_campaign_source_sha256":lore["campaign_source_sha256"],
        "current_campaign_lore_source_sha256":lore_version["version"]["sha256"],
        "current_gameplay_outcomes_source_sha256":
            portfolio_version["version"]["sha256"],
        "verified_canonical_story_bible_sha256":lore["story_bible_source_sha256"],
        "verified_full_story_history_digest":index["digest"],
        "authored_story_scenes_in_full_history":len(history),
        "real_player_scenarios_run":len(scenarios),
        "distinct_real_game_nodes_routes":len(all_paths),
        "original_causal_event_ids_encountered":sorted(all_ids),
        "original_character_ids_encountered":sorted(all_actor_ids),
        "canonical_regions_encountered":sorted(all_regions),
        "authored_character_change_fields_encountered":sorted(all_fields),
        "real_gameplay_to_original_narrative_links":scenarios,
        "between_outcome_causal_differences":matrix,
        "mechanical_game_faction_karma_reputation_mutations_executed":False,
        "all_possible_game_choices_or_plot_outcomes_verified":False,
        "full_original_story_history_checked":True,
        "source_metadata_not_a_trained_model_or_story_generation":True,
    }
    document={**body,"digest":canonical_digest(body)}
    if len((canonical_json(document)+"\n").encode("utf-8"))>MAX_SOURCE_BYTES:
        raise JeevesAppwideError("original cast/consequence source exceeds review budget")
    return document


def rebuild_narrative_consequences(workspace,project,document):
    if (type(document) is not dict or document.get("schema")!=DOCUMENT
            or document.get("project")!=project):
        raise JeevesAppwideError("exact source-authored consequence matrix required")
    return compile_narrative_consequences(
        workspace,project,document.get("campaign_id"))


class JeevesNarrativeConsequences:
    """Human-reviewed, content-addressed real game/story outcome source."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("scanned application source needed")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("source-authorized selected game workspace needed")
        self.inv=inventory;self.ws=workspace

    def _prepare(self,*,project,campaign_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale source inventory")
        document=compile_narrative_consequences(self.ws,project,campaign_id)
        location="game/campaigns/"+campaign_id+"_consequences.json"
        files={file.path:file for file in self.ws.files("current",project)}
        before=files[location].sha256 if location in files else EMPTY_SHA
        text=canonical_json(document)+"\n"
        candidate=sha256(text.encode()).hexdigest()
        body={
            "schema":SCHEMA+".plan",
            "project":project,"campaign_id":campaign_id,
            "inventory_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "source_path":location,
            "prior_source_sha256":before,
            "new_source_sha256":candidate,
            "new_document_digest":document["digest"],
            "game_scenarios_reexecuted":document["real_player_scenarios_run"],
            "distinct_actual_game_routes":document["distinct_real_game_nodes_routes"],
            "original_signed_causal_event_ids":
                document["original_causal_event_ids_encountered"],
            "original_character_ids":document["original_character_ids_encountered"],
            "original_regions":document["canonical_regions_encountered"],
            "game_characters_mechanically_changed_by_metadata_only":False,
            "already_current":before==candidate,
            "source_committed":False,
            "human_review_required":True,
        }
        return {**body,"digest":digest(body)},text

    def plan(self,*,project,campaign_id,expected_snapshot=None):
        body,_=self._prepare(project=project,campaign_id=campaign_id,
                             expected_snapshot=expected_snapshot)
        return body

    def stage(self,*,project,campaign_id,expected_plan_digest,reason,
              expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("human review required to stage narrative consequences")
        if (type(expected_plan_digest) is not str or
                not SHA.fullmatch(expected_plan_digest)
                or type(reason) is not str or not 12<=len(reason)<=1000):
            raise JeevesAppwideError("exact source receipt and reviewed source reason required")
        report,source=self._prepare(
            project=project,campaign_id=campaign_id,expected_snapshot=expected_snapshot)
        if expected_plan_digest!=report["digest"]:
            raise JeevesAppwideError("original game narrative source changed after review")
        if report["already_current"]:
            raise JeevesAppwideError("matching original source already published")
        proposed=self.ws.propose(
            project,report["source_path"],source,
            expected_sha256=report["prior_source_sha256"],
            reason=reason,authorized=True)
        body={
            "schema":SCHEMA+".staged",
            "project":project,"campaign_id":campaign_id,
            "source_path":report["source_path"],
            "proposal_id":proposed["proposal_id"],
            "previous_source_sha256":report["prior_source_sha256"],
            "new_source_sha256":report["new_source_sha256"],
            "human_commit_pending":True,
            "source_files_committed":0,
        }
        return {**body,"digest":digest(body)}

    def verify(self,*,project,campaign_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale application inventory")
        if (type(project) is not str or project!=self.ws.active()
                or type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
            raise JeevesAppwideError("current original game campaign required")
        location="game/campaigns/"+campaign_id+"_consequences.json"
        source=self.ws.read("current",project,location)
        original=_json(source["content"])
        generated=rebuild_narrative_consequences(self.ws,project,original)
        if generated!=original:
            raise JeevesAppwideError("signed game/story consequence source is stale")
        body={
            "schema":SCHEMA+".verified",
            "project":project,"campaign_id":campaign_id,
            "actual_consequence_source_sha256":source["version"]["sha256"],
            "actual_player_scenarios_reexecuted":generated["real_player_scenarios_run"],
            "original_canonical_cast_source_verified":True,
            "original_causal_event_count":
                len(generated["original_causal_event_ids_encountered"]),
            "distinct_real_game_routes":generated["distinct_real_game_nodes_routes"],
            "game_state_mechanics_mutated":False,
            "actual_model_trained_or_hardware_qualified":False,
            "original_source_mutated":False,
        }
        return {**body,"digest":digest(body)}
