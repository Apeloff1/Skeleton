"""Independent, streaming local verification of emitted studio sandbox files."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any

from .studio_ecosystem_journal import HEX, _private_directory
from .studio_ecosystem_offline_bundle import _canonical
from .studio_ecosystem_quest import StudioQuestError

FILES = {
    "index.html": "index_html_sha256",
    "environment.svg": "environment_svg_sha256",
    "soundscape.wav": "soundscape_wav_sha256",
    "studio.html": "studio_html_sha256",
}
KEYS = {"schema","project_id","source_chain_sha256","index_html_sha256",
        "environment_svg_sha256","soundscape_wav_sha256","studio_html_sha256",
        "cue_id","grid_winning_replay_verified","target_genre_implemented",
        "rights_independently_qualified","release_certified"}


def _read_receipt(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:
        raise StudioQuestError("missing or oversized offline manifest")
    raw=path.read_bytes()
    def unique(pairs: list[tuple[str,object]]) -> dict[str,object]:
        found: dict[str,object]={}
        for key,value in pairs:
            if key in found:
                raise StudioQuestError("duplicate offline manifest key")
            found[key]=value
        return found
    try:
        data=json.loads(raw.decode("ascii"),object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            StudioQuestError("invalid manifest number")))
    except (UnicodeError,ValueError) as exc:
        raise StudioQuestError("malformed offline manifest") from exc
    if (not isinstance(data,dict) or set(data)!=KEYS or
            data["schema"]!="skeleton.game_builder.studio_offline_package.v1" or
            data["target_genre_implemented"] is not False or
            data["rights_independently_qualified"] is not False or
            data["release_certified"] is not False or
            data["grid_winning_replay_verified"] is not True or
            not isinstance(data["cue_id"],str) or
            not isinstance(data["project_id"],str) or
            not isinstance(data["source_chain_sha256"],str) or
            not HEX.fullmatch(data["source_chain_sha256"]) or
            raw!=_canonical(data)):
        raise StudioQuestError("invalid or noncanonical offline release receipt")
    if any(not isinstance(data[k],str) or not HEX.fullmatch(data[k])
           for k in FILES.values()):
        raise StudioQuestError("malformed bundled content identity")
    return data


def _hash_file(path: Path) -> tuple[str,int]:
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
    digest=sha256()
    total=0
    with os.fdopen(os.open(path,flags),"rb") as source:
        before=os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or
                (os.name=="posix" and before.st_mode & 0o077)):
            raise StudioQuestError("untrusted bundled file")
        while data:=source.read(1024*1024):
            digest.update(data)
            total+=len(data)
        after=os.fstat(source.fileno())
        if (before.st_dev!=after.st_dev or before.st_ino!=after.st_ino or
                before.st_size!=after.st_size or
                before.st_mtime_ns!=after.st_mtime_ns):
            raise StudioQuestError("bundle file changed during verification")
    return digest.hexdigest(),total


def verify_studio_bundle(path: Path, *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("offline bundle verification requires authorization")
    path=Path(path)
    _private_directory(path)
    found={entry.name for entry in path.iterdir()}
    if found!=set(FILES)|{"manifest.json"}:
        raise StudioQuestError("incomplete or altered offline bundle inventory")
    receipt=_read_receipt(path/"manifest.json")
    if path.name!=receipt["project_id"]:
        raise StudioQuestError("offline bundle directory identity mismatch")
    sizes={}
    for name,key in FILES.items():
        observed,count=_hash_file(path/name)
        if observed!=receipt[key]:
            raise StudioQuestError("offline bundle media digest mismatch")
        sizes[name]=count
    return {"schema":"skeleton.game_builder.studio_offline_verify.v1",
            "project_id":receipt["project_id"],
            "source_chain_sha256":receipt["source_chain_sha256"],
            "files_verified":len(FILES)+1,
            "verified_file_bytes":sizes,
            "local_bundle_integrity_verified":True,
            "independent_rights_verified":False,
            "native_gameplay_qualified":False,
            "consumer_release_certified":False}
