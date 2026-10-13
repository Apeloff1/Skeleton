"""Exact-source Game Studio dependency index for Jeeves and human reviewers.

Unlike a bare file tree, this index reads actual current game documents and
connects signed system, scene, gameplay, campaign, lore, outcome, consequence
and native/browser release sources by their recorded SHA or canon digest.
It is explicitly a *bounded static dependency scan*, not gameplay, graph
execution, artifact certification or automatic source repair.
"""
from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
import re

from .game_project_workspace import GameWorkspace,_json
from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest

SCHEMA="skeleton.ai.game_source_graph.v1"
MAX_SCAN=1400
MAX_DEPENDENCIES=9000
MAX_PAGE=80
SHA=re.compile(r"[a-f0-9]{64}\Z")


def _kind(path):
    if re.fullmatch(r"systems/[a-z][a-z0-9_]{1,63}\.json",path):
        return "original_engine_settings"
    if re.fullmatch(r"scenes/advanced_[a-z0-9_]+\.json",path):
        return "original_advanced_scene"
    if path.startswith("game/replays/") and path.endswith(".json"):
        return "played_game_session"
    if path.startswith("game/campaigns/") and path.endswith(".json"):
        if path.endswith("_lore.json"):return "original_story_campaign_links"
        if path.endswith("_outcomes.json"):return "played_ending_coverage"
        if path.endswith("_consequences.json"):return "original_plot_consequences"
        return "original_game_campaign"
    if path.startswith("assets/forge/") and path.endswith(".json"):
        return "typed_forge_blueprint"
    if path=="game/story_bible.json":
        return "original_story_bible"
    if path.startswith(("story/scenes/","story/chapters/")) and path.endswith(".json"):
        return "source_signed_story_scene"
    if path.startswith("game/releases/") and path.endswith("/release.json"):
        return "source_only_game_release"
    return None


def _dependencies(path,kind,doc):
    result=[]
    def add(target,sha,semantics="source_sha256"):
        if type(target) is str and type(sha) is str and SHA.fullmatch(sha):
            result.append({"target":target,
                           "expected_sha256_or_canon_digest":sha,
                           "semantics":semantics})
        else:
            result.append({"target":str(target)[:280],
                           "expected_sha256_or_canon_digest":None,
                           "semantics":semantics})
    if kind=="original_advanced_scene":
        add("systems/"+str(doc.get("editor"))+".json",
            doc.get("settings_digest"),"canonical_document_digest")
    elif kind=="played_game_session":
        editor=doc.get("editor");scene=doc.get("scene_id")
        add("systems/"+str(editor)+".json",doc.get("system_sha256"))
        add("scenes/advanced_"+str(editor)+"_"+str(scene)+".json",
            doc.get("scene_sha256"))
    elif kind=="original_game_campaign":
        bindings=doc.get("source_bindings",{})
        if type(bindings) is dict:
            for node in bindings.values():
                if type(node) is not dict:continue
                editor=node.get("editor");scene=node.get("scene_id")
                add("systems/"+str(editor)+".json",
                    node.get("approved_system_sha256"))
                add("scenes/advanced_"+str(editor)+"_"+str(scene)+".json",
                    node.get("approved_scene_sha256"))
    elif kind=="original_story_campaign_links":
        p=path[:-len("_lore.json")]
        add(p+".json",doc.get("campaign_source_sha256"))
        add("game/story_bible.json",doc.get("story_bible_source_sha256"))
        nodes=doc.get("narrative_sources",[])
        if type(nodes) is list:
            for item in nodes:
                if type(item) is dict:
                    add(item.get("approved_story_path"),
                        item.get("approved_story_sha256"))
    elif kind=="played_ending_coverage":
        add(path[:-len("_outcomes.json")]+".json",
            doc.get("approved_campaign_source_sha256"))
    elif kind=="original_plot_consequences":
        prefix=path[:-len("_consequences.json")]
        add(prefix+".json",doc.get("current_campaign_source_sha256"))
        add(prefix+"_lore.json",doc.get("current_campaign_lore_source_sha256"))
        add(prefix+"_outcomes.json",
            doc.get("current_gameplay_outcomes_source_sha256"))
        add("game/story_bible.json",
            doc.get("verified_canonical_story_bible_sha256"))
    elif kind=="source_only_game_release":
        base=path.rsplit("/",1)[0]+"/"
        entries=doc.get("files",{})
        if type(entries) is dict:
            for member,checksum in sorted(entries.items()):
                if (type(member) is str and
                        not member.startswith("/") and "\\" not in member and
                        ".." not in PurePosixPath(member).parts):
                    add(base+member,checksum)
    return result


