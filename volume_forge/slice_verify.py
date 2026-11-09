"""Slice-verify one emitted binding. Do not import the shard."""

from __future__ import annotations

from pathlib import Path


def first_binding(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    start = text.index("def b_")
    end = text.index("\ndef b_", start + 1)
    ns: dict[str, object] = {}
    exec(text[start:end], ns)
    fn = next(v for k, v in ns.items() if k.startswith("b_"))
    out = fn(1.0)  # type: ignore[operator]
    if int(out["stored_prose"]) != 0:
        raise RuntimeError("stored_prose")
    if float(out["mass"]) > 1.1:
        raise RuntimeError("clip")
    return out


if __name__ == "__main__":
    import sys
    print(first_binding(Path(sys.argv[1])))
