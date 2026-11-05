"""Deterministic source-controlled trust-gate inventory with byte-bound custody.

Reads code checkout under the installed package only. This is not a secure
loader for untrusted files or an independent Git signature/provenance check.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from .contracts import fail,load_json
from .engine import domains
from .fixtures import run_all

_CASES=("00_baseline","01_valid_variant","02_missing_field",
        "03_extra_field","04_wrong_primary_type","05_null_primary",
        "06_oversized_primary","07_wrong_last_type","08_surrogate_unicode",
        "09_cross_field_a","10_cross_field_b","11_cross_field_c")

def inventory():
    base=Path(__file__).parent
    hasher=hashlib.sha256()
    seen=set()
    total=0
    for name in domains():
        candidates=[base/"schemas"/(name+".json"),base/"semantics"/(name+".py")]
        candidates.extend(base/"fixtures"/name/(case+".json") for case in _CASES)
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                fail("trust gate source file missing or a symlink")
            rel=path.relative_to(base).as_posix()
            if rel in seen: fail("duplicate trust gate inventory path")
            seen.add(rel)
            raw=path.read_bytes()
            if not 1<=len(raw)<=131072:
                fail("trust gate source byte bound exceeded")
            if rel.endswith(".json"):
                obj=load_json(raw,ceiling=131072)
                if rel.startswith("schemas/"):
                    if type(obj) is not dict or set(obj)!={"type","fields"}:
                        fail("unrecognized schema inventory")
                else:
                    if (type(obj) is not dict or obj.get("gate")!=name
                        or obj.get("case") not in _CASES):
                        fail("fixture filename and authority mismatch")
                    total+=1
            hasher.update(len(rel.encode()).to_bytes(4,"big"))
            hasher.update(rel.encode("utf-8"))
            hasher.update(len(raw).to_bytes(8,"big"))
            hasher.update(raw)
    if total!=240 or len(seen)!=280:
        fail("incomplete source-controlled trust matrix")
    return {"schema":"ai-trust-inventory.v1","gates":20,
            "source_files":len(seen),"fixture_cases":total,
            "source_digest":hasher.hexdigest(),
            "status":"source-tree-structurally-complete"}

def qualification_snapshot(*,execute_fixtures=False):
    source=inventory()
    if execute_fixtures is True:
        outcomes=run_all()
        source["fixtures_executed"]=sum(x["total"] for x in outcomes)
        source["expected_denials_observed"]=sum(x["rejected"] for x in outcomes)
        source["status"]="source-fixtures-verified"
    elif execute_fixtures is not False:
        fail("explicit boolean fixture choice required")
    return source
