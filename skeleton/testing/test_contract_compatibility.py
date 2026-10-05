from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_machine_inventory_covers_every_runtime_schema_exactly_once():
 schemas=json.loads((ROOT/"machine/ai_runtime_schemas.json").read_text())
 conformance=json.loads((ROOT/"machine/contract_conformance.json").read_text())
 records=schemas["records"]
 assert isinstance(records,dict)
 names=set(records)
 entries=conformance["entries"]
 inventory=[e["contract"] for e in entries]
 assert len(inventory)==len(set(inventory))
 assert set(inventory)==names
 owners={name:record["owner_plane"] for name,record in records.items()}
 assert all(e["producer_plane"]==owners[e["contract"]] for e in entries)
 assert all(e["consumer_planes"] for e in entries)

def test_machine_conformance_vectors_are_unique_and_fail_closed():
 conformance=json.loads((ROOT/"machine/contract_conformance.json").read_text())
 vectors=conformance["vectors"]
 ids=[v["id"] for v in vectors]
 assert len(ids)==len(set(ids))
 assert {"JSON-DUPLICATE-KEY","JSON-NAN","JSON-INFINITY","JSON-NEG-INFINITY","JSON-UNICODE-ROUNDTRIP","SCHEMA-ABSENT-REQUIRED","SCHEMA-NULL-NONNULLABLE","SCHEMA-UNKNOWN-ENUM","SCHEMA-NULL-NULLABLE"}<=set(ids)
 assert all(v["expected"] in {"accept","reject"} for v in vectors)

def test_machine_validator_executes_complete_inventory_and_vectors():
 import importlib.util
 spec=importlib.util.spec_from_file_location("contract_conformance",ROOT/"scripts/check_architecture_contract_conformance.py")
 assert spec and spec.loader
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 result=module.validate(ROOT)
 assert result["status"]=="valid"
 assert result["contract_count"]==36
 assert result["executed_vector_count"]==result["vector_count"]
 assert result["authority_scope"]=="contract-conformance-only"
 assert len(result["qualification_digest"])==64
 assert set(result["source_digests"])=={"catalog","schema_catalog","interface_registry"}

def test_governed_canonical_conformance_surface_matches_canonical():
 from skeleton.contracts.canonical import CanonicalEnvelope,EvidenceRef,Identity,canonical_conformance_vector
 from skeleton.ai.runtime.contracts.canonical import CanonicalEnvelope as GEnvelope,EvidenceRef as GEvidenceRef,Identity as GIdentity,canonical_conformance_vector as governed
 canonical=CanonicalEnvelope(1,"compat",Identity("Apeloff1/Skeleton","a"*40),(EvidenceRef("repo","b"*64),),("b","a"),{"snow":"Ω"})
 mirrored=GEnvelope(1,"compat",GIdentity("Apeloff1/Skeleton","a"*40),(GEvidenceRef("repo","b"*64),),("b","a"),{"snow":"Ω"})
 assert governed(mirrored)==canonical_conformance_vector(canonical)
