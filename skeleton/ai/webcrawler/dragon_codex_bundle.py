"""Deterministic original game-world source bundles for every catalog target.

Package actual engine-bounded world chunks, original per-platform 8x8 tiles,
story/route grammar and, for desktop family, compilable C99 game source.
Every ZIP member is content-addressed and allowlisted. Packaging needs an
explicit author rights attestation; it never grants ROM SDK licenses, hardware
test reports or global originality clearance.

This is an auditable SOURCE PRODUCT, not a fake console ROM.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json
import re

from .dragon_world_codex import CodexAddress,validate
from .dragon_codex_platforms import content_pack
from .dragon_codex_tiles import tile_pack
from .dragon_codex_desktop import emit_codex_c99
from .dragon_world_story_grammar import bible
from .dragon_native_targets import CATALOG

SCHEMA="skeleton.ai.dragon.original_codex_source_bundle.v1"
MAX_ZIP=2_000_000
MAX_MEMBERS=10
DESKTOP=frozenset(("pc_linux","pc_windows","pc_macos","steam_deck"))
SAFE_MEMBER=re.compile(r"[A-Za-z0-9_./-]{1,95}\Z")
SOURCE_NOTE=(
    "Dragon original world Codex source bundle.\n"
    "All game maps, rules, sprites and text in this package are generated "
    "from the attested original source design.\n"
    "This package does not contain proprietary ROM/BIOS/SDK keys, "
    "third-party game assets or executable binaries.\n"
    "The source manifest is not independent publication IP clearance.\n"
    "For desktop C99: cc -std=c99 src/dragon_codex_game.c -o dragon_codex ; "
    "./dragon_codex --selftest\n"
    "Non-desktop targets receive original content and tile data only: "
    "a true platform runtime and independent compiler/hardware work remain.\n"
)

@dataclass(frozen=True)
class CodexSourceBundle:
    schema:str
    target:str
    original_world_digest:str
    sha256:str
    compressed_bytes:int
    source_members:tuple[str,...]
    rights_attested:bool
    game_binary_included:bool
    native_project_compilation_verified:bool
    source_content_verified:bool
    claim:str
    zip_bytes:bytes


def _json(obj:object)->bytes:
    return (json.dumps(obj,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)+"\n").encode()


def _sha(data:bytes)->str:
    return sha256(data).hexdigest()


def _members(source:CodexAddress,target:str,chunks:int)->dict[str,bytes]:
    validate(source)
    if type(target) is not str or target not in CATALOG:
        raise ValueError("source game target is not in the native platform catalog")
    if type(chunks) is not int or not 1<=chunks<=4:
        raise ValueError("world game source bundle must contain 1..4 playable chunks")
    content=content_pack(source,target,chunks=chunks)
    art=tile_pack(source,target)
    narrative=bible(source)
    files={
        "README.txt":SOURCE_NOTE.encode(),
        "world/original-world.json":_json(content),
        "world/world-source.json":_json({
            "source":source.decimal_index,
            "digest":source.codex_digest,
            "rights":True,"world_source_schema":source.schema,
            "target":target,"game_binary_claim":False,
        }),
        "art/original-tiles.json":_json({
            "schema":art.schema,"target":target,
            "encoding":art.native_layout,"palette":art.palette,
            "named_tiles":art.named_tiles,
            "tile_hex":art.tile_hex,"artwork_hashes":art.artwork_hashes,
            "geometry":art.tile_pixels,
            "native_binary_claim":False,
        }),
        "art/original-tiles.bin":b"".join(
            bytes.fromhex(data) for data in art.tile_hex
        ),
        "story/original-narrative-rules.json":_json(asdict(narrative)),
    }
    if target in DESKTOP:
        code=emit_codex_c99(source)
        files["src/dragon_codex_game.c"]=code.source.encode("utf-8")
    return files


def _make_archive(files:dict[str,bytes])->bytes:
    if len(files)>MAX_MEMBERS or len(set(files))!=len(files):
        raise ValueError("source game archive has too many or ambiguous members")
    stream=BytesIO()
    with ZipFile(stream,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(files):
            if (not SAFE_MEMBER.fullmatch(path) or path.startswith("/")
                or ".." in path.split("/") or
                not isinstance(files[path],bytes) or
                len(files[path])>MAX_ZIP):
                raise ValueError("unsafe original game ZIP source entry")
            info=ZipInfo(path,date_time=(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.create_system=3
            info.external_attr=0o100644<<16
            z.writestr(info,files[path],compress_type=ZIP_DEFLATED,
                       compresslevel=9)
    data=stream.getvalue()
    if not 0<len(data)<=MAX_ZIP:
        raise ValueError("original game source archive exceeded bounded response")
    return data


def publish_codex_source(source:CodexAddress,target:str,
                         *,chunks:int=1,rights_attested:bool=False,
                         )->CodexSourceBundle:
    if rights_attested is not True:
        raise PermissionError("original world source author rights attestation required")
    files=_members(source,target,chunks)
    manifest={
        "schema":SCHEMA,
        "original_world_digest":source.codex_digest,
        "world_decimal_address":source.decimal_index,
        "target":target,"rights_attested":True,
        "game_binary_included":False,
        "actual_native_compilation_verified":False,
        "hardware_test_verified":False,
        "source_members":{
            path:{"sha256":_sha(blob),"bytes":len(blob)}
            for path,blob in sorted(files.items())
        },
        "content_count":len(files),
        "scope":"source-generated original homebrew content; no third-party "
                "SDK, binary, storefront or publication clearance",
    }
    files["RELEASE_MANIFEST.json"]=_json(manifest)
    blob=_make_archive(files)
    return CodexSourceBundle(
        schema=SCHEMA,target=target,
        original_world_digest=source.codex_digest,
        sha256=_sha(blob),compressed_bytes=len(blob),
        source_members=tuple(sorted(files)),
        rights_attested=True,game_binary_included=False,
        native_project_compilation_verified=False,
        source_content_verified=True,
        claim="deterministic original source+art bundle with manifest, "
              "not precompiled executable or universal legal approval",
        zip_bytes=blob,
    )


def verify_codex_source(source:CodexAddress,
                        archive:CodexSourceBundle, *,
                        chunks:int=1)->dict:
    if not isinstance(archive,CodexSourceBundle) or archive.schema!=SCHEMA:
        raise ValueError("unrecognized original game source release")
    expected=publish_codex_source(
        source,archive.target,chunks=chunks,rights_attested=True,
    )
    if expected!=archive:
        raise ValueError("original world release source, rights or ZIP contents changed")
    with ZipFile(BytesIO(archive.zip_bytes),"r") as z:
        listed=z.infolist()
        names=[item.filename for item in listed]
        if sorted(names)!=list(archive.source_members):
            raise ValueError("original game ZIP contains unexpected paths")
        if any(item.is_dir() or (item.external_attr>>16)&0o170000!=0o100000
               for item in listed):
            raise ValueError("source ZIP contains a symlink or untrusted entry")
        manifest=json.loads(z.read("RELEASE_MANIFEST.json"))
        if (manifest["original_world_digest"]!=source.codex_digest or
                manifest["actual_native_compilation_verified"] or
                manifest["game_binary_included"]):
            raise ValueError("source bundle claims a binary or different design")
        for path,info in manifest["source_members"].items():
            data=z.read(path)
            if _sha(data)!=info["sha256"] or len(data)!=info["bytes"]:
                raise ValueError("source entry fails independent hash custody")
    return {
        "schema":SCHEMA,"verified":True,
        "sha256":archive.sha256,
        "target":archive.target,"files":len(archive.source_members),
        "size":archive.compressed_bytes,
        "game_binary_present":False,
        "original_rights_attested":True,
    }
