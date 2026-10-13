"""Local-first three-lane game creation workspace with human-reviewed edits.

Current projects are writable through optimistic edit proposals. Previous
snapshots and demos are immutable references until explicitly forked. Symlinks,
traversal and unexpected file overwrites fail closed; reviewed executable
scripts are *stored*, never executed. Records support both visual and CLI use.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from .contracts import canonical_json, canonical_digest

IDENT=re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
SEGMENT=re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
ALLOWED=frozenset({
    ".json",".md",".txt",".py",".gd",".tscn",".cfg",".toml",
    ".yml",".yaml",".html",".js",".css",".ini",".csv",".godot",
})
SOURCE_MAX=256000
PROJECT_MAX_FILES=12512
PROJECT_MAX_BYTES=256_000_000


class WorkspaceError(ValueError):
    """An unsafe, stale or unauthorized original-project edit."""


def _name(value):
    if not isinstance(value,str) or not IDENT.fullmatch(value):
        raise WorkspaceError("project and genre IDs must be safe original identifiers")
    return value


def _relative(value):
    if not isinstance(value,str) or not 1<=len(value)<=450 or "\\" in value:
        raise WorkspaceError("relative original file location required")
    parts=PurePosixPath(value).parts
    if (not parts or len(parts)>12 or any(
        not SEGMENT.fullmatch(p) or p in {".",".."} or p.startswith(".")
        for p in parts
    )):
        raise WorkspaceError("file location violates contained editable tree")
    if Path(parts[-1]).suffix not in ALLOWED:
        raise WorkspaceError("unreviewed executable/binary artifact extension")
    return PurePosixPath(*parts).as_posix()


def _digest(data: bytes):
    return sha256(data).hexdigest()


def _read(path: Path,maximum=SOURCE_MAX):
    if path.is_symlink() or not path.is_file():
        raise WorkspaceError("files must be regular and never symlinks")
    if path.stat().st_size>maximum:
        raise WorkspaceError("file exceeds local consumer source limit")
    data=path.read_bytes()
    if len(data)>maximum:
        raise WorkspaceError("source changed size during inspection")
    try:
        return data.decode("utf-8","strict")
    except UnicodeError as exc:
        raise WorkspaceError("current editable source must be UTF-8") from exc


def _json(content):
    try:
        def unique(pairs):
            result={}
            for k,v in pairs:
                if k in result:
                    raise ValueError("duplicate JSON keys")
                result[k]=v
            return result
        return json.loads(content,object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(
                              ValueError("non-finite JSON number")))
    except (ValueError,UnicodeError,TypeError) as exc:
        raise WorkspaceError("ambiguous editor JSON rejected") from exc


def _newfile(path: Path,text: str):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() or path.is_symlink():
        raise WorkspaceError("workbench never silently overwrites an existing file")
    with path.open("xb") as f:
        f.write(text.encode("utf-8"))


@dataclass(frozen=True,slots=True)
class FileVersion:
    tree: str
    project: str
    path: str
    sha256: str
    bytes: int
    editable: bool

    def payload(self):
        return dict(tree=self.tree,project=self.project,path=self.path,
                    sha256=self.sha256,bytes=self.bytes,editable=self.editable)


class GameWorkspace:
    def __init__(self,root: str|Path):
        self.root=Path(root).absolute()
        if (not self.root.is_dir() or self.root.is_symlink()
                or not (self.root/"workspace.json").is_file()):
            raise WorkspaceError("initialize a local game workspace first")
        self._metadata()

    @classmethod
    def create(cls,root: str|Path,*,authorized: bool):
        if not authorized:
            raise PermissionError("creating workspace requires local operator approval")
        p=Path(root).absolute()
        if p.exists() or p.is_symlink() or not p.parent.is_dir() or p.parent.is_symlink():
            raise WorkspaceError("create a new workbench beneath a real existing directory")
        p.mkdir(mode=0o700)
        try:
            for name in ("current","previous","demos","reviews/proposals",
                         "reviews/accepted","training/quarantine"):
                (p/name).mkdir(parents=True)
            _newfile(p/"workspace.json",canonical_json({
                "schema":"skeleton.game_builder.workbench.v1",
                "active":None,"revision":0,"project_history":[],
            })+"\n")
            return cls(p)
        except BaseException:
            shutil.rmtree(p,ignore_errors=True)
            raise

    def _metadata(self):
        info=_json(_read(self.root/"workspace.json",200000))
        if (type(info) is not dict or info.get("schema")!=
            "skeleton.game_builder.workbench.v1"):
            raise WorkspaceError("workbench schema mismatch")
        return info

    def _write_metadata(self,record):
        self._atomic(self.root/"workspace.json",canonical_json(record)+"\n")

    def _atomic(self,path: Path,text: str):
        if path.is_symlink() or not path.parent.is_dir():
            raise WorkspaceError("cannot atomically edit a symlink or unknown parent")
        fd,name=tempfile.mkstemp(prefix=".studio-",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                f.write(text)
                f.flush();os.fsync(f.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def active(self):
        return self._metadata()["active"]

    def _tree_root(self,tree,project):
        if tree not in {"current","previous","demos"}:
            raise WorkspaceError("unknown workspace tree")
        # Previous/demo refs are genre/name subfolders, current is ID only.
        if tree=="current":
            _name(project);path=self.root/"current"/project
        else:
            elements=project.split("/")
            if len(elements)!=2:
                raise WorkspaceError("archive location needs genre/project ID")
            for element in elements:_name(element)
            path=self.root/tree/elements[0]/elements[1]
        if not path.is_dir() or path.is_symlink():
            raise WorkspaceError("requested original project does not exist")
        return path

    def _file(self,tree,project,relative):
        relative=_relative(relative)
        root=self._tree_root(tree,project)
        path=root.joinpath(*PurePosixPath(relative).parts)
        parent=path.parent
        while parent!=root:
            if parent.is_symlink():
                raise WorkspaceError("symlink would escape project editing boundary")
            parent=parent.parent
        if path.is_symlink():
            raise WorkspaceError("source symlinks may not be edited")
        return path

    def create_project(self,project: str,genre: str,*,authorized: bool,
                       director_json: dict|None=None):
        if not authorized:
            raise PermissionError("project creation requires active designer supervision")
        _name(project);_name(genre)
        dest=self.root/"current"/project
        if dest.exists() or dest.is_symlink():
            raise WorkspaceError("new current project ID needed; archive existing first")
        if director_json is not None and type(director_json) is not dict:
            raise WorkspaceError("typed original director blueprint required")
        dest.mkdir()
        try:
            for segment in ("game","npcs","scenes","missions","dialogue","cinematics",
                            "assets","engine","reviews","almanacs","notes"):
                (dest/segment).mkdir()
            _newfile(dest/"project.json",canonical_json({
                "schema":"skeleton.game_builder.workbench_project.v1",
                "project":project,"genre":genre,
                "rights_status":"original_assets_only_review_pending",
                "editor_authority":"human_supervision",
                "native_release_certified":False,
            })+"\n")
            if director_json:
                _newfile(dest/"game"/"director.json",canonical_json(director_json)+"\n")
            else:
                _newfile(dest/"game"/"readme.md",
                         "# Original game\nAuthor the scene and quest director for this project.\n")
            info=self._metadata()
            info["active"]=project
            info["revision"]+=1
            info["project_history"].append(dict(project=project,genre=genre,
                                                operation="created"))
            self._write_metadata(info)
        except BaseException:
            shutil.rmtree(dest,ignore_errors=True)
            raise
        return self.tree()

    def select_project(self,project: str,*,authorized: bool):
        if not authorized:
            raise PermissionError("switching active project requires operator intent")
        self._tree_root("current",project)
        info=self._metadata()
        info["active"]=project;info["revision"]+=1
        info["project_history"].append(dict(project=project,
                                            operation="selected"))
        self._write_metadata(info)
        return self.tree()

    def projects(self,tree: str):
        if tree not in {"current","previous","demos"}:
            raise WorkspaceError("unknown original workspace tree")
        base=self.root/tree
        if tree=="current":
            return tuple(sorted(p.name for p in base.iterdir()
                                if p.is_dir() and not p.is_symlink()
                                and IDENT.fullmatch(p.name)))
        result=[]
        for genre in base.iterdir():
            if not genre.is_dir() or genre.is_symlink() or not IDENT.fullmatch(genre.name):
                continue
            for project in genre.iterdir():
                if project.is_dir() and not project.is_symlink() and IDENT.fullmatch(project.name):
                    result.append(genre.name+"/"+project.name)
        return tuple(sorted(result))

    def files(self,tree: str,project: str):
        root=self._tree_root(tree,project)
        items=[]
        total=0
        for entry in sorted(root.rglob("*")):
            if entry.is_symlink():
                raise WorkspaceError("symlink detected inside original game sources")
            if not entry.is_file():
                continue
            relative=entry.relative_to(root).as_posix()
            if relative=="snapshot.json":
                continue
            _relative(relative)
            data=_read(entry)
            items.append(FileVersion(tree,project,relative,
                                     _digest(data.encode()),len(data.encode()),
                                     tree=="current" and project==self.active()))
            total+=len(data.encode())
            if len(items)>PROJECT_MAX_FILES or total>PROJECT_MAX_BYTES:
                raise WorkspaceError("game source tree exceeds bounded editable budget")
        return tuple(items)

    def tree(self):
        return dict(schema="skeleton.game_builder.workbench_trees.v1",
                    active=self.active(),revision=self._metadata()["revision"],
                    previous=[dict(ref=p,files=len(self.files("previous",p)))
                              for p in self.projects("previous")],
                    current=[dict(ref=p,files=len(self.files("current",p)))
                             for p in self.projects("current")],
                    demos=[dict(ref=p,files=len(self.files("demos",p)))
                           for p in self.projects("demos")],
                    review_proposals=len(list((self.root/"reviews/proposals").glob("*.json"))),
                    training_quarantine=len(list((self.root/"training/quarantine").glob("*.jsonl"))))

    def read(self,tree: str,project: str,relative: str):
        path=self._file(tree,project,relative)
        body=_read(path)
        return dict(version=FileVersion(tree,project,_relative(relative),
                                        _digest(body.encode()),len(body.encode()),
                                        tree=="current" and project==self.active()).payload(),
                    content=body)

    def _validate_advanced_scene_source(self,project: str,relative: str,document):
        from .advanced_level_scenes import validate_advanced_scene, scene_path
        from .advanced_gameplay_runtime import ENGINES
        if type(document) is not dict or document.get("editor") not in ENGINES:
            raise WorkspaceError("advanced scene needs an executable game editor")
        if relative!=scene_path(document):
            raise WorkspaceError("advanced scene filename mismatches original game identity")
        # Scenes bind the EXACT approved system source, not unsupervised UI
        # parameters. An unapproved system proposal cannot authorize a scene.
        editor=document["editor"]
        config_path=self._file("current",project,"systems/"+editor+".json")
        if not config_path.exists():
            raise WorkspaceError("approve the authored system configuration before its scene")
        from .system_editors import validate_editor_document
        config=validate_editor_document(_json(_read(config_path)))
        validate_advanced_scene(document,config["settings"])

    def _validate_campaign_lore_source(self, project, relative, document):
        """Reject uncommitted narrative links and invalid full-history evidence."""
        from .jeeves_campaign_lore import rebuild_campaign_lore_document
        if type(document) is not dict:
            raise WorkspaceError("exact original campaign narrative source required")
        rebuilt=rebuild_campaign_lore_document(self,project,document)
        if rebuilt!=document or relative!=(
                "game/campaigns/"+document["campaign_id"]+"_lore.json"):
            raise WorkspaceError("campaign original cast/plot/location source changed")
        return {
            "schema":document["schema"],
            "campaign_id":document["campaign_id"],
            "full_approved_story_history_reverified":True,
            "gameplay_campaign_sha256":document["campaign_source_sha256"],
            "source_files_mutated":False,
        }

    def _validate_advanced_campaign_source(self, project, relative, document):
        """Replay actual scene-linked, choice-branching game campaign at commit.

        A digest alone is not a game. Rebuild graph, endings and all real
        engine action receipts from saved current source versions.
        """
        from .jeeves_campaign_graph import rebuild_campaign_document
        if type(document) is not dict:
            raise WorkspaceError("typed original campaign document required")
        expected = rebuild_campaign_document(self, project, document)
        if expected != document:
            raise WorkspaceError(
                "game campaign graph, choices or actual gameplay proof changed")
        if relative != "game/campaigns/" + document["campaign_id"] + ".json":
            raise WorkspaceError("campaign source path mismatches authored campaign ID")
        return {
            "schema":document["schema"],
            "campaign_id":document["campaign_id"],
            "path":relative,
            "original_source_reexecuted_at_commit":True,
            "source_gameplay_receipt_digest":document["digest"],
            "native_or_external_model_execution_claimed":False,
        }

    def _validate_advanced_replay_source(self, project: str, relative: str,
                                         document: dict):
        """Commit-time authentic game action replay bound to actual saved sources.

        Scene/system inputs come from human-committed workspace content, not
        the submitted replay's claimed configuration or arbitrary model text.
        """
        from .advanced_level_scenes import scene_path
        from .advanced_gameplay_runtime import (
            ENGINES, verify_advanced_session, ACTION_HELP,
        )
        from .system_editors import validate_editor_document
        from .contracts import canonical_digest
        import re
        if (type(document) is not dict
                or set(document) != {
                    "schema", "project", "editor", "scene_id",
                    "system_sha256", "scene_sha256", "session", "digest"
                }
                or document.get("schema") !=
                   "skeleton.game_builder.approved_advanced_replay_source.v1"
                or document.get("project") != project):
            raise WorkspaceError("exact signed original gameplay replay source required")
        editor=document["editor"]
        scene_id=document["scene_id"]
        if (type(editor) is not str or editor not in ENGINES
                or type(scene_id) is not str
                or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}",scene_id)
                or relative != "game/replays/" + editor + "_" + scene_id + ".json"):
            raise WorkspaceError("advanced replay path mismatches its original editor/scene")
        canonical=dict(document)
        candidate=canonical.pop("digest")
        if (type(candidate) is not str or
                canonical_digest(canonical) != candidate):
            raise WorkspaceError("advanced replay source fingerprint mismatch")
        system_file=self._file("current",project,"systems/"+editor+".json")
        scene_file=self._file(
            "current",project,
            "scenes/advanced_"+editor+"_"+scene_id+".json")
        system_text=_read(system_file)
        scene_text=_read(scene_file)
        if (_digest(system_text.encode("utf-8")) != document["system_sha256"]
                or _digest(scene_text.encode("utf-8")) != document["scene_sha256"]):
            raise WorkspaceError("original game system/scene versions changed after replay")
        config=validate_editor_document(_json(system_text))
        scene=_json(scene_text)
        if (config["editor"]!=editor or scene_path(scene)!=
                "scenes/advanced_"+editor+"_"+scene_id+".json"):
            raise WorkspaceError("advanced replay source/canon binding invalid")
        session=document["session"]
        if (type(session) is not dict or session.get("editor")!=editor
                or session.get("scene")!=scene):
            raise WorkspaceError("replay transcript does not match original authored scene")
        if (type(session.get("actions")) is not list
                or len(session["actions"])>128 or
                any(action not in ACTION_HELP[editor]
                    for action in session["actions"])):
            raise WorkspaceError("unknown or unbounded real game actions")
        verify_advanced_session(session,config["settings"])
        return {
            "schema":document["schema"],
            "project":project,
            "source_path":relative,
            "scene_digest":scene["digest"],
            "replayed_turns":len(session["actions"]),
            "original_system_sha256":document["system_sha256"],
            "original_scene_sha256":document["scene_sha256"],
            "session_digest":session["digest"],
            "canonical_reference_gameplay_verified":True,
            "native_hardware_replay_executed":False,
        }

    def _validate_forge_blueprint(self, relative: str, document: dict):
        """Verify installed Forge kinds, typed ports and DAG before accepting source.

        Both proposal and actual human commit use this same canonical check;
        no untrusted submitted graph bypasses the real installed Forge.
        """
        from .contracts import canonical_digest
        from .jeeves_app_runtime import _review_forge_graph
        if (type(document) is not dict
                or set(document) != {
                    "schema", "id", "name", "components", "wires",
                    "review_digest", "digest"
                }
                or document.get("schema") !=
                   "skeleton.game_builder.reviewed_forge_source.v1"):
            raise WorkspaceError("exact original Forge source schema required")
        blueprint_id = document["id"]
        if (type(blueprint_id) is not str
                or not IDENT.fullmatch(blueprint_id)
                or relative != "assets/forge/" + blueprint_id + ".json"):
            raise WorkspaceError("Forge source filename must match blueprint identity")
        signed = dict(document)
        recorded = signed.pop("digest")
        if type(recorded) is not str or canonical_digest(signed) != recorded:
            raise WorkspaceError("original Forge blueprint source digest mismatch")
        current = _review_forge_graph({
            "name": document["name"],
            "components": document["components"],
            "wires": document["wires"],
        })
        if current["valid"] is not True or current["digest"] != document["review_digest"]:
            raise WorkspaceError("Forge ports/kinds/wires differ from installed graph validation")
        return {
            "schema": document["schema"],
            "blueprint_id": blueprint_id,
            "source_sha256": canonical_digest(document),
            "review_digest": current["digest"],
            "canonical_forge_graph_accepted": True,
            "forge_runtime_asset_built": False,
        }

    def propose(self,project: str,relative: str,text: str,*,expected_sha256: str,
                reason: str,authorized: bool):
        if not authorized:
            raise PermissionError("source editing requires local designer authority")
        if project!=self.active():
            raise WorkspaceError("edits require the current explicitly selected project")
        if type(text) is not str or len(text.encode("utf-8"))>SOURCE_MAX:
            raise WorkspaceError("bounded UTF-8 targeted edit required")
        if not isinstance(reason,str) or not 10<=len(reason)<=1000:
            raise WorkspaceError("designer change request needs a concrete reason")
        file=self._file("current",project,relative)
        existing=_read(file) if file.exists() else ""
        if _digest(existing.encode())!=expected_sha256:
            raise WorkspaceError("stale base SHA; re-open affected file before editing")
        if file.suffix==".json":
            parsed = _json(text)
            if relative.startswith("systems/"):
                from .system_editors import validate_editor_document, editor_path
                document = validate_editor_document(parsed)
                if relative != editor_path(document["editor"]):
                    raise WorkspaceError("editor source path does not match typed system ID")
            if relative.startswith("scenes/advanced_"):
                self._validate_advanced_scene_source(project,relative,parsed)
            if relative.startswith("assets/forge/"):
                self._validate_forge_blueprint(relative,parsed)
            if relative.startswith("game/replays/"):
                self._validate_advanced_replay_source(project,relative,parsed)
            if relative.startswith("game/campaigns/"):
                if relative.endswith("_lore.json"):
                    self._validate_campaign_lore_source(project,relative,parsed)
                else:
                    self._validate_advanced_campaign_source(project,relative,parsed)
            if (relative in ("game/story_bible.json","game/continuity_contract.json")
                    or relative.startswith(("story/scenes/","story/chapters/"))):
                from .story_workspace import validate_story_workspace_source
                validate_story_workspace_source(self,project,relative,parsed)
        proposal=dict(
            schema="skeleton.game_builder.targeted_edit.v1",
            project=project,path=_relative(relative),reason=reason,
            expected_sha256=expected_sha256,
            new_sha256=_digest(text.encode()),new_content=text,
            executable_source=file.suffix in {".py",".js",".gd"},
            requires_explicit_human_commit=True,
            changes_other_files=False,
        )
        proposal_id=canonical_digest(proposal)
        output=self.root/"reviews/proposals"/(proposal_id+".json")
        if not output.exists():
            _newfile(output,canonical_json(proposal)+"\n")
        return dict(proposal_id=proposal_id,project=project,path=relative,
                    before=expected_sha256,after=proposal["new_sha256"],
                    human_commit_required=True)

    def commit(self,proposal_id: str,*,human_approved: bool,authorized: bool):
        if not authorized or human_approved is not True:
            raise PermissionError("targeted file changes need explicit human commit")
        if not isinstance(proposal_id,str) or not re.fullmatch(r"[a-f0-9]{64}",proposal_id):
            raise WorkspaceError("content-addressed original edit ID required")
        proposal_path=self.root/"reviews/proposals"/(proposal_id+".json")
        proposal=_json(_read(proposal_path,300000))
        if canonical_digest(proposal)!=proposal_id:
            raise WorkspaceError("review proposal was changed after signoff")
        project=proposal["project"]
        if project!=self.active():
            raise WorkspaceError("cannot commit a proposal for an inactive project")
        path=self._file("current",project,proposal["path"])
        before=_read(path) if path.exists() else ""
        if _digest(before.encode())!=proposal["expected_sha256"]:
            raise WorkspaceError("optimistic edit conflict: source changed during review")
        if _digest(proposal["new_content"].encode())!=proposal["new_sha256"]:
            raise WorkspaceError("proposed artifact no longer matches human-reviewed text")
        if path.suffix==".json":
            parsed = _json(proposal["new_content"])
            if proposal["path"].startswith("systems/"):
                from .system_editors import validate_editor_document, editor_path
                document = validate_editor_document(parsed)
                if proposal["path"] != editor_path(document["editor"]):
                    raise WorkspaceError("editor document path mismatches its system identity")
            if proposal["path"].startswith("scenes/advanced_"):
                self._validate_advanced_scene_source(project,proposal["path"],parsed)
            if proposal["path"].startswith("assets/forge/"):
                self._validate_forge_blueprint(proposal["path"],parsed)
            if proposal["path"].startswith("game/replays/"):
                self._validate_advanced_replay_source(project,proposal["path"],parsed)
            if proposal["path"].startswith("game/campaigns/"):
                if proposal["path"].endswith("_lore.json"):
                    self._validate_campaign_lore_source(project,proposal["path"],parsed)
                else:
                    self._validate_advanced_campaign_source(project,proposal["path"],parsed)
            if (proposal["path"] in ("game/story_bible.json",
                                      "game/continuity_contract.json") or
                    proposal["path"].startswith(("story/scenes/","story/chapters/"))):
                from .story_workspace import validate_story_workspace_source
                validate_story_workspace_source(self,project,proposal["path"],parsed)
            if proposal["path"]=="game/director.json":
                from .quest_scene_forge import compile_director_blueprint
                compile_director_blueprint(_json(proposal["new_content"]),
                                           human_reviewed=True)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        # Existing source gets atomically replaced only after SHA compare;
        # new files are exclusive creates.
        if path.exists():
            self._atomic(path,proposal["new_content"])
        else:
            _newfile(path,proposal["new_content"])
        accepted=self.root/"reviews/accepted"/(proposal_id+".json")
        _newfile(accepted,canonical_json({
            "schema":"skeleton.game_builder.approved_targeted_edit.v1",
            "proposal":proposal_id,"project":project,
            "path":proposal["path"],"approved":True,
            "result_sha256":proposal["new_sha256"],
            "automated_publication":False,
        })+"\n")
        info=self._metadata();info["revision"]+=1
        self._write_metadata(info)
        return dict(approved=True,proposal=proposal_id,
                    path=proposal["path"],sha256=proposal["new_sha256"])

    def archive(self,project: str,*,authorized: bool,genre: str|None=None,
                demo: bool=False):
        if not authorized:
            raise PermissionError("archiving original product requires human approval")
        current=self._tree_root("current",project)
        record=_json(self.read("current",project,"project.json")["content"])
        selected=genre or record["genre"]
        _name(selected)
        records=self.files("current",project)
        signature=canonical_digest([r.payload() for r in records])
        name=project+"-"+signature[:12]
        _name(name)
        tree="demos" if demo else "previous"
        parent=self.root/tree/selected
        parent.mkdir(exist_ok=True)
        destination=parent/name
        if destination.exists() or destination.is_symlink():
            raise WorkspaceError("an identical immutable archive already exists")
        destination.mkdir()
        try:
            for row in records:
                data=self.read("current",project,row.path)["content"]
                _newfile(destination/row.path,data)
            _newfile(destination/"snapshot.json",canonical_json({
                "schema":"skeleton.game_builder.original_snapshot.v1",
                "project":project,"genre":selected,"snapshot":name,
                "source_signature":signature,
                "source_files":{row.path:row.sha256 for row in records},
                "immutable_after_creation":True,
                "archived_revision":self._metadata()["revision"]+1,
                "demo":demo,
                "human_approved":True,
            })+"\n")
        except BaseException:
            shutil.rmtree(destination,ignore_errors=True);raise
        info=self._metadata()
        info["revision"]+=1
        info["project_history"].append(dict(
            project=project,genre=selected,operation="demo" if demo else "archive",
            ref=selected+"/"+name,
        ))
        self._write_metadata(info)
        return dict(ref=selected+"/"+name,tree=tree,
                    source_signature=signature,files=len(records))

    def fork_reference(self,tree: str,reference: str,target_project: str,*,
                       authorized: bool):
        if not authorized:
            raise PermissionError("forking historical original game requires human approval")
        if tree not in {"previous","demos"}:
            raise WorkspaceError("only immutable prior or demo projects may be forked")
        _name(target_project)
        source=self._tree_root(tree,reference)
        snapshot=_json(_read(source/"snapshot.json",100000))
        if snapshot.get("demo") != (tree=="demos"):
            raise WorkspaceError("archive provenance disagrees with read-only project lane")
        records=self.files(tree,reference)
        if {row.path:row.sha256 for row in records}!=snapshot["source_files"]:
            raise WorkspaceError("immutable original project source hashes failed")
        target=self.root/"current"/target_project
        if target.exists() or target.is_symlink():
            raise WorkspaceError("fork requires a unique new current project")
        target.mkdir()
        try:
            for row in records:
                body=self.read(tree,reference,row.path)["content"]
                if row.path=="project.json":
                    item=_json(body)
                    item["project"]=target_project
                    body=canonical_json(item)+"\n"
                _newfile(target/row.path,body)
            self.select_project(target_project,authorized=True)
        except BaseException:
            shutil.rmtree(target,ignore_errors=True);raise
        return dict(forked_from=reference,source_lane=tree,
                    active=target_project,
                    source_signature=snapshot["source_signature"],
                    files=len(records))

    def autoload_previous(self,genre: str,target_project: str,*,authorized: bool):
        if not authorized:
            raise PermissionError("autoloading previous genre needs explicit user intent")
        _name(genre);_name(target_project)
        entries=[p for p in self.projects("previous") if p.startswith(genre+"/")]
        if not entries:
            raise WorkspaceError("no original previous project for requested genre")
        def rank(reference):
            snapshot=_json(_read(
                self._tree_root("previous",reference)/"snapshot.json",100000))
            return (snapshot.get("archived_revision",0),reference)
        selected=max(entries,key=rank)
        output=self.fork_reference("previous",selected,target_project,authorized=True)
        return dict(**output,autoloaded_from=selected)

    def fork_demo(self,reference: str,target_project: str,*,authorized: bool):
        return self.fork_reference("demos",reference,target_project,
                                   authorized=authorized)

__all__=[
    "WorkspaceError","GameWorkspace","FileVersion",
    "SOURCE_MAX","PROJECT_MAX_FILES",
]
