"""Named quill cuts."""

from __future__ import annotations

from typing import Any


class QuillcutPackError(ValueError):
    pass


QUILL = tuple(f"qc_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in QUILL:
        raise QuillcutPackError(name)
    nxt = dict(state)
    nxt["quillcut"] = name
    nxt["nib"] = 1
    nxt["stored_prose"] = 0
    return nxt
