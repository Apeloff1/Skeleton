from __future__ import annotations
import hashlib,pytest
from skeleton.supply_chain.model_bom import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def bom():return MBOM("MODEL.1",S("model"),(ModelComponent("COMP.BASE","base_model",S("base")),ModelComponent("COMP.TOK","tokenizer",S("tok"))),ModelLineage("RUN.TRAIN.1",S("train-evidence"),S("opaque-dataset-ref"),"RUN.POST.1",S("post-evidence")))
def test_mbom_binds_exact_model_components_and_lineage():assert len(bom().digest)==64
def test_model_artifact_change_changes_mbom_identity():
 a=bom();b=MBOM(a.model_id,S("different"),a.components,a.lineage);assert a.digest!=b.digest
def test_dataset_is_recorded_as_opaque_digest_not_payload():assert bom().lineage.dataset_ref_digest==S("opaque-dataset-ref")
def test_incomplete_post_training_lineage_rejected():
 with pytest.raises(MBOMError,match="incomplete"):ModelLineage("RUN.TRAIN.1",S("e"),S("d"),"RUN.POST.1",None)
def test_duplicate_component_identity_rejected():
 c=ModelComponent("COMP.BASE","base_model",S("base"))
 with pytest.raises(MBOMError,match="duplicate"):MBOM("MODEL.1",S("m"),(c,c),ModelLineage("RUN.TRAIN.1",S("e"),S("d")))
