from __future__ import annotations

from pathlib import Path


COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _service_block(name: str) -> str:
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    marker = f"  {name}:"
    start = lines.index(marker)
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            break
        body.append(line)
    return "\n".join(body)


def test_api_runtime_roots_are_read_only_with_explicit_tmpfs() -> None:
    for service in ("skeleton", "backend"):
        block = _service_block(service)
        assert "    read_only: true" in block
        assert "    tmpfs:" in block
        assert "      - /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777" in block
        assert "      - no-new-privileges:true" in block
        assert "    cap_drop:\n      - ALL" in block


def test_backend_code_mounts_are_read_only_but_runtime_data_stays_writable() -> None:
    block = _service_block("backend")
    assert "      - ./backend:/app:ro" in block
    assert "      - ./skeleton:/app/skeleton:ro" in block
    assert "      - backend_data:/app/data" in block
    assert "      - backend_data:/app/data:ro" not in block
