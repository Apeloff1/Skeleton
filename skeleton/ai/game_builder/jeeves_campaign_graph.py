"""Actually simulate a bounded original multi-ending game campaign graph.

Every narrative scene is bound to a real approved advanced game engine and
authored original scene, with user-specified actions executed in its
existing reference runtime. Branch choices are deterministic typed predicates
over actual gameplay result, not fabricated plot state. All paths and fallback
endings are statically validated. The source proposal and human commit
re-run the compiler and verify the exact resulting campaign receipt.

This is a finite offline campaign decision graph, not a trained generative
narrative model, a native game executable or independently tested production.
"""
from __future__ import annotations

from collections import Counter,deque
from hashlib import sha256
import re

from .contracts import canonical_json,canonical_digest
from .game_project_workspace import GameWorkspace,_json
from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_advanced_replay import load_approved_advanced_scene
from .advanced_gameplay_runtime import ACTION_HELP,run_advanced_session

SCHEMA="skeleton.ai.jeeves_campaign_graph.v1"
SOURCE="skeleton.game_builder.reviewed_campaign_graph.v1"
IDENT=re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
EMPTY_SHA=sha256(b"").hexdigest()
MAX_NODES=8
MAX_EDGES=24
MAX_ACTIONS=256
MAX_SOURCE_BYTES=220_000
PREDICATES=frozenset({"always","finished","failed","score_at_least","turns_at_most"})
ENDINGS=frozenset({"good","neutral","evil","open","resolution","cliffhanger"})


def _checked_spec(spec):
    if (type(spec) is not dict or
            set(spec)!={"campaign_id","start","nodes","edges"}
            or type(spec["campaign_id"]) is not str
            or not IDENT.fullmatch(spec["campaign_id"])
            or type(spec["start"]) is not str
            or not IDENT.fullmatch(spec["start"])
            or type(spec["nodes"]) is not list
            or not 2<=len(spec["nodes"])<=MAX_NODES
            or type(spec["edges"]) is not list
            or not 1<=len(spec["edges"])<=MAX_EDGES):
        raise JeevesAppwideError("bounded original campaign graph/source required")
    ids=set()
    end_nodes=set()
    commands=0
    for node in spec["nodes"]:
        if (type(node) is not dict or
                set(node)!={"id","editor","scene_id","actions","ending"}
                or type(node["id"]) is not str or not IDENT.fullmatch(node["id"])
                or node["id"] in ids or
                type(node["editor"]) is not str or
                node["editor"] not in ACTION_HELP
                or type(node["scene_id"]) is not str or
                not IDENT.fullmatch(node["scene_id"])
                or type(node["actions"]) is not list or
                len(node["actions"])>128 or
                any(type(a) is not str or
                    a not in ACTION_HELP[node["editor"]]
                    for a in node["actions"])):
            raise JeevesAppwideError("bad game node, action or reused source identity")
        if node["ending"] is not None and (
                type(node["ending"]) is not str or
                node["ending"] not in ENDINGS):
            raise JeevesAppwideError("unsupported authored original ending category")
        commands+=len(node["actions"])
        ids.add(node["id"])
        if node["ending"] is not None:
            end_nodes.add(node["id"])
    if commands>MAX_ACTIONS or spec["start"] not in ids or not end_nodes:
        raise JeevesAppwideError("missing start/end or too many gameplay turns")
    outgoing={node_id:[] for node_id in ids}
    incoming={node_id:0 for node_id in ids}
    pairs=set()
    for e in spec["edges"]:
        if (type(e) is not dict or
                set(e)!={"source","target","priority","predicate","threshold"}
                or type(e["source"]) is not str
                or type(e["target"]) is not str
                or type(e["predicate"]) is not str
                or e["source"] not in ids or e["target"] not in ids
                or e["source"]==e["target"]
                or type(e["priority"]) is not int
                or not 0<=e["priority"]<=MAX_EDGES
                or e["predicate"] not in PREDICATES
                or (e["predicate"] in {"score_at_least","turns_at_most"}
                    and (type(e["threshold"]) is not int or
                         not 0<=e["threshold"]<=100000))
                or (e["predicate"] not in {"score_at_least","turns_at_most"}
                    and e["threshold"] is not None)):
            raise JeevesAppwideError("invalid original outcome branch")
        order=(e["source"],e["priority"])
        if order in pairs:
            raise JeevesAppwideError("ambiguous equal-priority branches")
        pairs.add(order)
        outgoing[e["source"]].append(e)
        incoming[e["target"]]+=1
    for key in ids:
        rows=sorted(outgoing[key],key=lambda e:e["priority"])
        if key in end_nodes:
            if rows:
                raise JeevesAppwideError("ending scene cannot have outgoing branch")
        elif not rows or rows[-1]["predicate"]!="always" or sum(
                x["predicate"]=="always" for x in rows)!=1:
            raise JeevesAppwideError("nonending scene must end with unique fallback branch")
    # All authored nodes must be reachable and no cycle/dead-end hidden by
    # mutually exclusive branching. This is a graph check, not a claim all
    # possible social/plot outcomes have been authored.
    ready=sorted(k for k,v in incoming.items() if v==0)
    order=[]
    while ready:
        ident=ready.pop(0)
        order.append(ident)
        for edge in sorted(outgoing[ident],key=lambda e:(e["priority"],e["target"])):
            incoming[edge["target"]]-=1
            if incoming[edge["target"]]==0:
                ready.append(edge["target"])
                ready.sort()
    if len(order)!=len(ids):
        raise JeevesAppwideError("original campaign graph has a cycle")
    reachable={spec["start"]}
    frontier=deque([spec["start"]])
    while frontier:
        for edge in outgoing[frontier.popleft()]:
            if edge["target"] not in reachable:
                reachable.add(edge["target"]);frontier.append(edge["target"])
    if reachable!=ids:
        raise JeevesAppwideError("original campaign contains disconnected scene")
    if len(end_nodes)<2:
        raise JeevesAppwideError("at least two different authored endings required")
    if len({n["ending"] for n in spec["nodes"] if n["ending"] is not None})<2:
        raise JeevesAppwideError("multiple authored ending categories required")
    return sorted(spec["nodes"],key=lambda n:n["id"]),outgoing,order


