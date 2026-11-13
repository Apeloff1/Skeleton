"""Structural local-AI health is not evidence of native GGUF inference."""
from . import get_complete
from .version import __version__, __seams__


def health() -> dict:
    """Expose structural status separately from fail-closed inference readiness."""
    status = get_complete().status()
    seams = status.get("seams")
    structural = (
        type(seams) is int
        and type(__seams__) is int
        and seams >= __seams__
        and status.get("status") == "complete"
    )
    return {
        "version": __version__,
        "declared_seams": __seams__,
        "loaded_seams": seams,
        "adapter": status.get("adapter"),
        "bridge": status.get("bridge"),
        "healthy": structural,
        "inference_ready": False,
        "readiness_code": "NATIVE_GGUF_INFERENCE_UNVERIFIED",
        "readiness_evidence": None,
    }
