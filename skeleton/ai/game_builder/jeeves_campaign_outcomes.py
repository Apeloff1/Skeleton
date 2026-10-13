"""Real source-bound branching-game outcome coverage across player action variants.

One authored campaign defines candidate outcome branches. This engine
actually invokes the canonical reference-game simulators for a bounded
set of distinct player-action profiles and reports only outcomes
*observed*. It never equates structurally declared endings with playable
or reachable endings, invents a player choice, or runs native hardware.

Accepted outcome portfolios are verified against the current approved
campaign and underlying scene/system sources on both proposal and commit.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .contracts import canonical_json,canonical_digest
from .game_project_workspace import GameWorkspace,_json
from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_campaign_graph import (
    rebuild_campaign_document,compile_campaign,_condition,
)
from .advanced_gameplay_runtime import ACTION_HELP

SCHEMA="skeleton.ai.jeeves_campaign_outcome_coverage.v1"
SOURCE="skeleton.game_builder.reviewed_campaign_outcome_portfolio.v1"
IDENT=re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
EMPTY_SHA=sha256(b"").hexdigest()
MAX_SCENARIOS=12
MAX_OVERRIDE_ACTIONS=1024
MAX_SOURCE_BYTES=190000


def _typed_scenarios(original,scenarios):
    """Fail closed on extra fields, duplicate profiles and unbounded commands."""
    if (type(scenarios) is not list or
            not 2<=len(scenarios)<=MAX_SCENARIOS):
        raise JeevesAppwideError("2–12 source-backed player action scenarios required")
    nodes={n["id"]:n for n in original["nodes"]}
    names=set()
    profiles=set()
    total=0
    rows=[]
    for row in scenarios:
        if (type(row) is not dict or
                set(row)!={"scenario_id","overrides"} or
                type(row["scenario_id"]) is not str or
                not IDENT.fullmatch(row["scenario_id"]) or
                row["scenario_id"] in names or
                type(row["overrides"]) is not dict or
                not row["overrides"] or
                len(row["overrides"])>len(nodes)):
            raise JeevesAppwideError("distinct bounded original scenario IDs and overrides required")
        names.add(row["scenario_id"])
        overrides={}
        for key,actions in row["overrides"].items():
            if (type(key) is not str or key not in nodes
                    or type(actions) is not list or len(actions)>128 or
                    any(type(action) is not str or
                        action not in ACTION_HELP[nodes[key]["editor"]]
                        for action in actions)):
                raise JeevesAppwideError("unknown original scene or illegal gameplay action override")
            if actions==nodes[key]["actions"]:
                raise JeevesAppwideError("unchanged node actions are not an outcome scenario")
            total+=len(actions)
            overrides[key]=list(actions)
        fingerprint=digest(overrides)
        if fingerprint in profiles:
            raise JeevesAppwideError("duplicate player action variant adds no coverage")
        profiles.add(fingerprint)
        rows.append({"scenario_id":row["scenario_id"],
                     "overrides":dict(sorted(overrides.items()))})
    if total>MAX_OVERRIDE_ACTIONS:
        raise JeevesAppwideError("combined player action scenario budget exceeded")
    return sorted(rows,key=lambda row:row["scenario_id"])


def compile_outcome_portfolio(workspace,project,campaign_id,scenarios):
    """Actually replay the approved game for each distinct action portfolio."""
    if (not isinstance(workspace,GameWorkspace) or
            type(project) is not str or project!=workspace.active() or
            type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
        raise JeevesAppwideError("active original game and campaign required")
    location="game/campaigns/"+campaign_id+".json"
    current=workspace.read("current",project,location)
    original=_json(current["content"])
    if (original.get("campaign_id")!=campaign_id or
            rebuild_campaign_document(workspace,project,original)!=original):
        raise JeevesAppwideError("source-committed original campaign needs valid real game replay")
    typed=_typed_scenarios(original,scenarios)
    base_spec={key:original[key] for key in ("campaign_id","start","nodes","edges")}
    endings={
        node["id"]:node["ending"]
        for node in original["nodes"] if node["ending"] is not None
    }
    all_edges=sorted(
        ((edge["source"],edge["target"],edge["priority"])
         for edge in original["edges"]),
        key=lambda x:(x[0],x[2],x[1])
    )
    observed_nodes=set()
    observed_categories=set()
    witnessed_edges=set()
    results=[]
    total_sessions=0
    for scenario in typed:
        spec={
            **base_spec,
            "nodes":[{
                **node,
                "actions":scenario["overrides"].get(node["id"],node["actions"]),
            } for node in original["nodes"]],
        }
        executed=compile_campaign(workspace,project,spec)
        path=executed["route"]
        if not path or path[-1]["node"] not in endings:
            raise JeevesAppwideError("authored scenario did not reach a valid observed ending")
        reached=path[-1]["node"]
        for step in path:
            nxt=step["chosen_next"]
            if nxt is not None:
                actual=executed["reference_sessions"][step["node"]]
                choices=[
                    (edge["source"],edge["target"],edge["priority"])
                    for edge in sorted(original["edges"],key=lambda e:e["priority"])
                    if edge["source"]==step["node"] and _condition(
                        edge["predicate"],edge["threshold"],{
                            "state":actual["state"],
                            "validated_turn_count":actual["turns_executed"],
                        })
                ]
                if not choices or choices[0][1]!=nxt:
                    raise JeevesAppwideError("actual branch priority differs from real session")
                witnessed_edges.add(choices[0])
        observed_nodes.add(reached)
        observed_categories.add(endings[reached])
        total_sessions+=len(executed["reference_sessions"])
        results.append({
            "scenario_id":scenario["scenario_id"],
            "source_action_variant_digest":digest(scenario["overrides"]),
            "compiler_output_digest":executed["digest"],
            "reference_gameplay_sessions_run":len(executed["reference_sessions"]),
            "real_path":[dict(step) for step in path],
            "real_reached_ending_node":reached,
            "real_reached_ending_category":endings[reached],
            "actual_total_scene_actions":sum(
                len(n["actions"]) for n in spec["nodes"]),
            "original_game_actions_executed":True,
            "browser_or_native_binary_executed":False,
        })
    missing_nodes=sorted(set(endings)-observed_nodes)
    missing_categories=sorted(set(endings.values())-observed_categories)
    missing_edges=[
        {"source":a,"target":b,"priority":c}
        for a,b,c in all_edges if (a,b,c) not in witnessed_edges
    ]
    body={
        "schema":SOURCE,
        "project":project,"campaign_id":campaign_id,
        "approved_campaign_source_sha256":current["version"]["sha256"],
        "approved_campaign_document_digest":original["digest"],
        "original_reference_route_digest":digest(original["route"]),
        "scenarios":typed,
        "executed_scenarios":results,
        "actual_gameplay_session_executions":total_sessions,
        "authored_ending_node_count":len(endings),
        "observed_ending_node_count":len(observed_nodes),
        "unobserved_authored_ending_node_ids":missing_nodes,
        "authored_ending_category_count":len(set(endings.values())),
        "observed_ending_category_count":len(observed_categories),
        "unobserved_authored_ending_categories":missing_categories,
        "authored_branch_edges":len(all_edges),
        "observed_branch_edges":len(witnessed_edges),
        "unobserved_branch_edges":missing_edges,
        "all_authored_ending_nodes_observed_in_supplied_scenarios":
            not missing_nodes,
        "all_declared_branch_edges_observed_in_supplied_scenarios":
            not missing_edges,
        "proof_scope":"only_supplied_real_game_action_variants",
        "unobserved_or_arbitrary_player_decisions_not_proven":True,
        "actual_native_hardware_executed":False,
        "independent_story_or_quality_acceptance_claimed":False,
    }
    document={**body,"digest":canonical_digest(body)}
    if len((canonical_json(document)+"\n").encode("utf-8"))>MAX_SOURCE_BYTES:
        raise JeevesAppwideError("actual original campaign outcome evidence exceeds source budget")
    return document


def rebuild_outcome_portfolio(workspace,project,document):
    if (type(document) is not dict or
            document.get("schema")!=SOURCE or
            document.get("project")!=project):
        raise JeevesAppwideError("signed original game outcome source required")
    return compile_outcome_portfolio(
        workspace,project,document.get("campaign_id"),
        document.get("scenarios"))


class JeevesCampaignOutcomes:
    """Bounded real alternate player-action endings and source-review lifecycle."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("scanned original application inventory required")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("current selected game workspace required")
        self.inv=inventory;self.ws=workspace

    def _plan(self,*,project,campaign_id,scenarios,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale reviewed app source inventory")
        document=compile_outcome_portfolio(
            self.ws,project,campaign_id,scenarios)
        location="game/campaigns/"+campaign_id+"_outcomes.json"
        old={entry.path:entry for entry in self.ws.files("current",project)}
        prior=old[location].sha256 if location in old else EMPTY_SHA
        payload=canonical_json(document)+"\n"
        sha=sha256(payload.encode()).hexdigest()
        receipt={
            "schema":SCHEMA+".plan",
            "project":project,"campaign_id":campaign_id,
            "repository_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "approved_game_campaign_source_sha256":
                document["approved_campaign_source_sha256"],
            "source_path":location,
            "old_source_sha256":prior,"candidate_source_sha256":sha,
            "candidate_document_digest":document["digest"],
            "real_scenarios_executed":len(document["executed_scenarios"]),
            "real_gameplay_sessions_executed":
                document["actual_gameplay_session_executions"],
            "authored_ending_nodes":document["authored_ending_node_count"],
            "actually_observed_ending_nodes":document["observed_ending_node_count"],
            "unobserved_ending_nodes":
                document["unobserved_authored_ending_node_ids"],
            "authored_branch_edges":document["authored_branch_edges"],
            "actually_exercised_branch_edges":document["observed_branch_edges"],
            "all_branch_paths_or_player_choices_covered":
                document["all_declared_branch_edges_observed_in_supplied_scenarios"],
            "already_current":prior==sha,
            "real_game_source_used":True,
            "evidence_is_only_supplied_action_variants":True,
            "human_review_before_source_commit":True,
            "source_files_committed":0,
        }
        return {**receipt,"digest":digest(receipt)},payload

    def plan(self,*,project,campaign_id,scenarios,
             expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer approval required to execute game scenario portfolio")
        report,_=self._plan(project=project,campaign_id=campaign_id,
                            scenarios=scenarios,expected_snapshot=expected_snapshot)
        return report

    def stage(self,*,project,campaign_id,scenarios,expected_plan_digest,
              reason,expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer review needed for authored multi-ending scenario source")
        if (type(expected_plan_digest) is not str or
                not SHA.fullmatch(expected_plan_digest) or
                type(reason) is not str or not 12<=len(reason)<=1000):
            raise JeevesAppwideError("exact reviewed original game scenario digest and rationale needed")
        report,content=self._plan(
            project=project,campaign_id=campaign_id,scenarios=scenarios,
            expected_snapshot=expected_snapshot)
        if report["digest"]!=expected_plan_digest:
            raise JeevesAppwideError("real campaign source changed since reviewed outcome plan")
        if report["already_current"]:
            raise JeevesAppwideError("identical real scenario coverage source already approved")
        proposal=self.ws.propose(
            project,report["source_path"],content,
            expected_sha256=report["old_source_sha256"],
            reason=reason,authorized=True)
        body={
            "schema":SCHEMA+".stage","project":project,
            "campaign_id":campaign_id,
            "source_path":report["source_path"],
            "proposal_id":proposal["proposal_id"],
            "actual_game_session_runs":report["real_gameplay_sessions_executed"],
            "actual_distinct_ending_nodes_observed":
                report["actually_observed_ending_nodes"],
            "human_source_approval_still_required":True,
            "source_files_committed":0,
        }
        return {**body,"digest":digest(body)}

    def verify(self,*,project,campaign_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale app inventory")
        if (type(project) is not str or project!=self.ws.active() or
                type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
            raise JeevesAppwideError("active original project and committed campaign required")
        location="game/campaigns/"+campaign_id+"_outcomes.json"
        content=self.ws.read("current",project,location)
        authored=_json(content["content"])
        rebuilt=rebuild_outcome_portfolio(self.ws,project,authored)
        if rebuilt!=authored:
            raise JeevesAppwideError("signed original outcome source now differs from real game")
        body={
            "schema":SCHEMA+".verified",
            "project":project,"campaign_id":campaign_id,
            "current_approved_portfolio_sha256":content["version"]["sha256"],
            "portfolio_document_digest":rebuilt["digest"],
            "reference_gameplay_sessions_reexecuted":
                rebuilt["actual_gameplay_session_executions"],
            "real_endings_exercised":rebuilt["observed_ending_node_count"],
            "authored_endings":rebuilt["authored_ending_node_count"],
            "actual_branches_covered":rebuilt["observed_branch_edges"],
            "authored_branches":rebuilt["authored_branch_edges"],
            "unobserved_ending_nodes":
                rebuilt["unobserved_authored_ending_node_ids"],
            "actual_reference_gameplay_ran":True,
            "native_binary_or_all_unseen_choices_verified":False,
            "sources_not_modified":True,
        }
        return {**body,"digest":digest(body)}
