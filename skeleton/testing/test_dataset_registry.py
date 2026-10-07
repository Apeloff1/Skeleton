import pytest

from skeleton.data.dataset_registry import (
    Dataset,
    DatasetRegistry,
    DatasetRegistryError,
)


def _registry() -> DatasetRegistry:
    registry = DatasetRegistry()
    registry.register_dataset(Dataset("dataset", "owner"))
    return registry


def test_split_leakage_version_immutability_and_rights() -> None:
    registry = _registry()
    registry.register_version(
        dataset_id="dataset",
        version=1,
        source_refs=["source"],
        allowed_uses=["train", "public_export"],
        pii=True,
        retention_until_epoch=5,
        contamination_tags=["benchmark"],
    )
    registry.register_split(
        dataset_id="dataset",
        version=1,
        name="train",
        record_ids=["1", "2"],
    )
    with pytest.raises(DatasetRegistryError, match="split leakage"):
        registry.register_split(
            dataset_id="dataset",
            version=1,
            name="eval",
            record_ids=["2"],
        )
    with pytest.raises(DatasetRegistryError, match="benchmark contamination"):
        registry.authorize_use(
            dataset_id="dataset",
            version=1,
            use="train",
            current_epoch=1,
        )
    with pytest.raises(DatasetRegistryError, match="PII export"):
        registry.authorize_use(
            dataset_id="dataset",
            version=1,
            use="public_export",
            current_epoch=1,
        )


def test_malformed_governance_metadata_fails_closed() -> None:
    registry = _registry()
    with pytest.raises(DatasetRegistryError):
        registry.register_version(
            dataset_id="dataset",
            version=True,
            source_refs=["source"],
            allowed_uses=["train"],
            pii=False,
            retention_until_epoch=None,
        )
    with pytest.raises(DatasetRegistryError):
        registry.register_version(
            dataset_id="dataset",
            version=1,
            source_refs="source",
            allowed_uses=["train"],
            pii=False,
            retention_until_epoch=None,
        )
    with pytest.raises(DatasetRegistryError):
        registry.register_version(
            dataset_id="dataset",
            version=1,
            source_refs=["source"],
            allowed_uses=["train"],
            pii=False,
            retention_until_epoch=-1,
        )


def test_empty_split_is_rejected() -> None:
    registry = _registry()
    registry.register_version(
        dataset_id="dataset",
        version=1,
        source_refs=["source"],
        allowed_uses=["train"],
        pii=False,
        retention_until_epoch=None,
    )
    with pytest.raises(DatasetRegistryError, match="record ids required"):
        registry.register_split(
            dataset_id="dataset",
            version=1,
            name="train",
            record_ids=[],
        )
