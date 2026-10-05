from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_machine_inventory_covers_every_runtime_schema_exactly_once():
 schemas=json.loads((ROOT/"machine/ai_runtime_schemas.json").read_text())
 conformance=json.loads((ROOT/"machine/contract_conformance.json").read_text())
 records=schemas["records"]
 names=[r["name"] for r in records]
 entries=conformance["entries"]
 inventory=[e["contract"] for e in entries]
 assert len(inventory)==len(set(inventory))
 assert set(inventory)==set(names)
 owners={r["name"]:r["owner_plane"] for r in records}
 assert all(e["producer_plane"]==owners[e["contract"]] for e in entries)
 assert all(e["consumer_planes"] for e in entries)

def test_machine_conformance_vectors_are_unique_and_fail_closed():
 conformance=json.loads((ROOT/"machine/contract_conformance.json").read_text())
 vectors=conformance["vectors"]
 ids=[v["id"] for v in vectors]
 assert len(ids)==len(set(ids))
 assert {"JSON-DUPLICATE-KEY","JSON-NAN","JSON-INFINITY","JSON-NEG-INFINITY","JSON-UNICODE-ROUNDTRIP","SCHEMA-ABSENT-REQUIRED","SCHEMA-NULL-NONNULLABLE","SCHEMA-UNKNOWN-ENUM","SCHEMA-NULL-NULLABLE"}<=set(ids)
 assert all(v["expected"] in {"accept","reject"} for v in vectors)