def _condition(predicate, threshold, report):
    if predicate=="always":
        return True
    if predicate=="finished":
        return report["state"]["finished"] is True
    if predicate=="failed":
        return report["state"]["failed"] is True
    if predicate=="score_at_least":
        score=report["state"].get("score",0)
        return type(score) in (int,float) and score>=threshold
    if predicate=="turns_at_most":
        return report["validated_turn_count"]<=threshold
    raise JeevesAppwideError("unknown gameplay branch predicate")


def rebuild_campaign_document(workspace,project,document):
    """Re-run true source-linked action transcripts and graph with current rules."""
    if type(document) is not dict or set(document)!={
            "schema","project","campaign_id","start","nodes","edges",
            "source_bindings","reference_sessions","route","ending",
            "digest"} or document.get("schema")!=SOURCE or document.get("project")!=project:
        raise JeevesAppwideError("exact canonical authored campaign source required")
    spec={k:document[k] for k in ("campaign_id","start","nodes","edges")}
    return compile_campaign(workspace,project,spec)


def compile_campaign(workspace,project,spec):
    if not isinstance(workspace,GameWorkspace) or workspace.active()!=project:
        raise JeevesAppwideError("current original game project required")
    nodes,outgoing,_=_checked_spec(spec)
    sessions={}
    bindings={}
    for node in nodes:
        editor=node["editor"];scene_id=node["scene_id"]
        config,scene,sys_sha,scene_sha,_=load_approved_advanced_scene(
            workspace,project=project,editor=editor,scene_id=scene_id)
        report=run_advanced_session(
            editor,config["settings"],node["actions"],
            seed=scene["seed"],scene=scene)
        bindings[node["id"]]={
            "editor":editor,"scene_id":scene_id,
            "approved_system_sha256":sys_sha,
            "approved_scene_sha256":scene_sha,
            "source_scene_digest":scene["digest"],
        }
        sessions[node["id"]]={
            "receipt_digest":report["digest"],
            "trace_head_digest":report["head_digest"],
            "turns_executed":report["validated_turn_count"],
            "terminal":report["terminal"],
            "state":report["state"],
            "replayed_by_canonical_engine":True,
        }
    # Walk a finite deterministic branch, evaluating ONLY observed actual
    # game session result states. Do not invent other unseen player actions.
    current=spec["start"]
    route=[]
    seen=set()
    while current not in seen:
        seen.add(current)
        state=sessions[current]
        selected=None
        for edge in sorted(outgoing[current],key=lambda e:e["priority"]):
            if _condition(edge["predicate"],edge["threshold"],{
                "state":state["state"],
                "validated_turn_count":state["turns_executed"],
            }):
                selected=edge["target"]
                break
        route.append({
            "node":current,"actual_source_session_digest":state["receipt_digest"],
            "chosen_next":selected,
        })
        if selected is None:
            break
        current=selected
    endings={n["id"]:n["ending"] for n in nodes}
    if current not in endings or endings[current] is None:
        raise JeevesAppwideError("original campaign route ended without authored ending")
    body={
        "schema":SOURCE,
        "project":project,"campaign_id":spec["campaign_id"],
        "start":spec["start"],"nodes":spec["nodes"],"edges":spec["edges"],
        "source_bindings":dict(sorted(bindings.items())),
        "reference_sessions":dict(sorted(sessions.items())),
        "route":route,
        "ending":endings[current],
    }
    candidate={**body,"digest":canonical_digest(body)}
    if len((canonical_json(candidate)+"\n").encode("utf-8"))>MAX_SOURCE_BYTES:
        raise JeevesAppwideError("actual original campaign source exceeds workspace budget")
    return candidate


