#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"machine/functional_llm_game_builder_10mb_manifest.json"

def fail(msg:str)->None:
    raise SystemExit("FLGB masterplan invalid: "+msg)

def main()->int:
    data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("kind")!="functional-llm-game-builder-execution-atlas": fail("wrong kind")
    if data.get("plan_version")!="2.5.0": fail("unexpected plan version")
    shards=data.get("shards")
    if not isinstance(shards,list) or len(shards)!=18: fail("expected 18 shards")
    ids=[s.get("id") for s in shards]
    expected=[f"FLGB-{i:02d}" for i in range(1,19)]
    if ids!=expected: fail("shard IDs are incomplete or out of order")
    total=0
    for s in shards:
        p=ROOT/s["path"]
        if not p.is_file(): fail(f"missing {s['path']}")
        raw=p.read_bytes()
        total+=len(raw)
        if len(raw)<int(s.get("min_bytes",620000)): fail(f"undersized {s['path']}")
        if len(raw)!=int(s["bytes"]): fail(f"byte manifest stale for {s['path']}")
        text=raw.decode("utf-8")
        if f"# {s['id']}" not in text: fail(f"header mismatch {s['id']}")
        if "Implementation signed: false" not in text: fail(f"missing unsigned implementation marker {s['id']}")
        if "Independent verification signed: false" not in text: fail(f"missing unsigned verification marker {s['id']}")
        atoms=set(re.findall(rf"## ({re.escape(s['id'])}-\d{{5}})",text))
        if len(atoms)<250: fail(f"insufficient requirement atoms in {s['id']}: {len(atoms)}")
        for token in ("Objective","Acceptance","Failure","provenance","cancellation"):
            if token.lower() not in text.lower(): fail(f"{s['id']} missing {token} semantics")
    if total<10_000_000: fail(f"aggregate specification bytes below 10MB: {total}")
    if total!=int(data["bytes"]["shard_total"]): fail("aggregate byte total stale")
    if data["completion"].get("runtime_completion_claim") is not False: fail("runtime completion must remain fail-closed")
    if data["completion"].get("implementation_signed") is not False: fail("implementation cannot be auto-signed")
    if data["completion"].get("independent_verification_signed") is not False: fail("verification cannot be auto-signed")
    coverage=data.get("coverage",{})
    if coverage.get("required_planes")!=expected: fail("coverage planes mismatch")
    if not coverage.get("plan_surface_no_known_unmapped_primary_domain"): fail("plan coverage assertion missing")
    e2e=data.get("end_to_end_acceptance",[])
    if len(e2e)<12: fail("end-to-end spine incomplete")
    shard17=(ROOT/shards[16]["path"]).read_text(encoding="utf-8")
    for token in ("Forge-100","Forge-1000","Forge-10000","rights","clean-room"):
        if token.lower() not in shard17.lower(): fail(f"rival/rights plane missing {token}")
    shard14=(ROOT/shards[13]["path"]).read_text(encoding="utf-8")
    for token in ("longform","canon","continuity","timeline"):
        if token.lower() not in shard14.lower(): fail(f"long-form plane missing {token}")
    print(f"FLGB masterplan valid: {len(shards)} shards, {total} bytes, runtime completion remains unsigned")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
