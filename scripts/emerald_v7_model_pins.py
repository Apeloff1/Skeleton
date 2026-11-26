"""Immutable Emerald V7 donor identity, importable without NumPy/renderer code.

The exporter, authenticated raw Git publisher and independent remote-byte
reassembler share exactly these pins. Do not repin to satisfy a failed model.
"""
from __future__ import annotations

SOURCES = {
    "pathfinder": (
        114693124,
        "20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063",
    ),
    "archivist": (
        114815776,
        "8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973",
    ),
}

OUTPUTS = {
    "pathfinder": (
        114696520,
        "27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade",
    ),
    "archivist": (
        114819168,
        "f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf",
    ),
}

DONOR = "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
ROOT_JOINT = 34
ANGLE = 0.18
TARGET_CLIP = "orbit-02"


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)
