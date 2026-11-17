"""Restart-safe offline preparation of a reviewed multi-publisher source index.

This tool consumes already acquired, locally held metadata exports. It never
contacts a publisher, issues a crawl grant, or activates the output generation.
A campaign is byte-pinned; retries can reuse only matching reviewed receipts.
The existing normalizer and immutable index builder retain their authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from .source_catalogue_bulk import _publish_new
from .source_catalogue_index import (
    DB_NAME, IndexedCatalogue, MAX_EXPORTS, MAX_EXPORT_BYTES, MAX_SOURCES,
    TARGET, _hash_file, _hex, _json, manifest_bytes, build_index,
)
from .source_catalogue_normalize import MODES, normalize
from .source_navigation import REGISTRY_PATH, packaged_catalogue_bytes, _root

SCHEMA = "skeleton.dragon.source-import-campaign.v1"
RECEIPT_SCHEMA = "skeleton.dragon.source-import-campaign-receipt.v1"
ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
PATH_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
PLAN_FIELDS = {"schema", "minimum_sources", "base_sha256", "exports"}
EXPORT_FIELDS = {"id", "file", "sha256", "mode", "publisher", "rights_reference"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_json(path, value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")+b"\n"
    _publish_new(path, raw)


def _local_file(root, relative):
    """Constrain manifest locators to an explicitly chosen local input root."""
    if (not isinstance(relative,str) or len(relative)>512
            or "\\" in relative or relative.startswith("/")):
        raise ValueError("campaign local export path")
    parts = relative.split("/")
    if not parts or len(parts)>8 or any(not PATH_PART.fullmatch(x) for x in parts):
        raise ValueError("campaign local export path component")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("campaign input symlink")
    if not path.is_file():
        raise ValueError("campaign local export is unavailable")
    return path


def _dir(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("campaign directory is not a regular directory")
    path.mkdir(exist_ok=True)
    return path


def _plan(raw, plan_sha256):
    _hex(plan_sha256)
    if _sha(raw)!=plan_sha256:
        raise ValueError("campaign plan digest mismatch")
    plan = _json(raw)
    if (not isinstance(plan,dict) or set(plan)!=PLAN_FIELDS
            or plan["schema"]!=SCHEMA
            or type(plan["minimum_sources"]) is not int
            or not 1<=plan["minimum_sources"]<=MAX_SOURCES
            or not isinstance(plan["exports"],list)
            or not 1<=len(plan["exports"])<=MAX_EXPORTS):
        raise ValueError("campaign plan schema")
    _hex(plan["base_sha256"])
    ids=set()
    for item in plan["exports"]:
        if (not isinstance(item,dict) or set(item)!=EXPORT_FIELDS
                or not isinstance(item["id"],str) or not ID.fullmatch(item["id"])
                or item["id"] in ids or item["mode"] not in MODES):
            raise ValueError("campaign export schema or duplicate identity")
        ids.add(item["id"])
        _hex(item["sha256"])
        _root(item["publisher"])
        rights=item["rights_reference"]
        if (not isinstance(rights,str) or not rights.strip() or len(rights)>512
                or any(ord(c)<32 or ord(c)==127 for c in rights)):
            raise ValueError("campaign publisher review reference")
    return plan


def _checked_normalization(item, source, output, receipt):
    """Revalidate both inputs and outputs; report receipts are not permission."""
    if output.is_symlink() or receipt.is_symlink():
        raise ValueError("campaign normalization symlink")
    if not output.exists() and not receipt.exists():
        normalize(source,output,receipt,mode=item["mode"],publisher=item["publisher"],
                  rights_reference=item["rights_reference"],input_sha256=item["sha256"])
    if not output.is_file() or not receipt.is_file():
        raise ValueError("normalization interrupted; inspect orphan output, use new campaign work directory")
    rec=_json(manifest_bytes(receipt))
    expected={"schema":"skeleton.dragon.source-normalization.v1","mode":item["mode"],
              "publisher":item["publisher"],"rights_reference":item["rights_reference"],
              "input_sha256":item["sha256"],"unique_source_count_claimed":False,
              "network_authorized":False,"rights_verified":False,"access_verified":False}
    if not isinstance(rec,dict) or any(rec.get(k)!=v for k,v in expected.items()):
        raise ValueError("normalization receipt binding mismatch")
    if any(rec[k] is not False for k in ("unique_source_count_claimed",
                   "network_authorized","rights_verified","access_verified")):
        raise ValueError("normalization receipt authority mismatch")
    digest,sig=_hash_file(output,MAX_EXPORT_BYTES)
    src_digest,_=_hash_file(source,MAX_EXPORT_BYTES)
    export={"path":str(output.resolve()),"sha256":digest,
            "publisher":item["publisher"],"rights_reference":item["rights_reference"]}
    if (src_digest!=item["sha256"] or rec.get("output_sha256")!=digest
            or rec.get("output_bytes")!=sig[2] or rec.get("index_export")!=export):
        raise ValueError("normalization bytes or export receipt changed")
    counts=rec.get("counts")
    if (not isinstance(counts,dict) or type(counts.get("written")) is not int
            or not 1<=counts["written"]<=MAX_SOURCES):
        raise ValueError("normalization receipt count")
    return export,{"id":item["id"],"input_sha256":src_digest,
                   "normalized_sha256":digest,"candidate_rows":counts["written"]}


def run_campaign(plan_path, *, plan_sha256, input_root, work_dir, base_path=REGISTRY_PATH):
    """Normalize many reviewed exports, then publish one verified generation.

    Existing completed outputs may be reopened. Partial generation publication
    is held rather than repaired destructively. Use an operator-controlled,
    non-concurrently-written directory; no automatic deployment or mutation of
    the packaged catalogue or a previously active generation.
    """
    plan_path=Path(plan_path)
    raw=manifest_bytes(plan_path)
    plan=_plan(raw,plan_sha256)
    base_path=Path(base_path)
    if _sha(packaged_catalogue_bytes(base_path))!=plan["base_sha256"]:
        raise ValueError("campaign packaged catalogue digest mismatch")
    input_root=Path(input_root).resolve(strict=True)
    if not input_root.is_dir():
        raise ValueError("campaign input root must be a directory")
    work_dir=Path(work_dir)
    _dir(work_dir)
    work_dir=work_dir.resolve(strict=True)
    # Keep operator inputs and immutable output generations in disjoint trees.
    if work_dir==input_root or input_root in work_dir.parents or work_dir in input_root.parents:
        raise ValueError("campaign input and output trees must be disjoint")
    if work_dir in plan_path.resolve().parents or work_dir in base_path.resolve().parents:
        raise ValueError("campaign configuration cannot be inside output tree")
    pin_path=work_dir/"campaign-plan.json"
    if pin_path.is_symlink():
        raise ValueError("campaign plan output symlink")
    if pin_path.exists():
        if manifest_bytes(pin_path)!=raw:
            raise ValueError("campaign directory is pinned to a different plan")
    else:
        _publish_new(pin_path,raw)
    prepared=_dir(work_dir/"normalized")
    exports=[]
    rows=[]
    for item in plan["exports"]:
        local=_local_file(input_root,item["file"])
        output=prepared/(item["id"]+".jsonl")
        receipt=prepared/(item["id"]+".receipt.json")
        export,note=_checked_normalization(item,local,output,receipt)
        exports.append(export)
        rows.append(note)
    if manifest_bytes(plan_path)!=raw:
        raise ValueError("campaign plan changed during preparation")
    generation=_dir(work_dir/"index")
    manifest=generation/"dragon_source_catalogue.index.json"
    db=generation/DB_NAME
    receipt_path=work_dir/"campaign-receipt.json"
    if any(p.is_symlink() for p in (manifest,db,receipt_path)):
        raise ValueError("campaign generation output symlink")
    if not manifest.exists() and not db.exists() and not receipt_path.exists():
        build_index(base_path,exports,generation,base_sha256=plan["base_sha256"],
                    minimum=plan["minimum_sources"])
    if not manifest.is_file() or not db.is_file():
        raise ValueError("generation publication incomplete; review orphan, use new work directory")
    registry=IndexedCatalogue(manifest,base_path=base_path)
    index_manifest=_json(manifest_bytes(manifest))
    declared=index_manifest.get("exports")
    if (not isinstance(declared,list) or len(declared)!=len(exports)
            or any(any(actual.get(k)!=expected[k] for k in ("publisher","rights_reference","sha256"))
                   for actual,expected in zip(declared,exports))):
        raise ValueError("campaign generation does not match reviewed exports")
    if registry.count<plan["minimum_sources"]:
        raise ValueError("campaign minimum populated source count not reached")
    result={"schema":RECEIPT_SCHEMA,"campaign_sha256":plan_sha256,
            "base_sha256":plan["base_sha256"],"generation_sha256":registry.digest,
            "index_file_sha256":index_manifest["file_sha256"],
            "sources":registry.count,"hosts":registry.summary()["hosts"],
            "minimum_sources":plan["minimum_sources"],"target_389400_reached":registry.count>=TARGET,
            "normalized_exports":rows,"conflicts_held":index_manifest["conflicts_held"],
            "candidate_metadata_only":True,"network_authorized":False,
            "rights_verified":False,"access_verified":False,"generation_activated":False}
    if receipt_path.exists():
        if _json(manifest_bytes(receipt_path))!=result:
            raise ValueError("campaign completion receipt mismatch")
    else:
        _write_json(receipt_path,result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--plan-sha256",required=True)
    parser.add_argument("--input-root",type=Path,required=True)
    parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--base",type=Path,default=REGISTRY_PATH)
    args=parser.parse_args(argv)
    print(json.dumps(run_campaign(args.plan,plan_sha256=args.plan_sha256,
                        input_root=args.input_root,work_dir=args.work_dir,
                        base_path=args.base),sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
