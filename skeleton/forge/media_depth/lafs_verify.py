"""LAFS provenance verify + chain helpers (deepen)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from skeleton.forge.lafs import Lafs, LafsError, Manifest


@dataclass
class ProvenanceChain:
    """Ordered digest chain for a published asset."""

    asset: str
    digests: List[str] = field(default_factory=list)
    manifest_id: Optional[str] = None

    def append(self, digest: str) -> None:
        if len(digest) != 64:
            raise ValueError("digest")
        self.digests.append(digest)

    def tip(self) -> Optional[str]:
        return self.digests[-1] if self.digests else None

    def bundle_digest(self) -> str:
        return hashlib.sha256("".join(self.digests).encode()).hexdigest()


class LafsVerifier:
    """Verify chunks against LAFS store; rebuild from manifest."""

    def __init__(self, lafs: Lafs) -> None:
        self.lafs = lafs

    def verify_manifest(self, manifest: Manifest) -> Dict[str, Any]:
        missing: List[str] = []
        corrupt: List[str] = []
        total = 0
        for d in manifest.chunks:
            try:
                chunk = self.lafs.get_chunk(d)
            except Exception:
                missing.append(d)
                continue
            if hashlib.sha256(chunk.bytes).hexdigest() != d:
                corrupt.append(d)
            else:
                total += len(chunk.bytes)
        ok = not missing and not corrupt and total == manifest.total_bytes
        return {
            "ok": ok,
            "missing": missing,
            "corrupt": corrupt,
            "bytes": total,
            "expected_bytes": manifest.total_bytes,
        }

    def chain_from_manifest(self, asset: str, manifest: Manifest) -> ProvenanceChain:
        chain = ProvenanceChain(asset=asset, digests=list(manifest.chunks), manifest_id=manifest.id)
        return chain


def pin_label_0(name: str) -> str:
    return hashlib.sha256(f"pin-0-{name}".encode()).hexdigest()[:24]


def chunk_pad_0(data: bytes) -> str:
    return hashlib.sha256(data + bytes([0])).hexdigest()


def pin_label_1(name: str) -> str:
    return hashlib.sha256(f"pin-1-{name}".encode()).hexdigest()[:24]


def chunk_pad_1(data: bytes) -> str:
    return hashlib.sha256(data + bytes([1])).hexdigest()


def pin_label_2(name: str) -> str:
    return hashlib.sha256(f"pin-2-{name}".encode()).hexdigest()[:24]


def chunk_pad_2(data: bytes) -> str:
    return hashlib.sha256(data + bytes([2])).hexdigest()


def pin_label_3(name: str) -> str:
    return hashlib.sha256(f"pin-3-{name}".encode()).hexdigest()[:24]


def chunk_pad_3(data: bytes) -> str:
    return hashlib.sha256(data + bytes([3])).hexdigest()


def pin_label_4(name: str) -> str:
    return hashlib.sha256(f"pin-4-{name}".encode()).hexdigest()[:24]


def chunk_pad_4(data: bytes) -> str:
    return hashlib.sha256(data + bytes([4])).hexdigest()


def pin_label_5(name: str) -> str:
    return hashlib.sha256(f"pin-5-{name}".encode()).hexdigest()[:24]


def chunk_pad_5(data: bytes) -> str:
    return hashlib.sha256(data + bytes([5])).hexdigest()


def pin_label_6(name: str) -> str:
    return hashlib.sha256(f"pin-6-{name}".encode()).hexdigest()[:24]


def chunk_pad_6(data: bytes) -> str:
    return hashlib.sha256(data + bytes([6])).hexdigest()


def pin_label_7(name: str) -> str:
    return hashlib.sha256(f"pin-7-{name}".encode()).hexdigest()[:24]


def chunk_pad_7(data: bytes) -> str:
    return hashlib.sha256(data + bytes([7])).hexdigest()


def pin_label_8(name: str) -> str:
    return hashlib.sha256(f"pin-8-{name}".encode()).hexdigest()[:24]


def chunk_pad_8(data: bytes) -> str:
    return hashlib.sha256(data + bytes([8])).hexdigest()


def pin_label_9(name: str) -> str:
    return hashlib.sha256(f"pin-9-{name}".encode()).hexdigest()[:24]


def chunk_pad_9(data: bytes) -> str:
    return hashlib.sha256(data + bytes([9])).hexdigest()


def pin_label_10(name: str) -> str:
    return hashlib.sha256(f"pin-10-{name}".encode()).hexdigest()[:24]


def chunk_pad_10(data: bytes) -> str:
    return hashlib.sha256(data + bytes([10])).hexdigest()


def pin_label_11(name: str) -> str:
    return hashlib.sha256(f"pin-11-{name}".encode()).hexdigest()[:24]


def chunk_pad_11(data: bytes) -> str:
    return hashlib.sha256(data + bytes([11])).hexdigest()


def pin_label_12(name: str) -> str:
    return hashlib.sha256(f"pin-12-{name}".encode()).hexdigest()[:24]


def chunk_pad_12(data: bytes) -> str:
    return hashlib.sha256(data + bytes([12])).hexdigest()


def pin_label_13(name: str) -> str:
    return hashlib.sha256(f"pin-13-{name}".encode()).hexdigest()[:24]


def chunk_pad_13(data: bytes) -> str:
    return hashlib.sha256(data + bytes([13])).hexdigest()


def pin_label_14(name: str) -> str:
    return hashlib.sha256(f"pin-14-{name}".encode()).hexdigest()[:24]


def chunk_pad_14(data: bytes) -> str:
    return hashlib.sha256(data + bytes([14])).hexdigest()


def pin_label_15(name: str) -> str:
    return hashlib.sha256(f"pin-15-{name}".encode()).hexdigest()[:24]


def chunk_pad_15(data: bytes) -> str:
    return hashlib.sha256(data + bytes([15])).hexdigest()


def pin_label_16(name: str) -> str:
    return hashlib.sha256(f"pin-16-{name}".encode()).hexdigest()[:24]


def chunk_pad_16(data: bytes) -> str:
    return hashlib.sha256(data + bytes([16])).hexdigest()


def pin_label_17(name: str) -> str:
    return hashlib.sha256(f"pin-17-{name}".encode()).hexdigest()[:24]


def chunk_pad_17(data: bytes) -> str:
    return hashlib.sha256(data + bytes([17])).hexdigest()


def pin_label_18(name: str) -> str:
    return hashlib.sha256(f"pin-18-{name}".encode()).hexdigest()[:24]


def chunk_pad_18(data: bytes) -> str:
    return hashlib.sha256(data + bytes([18])).hexdigest()


def pin_label_19(name: str) -> str:
    return hashlib.sha256(f"pin-19-{name}".encode()).hexdigest()[:24]


def chunk_pad_19(data: bytes) -> str:
    return hashlib.sha256(data + bytes([19])).hexdigest()


def pin_label_20(name: str) -> str:
    return hashlib.sha256(f"pin-20-{name}".encode()).hexdigest()[:24]


def chunk_pad_20(data: bytes) -> str:
    return hashlib.sha256(data + bytes([20])).hexdigest()


def pin_label_21(name: str) -> str:
    return hashlib.sha256(f"pin-21-{name}".encode()).hexdigest()[:24]


def chunk_pad_21(data: bytes) -> str:
    return hashlib.sha256(data + bytes([21])).hexdigest()


def pin_label_22(name: str) -> str:
    return hashlib.sha256(f"pin-22-{name}".encode()).hexdigest()[:24]


def chunk_pad_22(data: bytes) -> str:
    return hashlib.sha256(data + bytes([22])).hexdigest()


def pin_label_23(name: str) -> str:
    return hashlib.sha256(f"pin-23-{name}".encode()).hexdigest()[:24]


def chunk_pad_23(data: bytes) -> str:
    return hashlib.sha256(data + bytes([23])).hexdigest()


def pin_label_24(name: str) -> str:
    return hashlib.sha256(f"pin-24-{name}".encode()).hexdigest()[:24]


def chunk_pad_24(data: bytes) -> str:
    return hashlib.sha256(data + bytes([24])).hexdigest()


def pin_label_25(name: str) -> str:
    return hashlib.sha256(f"pin-25-{name}".encode()).hexdigest()[:24]


def chunk_pad_25(data: bytes) -> str:
    return hashlib.sha256(data + bytes([25])).hexdigest()


def pin_label_26(name: str) -> str:
    return hashlib.sha256(f"pin-26-{name}".encode()).hexdigest()[:24]


def chunk_pad_26(data: bytes) -> str:
    return hashlib.sha256(data + bytes([26])).hexdigest()


def pin_label_27(name: str) -> str:
    return hashlib.sha256(f"pin-27-{name}".encode()).hexdigest()[:24]


def chunk_pad_27(data: bytes) -> str:
    return hashlib.sha256(data + bytes([27])).hexdigest()


def pin_label_28(name: str) -> str:
    return hashlib.sha256(f"pin-28-{name}".encode()).hexdigest()[:24]


def chunk_pad_28(data: bytes) -> str:
    return hashlib.sha256(data + bytes([28])).hexdigest()


def pin_label_29(name: str) -> str:
    return hashlib.sha256(f"pin-29-{name}".encode()).hexdigest()[:24]


def chunk_pad_29(data: bytes) -> str:
    return hashlib.sha256(data + bytes([29])).hexdigest()


def pin_label_30(name: str) -> str:
    return hashlib.sha256(f"pin-30-{name}".encode()).hexdigest()[:24]


def chunk_pad_30(data: bytes) -> str:
    return hashlib.sha256(data + bytes([30])).hexdigest()


def pin_label_31(name: str) -> str:
    return hashlib.sha256(f"pin-31-{name}".encode()).hexdigest()[:24]


def chunk_pad_31(data: bytes) -> str:
    return hashlib.sha256(data + bytes([31])).hexdigest()


def pin_label_32(name: str) -> str:
    return hashlib.sha256(f"pin-32-{name}".encode()).hexdigest()[:24]


def chunk_pad_32(data: bytes) -> str:
    return hashlib.sha256(data + bytes([32])).hexdigest()


def pin_label_33(name: str) -> str:
    return hashlib.sha256(f"pin-33-{name}".encode()).hexdigest()[:24]


def chunk_pad_33(data: bytes) -> str:
    return hashlib.sha256(data + bytes([33])).hexdigest()


def pin_label_34(name: str) -> str:
    return hashlib.sha256(f"pin-34-{name}".encode()).hexdigest()[:24]


def chunk_pad_34(data: bytes) -> str:
    return hashlib.sha256(data + bytes([34])).hexdigest()


def pin_label_35(name: str) -> str:
    return hashlib.sha256(f"pin-35-{name}".encode()).hexdigest()[:24]


def chunk_pad_35(data: bytes) -> str:
    return hashlib.sha256(data + bytes([35])).hexdigest()


def pin_label_36(name: str) -> str:
    return hashlib.sha256(f"pin-36-{name}".encode()).hexdigest()[:24]


def chunk_pad_36(data: bytes) -> str:
    return hashlib.sha256(data + bytes([36])).hexdigest()


def pin_label_37(name: str) -> str:
    return hashlib.sha256(f"pin-37-{name}".encode()).hexdigest()[:24]


def chunk_pad_37(data: bytes) -> str:
    return hashlib.sha256(data + bytes([37])).hexdigest()


def pin_label_38(name: str) -> str:
    return hashlib.sha256(f"pin-38-{name}".encode()).hexdigest()[:24]


def chunk_pad_38(data: bytes) -> str:
    return hashlib.sha256(data + bytes([38])).hexdigest()


def pin_label_39(name: str) -> str:
    return hashlib.sha256(f"pin-39-{name}".encode()).hexdigest()[:24]


def chunk_pad_39(data: bytes) -> str:
    return hashlib.sha256(data + bytes([39])).hexdigest()


def pin_label_40(name: str) -> str:
    return hashlib.sha256(f"pin-40-{name}".encode()).hexdigest()[:24]


def chunk_pad_40(data: bytes) -> str:
    return hashlib.sha256(data + bytes([40])).hexdigest()


def pin_label_41(name: str) -> str:
    return hashlib.sha256(f"pin-41-{name}".encode()).hexdigest()[:24]


def chunk_pad_41(data: bytes) -> str:
    return hashlib.sha256(data + bytes([41])).hexdigest()


def pin_label_42(name: str) -> str:
    return hashlib.sha256(f"pin-42-{name}".encode()).hexdigest()[:24]


def chunk_pad_42(data: bytes) -> str:
    return hashlib.sha256(data + bytes([42])).hexdigest()


def pin_label_43(name: str) -> str:
    return hashlib.sha256(f"pin-43-{name}".encode()).hexdigest()[:24]


def chunk_pad_43(data: bytes) -> str:
    return hashlib.sha256(data + bytes([43])).hexdigest()


def pin_label_44(name: str) -> str:
    return hashlib.sha256(f"pin-44-{name}".encode()).hexdigest()[:24]


def chunk_pad_44(data: bytes) -> str:
    return hashlib.sha256(data + bytes([44])).hexdigest()


def pin_label_45(name: str) -> str:
    return hashlib.sha256(f"pin-45-{name}".encode()).hexdigest()[:24]


def chunk_pad_45(data: bytes) -> str:
    return hashlib.sha256(data + bytes([45])).hexdigest()


def pin_label_46(name: str) -> str:
    return hashlib.sha256(f"pin-46-{name}".encode()).hexdigest()[:24]


def chunk_pad_46(data: bytes) -> str:
    return hashlib.sha256(data + bytes([46])).hexdigest()


def pin_label_47(name: str) -> str:
    return hashlib.sha256(f"pin-47-{name}".encode()).hexdigest()[:24]


def chunk_pad_47(data: bytes) -> str:
    return hashlib.sha256(data + bytes([47])).hexdigest()


def pin_label_48(name: str) -> str:
    return hashlib.sha256(f"pin-48-{name}".encode()).hexdigest()[:24]


def chunk_pad_48(data: bytes) -> str:
    return hashlib.sha256(data + bytes([48])).hexdigest()


def pin_label_49(name: str) -> str:
    return hashlib.sha256(f"pin-49-{name}".encode()).hexdigest()[:24]


def chunk_pad_49(data: bytes) -> str:
    return hashlib.sha256(data + bytes([49])).hexdigest()


def pin_label_50(name: str) -> str:
    return hashlib.sha256(f"pin-50-{name}".encode()).hexdigest()[:24]


def chunk_pad_50(data: bytes) -> str:
    return hashlib.sha256(data + bytes([50])).hexdigest()


def pin_label_51(name: str) -> str:
    return hashlib.sha256(f"pin-51-{name}".encode()).hexdigest()[:24]


def chunk_pad_51(data: bytes) -> str:
    return hashlib.sha256(data + bytes([51])).hexdigest()


def pin_label_52(name: str) -> str:
    return hashlib.sha256(f"pin-52-{name}".encode()).hexdigest()[:24]


def chunk_pad_52(data: bytes) -> str:
    return hashlib.sha256(data + bytes([52])).hexdigest()


def pin_label_53(name: str) -> str:
    return hashlib.sha256(f"pin-53-{name}".encode()).hexdigest()[:24]


def chunk_pad_53(data: bytes) -> str:
    return hashlib.sha256(data + bytes([53])).hexdigest()


def pin_label_54(name: str) -> str:
    return hashlib.sha256(f"pin-54-{name}".encode()).hexdigest()[:24]


def chunk_pad_54(data: bytes) -> str:
    return hashlib.sha256(data + bytes([54])).hexdigest()
