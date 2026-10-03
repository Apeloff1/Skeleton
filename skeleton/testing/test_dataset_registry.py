import pytest
from skeleton.data.dataset_registry import *
def test_split_leakage_version_immutability_and_rights():
 r=DatasetRegistry(); r.register_dataset(Dataset("d","o")); r.register_version(dataset_id="d",version=1,source_refs=["src"],allowed_uses=["train","public_export"],pii=True,retention_until_epoch=5,contamination_tags=["benchmark"]); r.register_split(dataset_id="d",version=1,name="train",record_ids=["1","2"])
 with pytest.raises(DatasetRegistryError): r.register_split(dataset_id="d",version=1,name="eval",record_ids=["2"])
 with pytest.raises(DatasetRegistryError): r.authorize_use(dataset_id="d",version=1,use="train",current_epoch=1)
 with pytest.raises(DatasetRegistryError): r.authorize_use(dataset_id="d",version=1,use="public_export",current_epoch=1)
