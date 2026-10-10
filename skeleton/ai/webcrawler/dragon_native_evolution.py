"""Bounded original-homebrew evolution series with truthful cross-platform receipts.

A series is a real offline work product: successive source projects are
generated, archived, individually audited and compared. The canonical manifest
is published last and includes precisely which video-game changes were
delivered; this does NOT claim AI training or improved subjective game quality.

Runs only under explicit local operator authority and against the existing
Dragon native emitter/portfolio owners. No third-party games, ROM scraping,
emulator bypass, proprietary SDK, or unattended crawler publication.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass,replace
from pathlib import Path
import json
import re

from .dragon_game_design import HEROES, THEMES, PALETTES
from .dragon_native_production import (
    PortableGameDesign,ProductionRequest,
    _atomic_new,_canonical,_hash,
    plan_production,publish_production,
    verify_published_production,portable_design_document,
)
from .dragon_native_production import load_portable_design

SCHEMA="skeleton.ai.dragon.homebrew_evolution_series.v1"
MAX_EDITIONS=12
MAX_RELEASE_TARGETS=3
MAX_RELEASE_COUNT=36
MAX_SERIES_INDEX_BYTES=128000
CLEAN_SEGMENT=re.compile(r"edition-(0[1-9]|1[0-2])\Z")
INDEX_SEGMENT=re.compile(r"dragon-production-[a-f0-9]{20}\.json\Z")


@dataclass(frozen=True)
class EvolutionSeriesRequest:
    base:ProductionRequest
    editions:int=4
    rotate_heroes:bool=True
    rotate_worlds:bool=True
    rotate_palettes:bool=True
    ramp_difficulty:bool=True

    def validate(self)->None:
        self.base.validate()
        if not isinstance(self.base.portable_design,PortableGameDesign):
            raise ValueError("evolution series requires a real typed game design")
        if self.base.compile_roms or self.base.require_compiled:
            raise ValueError("evolution series emits source only; ROM builds require separate approval")
        if self.base.rights_basis!="original_homebrew" or self.base.rights_reference:
            raise PermissionError("series presently requires directly attested original work without private rights references")
        if type(self.editions) is not int or not 2<=self.editions<=MAX_EDITIONS:
            raise ValueError("evolution series must have 2 to 12 bounded editions")
        if len(self.base.targets)>MAX_RELEASE_TARGETS or len(self.base.targets)*self.editions>MAX_RELEASE_COUNT:
            raise ValueError("too many source targets in evolution series")
        for toggle in ("rotate_heroes","rotate_worlds","rotate_palettes","ramp_difficulty"):
            if type(getattr(self,toggle)) is not bool:
                raise ValueError("evolution controls are strict booleans")


def variant_for(series:EvolutionSeriesRequest,edition:int)->ProductionRequest:
    """Deterministic, independent variants based on original author design."""
    series.validate()
    if type(edition) is not int or not 0<=edition<series.editions:
        raise ValueError("invalid game evolution edition")
    base=series.base
    profile=base.portable_design
    assert profile is not None
    def turn(options,initial,enabled):
        if not enabled:
            return initial
        ordered=sorted(options)
        return ordered[(ordered.index(initial)+edition)%len(ordered)]
    changed=replace(
        profile,
        hero=turn(HEROES,profile.hero,series.rotate_heroes),
        quest_theme=turn(THEMES,profile.quest_theme,series.rotate_worlds),
        palette=turn(PALETTES,profile.palette,series.rotate_palettes),
        difficulty=(
            min(10,max(1,profile.difficulty+edition))
            if series.ramp_difficulty else profile.difficulty
        ),
        stages=min(8,profile.stages+(edition//3)),
        candidates=min(24,profile.candidates+(edition//2)),
    )
    # First edition is the approved original baseline. Subsequent episodes
    # receive derived deterministic seeds and novel game project identities.
    seed=(base.seed+edition*0x9E3779B1)&0xffffffff
    return replace(base,seed=seed,portable_design=changed)


def preview_evolution_series(series:EvolutionSeriesRequest)->dict:
    """Read-only build matrix; no gameplay source is emitted in preview."""
    series.validate()
    variants=[]
    identities=set()
    all_ready=True
    for number in range(series.editions):
        spec=variant_for(series,number)
        decisions=plan_production(spec)
        ready=all(row.state=="source_ready" for row in decisions)
        all_ready=all_ready and ready
        if spec.request_id in identities:
            raise ValueError("evolution variant identities unexpectedly collided")
        identities.add(spec.request_id)
        variants.append({
            "edition":number+1,
            "request_id":spec.request_id,
            "seed":spec.seed,
            "design":portable_design_document(spec.portable_design),
            "target_states":[{"target":row.target,"state":row.state,
                              "reason":row.reason} for row in decisions],
            "source_ready":ready,
        })
    return {
        "schema":SCHEMA,"status":"source_ready" if all_ready else "blocked",
        "edition_count":series.editions,
        "target_count":len(series.base.targets),
        "project_count":series.editions*len(series.base.targets),
        "editions":variants,
        "claim":"planned original source iterations; not trained, compiled or playtested",
    }


def _base_document(series:EvolutionSeriesRequest)->dict:
    return {
        "title":series.base.title,
        "style":series.base.style,
        "targets":list(series.base.targets),
        "seed":series.base.seed,
        "portable_design":portable_design_document(series.base.portable_design),
        "editions":series.editions,
        "rotate_heroes":series.rotate_heroes,
        "rotate_worlds":series.rotate_worlds,
        "rotate_palettes":series.rotate_palettes,
        "ramp_difficulty":series.ramp_difficulty,
        "rights":"original_homebrew_operator_attested_not_independently_cleared",
    }


def _restore_series(document:dict)->EvolutionSeriesRequest:
    if not isinstance(document,dict):
        raise ValueError("invalid signed-scope series declaration")
    exact={"title","style","targets","seed","portable_design","editions",
           "rotate_heroes","rotate_worlds","rotate_palettes","ramp_difficulty","rights"}
    if set(document)!=exact:
        raise ValueError("series identity includes missing or unknown fields")
    if document["rights"]!="original_homebrew_operator_attested_not_independently_cleared":
        raise ValueError("series attempts to elevate legal origin status")
    profile=document["portable_design"]
    if not isinstance(profile,dict) or profile.get("schema")!="skeleton.ai.dragon.portable_game_design.v1":
        raise ValueError("invalid original design in series")
    if set(profile)!={"schema"}|set(PortableGameDesign.__dataclass_fields__):
        raise ValueError("missing/unknown authored game field")
    data={key:value for key,value in profile.items() if key!="schema"}
    base=ProductionRequest(
        title=document["title"],style=document["style"],
        targets=tuple(document["targets"]),seed=document["seed"],
        portable_design=PortableGameDesign(**data),original_work_attested=True,
    )
    result=EvolutionSeriesRequest(
        base=base,editions=document["editions"],
        rotate_heroes=document["rotate_heroes"],
        rotate_worlds=document["rotate_worlds"],
        rotate_palettes=document["rotate_palettes"],
        ramp_difficulty=document["ramp_difficulty"],
    )
    result.validate()
    return result


def _root(destination:Path,*,create:bool)->Path:
    root=Path(destination).expanduser().absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("symlink in evolution series root or ancestor")
    if root.exists() and not root.is_dir():
        raise ValueError("evolution series destination is not a directory")
    if create:
        root.mkdir(parents=True,exist_ok=True)
    elif not root.is_dir():
        raise ValueError("evolution series destination does not exist")
    return root


def build_evolution_series(series:EvolutionSeriesRequest,destination:Path,*,
                           authorized:bool,dry_run:bool=False)->dict:
    """Preflight all editions then create immutable releases; index last.

    A failed mid-series build leaves explicitly incomplete edition folders.
    Repeating the same deterministic request repairs them safely; no false
    global 'published' receipt is created until every edition is audited.
    """
    if authorized is not True:
        raise PermissionError("explicit original game evolution authorization required")
    preview=preview_evolution_series(series)
    if preview["status"]!="source_ready" or dry_run:
        return preview
    root=_root(destination,create=False) if Path(destination).exists() else (
        Path(destination).expanduser().absolute())
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("symlinked original game series output")
    if root.exists() and any(p.is_symlink() for p in root.iterdir()):
        raise ValueError("unsafe existing evolution artifacts")
    # No writes until the whole source/platform matrix is admitted.
    root=_root(root,create=True)
    ledger=[]
    previous=None
    for number in range(series.editions):
        specification=variant_for(series,number)
        label="edition-"+format(number+1,"02d")
        edition_dir=root/label
        released=publish_production(specification,edition_dir,authorized=True)
        if released["status"]!="published":
            raise RuntimeError("admitted original game unexpectedly failed publication")
        audit=verify_published_production(edition_dir,released["index"])
        if audit["archives_verified"]!=len(specification.targets):
            raise ValueError("original game edition did not pass release verification")
        change_count=None
        if previous is not None:
            from .dragon_native_production import compare_verified_portfolios
            differences=compare_verified_portfolios(
                root/previous["directory"],previous["index"],
                edition_dir,released["index"])
            change_count=differences["changes"]
            if change_count==0:
                raise ValueError("evolution edition produced no game changes")
        item={
            "edition":number+1,"directory":label,
            "request_id":specification.request_id,
            "index":released["index"],"index_sha256":audit["index_sha256"],
            "archives_verified":audit["archives_verified"],
            "source_changes_from_previous":change_count,
            "previous_index_sha256":previous["index_sha256"] if previous else None,
        }
        ledger.append(item)
        previous=item
    manifest={
        "schema":SCHEMA,"base":_base_document(series),
        "edition_count":len(ledger),
        "source_project_count":len(ledger)*len(series.base.targets),
        "editions":ledger,
        "status":"original_source_releases_verified",
        "legal_claim":"original-homebrew attestation not independently legally verified",
        "verification_limit":"source differences and structural ROM checks do not certify gameplay or training",
    }
    encoded=_canonical(manifest)
    if len(encoded)>MAX_SERIES_INDEX_BYTES:
        raise ValueError("series index exceeds immutable publication budget")
    name="dragon-evolution-"+_hash(encoded)[:24]+".json"
    _atomic_new(root/name,encoded)
    return {"schema":SCHEMA,"status":"published","index":name,
            "index_sha256":_hash(encoded),"editions":len(ledger),
            "source_projects":manifest["source_project_count"],
            "evidence":"all source releases independently verified",
            "report":manifest}


def verify_evolution_series(destination:Path,index_name:str)->dict:
    root=_root(destination,create=False)
    if not re.fullmatch(r"dragon-evolution-[a-f0-9]{24}\.json",index_name):
        raise ValueError("invalid immutable evolution index name")
    path=root/index_name
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_SERIES_INDEX_BYTES:
        raise ValueError("missing or unsafe original game evolution manifest")
    raw=path.read_bytes()
    if index_name!="dragon-evolution-"+_hash(raw)[:24]+".json":
        raise ValueError("evolution manifest content address modified")
    manifest=json.loads(raw)
    if (not isinstance(manifest,dict) or manifest.get("schema")!=SCHEMA or
            manifest.get("status")!="original_source_releases_verified" or
            manifest.get("legal_claim")!=
                "original-homebrew attestation not independently legally verified"):
        raise ValueError("unrecognized game evolution evidence")
    series=_restore_series(manifest["base"])
    entries=manifest.get("editions")
    if (not isinstance(entries,list) or len(entries)!=series.editions or
            manifest.get("edition_count")!=series.editions or
            manifest.get("source_project_count")!=series.editions*len(series.base.targets)):
        raise ValueError("incorrect original series dimensions")
    seen=set()
    previous=None
    revisions=[]
    for i,entry in enumerate(entries):
        if not isinstance(entry,dict):
            raise ValueError("malformed evolution release entry")
        folder=entry.get("directory")
        if not isinstance(folder,str) or not CLEAN_SEGMENT.fullmatch(folder):
            raise ValueError("unsafe evolution release directory")
        if folder in seen or folder!="edition-"+format(i+1,"02d"):
            raise ValueError("missing or duplicate evolution source edition")
        seen.add(folder)
        index=entry.get("index")
        if not isinstance(index,str) or not INDEX_SEGMENT.fullmatch(index):
            raise ValueError("unsafe nested production receipt")
        location=root/folder
        if location.is_symlink():
            raise ValueError("symlinked original game edition")
        audit=verify_published_production(location,index)
        expected=variant_for(series,i)
        if (entry.get("edition")!=i+1 or
                audit["request_id"]!=expected.request_id or
                audit["request_id"]!=entry.get("request_id") or
                audit["index_sha256"]!=entry.get("index_sha256") or
                audit["archives_verified"]!=entry.get("archives_verified") or
                audit["archives_verified"]!=len(series.base.targets) or
                entry.get("previous_index_sha256")!=
                    (previous["index_sha256"] if previous else None)):
            raise ValueError("evolution edition failed replay or predecessor linkage")
        if previous is not None:
            earlier=json.loads((root/previous["directory"]/previous["index"]).read_text())
            latter=json.loads((location/index).read_text())
            a={x["target"]:x for x in earlier["entries"]}
            b={x["target"]:x for x in latter["entries"]}
            changes=sum(a[t]["archive_sha256"]!=b[t]["archive_sha256"] for t in a)
            if changes==0 or entry.get("source_changes_from_previous")!=changes:
                raise ValueError("evolution index falsely claims changed native games")
        else:
            if entry.get("source_changes_from_previous") is not None:
                raise ValueError("baseline edition has invented predecessor")
        revisions.append({"edition":i+1,"targets":audit["archives_verified"],
                          "index_sha256":audit["index_sha256"]})
        previous=entry
    return {
        "schema":SCHEMA,"status":"verified_original_game_evolution",
        "index_sha256":_hash(raw),
        "editions_verified":series.editions,
        "source_projects_verified":series.editions*len(series.base.targets),
        "revisions":revisions,
        "scope":"replayable original source releases only, not game quality or autonomous learning",
    }


def main(argv:list[str]|None=None)->int:
    from argparse import ArgumentParser
    parser=ArgumentParser(description="Produce or audit original homebrew series")
    sub=parser.add_subparsers(dest="command",required=True)
    for action in ("preview","build"):
        op=sub.add_parser(action)
        op.add_argument("--title",required=True)
        op.add_argument("--style",default="arcade_score_attack")
        op.add_argument("--targets",required=True)
        op.add_argument("--seed",type=int,default=1)
        op.add_argument("--editions",type=int,default=4)
        op.add_argument("--portable-design",type=Path,required=True)
        op.add_argument("--attest-original-rights",action="store_true")
        if action=="build":
            op.add_argument("--authorize-series",action="store_true")
            op.add_argument("--out",type=Path,required=True)
    audit=sub.add_parser("verify")
    audit.add_argument("--out",type=Path,required=True)
    audit.add_argument("--index",required=True)
    args=parser.parse_args(argv)
    if args.command=="verify":
        output=verify_evolution_series(args.out,args.index)
    else:
        request=ProductionRequest(
            title=args.title,style=args.style,
            targets=tuple(x.strip() for x in args.targets.split(",")),
            seed=args.seed,original_work_attested=args.attest_original_rights,
            portable_design=load_portable_design(args.portable_design),
        )
        plan=EvolutionSeriesRequest(base=request,editions=args.editions)
        output=(preview_evolution_series(plan) if args.command=="preview"
                else build_evolution_series(plan,args.out,authorized=args.authorize_series))
    print(json.dumps(output,sort_keys=True,indent=2))
    return 0 if output.get("status") not in ("blocked",) else 2

if __name__=="__main__":
    raise SystemExit(main())
