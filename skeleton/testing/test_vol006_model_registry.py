from dataclasses import FrozenInstanceError
import pytest
from skeleton.modeling.registry import *

D="0"*64
def ds(**kw):
    x=dict(dataset_id="d1",content_digest=D,rights="licensed",integrity_digest="1"*64,pii_policy="redacted",dedup_digest="2"*64,contamination_digest="3"*64,sources=("src:a",),metadata={"z":[2,1]}); x.update(kw); return DatasetManifest(**x)
def run(**kw):
    x=dict(run_id="r1",dataset_digests=(ds().manifest_digest,),code_digest="4"*64,config_digest="5"*64,hardware_digest="6"*64,seed=7,status="completed"); x.update(kw); return TrainingRun(**x)
def artifact(r,**kw):
    x=dict(artifact_id="a1",content_digest="7"*64,training_run_digest=r.run_digest,evaluation_digest="8"*64,format="safetensors"); x.update(kw); return ModelArtifact(**x)

def test_end_to_end_lineage_is_deterministic_and_verifiable():
    reg=ModelDevelopmentRegistry(); d=ds(); reg.add_dataset(d); r=run(); reg.add_run(r); a=artifact(r); reg.add_artifact(a)
    l=reg.lineage(a.artifact_digest)
    assert reg.verify(a.artifact_digest,l)
    assert l.dataset_digests==(d.manifest_digest,)
    assert reg.snapshot_digest()==reg.snapshot_digest()

def test_registry_is_idempotent_but_rejects_identity_collision():
    reg=ModelDevelopmentRegistry(); d=ds(); assert reg.add_dataset(d)==reg.add_dataset(d)
    with pytest.raises(CollisionError): reg.add_dataset(ds(content_digest="9"*64))

def test_unknown_lineage_and_incomplete_runs_fail_closed():
    reg=ModelDevelopmentRegistry()
    with pytest.raises(LineageError): reg.add_run(run())
    d=ds(); reg.add_dataset(d); r=run(status="candidate"); reg.add_run(r)
    with pytest.raises(LineageError): reg.add_artifact(artifact(r))

def test_artifact_never_carries_production_authority():
    r=run()
    with pytest.raises(RegistryError): artifact(r,authority_scope="production")

def test_dataset_governance_fields_are_mandatory_and_bounded():
    with pytest.raises(RegistryError): ds(rights="unknown")
    with pytest.raises(RegistryError): ds(pii_policy="unknown")
    with pytest.raises(RegistryError): ds(sources=())
    with pytest.raises(RegistryError): ds(sources=("x","x"))

def test_digest_bearing_metadata_is_deeply_immutable():
    d=ds(metadata={"nested":{"x":[1,2]}})
    with pytest.raises(TypeError): d.metadata["nested"]["x"]=3
    with pytest.raises(FrozenInstanceError): d.dataset_id="other"

def test_noncanonical_metadata_rejected():
    with pytest.raises(RegistryError): ds(metadata={"x":float("nan")})
    with pytest.raises(RegistryError): ds(metadata={"x":object()})

def test_order_canonicalization_and_seed_type():
    d1=ds(sources=("b","a")); d2=ds(sources=("a","b"))
    assert d1.manifest_digest==d2.manifest_digest
    with pytest.raises(RegistryError): run(seed=True)

def test_parent_artifacts_must_exist():
    reg=ModelDevelopmentRegistry(); d=ds(); reg.add_dataset(d)
    with pytest.raises(LineageError): reg.add_run(run(parent_artifact_digests=("f"*64,)))

def test_tampered_lineage_does_not_verify():
    reg=ModelDevelopmentRegistry(); d=ds(); reg.add_dataset(d); r=run(); reg.add_run(r); a=artifact(r); reg.add_artifact(a)
    good=reg.lineage(a.artifact_digest)
    bad=TrainingLineage(good.artifact_digest,good.run_digest,good.dataset_digests,"9"*64,good.config_digest,good.hardware_digest,good.evaluation_digest)
    assert not reg.verify(a.artifact_digest,bad)

def test_canonical_and_ai_mirror_are_byte_identical():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert (root/"skeleton/modeling/registry.py").read_bytes()==(root/"skeleton/ai/modeling/registry.py").read_bytes()
