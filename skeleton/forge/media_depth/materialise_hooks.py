"""Thin materialise hooks for media artefacts — extend-only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from skeleton.forge.lafs import Lafs
from skeleton.forge.media_depth.asset_kinds import AssetKind, decide_kind_pipeline, infer_kind
from skeleton.forge.media_depth.lafs_verify import LafsVerifier, ProvenanceChain
from skeleton.forge.media_studio import MediaStudio


@dataclass
class MediaMaterialiseHook:
    """Attach media publish + verify without rewriting VerificationLoop."""

    studio: MediaStudio
    lafs: Lafs

    def plan_for_ext(self, ext: str) -> Dict[str, Any]:
        kind = infer_kind(ext)
        pipeline = decide_kind_pipeline(kind)
        return {"kind": kind.value, "pipeline": list(pipeline)}

    def publish_bytes(self, asset: str, payload: bytes, *, name: Optional[str] = None) -> Dict[str, Any]:
        digest = self.lafs.put_chunk(payload)
        man = self.lafs.pin_manifest(name or asset, [digest])
        verifier = LafsVerifier(self.lafs)
        report = verifier.verify_manifest(man)
        chain = verifier.chain_from_manifest(asset, man)
        return {
            "asset": asset,
            "manifest": man.to_dict(),
            "verify": report,
            "provenance": chain.bundle_digest(),
        }


def hook_tag_0(asset: str) -> str:
    return f"media-hook-0-{asset}"


def hook_tag_1(asset: str) -> str:
    return f"media-hook-1-{asset}"


def hook_tag_2(asset: str) -> str:
    return f"media-hook-2-{asset}"


def hook_tag_3(asset: str) -> str:
    return f"media-hook-3-{asset}"


def hook_tag_4(asset: str) -> str:
    return f"media-hook-4-{asset}"


def hook_tag_5(asset: str) -> str:
    return f"media-hook-5-{asset}"


def hook_tag_6(asset: str) -> str:
    return f"media-hook-6-{asset}"


def hook_tag_7(asset: str) -> str:
    return f"media-hook-7-{asset}"


def hook_tag_8(asset: str) -> str:
    return f"media-hook-8-{asset}"


def hook_tag_9(asset: str) -> str:
    return f"media-hook-9-{asset}"


def hook_tag_10(asset: str) -> str:
    return f"media-hook-10-{asset}"


def hook_tag_11(asset: str) -> str:
    return f"media-hook-11-{asset}"


def hook_tag_12(asset: str) -> str:
    return f"media-hook-12-{asset}"


def hook_tag_13(asset: str) -> str:
    return f"media-hook-13-{asset}"


def hook_tag_14(asset: str) -> str:
    return f"media-hook-14-{asset}"


def hook_tag_15(asset: str) -> str:
    return f"media-hook-15-{asset}"


def hook_tag_16(asset: str) -> str:
    return f"media-hook-16-{asset}"


def hook_tag_17(asset: str) -> str:
    return f"media-hook-17-{asset}"


def hook_tag_18(asset: str) -> str:
    return f"media-hook-18-{asset}"


def hook_tag_19(asset: str) -> str:
    return f"media-hook-19-{asset}"


def hook_tag_20(asset: str) -> str:
    return f"media-hook-20-{asset}"


def hook_tag_21(asset: str) -> str:
    return f"media-hook-21-{asset}"


def hook_tag_22(asset: str) -> str:
    return f"media-hook-22-{asset}"


def hook_tag_23(asset: str) -> str:
    return f"media-hook-23-{asset}"


def hook_tag_24(asset: str) -> str:
    return f"media-hook-24-{asset}"


def hook_tag_25(asset: str) -> str:
    return f"media-hook-25-{asset}"


def hook_tag_26(asset: str) -> str:
    return f"media-hook-26-{asset}"


def hook_tag_27(asset: str) -> str:
    return f"media-hook-27-{asset}"


def hook_tag_28(asset: str) -> str:
    return f"media-hook-28-{asset}"


def hook_tag_29(asset: str) -> str:
    return f"media-hook-29-{asset}"


def hook_tag_30(asset: str) -> str:
    return f"media-hook-30-{asset}"


def hook_tag_31(asset: str) -> str:
    return f"media-hook-31-{asset}"


def hook_tag_32(asset: str) -> str:
    return f"media-hook-32-{asset}"


def hook_tag_33(asset: str) -> str:
    return f"media-hook-33-{asset}"


def hook_tag_34(asset: str) -> str:
    return f"media-hook-34-{asset}"


def hook_tag_35(asset: str) -> str:
    return f"media-hook-35-{asset}"


def hook_tag_36(asset: str) -> str:
    return f"media-hook-36-{asset}"


def hook_tag_37(asset: str) -> str:
    return f"media-hook-37-{asset}"


def hook_tag_38(asset: str) -> str:
    return f"media-hook-38-{asset}"


def hook_tag_39(asset: str) -> str:
    return f"media-hook-39-{asset}"