class JeevesCampaignGraph:
    """Exact reviewed original game-source campaign, with two or more endings."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("source-pinned canonical inventory required")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("canonical original GameWorkspace required")
        self.inv=inventory
        self.ws=workspace

    def _prepared(self,*,project,spec,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale original application snapshot")
        if type(project) is not str or project!=self.ws.active():
            raise JeevesAppwideError("current selected original game required")
        doc=compile_campaign(self.ws,project,spec)
        path="game/campaigns/"+doc["campaign_id"]+".json"
        existing={f.path:f for f in self.ws.files("current",project)}
        previous=existing[path].sha256 if path in existing else EMPTY_SHA
        content=canonical_json(doc)+"\n"
        after=sha256(content.encode()).hexdigest()
        evidence={
            "schema":SCHEMA+".plan",
            "project":project,"campaign_id":doc["campaign_id"],
            "inventory_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "source_path":path,
            "prior_source_sha256":previous,"proposed_source_sha256":after,
            "campaign_source_digest":doc["digest"],
            "node_count":len(spec["nodes"]),
            "edge_count":len(spec["edges"]),
            "authored_ending_categories":sorted(set(
                x["ending"] for x in spec["nodes"] if x["ending"] is not None)),
            "actual_route":doc["route"],
            "actual_reached_ending":doc["ending"],
            "real_reference_sessions_executed":len(doc["reference_sessions"]),
            "input_scene_source_versions":doc["source_bindings"],
            "already_current":previous==after,
            "winning_outcome_not_implied":True,
            "independent_model_or_hardware_quality_not_claimed":True,
            "source_files_mutated":False,
        }
        return {**evidence,"digest":digest(evidence)},content

    def plan(self,*,project,spec,expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer approval needed for real multi-scene replay")
        receipt,_=self._prepared(
            project=project,spec=spec,expected_snapshot=expected_snapshot)
        return receipt

    def stage(self,*,project,spec,expected_plan_digest,reason,
              expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("operator approval required to stage campaign source")
        if (type(expected_plan_digest) is not str or
                not SHA.fullmatch(expected_plan_digest)
                or type(reason) is not str or not 12<=len(reason)<=1000):
            raise JeevesAppwideError("exact reviewed plan and concrete designer rationale required")
        receipt,source=self._prepared(
            project=project,spec=spec,expected_snapshot=expected_snapshot)
        if receipt["digest"]!=expected_plan_digest:
            raise JeevesAppwideError("authored campaign source changed after review")
        if receipt["already_current"]:
            raise JeevesAppwideError("same original campaign source already committed")
        proposal=self.ws.propose(
            project,receipt["source_path"],source,
            expected_sha256=receipt["prior_source_sha256"],
            reason=reason,authorized=True)
        body={
            "schema":SCHEMA+".staged",
            "project":project,"campaign_id":receipt["campaign_id"],
            "plan_digest":receipt["digest"],"proposal_id":proposal["proposal_id"],
            "actual_reference_scene_count":receipt["real_reference_sessions_executed"],
            "original_campaign_source":receipt["source_path"],
            "published_source_files":0,
            "human_review_and_canonical_commit_required":True,
        }
        return {**body,"digest":digest(body)}

    def verify(self,*,project,campaign_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale app inventory snapshot")
        if (type(project) is not str or self.ws.active()!=project or
                type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
            raise JeevesAppwideError("active original game and campaign ID required")
        path="game/campaigns/"+campaign_id+".json"
        current=self.ws.read("current",project,path)
        original=_json(current["content"])
        rebuilt=rebuild_campaign_document(self.ws,project,original)
        if rebuilt!=original:
            raise JeevesAppwideError("published campaign scene or actual replay drifted")
        body={
            "schema":SCHEMA+".verified","project":project,
            "campaign_id":campaign_id,
            "source_path":path,
            "source_sha256":current["version"]["sha256"],
            "actual_reference_sessions_reexecuted":len(rebuilt["reference_sessions"]),
            "authored_ending_count":sum(1 for node in rebuilt["nodes"]
                                      if node["ending"] is not None),
            "actual_reached_ending":rebuilt["ending"],
            "source_scenarios_sha256":dict(sorted((
                ident,proof["receipt_digest"]) for ident,proof in
                rebuilt["reference_sessions"].items())),
            "real_runtime_reference_execution_occurred":True,
            "source_and_models_not_modified":True,
            "native_platform_binary_verified":False,
        }
        return {**body,"digest":digest(body)}
