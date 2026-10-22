"""skeleton/simulation/platform/visual_verification.py
Fail-closed visual verification receipt starter.
Binds PNG atlas and .tres identity. Never claims engine execution or visual render success.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

class VisualVerifyError(SkeletonError):
    code = "SIM_VISUAL"
    severity = "medium"

def verify_binding(
    atlas_path: Path,
    tres_path: Path,
    source_receipt: str,
) -> str:
    """Produce a receipt that the source-bound PNG and .tres exist and match expected suffixes.
    Does not claim Godot loaded them or that pixels were rendered.
    """
    if not atlas_path.exists() or atlas_path.suffix != ".png":
        raise VisualVerifyError("atlas PNG missing or wrong suffix")
    if not tres_path.exists() or tres_path.suffix != ".tres":
        raise VisualVerifyError("tres missing or wrong suffix")
    atlas_digest = hashlib.sha256(atlas_path.read_bytes()).hexdigest()
    tres_digest = hashlib.sha256(tres_path.read_bytes()).hexdigest()
    payload = f"{atlas_digest}:{tres_digest}:{source_receipt}"
    receipt = hashlib.sha256(payload.encode()).hexdigest()
    emit_receipt(
        kind="visual_binding",
        atlas=str(atlas_path),
        tres=str(tres_path),
        digest=receipt,
        source=source_receipt,
        stored_prose=0,
    )
    return receipt

def reject_false_engine_claim(claimed: bool) -> None:
    if claimed:
        raise VisualVerifyError("engine execution claim rejected without independent proof")
