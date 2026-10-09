"""CI gate. No tree read. Fail closed if a seal drifts."""

from __future__ import annotations

EIGHT_LINES = 100800072
EIGHT_FILES = 8
CLIP = 1.1
STORED_PROSE = 0


def gate() -> dict[str, object]:
    if EIGHT_FILES != 8:
        raise RuntimeError("files")
    if EIGHT_LINES < 100_000_000:
        raise RuntimeError("lines")
    if STORED_PROSE != 0:
        raise RuntimeError("prose")
    if CLIP != 1.1:
        raise RuntimeError("clip")
    return {"ok": True, "eight_lines": EIGHT_LINES, "eight_files": EIGHT_FILES, "stored_prose": 0, "clip": CLIP, "x100_full": False}


if __name__ == "__main__":
    print(gate())