class JeevesGameSourceGraph:
    """Source version dependency graph with stale/missing edge diagnostics."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("source-scanned application inventory needed")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("selected active original game workspace needed")
        self.inv=inventory;self.ws=workspace

    def index(self,*,project,offset=0,limit=50,
              expected_graph_digest=None,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("repository source inventory changed")
        if type(project) is not str or self.ws.active()!=project:
            raise JeevesAppwideError("active current game project required")
        if type(offset) is not int or not 0<=offset<=15000:
            raise JeevesAppwideError("bounded graph page offset required")
        if type(limit) is not int or not 1<=limit<=MAX_PAGE:
            raise JeevesAppwideError("bounded graph page size required")
        before=self.ws.tree()["revision"]
        files=self.ws.files("current",project)
        source={item.path:item for item in files}
        candidates=[
            (item,_kind(item.path)) for item in files if _kind(item.path)
        ]
        truncated=len(candidates)>MAX_SCAN
        candidates=candidates[:MAX_SCAN]
        nodes=[]
        dependencies=[]
        docs={}
        for item,kind in candidates:
            data=self.ws.read("current",project,item.path)
            try:
                doc=_json(data["content"])
            except ValueError:
                nodes.append({
                    "path":item.path,"kind":kind,
                    "source_sha256":item.sha256,
                    "bytes":item.bytes,
                    "json_status":"invalid",
                    "dependencies":0,
                })
                continue
            if type(doc) is not dict:
                nodes.append({
                    "path":item.path,"kind":kind,
                    "source_sha256":item.sha256,
                    "bytes":item.bytes,
                    "json_status":"invalid",
                    "dependencies":0,
                })
                continue
            docs[item.path]=doc
            claimed=_dependencies(item.path,kind,doc)
            for row in claimed:
                dependencies.append({"source":item.path,**row})
            if len(dependencies)>MAX_DEPENDENCIES:
                raise JeevesAppwideError("source dependency edges exceed bounded index")
            nodes.append({
                "path":item.path,"kind":kind,
                "source_sha256":item.sha256,
                "bytes":item.bytes,
                "json_status":"parsed",
                "dependencies":len(claimed),
            })
        for edge in dependencies:
            target=edge["target"]
            original=source.get(target)
            expected=edge["expected_sha256_or_canon_digest"]
            semantics=edge["semantics"]
            if original is None:
                edge["status"]="missing"
                edge["observed_identity"]=None
            else:
                observed=(docs.get(target,{}).get("digest")
                          if semantics=="canonical_document_digest" else
                          original.sha256)
                # Some dependency source documents are outside the scan
                # budget: report unknown, never silently call them current.
                if semantics=="canonical_document_digest" and observed is None:
                    edge["status"]="not_inspected"
                else:
                    edge["status"]=(
                        "current" if expected is not None and expected==observed
                        else "drifted")
                edge["observed_identity"]=observed
        if self.ws.tree()["revision"]!=before:
            raise JeevesAppwideError("current game source tree changed during scan")
        indexes={
            "schema":SCHEMA+".index",
            "project":project,"inventory_snapshot":self.inv._digest,
            "workspace_revision":before,
            "total_current_original_game_files":len(files),
            "total_relevant_game_source_nodes":len([
                item for item in files if _kind(item.path)]),
            "nodes_scanned":len(nodes),
            "full_game_source_inventory_scanned":not truncated,
            "nodes_omitted_by_budget":max(0,len([
                item for item in files if _kind(item.path)])-len(nodes)),
            "source_kind_counts":dict(sorted(Counter(
                row["kind"] for row in nodes).items())),
            "source_dependency_count":len(dependencies),
            "edges_missing":sum(e["status"]=="missing" for e in dependencies),
            "edges_drifted":sum(e["status"]=="drifted" for e in dependencies),
            "edges_unknown":sum(e["status"]=="not_inspected" for e in dependencies),
            "source_metadata_graph_only_not_executable_acceptance":True,
            "unscanned_or_malformed_source_not_verified":True,
        }
        graph_sha=digest({"summary":indexes,"nodes":nodes,"edges":dependencies})
        if expected_graph_digest is not None and graph_sha!=expected_graph_digest:
            raise JeevesAppwideError("original game source graph changed between pages")
        paged=nodes[offset:offset+limit]
        paths={n["path"] for n in paged}
        result={
            **indexes,
            "graph_digest":graph_sha,
            "offset":offset,"limit":limit,
            "next_offset":offset+len(paged) if offset+len(paged)<len(nodes) else None,
            "nodes":paged,
            "dependencies_for_page":[
                edge for edge in dependencies if edge["source"] in paths
            ],
            "graph_source_mutated":False,
        }
        return {**result,"digest":digest(result)}
