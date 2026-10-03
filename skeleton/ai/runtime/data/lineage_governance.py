"""Governed lineage policy with immutable transform identities."""
from __future__ import annotations

from dataclasses import dataclass


LEVEL = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


class LineageGovernanceError(ValueError):
    pass


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


@dataclass(frozen=True, slots=True)
class LineageAsset:
    asset_id: str
    classification: str
    trust: str
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class TransformationReceipt:
    transformation_id: str
    version: str
    environment_digest: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    classification: str
    trust: str


class GovernedLineage:
    def __init__(self) -> None:
        self._assets: dict[str, LineageAsset] = {}
        self._receipts: list[TransformationReceipt] = []
        self._transforms: dict[str, TransformationReceipt] = {}

    def register(self, asset: LineageAsset) -> None:
        if not isinstance(asset.asset_id, str) or not asset.asset_id:
            raise LineageGovernanceError("invalid asset identity")
        if asset.classification not in LEVEL:
            raise LineageGovernanceError("invalid classification")
        if asset.trust not in {"trusted", "untrusted"}:
            raise LineageGovernanceError("invalid trust")
        if not isinstance(asset.deleted, bool):
            raise LineageGovernanceError("deleted must be boolean")
        old = self._assets.get(asset.asset_id)
        if old is not None and old != asset:
            raise LineageGovernanceError("asset identity cannot be rebound")
        self._assets[asset.asset_id] = asset

    def transform(
        self,
        *,
        transformation_id: str,
        version: str,
        environment_digest: str,
        inputs,
        outputs,
        classification: str,
        trust: str,
    ) -> TransformationReceipt:
        if isinstance(inputs, (str, bytes)) or isinstance(outputs, (str, bytes)):
            raise LineageGovernanceError("inputs/outputs must be identity collections")
        ins = tuple(inputs)
        outs = tuple(outputs)
        if (
            not isinstance(transformation_id, str)
            or not transformation_id
            or not isinstance(version, str)
            or not version
            or not _is_digest(environment_digest)
            or not ins
            or not outs
            or any(not isinstance(item, str) or not item for item in (*ins, *outs))
            or len(set(ins)) != len(ins)
            or len(set(outs)) != len(outs)
            or set(ins) & set(outs)
        ):
            raise LineageGovernanceError("invalid transform")
        if classification not in LEVEL:
            raise LineageGovernanceError("invalid classification")
        if trust not in {"trusted", "untrusted"}:
            raise LineageGovernanceError("invalid trust")

        candidate = TransformationReceipt(
            transformation_id,
            version,
            environment_digest,
            ins,
            outs,
            classification,
            trust,
        )
        old = self._transforms.get(transformation_id)
        if old is not None:
            if old != candidate:
                raise LineageGovernanceError("transformation identity cannot be rebound")
            return old

        source_assets = []
        for asset_id in ins:
            asset = self._assets.get(asset_id)
            if asset is None or asset.deleted:
                raise LineageGovernanceError("input unavailable")
            source_assets.append(asset)

        inherited = max(
            source_assets,
            key=lambda asset: LEVEL[asset.classification],
        ).classification
        if LEVEL[classification] < LEVEL[inherited]:
            raise LineageGovernanceError("classification laundering is forbidden")
        if any(asset.trust == "untrusted" for asset in source_assets) and trust == "trusted":
            raise LineageGovernanceError("trust upgrade is forbidden")
        if any(output in self._assets for output in outs):
            raise LineageGovernanceError("output exists")

        for output in outs:
            self._assets[output] = LineageAsset(
                output,
                classification,
                trust,
                False,
            )
        self._receipts.append(candidate)
        self._transforms[transformation_id] = candidate
        return candidate

    def downstream(self, asset_id: str) -> tuple[str, ...]:
        seen: set[str] = set()
        queue = [asset_id]
        while queue:
            current = queue.pop()
            for receipt in self._receipts:
                if current in receipt.inputs:
                    for output in receipt.outputs:
                        if output not in seen:
                            seen.add(output)
                            queue.append(output)
        return tuple(sorted(seen))

    def mark_deleted(self, asset_id: str) -> tuple[str, ...]:
        if asset_id not in self._assets:
            raise KeyError(asset_id)
        affected = (asset_id, *self.downstream(asset_id))
        for identity in affected:
            asset = self._assets[identity]
            self._assets[identity] = LineageAsset(
                asset.asset_id,
                asset.classification,
                asset.trust,
                True,
            )
        return affected

    def asset(self, asset_id: str) -> LineageAsset:
        return self._assets[asset_id]
