"""Jeeves' whole-application indexed capability and operator-governed runtime.

Every regular source/resource file under a reviewed repository root is discoverable.
Discovery is NOT executable tool authority: only typed adapters become callable.
No dynamic import, exec, eval, shell invocation, symlink traversal, secrets
exfiltration or automatic self-modifying code runs through this interface.

The inventory is intentionally tree-agnostic: it scales to previously unknown
forge, crawler, editor, AI, shell, dragon, frontend and module families.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import difflib
import json
import os
from pathlib import Path
from collections import Counter
import re
import stat

SCHEMA = "skeleton.ai.jeeves_appwide_inventory.v1"
ACTION_SCHEMA = "skeleton.ai.jeeves_appwide_action_receipt.v1"
MAX_FILES = 200_000
MAX_SOURCE = 256_000
MAX_PATCH = 120_000
MAX_QUERY = 180
MAX_PAGE = 100
MAX_DEPTH = 32
FORBIDDEN_NAMES = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv",
    "node_modules", "dist", "build", ".next", ".turbo",
})
PRIVATE = re.compile(
    r"(?:^|[./_-])(?:\.env|credentials|password|private|secret|"
    r"token|api[_-]?key|oauth|session|cookie|ssh|vault|id_rsa|id_ed25519|\.pem|\.key|\.p12)(?:$|[./_-])",
    re.I)
INVENTORY_ROOTS = (
    "skeleton", "backend", "frontend", "apps", "docs",
    "tests", "scripts", "tools", "packages", "satellites",
)
DOMAINS = (
    ("forge", ("forge", "craft", "blueprint", "asset_pipeline")),
    ("crawler", ("crawler", "crawl", "recrawl", "research", "rss", "search")),
    ("companion", ("dragon", "companion", "tamagotchi", "hatchling")),
    ("jeeves", ("jeeves", "agent", "supervisor", "secretary")),
    ("editor", ("editor", "studio", "canvas", "scene_builder", "director")),
    ("game", ("game", "world", "npc", "quest", "engine", "simulation")),
    ("learning", ("weight", "training", "distill", "almanac", "learn", "mirror")),
    ("runtime", ("runtime", "kernel", "worker", "execution", "orchestr")),
    ("frontend", ("frontend", "components", "views", "pages", "ui")),
    ("security", ("security", "policy", "sandbox", "assurance", "audit")),
    ("build", ("workflow", "release", "ci", "build", "installer", "packag")),
    ("data", ("dataset", "fixture", "vault", "database", "data")),
)
SOURCE_SUFFIXES = frozenset({".py",".js",".jsx",".ts",".tsx",".mjs",".cjs",
                             ".gd",".rs",".go",".java",".kt",".cpp",".c",
                             ".h",".cs",".swift",".rb",".sh",".ps1"})
TEXT_SUFFIXES = SOURCE_SUFFIXES | frozenset({
    ".json",".jsonl",".md",".txt",".toml",".ini",".cfg",
    ".yml",".yaml",".xml",".html",".css",".csv",".sql",
    ".graphql",".proto",".svg",".gitattributes",".gitignore",
})


class JeevesAppwideError(ValueError):
    """Unknown root, unauthorized operation, stale content or unsafe file."""


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      separators=(",",":"),allow_nan=False)


def digest(value):
    try:
        return sha256(canonical(value).encode("utf-8")).hexdigest()
    except (TypeError,ValueError,OverflowError) as exc:
        raise JeevesAppwideError("invalid finite canonical evidence") from exc


def _relative(path):
    if type(path) is not str or not 1 <= len(path) <= 400 or "\\" in path:
        raise JeevesAppwideError("relative file name required")
    pieces=path.split("/")
    if any(not bit or bit in (".","..") or "\x00" in bit for bit in pieces):
        raise JeevesAppwideError("file traversal or ambiguous path blocked")
    if pieces[0] in FORBIDDEN_NAMES:
        raise JeevesAppwideError("private runtime files are not inventoried")
    return path


def _classification(path):
    low=path.lower()
    result=[]
    for domain,hints in DOMAINS:
        if any(word in low for word in hints):
            result.append(domain)
    return result or ["general"]


def _kind(path):
    suffix=Path(path).suffix.lower()
    if suffix in SOURCE_SUFFIXES:return "source"
    if suffix in TEXT_SUFFIXES:return "text"
    return "resource"


@dataclass(frozen=True)
class Entry:
    path: str
    bytes: int
    kind: str
    domains: tuple[str,...]
    readable: bool
    executable_adapter_bound: bool = False

    def payload(self):
        return {"path":self.path,"bytes":self.bytes,"kind":self.kind,
                "domains":list(self.domains),"readable":self.readable,
                "executable_adapter_bound":self.executable_adapter_bound}


class AppwideInventory:
    """Deterministic bounded scan of a repository checkout, not a name heuristic.

    It includes *all* regular files (even unrelated categories), and reports
    every skipped/unreadable file separately instead of silently declaring
    perfect coverage. File contents are read only via explicit exact path.
    """
    def __init__(self,repo_root):
        root=Path(repo_root)
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise JeevesAppwideError("real repository directory required")
        self.root=root.resolve(strict=True)
        self._files={}
        self._blocked={}
        self._digest=None

    def scan(self):
        files={}
        blocked={}
        stack=[(self.root,0)]
        while stack:
            directory,depth=stack.pop()
            if depth>MAX_DEPTH:
                blocked[directory.relative_to(self.root).as_posix()]="max_depth"
                continue
            try:
                rows=sorted(os.scandir(directory),key=lambda x:x.name)
            except OSError:
                blocked[directory.relative_to(self.root).as_posix()]="unreadable_directory"
                continue
            for item in rows:
                path=Path(item.path)
                rel=path.relative_to(self.root).as_posix()
                if item.name in FORBIDDEN_NAMES:
                    blocked[rel]="generated_or_private_runtime_tree"
                    continue
                try:
                    attrs=item.stat(follow_symlinks=False)
                except OSError:
                    blocked[rel]="unreadable_metadata"
                    continue
                if stat.S_ISLNK(attrs.st_mode):
                    blocked[rel]="symlink_not_followed"
                    continue
                if stat.S_ISDIR(attrs.st_mode):
                    stack.append((path,depth+1))
                    continue
                if not stat.S_ISREG(attrs.st_mode):
                    blocked[rel]="not_regular_file"
                    continue
                if len(files)>=MAX_FILES:
                    raise JeevesAppwideError(
                        "inventory budget exceeded: refusal is safer than hidden truncation")
                private=bool(PRIVATE.search(rel))
                files[rel]=Entry(rel,attrs.st_size,_kind(rel),
                                 tuple(_classification(rel)),
                                 not private)
        self._files=dict(sorted(files.items()))
        self._blocked=dict(sorted(blocked.items()))
        self._digest=digest([[x.path,x.bytes,x.kind,x.readable]
                             for x in self._files.values()])
        return self.report()

    def _require_scanned(self):
        if self._digest is None:
            raise JeevesAppwideError("explicit inventory scan required")

    def report(self):
        self._require_scanned()
        domains=Counter(d for e in self._files.values() for d in e.domains)
        roots=Counter(p.split("/")[0] for p in self._files)
        return {
            "schema":SCHEMA,"scanned_regular_files":len(self._files),
            "classified_files":len(self._files),
            "readable_files":sum(int(e.readable) for e in self._files.values()),
            "restricted_files":sum(int(not e.readable) for e in self._files.values()),
            "skipped_paths":len(self._blocked),
            "blocked_reasons":dict(Counter(self._blocked.values())),
            "domains":dict(sorted(domains.items())),
            "root_counts":dict(sorted(roots.items())),
            "snapshot_digest":self._digest,
            "visible_regular_files_discoverable":True,
            "excluded_and_unreadable_paths_are_not_executable":True,
            "all_files_executable":False,
            "all_features_working":False,
            "source_edits_require_review":True,
            "model_self_modification_allowed":False,
        }

    def search(self, *, query="", domain=None, offset=0, limit=40,
               expected_snapshot=None):
        self._require_scanned()
        if expected_snapshot is not None and expected_snapshot!=self._digest:
            raise JeevesAppwideError("stale inventory cursor")
        if type(query) is not str or len(query)>MAX_QUERY:
            raise JeevesAppwideError("bounded inventory search only")
        if domain is not None and (type(domain) is not str or
                                    domain not in {k for k,_ in DOMAINS}|{"general"}):
            raise JeevesAppwideError("unknown feature domain")
        if type(offset) is not int or offset<0 or offset>MAX_FILES:
            raise JeevesAppwideError("invalid deterministic file-page offset")
        if type(limit) is not int or not 1<=limit<=MAX_PAGE:
            raise JeevesAppwideError("bounded file pagination required")
        tokens=query.lower().split()
        matched=[e for e in self._files.values() if
                 (domain is None or domain in e.domains) and
                 all(t in e.path.lower() for t in tokens)]
        page=matched[offset:offset+limit]
        result={
            "schema":"skeleton.ai.jeeves_file_discovery_page.v1",
            "snapshot_digest":self._digest,"query":query,"domain":domain,
            "total_matches":len(matched),
            "offset":offset,"limit":limit,
            "next_offset":offset+len(page) if offset+len(page)<len(matched) else None,
            "files":[e.payload() for e in page],
            "all_entries_not_executable_by_discovery":True,
        }
        return {**result,"digest":digest(result)}

    def _safe_file(self,path,*,max_size=MAX_SOURCE):
        self._require_scanned()
        path=_relative(path)
        e=self._files.get(path)
        if e is None or not e.readable:
            raise JeevesAppwideError("unavailable or restricted repository file")
        if e.kind not in ("source","text"):
            raise JeevesAppwideError("binary/resource files need a specialized adapter")
        if e.bytes>max_size:
            raise JeevesAppwideError("file exceeds bounded context/page size")
        target=self.root
        pieces=path.split("/")
        for bit in pieces:
            target=target/bit
            try:
                status=os.lstat(target)
            except OSError as exc:
                raise JeevesAppwideError("repository file changed after scan") from exc
            if stat.S_ISLNK(status.st_mode):
                raise JeevesAppwideError("symlink/subtree swap blocked")
        try:
            if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
                flags=os.O_RDONLY | os.O_NOFOLLOW
                handles=[]
                try:
                    current=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
                    handles.append(current)
                    for component in pieces[:-1]:
                        current=os.open(component,
                                        flags|os.O_DIRECTORY,dir_fd=current)
                        handles.append(current)
                    fd=os.open(pieces[-1],flags,dir_fd=current)
                    with os.fdopen(fd,"rb") as stream:
                        data=stream.read(max_size+1)
                finally:
                    for fd in reversed(handles):
                        os.close(fd)
            else:
                # Windows path resolution and explicit symlink checks. This
                # branch never attempts shell/script execution or mutation.
                if target.resolve(strict=True).is_relative_to(self.root) is False:
                    raise JeevesAppwideError("unsafe changed source junction")
                with target.open("rb") as stream:
                    data=stream.read(max_size+1)
        except OSError as exc:
            raise JeevesAppwideError("source file unreadable or symlink swapped") from exc
        if len(data)>max_size or len(data)!=e.bytes:
            raise JeevesAppwideError("source changed since inventory scan")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JeevesAppwideError("non-UTF8 source requires separate binary reader") from exc

    def source(self,path):
        content=self._safe_file(path)
        result={
            "schema":"skeleton.ai.jeeves_source_inspection.v1",
            "path":path,"content":content,
            "sha256":sha256(content.encode("utf-8")).hexdigest(),
            "inventory_snapshot":self._digest,
            "read_only":True,
        }
        return result

    def propose_source_revision(self,*,path,expected_sha256,replacement,
                                reason,operator_authorized=False):
        """Review-only diff; does not alter repository files, run tests or merge."""
        if operator_authorized is not True:
            raise PermissionError("repository-wide code proposal requires operator authorization")
        if type(replacement) is not str or len(replacement.encode())>MAX_PATCH:
            raise JeevesAppwideError("bounded UTF-8 replacement needed")
        if type(reason) is not str or not 12<=len(reason)<=1000:
            raise JeevesAppwideError("reason for app improvement required")
        old=self.source(path)
        if expected_sha256!=old["sha256"]:
            raise JeevesAppwideError("optimistic source SHA conflict")
        if replacement==old["content"]:
            raise JeevesAppwideError("no-op modification rejected")
        diff="".join(difflib.unified_diff(
            old["content"].splitlines(keepends=True),
            replacement.splitlines(keepends=True),
            fromfile="a/"+path,tofile="b/"+path))
        if len(diff.encode())>MAX_PATCH*2:
            raise JeevesAppwideError("oversize review diff")
        body={
            "schema":"skeleton.ai.jeeves_appwide_code_change_proposal.v1",
            "path":path,"expected_sha256":expected_sha256,
            "proposed_sha256":sha256(replacement.encode()).hexdigest(),
            "reason":reason,"diff":diff,
            "inventory_snapshot":self._digest,
            "approval_required":True,"committed":False,
            "source_mutated":False,"automatic_self_update":False,
            "security_and_regression_review_required":True,
        }
        return {**body,"digest":digest(body)}


OPERATIONS = {
    "inventory.report":("read", "all scanned files",False),
    "inventory.search":("read", "paged whole app",False),
    "ai.contracts":("read", "static public code declarations (not callable rights)",False),
    "ai.impact":("read", "selected-source dependency and blast-radius preview",False),
    "ai.context":("read", "budgeted source-linked metadata context for Jeeves",False),
    "ai.duplicates":("read", "exact and heuristic near-duplicate review candidates",False),
    "ai.completion":("read", "full-app canonical readiness and evidence-gap census",False),
    "ai.deathmarch":("read", "prioritized evidence-gated cross-app completion backlog",False),
    "ai.graph":("read", "source-pinned cross-plane feature and release evidence graph",False),
    "ai.graph.neighbors":("read", "bounded graph ownership and dependency traversal",False),
    "ai.graph.impact":("read", "source-to-volume-to-enterprise declared impact receipts",False),
    "ai.coverage":("read", "per-volume source/test/evaluation path evidence audit",False),
    "ai.coverage.page":("read", "bounded volume gap inventory",False),
    "ai.verification.progress":("read", "measured static completion vs independent product and enterprise verification",False),
    "ai.verification.backlog":("read", "paged exact-source verification blockers with denominators",False),
    "ai.verification.volumes":("read", "paged 421 masterplan volume source and evidence gap frontier",False),
    "ai.cognition.uncertainty":("compute", "installed real uncertainty answer-abstain-escalate gate",False),
    "ai.cognition.strategy":("compute", "actual canonical resource-budgeted reasoning selection",False),
    "ai.cognition.stop":("compute", "actual guarded bounded cognitive stopping policy",False),
    "ai.cognition.build_plan":("compute", "actual installed original-game plan quality evaluation",False),
    "ai.cognition.static_plan":("compute", "installed exact DAG static analyzer and fault-injection simulator",False),
    "ai.release.gates":("read", "required exact-head release-gate authority census",False),
    "ai.release.gates.page":("read", "paged static CI gate provenance and missing workflows",False),
    "ai.adapter.audit":("read", "static registered tool-to-dispatch binding coverage",False),
    "ai.adapter.audit.page":("read", "bounded missing-dispatch audit records",False),
    "ai.api.bindings":("read", "selected frontend FastAPI literal route contract comparison",False),
    "ai.validation.frontier":("read", "changed source to declared test/evaluation qualification plan",False),
    "ai.validation.frontier.page":("read", "bounded suggested validation evidence page",False),
    "ai.milestones":("read", "dependency-ordered application milestone readiness",False),
    "ai.milestones.page":("read", "bounded source-pinned milestone page",False),
    "ai.milestones.critical":("read", "canonical dependency bottlenecks and longest structural chain",False),
    "ai.milestones.owners":("read", "page actual canonical task distribution by owner",False),
    "ai.workwaves":("read", "dependency-safe milestone parallelization with owner leases",False),
    "ai.workpack":("read", "source-hashed bounded implementation context for selected milestone IDs",False),
    "ai.code.search":("read", "bounded source-content lookup over inventoried files",False),
    "ai.code.snippet":("read", "line-paged verified UTF-8 source excerpt",False),
    "ai.code.dependencies":("read", "bounded real source import dependency graph",False),
    "ai.change_frontier":("read", "declared downstream change impact from exact repository paths",False),
    "studio.batch_preview":("compute", "bounded approved adapter previews across game/edit/forge planes",False),
    "source.inspect":("read", "UTF-8 source",False),
    "source.propose":("proposal", "exact-file reviewed code edit",True),
    "source.patchset.preview":("proposal", "source-pinned multi-file exact-hunk refactoring review",True),
    "editor.catalog":("read", "typed original-game editors",False),
    "editor.preview":("compute", "isolated editor simulation",False),
    "editor.template":("compute", "validated editable system template",False),
    "forge.tools":("read", "typed forge and studio tool discovery",False),
    "director.rpg":("compute", "bounded verified RPG chapter director",False),
    "director.world":("compute", "deterministic world-route director",False),
    "studio.assembly":("compute", "approved system integration audit",False),
    "studio.production.plan":("compute", "actual multi-engine original game production source plan",False),
    "studio.production.stage":("proposal", "reviewed original game system or scene source proposals",True),
    "studio.production.release_plan":("compute", "original replay-proven browser and Godot source package",True),
    "studio.production.release_stage":("proposal", "original browser and Godot artifact review staging",True),
    "studio.production.variants_plan":("compute", "bounded real original game source variants",True),
    "studio.production.variants_stage":("proposal", "stage independently built original game source variants",True),
    "studio.story.source_plan":("read", "full-story canonical 100-chapter source and continuity context",False),
    "studio.story.source_stage":("proposal", "signed full-history reviewed story source proposals",True),
    "studio.forge.plan":("compute", "actual installed typed Forge blueprint source validation",False),
    "studio.forge.stage":("proposal", "canonical reviewed Universal Forge game asset source",True),
    "studio.forge.verify":("read", "real project Forge source revalidation",False),
    "studio.advanced.replay.plan":("compute", "execute reference gameplay from actual approved advanced game scene",True),
    "studio.advanced.replay.stage":("proposal", "stage source-bound verified advanced gameplay receipt",True),
    "studio.advanced.replay.verify":("read", "reexecute committed advanced game session against approved system/scene",False),
    "studio.campaign.plan":("compute", "simulate bounded branching original game campaign across canonical scenes",True),
    "studio.campaign.stage":("proposal", "reviewed SHA-bound authored campaign source and actual route receipt",True),
    "studio.campaign.verify":("read", "replay committed original campaign source and endings",False),
    "studio.campaign.lore.plan":("read", "bind real character/region/plot story history to a committed game campaign",False),
    "studio.campaign.lore.stage":("proposal", "stage canonical full-story game campaign links for human review",True),
    "studio.campaign.lore.verify":("read", "reverify source-committed story/game causal binding",False),
    "studio.campaign.outcomes.plan":("compute", "run real player action variants across original authored campaign branches",True),
    "studio.campaign.outcomes.stage":("proposal", "stage observed multi-ending gameplay source and uncovered routes",True),
    "studio.campaign.outcomes.verify":("read", "reexecute committed game outcome portfolio and source identities",False),
    "studio.campaign.consequences.plan":("read", "historically signed NPC, faction and causal plot differences along real game outcomes",False),
    "studio.campaign.consequences.stage":("proposal", "original scene/event-to-game consequence source for human review",True),
    "studio.campaign.consequences.verify":("read", "rebuild full original narrative and real scenario consequences",False),
    "studio.production.prompt_plan":("compute", "user prompt to real installed game editor source plan",True),
    "studio.production.prompt_stage":("proposal", "stage prompt-selected reviewed game editors",True),
    "studio.production.review_bundle":("read", "exact-hash multi-proposal original source review",False),
    "studio.production.commit_bundle":("external_effect", "explicit human-approved original source commit group",True),
    "studio.production.queue":("read", "paged pending and accepted original source proposals",False),
    "studio.release.catalog":("read", "source-custodied original browser/Godot release identities",False),
    "studio.release.verify":("read", "approved source hash and canonical package proof verification",False),
    "studio.release.download":("compute", "designer-authorized deterministic accepted source ZIP",True),
    "studio.release.replay":("compute", "actual Python winning replay and byte-identical package rebuild",True),
    "studio.release.compare":("read", "source-hashed actual approved original game variant differences",False),
    "studio.tree":("read", "active project files",False),
    "studio.file":("read", "active project source",False),
    "studio.propose":("proposal", "targeted human-reviewed project edit",True),
    "jeeves.work_order":("compute", "original production director",False),
    "jeeves.chapter_chat":("compute", "source-backed chapter conversation",False),
    "crawler.plan":("compute", "bounded evidence-acquisition planner",False),
    "companion.visual":("compute", "dragon event visual reducer",False),
    "learning.improvement_proposal":("proposal", "model improvement review",True),
    "forge.kinds":("read", "installed Universal Forge component kinds",False),
    "forge.graph":("compute", "typed original asset forge graph with port and cycle validation",False),
    "game.compile.original":("compute", "bounded replay-verified browser game compiler",True),
    "game.compile.native":("compute", "bounded original game plus native source compiler",True),
    "game.mirror.review":("compute", "adversarial original game replay and source mirror",True),
    "companion.simulate":("compute", "consent-bound Dragon state machine rehearsal",False),
    "crawler.catalog":("read", "existing source workers and acquisition state",False),
    "tool.fabric":("read", "native canonical tool contract and executor status",False),
    "tool.plan":("proposal", "finite typed operator-supervised tool plan",True),
    "model.improvement":("proposal", "shadow-model and code change review plan",False),

}


class JeevesAppwideRuntime:
    """Typed adapters for *actual* supported features; no ambient tools."""
    def __init__(self,inventory,*,workspace=None):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("verified repository inventory needed")
        inventory._require_scanned()
        self.inventory=inventory
        self.workspace=workspace

    def catalog(self):
        evidence={
            "schema":"skeleton.ai.jeeves_operational_surface.v1",
            "inventory_digest":self.inventory._digest,
            "files_known":len(self.inventory._files),
            "registered_adapters":[{
                "name":name,"effect":row[0],"scope":row[1],
                "operator_gate":row[2],
            } for name,row in sorted(OPERATIONS.items())],
            "registered_action_count":len(OPERATIONS),
            "unregistered_code_execution_denied":True,
            "application_wide_edit_permissions_inherited":False,
        }
        return {**evidence,"digest":digest(evidence)}

    def invoke(self,action,params=None,*,authorized=False):
        if type(action) is not str or action not in OPERATIONS:
            raise JeevesAppwideError("no reviewed adapter for requested action")
        if type(params) is not dict:
            raise JeevesAppwideError("typed action parameters required")
        operation=OPERATIONS[action]
        if operation[2] and authorized is not True:
            raise PermissionError("explicit operator confirmation required")
        inv=self.inventory
        ws=self.workspace
        project=params.get("project")
        if action=="inventory.report":
            result=inv.report()
        elif action=="inventory.search":
            result=inv.search(**params)
        elif action in ("ai.contracts", "ai.impact", "ai.context", "ai.duplicates"):
            from .jeeves_capability_intelligence import JeevesStaticIntelligence
            intelligence=JeevesStaticIntelligence(inv)
            if action=="ai.contracts":
                result=intelligence.contracts(**params)
            elif action=="ai.impact":
                result=intelligence.impact(**params)
            elif action=="ai.context":
                result=intelligence.context(**params)
            else:
                result=intelligence.duplicates(**params)
        elif action=="ai.completion":
            from .jeeves_completion_census import JeevesCompletionCensus
            result=JeevesCompletionCensus(inv).report(**params)
        elif action=="ai.deathmarch":
            from .jeeves_completion_census import JeevesCompletionCensus
            result=JeevesCompletionCensus(inv).backlog(**params)
        elif action=="ai.graph":
            from .jeeves_evidence_graph import JeevesEvidenceGraph
            result=JeevesEvidenceGraph(inv).overview(**params)
        elif action=="ai.graph.neighbors":
            from .jeeves_evidence_graph import JeevesEvidenceGraph
            result=JeevesEvidenceGraph(inv).neighborhood(**params)
        elif action=="ai.graph.impact":
            from .jeeves_evidence_graph import JeevesEvidenceGraph
            result=JeevesEvidenceGraph(inv).impact(**params)
        elif action=="ai.coverage":
            from .jeeves_evidence_coverage import JeevesEvidenceCoverage
            result=JeevesEvidenceCoverage(inv).overview(**params)
        elif action=="ai.coverage.page":
            from .jeeves_evidence_coverage import JeevesEvidenceCoverage
            result=JeevesEvidenceCoverage(inv).page(**params)
        elif action in ("ai.verification.progress", "ai.verification.backlog"):
            from .jeeves_verification_progress import JeevesVerificationProgress
            verification=JeevesVerificationProgress(inv)
            if action=="ai.verification.progress":
                result=verification.overview(**params)
            else:
                result=verification.backlog(**params)
        elif action=="ai.verification.volumes":
            from .jeeves_verification_progress import JeevesVerificationProgress
            result=JeevesVerificationProgress(inv).volumes(**params)
        elif action in ("ai.cognition.uncertainty", "ai.cognition.strategy",
                        "ai.cognition.stop", "ai.cognition.build_plan",
                        "ai.cognition.static_plan"):
            from .jeeves_cognitive_studio import JeevesCognitiveStudio
            cognitive=JeevesCognitiveStudio(inv)
            if action=="ai.cognition.uncertainty":
                result=cognitive.uncertainty(**params)
            elif action=="ai.cognition.strategy":
                result=cognitive.strategy(**params)
            elif action=="ai.cognition.build_plan":
                result=cognitive.build_plan(**params)
            elif action=="ai.cognition.static_plan":
                result=cognitive.static_plan(**params)
            else:
                result=cognitive.stopping(**params)
        elif action=="ai.release.gates":
            from .jeeves_release_gate_inventory import JeevesReleaseGateInventory
            result=JeevesReleaseGateInventory(inv).overview(**params)
        elif action=="ai.release.gates.page":
            from .jeeves_release_gate_inventory import JeevesReleaseGateInventory
            result=JeevesReleaseGateInventory(inv).page(**params)
        elif action=="ai.adapter.audit":
            from .jeeves_adapter_dispatch_audit import JeevesAdapterDispatchAudit
            result=JeevesAdapterDispatchAudit(inv).overview(**params)
        elif action=="ai.adapter.audit.page":
            from .jeeves_adapter_dispatch_audit import JeevesAdapterDispatchAudit
            result=JeevesAdapterDispatchAudit(inv).page(**params)
        elif action=="ai.api.bindings":
            from .jeeves_crossplane_route_scout import JeevesAPIBindingScout
            result=JeevesAPIBindingScout(inv).inspect(**params)
        elif action=="ai.validation.frontier":
            from .jeeves_change_validation_frontier import JeevesChangeValidationFrontier
            result=JeevesChangeValidationFrontier(inv).overview(**params)
        elif action=="ai.validation.frontier.page":
            from .jeeves_change_validation_frontier import JeevesChangeValidationFrontier
            result=JeevesChangeValidationFrontier(inv).page(**params)
        elif action=="ai.milestones":
            from .jeeves_milestone_planner import JeevesMilestonePlanner
            result=JeevesMilestonePlanner(inv).overview(**params)
        elif action=="ai.milestones.page":
            from .jeeves_milestone_planner import JeevesMilestonePlanner
            result=JeevesMilestonePlanner(inv).page(**params)
        elif action in ("ai.milestones.critical", "ai.milestones.owners"):
            from .jeeves_critical_path import JeevesCriticalPath
            analysis=JeevesCriticalPath(inv)
            if action=="ai.milestones.critical":
                result=analysis.overview(**params)
            else:
                result=analysis.ownerload(**params)
        elif action in ("ai.workwaves", "ai.workpack", "ai.change_frontier"):
            from .jeeves_deathmarch_workpacks import JeevesWorkpackDirector
            director=JeevesWorkpackDirector(inv)
            if action=="ai.workwaves":
                result=director.waves(**params)
            elif action=="ai.workpack":
                result=director.workpack(**params)
            else:
                result=director.change_frontier(**params)
        elif action in ("ai.code.search", "ai.code.snippet"):
            from .jeeves_code_navigator import JeevesCodeNavigator
            navigator=JeevesCodeNavigator(inv)
            if action=="ai.code.search":
                result=navigator.search(**params)
            else:
                result=navigator.snippet(**params)
        elif action=="ai.code.dependencies":
            from .jeeves_dependency_navigation import JeevesSourceDependencyGraph
            result=JeevesSourceDependencyGraph(inv).walk(**params)
        elif action=="studio.batch_preview":
            from .jeeves_batch_workbench import run_batch_preview
            result=run_batch_preview(self, params)
        elif action in ("studio.production.plan", "studio.production.stage"):
            from .jeeves_production_wave import JeevesProductionWave
            director=JeevesProductionWave(inv, ws)
            if action=="studio.production.plan":
                result=director.plan(**params)
            else:
                result=director.stage(**params, operator_authorized=authorized)
        elif action in ("studio.production.release_plan", "studio.production.release_stage"):
            from .jeeves_original_release_wave import JeevesOriginalReleaseWave
            release=JeevesOriginalReleaseWave(inv, ws)
            if action=="studio.production.release_plan":
                result=release.plan(**params, operator_authorized=authorized)
            else:
                result=release.stage(**params, operator_authorized=authorized)
        elif action in ("studio.production.review_bundle", "studio.production.commit_bundle"):
            from .jeeves_production_review import JeevesProductionReview
            review=JeevesProductionReview(inv, ws)
            if action=="studio.production.review_bundle":
                result=review.review(**params)
            else:
                result=review.commit(**params, operator_authorized=authorized)
        elif action in ("studio.production.prompt_plan", "studio.production.prompt_stage"):
            from .jeeves_prompt_production import JeevesPromptProduction
            prompt_builder=JeevesPromptProduction(inv, ws)
            if action=="studio.production.prompt_plan":
                result=prompt_builder.plan(**params, operator_authorized=authorized)
            else:
                result=prompt_builder.stage(**params, operator_authorized=authorized)
        elif action in ("studio.production.variants_plan", "studio.production.variants_stage"):
            from .jeeves_game_variants import JeevesGameVariants
            variants=JeevesGameVariants(inv, ws)
            if action=="studio.production.variants_plan":
                result=variants.plan(**params, operator_authorized=authorized)
            else:
                result=variants.stage(**params, operator_authorized=authorized)
        elif action=="studio.production.queue":
            from .jeeves_proposal_queue import JeevesProposalQueue
            result=JeevesProposalQueue(inv, ws).page(**params)
        elif action in ("studio.release.catalog", "studio.release.verify",
                        "studio.release.download", "studio.release.replay",
                        "studio.release.compare"):
            from .jeeves_release_custody import JeevesReleaseCustody
            release=JeevesReleaseCustody(inv, ws)
            if action=="studio.release.catalog":
                result=release.catalog(**params)
            elif action=="studio.release.verify":
                result=release.verify(**params)
            elif action=="studio.release.compare":
                result=release.compare(**params)
            elif action=="studio.release.replay":
                result=release.replay(**params, operator_authorized=authorized)
            else:
                result=release.download(**params, operator_authorized=authorized)
        elif action in ("studio.story.source_plan", "studio.story.source_stage"):
            from .jeeves_story_production import JeevesStorySourceWave
            story_author=JeevesStorySourceWave(inv, ws)
            if action=="studio.story.source_plan":
                result=story_author.plan(**params)
            else:
                result=story_author.stage(**params, operator_authorized=authorized)
        elif action in ("studio.forge.plan", "studio.forge.stage",
                        "studio.forge.verify"):
            from .jeeves_forge_production import JeevesForgeProduction
            forge_author=JeevesForgeProduction(inv, ws)
            if action=="studio.forge.plan":
                result=forge_author.plan(**params)
            elif action=="studio.forge.stage":
                result=forge_author.stage(**params, operator_authorized=authorized)
            else:
                result=forge_author.verify(**params)
        elif action in ("studio.advanced.replay.plan",
                        "studio.advanced.replay.stage",
                        "studio.advanced.replay.verify"):
            from .jeeves_advanced_replay import JeevesAdvancedReplay
            session=JeevesAdvancedReplay(inv,ws)
            if action=="studio.advanced.replay.plan":
                result=session.plan(**params,operator_authorized=authorized)
            elif action=="studio.advanced.replay.stage":
                result=session.stage(**params,operator_authorized=authorized)
            else:
                result=session.verify(**params)
        elif action in ("studio.campaign.plan", "studio.campaign.stage",
                        "studio.campaign.verify"):
            from .jeeves_campaign_graph import JeevesCampaignGraph
            campaign=JeevesCampaignGraph(inv,ws)
            if action=="studio.campaign.plan":
                result=campaign.plan(**params,operator_authorized=authorized)
            elif action=="studio.campaign.stage":
                result=campaign.stage(**params,operator_authorized=authorized)
            else:
                result=campaign.verify(**params)
        elif action in ("studio.campaign.lore.plan","studio.campaign.lore.stage",
                        "studio.campaign.lore.verify"):
            from .jeeves_campaign_lore import JeevesCampaignLore
            lore=JeevesCampaignLore(inv,ws)
            if action=="studio.campaign.lore.plan":
                result=lore.plan(**params)
            elif action=="studio.campaign.lore.stage":
                result=lore.stage(**params,operator_authorized=authorized)
            else:
                result=lore.verify(**params)
        elif action in ("studio.campaign.outcomes.plan",
                        "studio.campaign.outcomes.stage",
                        "studio.campaign.outcomes.verify"):
            from .jeeves_campaign_outcomes import JeevesCampaignOutcomes
            outcomes=JeevesCampaignOutcomes(inv,ws)
            if action=="studio.campaign.outcomes.plan":
                result=outcomes.plan(**params,operator_authorized=authorized)
            elif action=="studio.campaign.outcomes.stage":
                result=outcomes.stage(**params,operator_authorized=authorized)
            else:
                result=outcomes.verify(**params)
        elif action in ("studio.campaign.consequences.plan",
                        "studio.campaign.consequences.stage",
                        "studio.campaign.consequences.verify"):
            from .jeeves_narrative_consequences import JeevesNarrativeConsequences
            consequences=JeevesNarrativeConsequences(inv,ws)
            if action=="studio.campaign.consequences.plan":
                result=consequences.plan(**params)
            elif action=="studio.campaign.consequences.stage":
                result=consequences.stage(
                    **params,operator_authorized=authorized)
            else:
                result=consequences.verify(**params)
        elif action=="source.inspect":
            result=inv.source(params["path"])
        elif action=="source.propose":
            result=inv.propose_source_revision(
                path=params["path"],expected_sha256=params["expected_sha256"],
                replacement=params["replacement"],reason=params["reason"],
                operator_authorized=authorized)
        elif action=="source.patchset.preview":
            from .jeeves_source_patchset import preview_source_patchset
            result=preview_source_patchset(inv, **params,
                                           operator_authorized=authorized)
        elif action=="editor.catalog":
            from .system_editors import catalog
            result={"editors":catalog(),"read_only":True}
        elif action=="editor.preview":
            from .system_editors import preview_editor
            result=preview_editor(params["editor"],params.get("settings"))
        elif action=="editor.template":
            from .system_editors import make_editor_document,editor_path
            name=params["editor"]
            result={"path":editor_path(name),
                    "document":make_editor_document(name,params.get("settings")),
                    "staged":False,"requires_approval":True}
        elif action=="forge.tools":
            from .studio_tool_fabric import ToolFabric,Actor,Phase
            who=Actor(params.get("actor","jeeves"))
            phase=Phase(params.get("phase","original"))
            result={"actor":who.value,"phase":phase.value,
                    "tools":[t.to_payload() for t in
                             ToolFabric().discover(actor=who,phase=phase)],
                    "any_tool_executed":False,
                    "backend_forge_binding_not_automatically_assumed":True}
        elif action=="director.rpg":
            from .advanced_rpg_planner import plan_original_rpg_chapter
            result=plan_original_rpg_chapter(
                params["scene"],params.get("settings"),
                max_nodes=params.get("max_nodes",8000))
        elif action=="director.world":
            from .advanced_world_planner import plan_original_world
            result=plan_original_world(
                params["scene"],params.get("settings"),
                max_states=params.get("max_states",50000))
        elif action in ("studio.tree","studio.file","studio.propose",
                        "studio.assembly",
                        "jeeves.work_order","jeeves.chapter_chat"):
            if ws is None or project != ws.active():
                raise JeevesAppwideError("explicitly selected current project required")
            if action=="studio.tree":
                result=ws.tree()
            elif action=="studio.assembly":
                from .system_editor_assembly import assemble_workspace_systems
                result=assemble_workspace_systems(ws,project,authorized=True)
            elif action=="studio.file":
                result=ws.read("current",project,params["path"])
            elif action=="studio.propose":
                result=ws.propose(project,params["path"],params["text"],
                                  expected_sha256=params["expected_sha256"],
                                  reason=params["reason"],authorized=authorized)
            elif action=="jeeves.work_order":
                from .jeeves_production_director import work_order
                result=work_order(ws,project,params["prompt"],
                                  cast=params.get("cast"),
                                  region=params.get("region"),
                                  act=params.get("act"),scene=params.get("scene"))
            else:
                from .jeeves_chapter_chat import chat_turn
                result=chat_turn(ws,project,params["prompt"],
                                 session=params.get("session"),
                                 cast=params.get("cast"),region=params.get("region"),
                                 act=params.get("act"),scene=params.get("scene"))
        elif action in (
            "forge.kinds","forge.graph","game.compile.original",
            "game.compile.native","game.mirror.review","companion.simulate",
            "crawler.catalog","tool.fabric","tool.plan","model.improvement"):
            if ws is None or project != ws.active():
                raise JeevesAppwideError("active project needed for production adapters")
            from .jeeves_app_runtime import dispatch_app_action
            from .jeeves_app_runtime import ACTIONS as canonical_actions
            require_canonical = canonical_actions[action][3]
            if require_canonical and not authorized:
                raise PermissionError("reviewed production operation requires approval")
            # The existing typed dispatcher remains the single actual
            # compiler/forge/companion executor; no substitute stack.
            # Project is an outer scoped authority selector, NOT one of the
            # canonical action's exact typed arguments. Passing it through
            # would break every underlying _exact() dispatcher contract
            # (forge, game compiler, crawler, Dragon, tool fabric, etc.).
            action_args={key:value for key,value in params.items()
                         if key!="project"}
            underlying=dispatch_app_action(
                ws,project,action,action_args,authorized=authorized)
            result={
                "canonical_adapter":action,
                "canonical_receipt_digest":underlying["digest"],
                "result":underlying["result"],
                "weights_changed":underlying["model_weights_changed"],
                "source_committed":underlying["source_files_committed"],
            }
        elif action=="crawler.plan":
            # No network access or automatic knowledge promotion.
            from ..webcrawler.active_research import plan_acquisition
            result={"targets":[{
                "start_year":t.start_year,"end_year":t.end_year,
                "priority":t.priority,"reasons":list(t.reasons),
            } for t in plan_acquisition(
                regimes=params.get("regimes",()),
                bias_rows=params.get("bias_rows",()),
                contradiction_rows=params.get("contradiction_rows",()),
                uncertainty_by_regime=params.get("uncertainty_by_regime"),
                limit=params.get("limit",10))],"crawl_started":False}
        elif action=="companion.visual":
            from ..webcrawler.dragon_visual_state import visual_state
            from types import SimpleNamespace
            event=params.get("event_kind")
            if type(event) is not str or event not in (
                "frontier_discovered","dragon_travel","visual_probe",
                "robots_check","fetch_started","fetch_received",
                "policy_rejected","acquisition_accepted","burn_started",
                "burn_chunk","burn_complete","retry_wait","crawl_complete"):
                raise JeevesAppwideError("known dragon event only")
            v=visual_state(SimpleNamespace(kind=event))
            result={"pose":v.pose,"effect":v.effect,"label":v.label,
                    "progress":v.progress,"crawler_not_started":True}
        elif action=="learning.improvement_proposal":
            target=inv.source(params["path"])
            evidence=params.get("evidence")
            if type(evidence) is not list or not 2<=len(evidence)<=32 or not all(
                type(e) is dict and "source_digest" in e and "claim" in e and
                type(e["source_digest"]) is str and
                re.fullmatch(r"[a-f0-9]{64}",e["source_digest"]) and
                type(e["claim"]) is str and 12<=len(e["claim"])<=1000
                for e in evidence):
                raise JeevesAppwideError("two separately cited evidence claims required")
            proposed=inv.propose_source_revision(
                path=params["path"],expected_sha256=target["sha256"],
                replacement=params["replacement"],reason=params["reason"],
                operator_authorized=authorized)
            result={
                "source_patch":proposed,
                "evidence":evidence,
                "evidence_claims_independently_verified":False,
                "requires_mirror_adversarial_tests":True,
                "requires_independent_benchmark_improvement":True,
                "shadow_weights_promoted":False,
                "normal_weights_modified":False,
                "hyperweights_modified":False,
                "code_automatically_deployed":False,
            }
        else:
            raise JeevesAppwideError("unreachable tool routing state")
        body={
            "schema":ACTION_SCHEMA,"action":action,
            "effect":operation[0],
            "input_digest":digest(params),
            "inventory_digest":inv._digest,
            "result":result,
            "read_only_or_review_only":action not in ("studio.propose",) and
                                   operation[0]!="external_effect",
            "unregistered_execution_denied":True,
            "operator_authorized":authorized is True,
        }
        return {**body,"digest":digest(body)}
