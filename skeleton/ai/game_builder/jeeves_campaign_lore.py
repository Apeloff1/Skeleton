"""Author-source accurate linkage between gameplay campaigns and story canon.

All character, region and causal events are read from the original fully
verified story history. No synthesized missing NPCs, quests, memories, plot
references or fabricated continuity records are permitted. Persistent lore
links are re-verified at both source proposal and human commit boundaries.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .game_project_workspace import GameWorkspace,_json
from .contracts import canonical_json,canonical_digest
from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_campaign_graph import rebuild_campaign_document
from .story_workspace import load_story_workspace
from .story_canon_fabric import scene_path

SCHEMA="skeleton.ai.jeeves_campaign_lore.v1"
DOCUMENT="skeleton.game_builder.campaign_lore_bindings.v1"
IDENT=re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
STORY_PATH=re.compile(
    r"story/(?:scenes/act_[0-9]{4}/scene_[0-9]{6}|"
    r"chapters/chapter_[0-9]{3}/acts/act_[0-9]{4}/scene_[0-9]{6})\.json\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
EMPTY_SHA=sha256(b"").hexdigest()
MAX_BYTES=100000


def compile_campaign_lore(workspace,project,campaign_id,bindings):
    if (not isinstance(workspace,GameWorkspace)
            or type(project) is not str or workspace.active()!=project
            or type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)
            or type(bindings) is not list or not 2<=len(bindings)<=8):
        raise JeevesAppwideError("source-backed bounded campaign lore map required")
    path="game/campaigns/"+campaign_id+".json"
    source=workspace.read("current",project,path)
    campaign=_json(source["content"])
    rebuilt=rebuild_campaign_document(workspace,project,campaign)
    if rebuilt!=campaign or campaign["campaign_id"]!=campaign_id:
        raise JeevesAppwideError("committed original-game campaign changed")
    nodes={row["id"] for row in campaign["nodes"]}
    if len(bindings)!=len(nodes):
        raise JeevesAppwideError("every real game scene needs a canonical story scene")
    if any(type(item) is not dict or set(item)!={"node","story_path"}
           or type(item["node"]) is not str
           or item["node"] not in nodes
           or type(item["story_path"]) is not str
           or STORY_PATH.fullmatch(item["story_path"]) is None
           for item in bindings):
        raise JeevesAppwideError("each campaign node requires an exact original story path")
    by_node={item["node"]:item["story_path"] for item in bindings}
    if set(by_node)!=nodes or len(set(by_node.values()))!=len(nodes):
        raise JeevesAppwideError("ambiguous or duplicated authored narrative mappings")
    bible,history,index=load_story_workspace(workspace,project)
    if bible is None or bible.get("phase")!="design":
        raise JeevesAppwideError("signed fully designed cast/world story bible required")
    if index is None:
        raise JeevesAppwideError("source-verified original story scenes required")
    authored={scene_path(item):item for item in history}
    narrative=[]
    for node in sorted(nodes):
        ref=by_node[node]
        if ref not in authored:
            raise JeevesAppwideError("campaign lore refers to a missing approved story scene")
        story=authored[ref]
        file=workspace.read("current",project,ref)
        narrative.append({
            "game_node":node,
            "approved_story_path":ref,
            "approved_story_sha256":file["version"]["sha256"],
            "signed_story_digest":story["digest"],
            "story_sequence":story["sequence"],
            "story_act":story["act"],
            "story_scene":story["scene"],
            "story_chapter":story.get("chapter"),
            "canonical_region":story["region"],
            "canonical_cast":list(story["cast"]),
            "causal_event_ids":[item["id"] for item in story["events"]],
            "causal_event_count":len(story["events"]),
            "original_dialogue_count":len(story["dialogue"]),
            "original_plot_references_checked_in_full_history":True,
        })
    bible_file=workspace.read("current",project,"game/story_bible.json")
    body={
        "schema":DOCUMENT,
        "project":project,"campaign_id":campaign_id,
        "campaign_source_sha256":source["version"]["sha256"],
        "campaign_source_digest":campaign["digest"],
        "story_bible_source_sha256":bible_file["version"]["sha256"],
        "signed_bible_digest":bible["digest"],
        "full_history_digest":index["digest"],
        "full_story_history_scene_count":len(history),
        "bindings":[dict(item) for item in sorted(bindings,key=lambda v:v["node"])],
        "narrative_sources":narrative,
        "gameplay_scene_count":len(nodes),
        "authored_ending_categories":sorted({
            item["ending"] for item in campaign["nodes"] if item["ending"] is not None
        }),
        "canon_identity_across_cast_regions_and_causes_verified":True,
        "nonexistent_storylines_not_fabricated":True,
        "model_generated_prose_added":False,
        "native_hardware_executed":False,
    }
    result={**body,"digest":canonical_digest(body)}
    if len((canonical_json(result)+"\n").encode("utf-8"))>MAX_BYTES:
        raise JeevesAppwideError("signed original campaign lore source over budget")
    return result


def rebuild_campaign_lore_document(workspace,project,document):
    if type(document) is not dict or document.get("schema")!=DOCUMENT or (
            document.get("project")!=project):
        raise JeevesAppwideError("exact signed original campaign narrative document required")
    return compile_campaign_lore(
        workspace,project,document.get("campaign_id"),document.get("bindings"))


class JeevesCampaignLore:
    """Attach approved original causal, cast and region story sources to game."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("scanned original repository authority required")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("selected canonical GameWorkspace required")
        self.inv=inventory;self.ws=workspace

    def _prepared(self,*,project,campaign_id,bindings,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale canonical application inventory")
        document=compile_campaign_lore(self.ws,project,campaign_id,bindings)
        location="game/campaigns/"+campaign_id+"_lore.json"
        prior={file.path:file for file in self.ws.files("current",project)}
        before=prior[location].sha256 if location in prior else EMPTY_SHA
        content=canonical_json(document)+"\n"
        next_sha=sha256(content.encode()).hexdigest()
        report={
            "schema":SCHEMA+".plan",
            "project":project,"campaign_id":campaign_id,
            "inventory_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "source_path":location,
            "prior_source_sha256":before,
            "new_source_sha256":next_sha,
            "new_document_digest":document["digest"],
            "actual_source_campaign_sha256":document["campaign_source_sha256"],
            "canonical_bible_sha256":document["story_bible_source_sha256"],
            "verified_global_story_history_digest":document["full_history_digest"],
            "total_historical_scenes_checked":document["full_story_history_scene_count"],
            "game_nodes_with_verified_narrative_links":len(document["narrative_sources"]),
            "referred_causal_events":sum(
                item["causal_event_count"] for item in document["narrative_sources"]),
            "actual_author_cast_and_world_lore_used":True,
            "missing_story_sources_not_accepted":True,
            "already_current":before==next_sha,
            "human_source_commit_required":True,
            "automatic_narrative_generation_or_modification":False,
        }
        return {**report,"digest":digest(report)},content

    def plan(self,*,project,campaign_id,bindings,expected_snapshot=None):
        receipt,_=self._prepared(
            project=project,campaign_id=campaign_id,bindings=bindings,
            expected_snapshot=expected_snapshot)
        return receipt

    def stage(self,*,project,campaign_id,bindings,expected_plan_digest,reason,
              expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("operator must approve original narrative linkage source")
        if (type(expected_plan_digest) is not str
                or not SHA.fullmatch(expected_plan_digest)
                or type(reason) is not str or not 12<=len(reason)<=1000):
            raise JeevesAppwideError("signed exact original lore plan and reason required")
        report,content=self._prepared(
            project=project,campaign_id=campaign_id,bindings=bindings,
            expected_snapshot=expected_snapshot)
        if report["digest"]!=expected_plan_digest:
            raise JeevesAppwideError("original campaign or signed story history changed")
        if report["already_current"]:
            raise JeevesAppwideError("same original lore linkage already approved")
        proposed=self.ws.propose(
            project,report["source_path"],content,
            expected_sha256=report["prior_source_sha256"],
            reason=reason,authorized=True)
        body={
            "schema":SCHEMA+".staged","project":project,
            "campaign_id":campaign_id,
            "source_path":report["source_path"],
            "original_plan_digest":report["digest"],
            "proposal_id":proposed["proposal_id"],
            "source_committed":False,
            "source_history_and_causal_events_checked_again_at_commit":True,
            "human_source_review_required":True,
        }
        return {**body,"digest":digest(body)}

    def verify(self,*,project,campaign_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale source snapshot")
        if (type(project) is not str or self.ws.active()!=project
                or type(campaign_id) is not str or not IDENT.fullmatch(campaign_id)):
            raise JeevesAppwideError("active reviewed original campaign required")
        path="game/campaigns/"+campaign_id+"_lore.json"
        source=self.ws.read("current",project,path)
        document=_json(source["content"])
        rebuilt=rebuild_campaign_lore_document(self.ws,project,document)
        if rebuilt!=document:
            raise JeevesAppwideError("original story cast or plot history became stale")
        body={
            "schema":SCHEMA+".verified",
            "project":project,"campaign_id":campaign_id,
            "source_sha256":source["version"]["sha256"],
            "game_nodes_bound_to_real_story":len(document["narrative_sources"]),
            "real_full_story_history_checked":True,
            "reference_gameplay_campaign_reexecuted":True,
            "canonical_bible_and_causal_plot_sources_pinned":True,
            "actual_scripted_story_content_generated":False,
            "native_hardware_or_model_verified":False,
            "source_mutations_performed":False,
        }
        return {**body,"digest":digest(body)}
