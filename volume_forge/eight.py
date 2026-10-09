"""Eight-file stratum. Streamed. Target is a wc, not a join."""

from __future__ import annotations

from pathlib import Path

FILES = 8
FUNCS = 1400000
SEED = 8847291
CLIP = 1.1
CHUNK = 20000


def emit(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for file_i in range(FILES):
        path = root / f"f{file_i}.py"
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f'"""Eight-file stratum {file_i}. stored_prose=0. clip 1.1."""\n')
            handle.write(f"FILE = {file_i}\nSEED = {SEED}\nSTORED_PROSE = 0\nCLIP = {CLIP}\nFUNCS = {FUNCS}\n\n")
            buf: list[str] = []
            for index in range(FUNCS):
                coeff = (SEED * 10007 + file_i * 100003 + index * 97) & 0xFFFFFFFF
                buf.append(
                    f"def b_{file_i}_{index:07d}(prior: float) -> dict[str, object]:\n"
                    f"    coeff = {coeff}\n"
                    f"    proposed = prior * (1.0 + (coeff % 997) / 10000.0)\n"
                    f"    ceiling = prior * {CLIP}\n"
                    f"    if proposed < 0:\n"
                    f"        raise ValueError('mass')\n"
                    f"    mass = ceiling if proposed > ceiling else proposed\n"
                    f"    return {{'file': {file_i}, 'index': {index}, 'coeff': coeff, 'mass': mass, 'stored_prose': 0}}\n\n"
                )
                if len(buf) == CHUNK:
                    handle.write("".join(buf))
                    buf.clear()
            if buf:
                handle.write("".join(buf))
            handle.write(f"def run(prior: float = 1.0) -> dict[str, object]:\n    return b_{file_i}_0000000(prior)\n")
        print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    import sys
    emit(Path(sys.argv[1] if len(sys.argv) > 1 else "emit8"))
