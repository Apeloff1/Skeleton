"""Reproducible offline Python zipapp build of the playable game.

Exports a *working standalone Python application archive* (.pyz) bundling
the exact transitive internal Python modules required by the studio. Requires
installed Python >=3.11 at destination. Never bundles external SDKs,
unlicensed ROMs, copyrighted game assets, platform keys or vendor runtimes.
Does not claim native EXE/ROM, app-store certification or binary signatures.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

ENTRY = "skeleton.game.generation.original_world_product_cli"
ARCHIVE_MAIN = (
    "from skeleton.game.generation.original_world_product_cli import main\n"
    "if __name__ == '__main__':\n"
    "    raise SystemExit(main())\n"
)
MAX_MODULES = 256
MAX_BYTES = 12 * 1024 * 1024
SCHEMA = "original-world-portable-app.v1"


def _sha(content: bytes) -> str:
    return sha256(content).hexdigest()


def _source_modules(root: Path) -> dict[str, bytes]:
    prefix = root / "skeleton" / "game" / "generation"
    if not prefix.is_dir():
        raise ValueError("game source directory missing; point --source-root to repository")
    pending, seen = ["original_world_product_cli"], set()
    output: dict[str, bytes] = {}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        if (not name.isidentifier() or not name.startswith(
                ("original_", "world_"))):
            raise ValueError("non-allowlisted game source dependency: " + name)
        path = prefix / (name + ".py")
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing or linked code dependency: " + name)
        raw = path.read_bytes()
        if len(raw) > 300000:
            raise ValueError("oversized or suspicious game source dependency")
        tree = ast.parse(raw.decode("utf-8"), filename=str(path))
        seen.add(name)
        output["skeleton/game/generation/" + name + ".py"] = raw
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level == 1 and node.module:
                if node.module.startswith(("original_", "world_")):
                    pending.append(node.module)
                else:
                    raise ValueError("unexpected relative game module: " + node.module)
            elif node.level > 0:
                raise ValueError("unexpected relative package traversal")
        if len(seen) > MAX_MODULES or sum(len(v) for v in output.values()) > MAX_BYTES:
            raise ValueError("unsafe archive source budget")
    return output


def build_portable_app(source_root: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    output = output.resolve()
    if output.suffix != ".pyz" or not output.parent.is_dir():
        raise ValueError("output must be an .pyz file in an existing directory")
    if output.is_symlink() or output.is_dir():
        raise ValueError("refusing unsafe or directory output")
    modules = _source_modules(source_root)
    contents = dict(modules)
    contents["__main__.py"] = ARCHIVE_MAIN.encode("utf-8")
    # The repository's package initializers import unrelated simulation
    # backends. Portable archives deliberately isolate only the audited,
    # transitively discovered original-game source modules.
    for directory in ("skeleton", "skeleton/game", "skeleton/game/generation"):
        contents[directory + "/__init__.py"] = b""
    manifest = {
        "schema": SCHEMA, "required_python": "3.11+",
        "entry": ENTRY,
        "native_exe_or_console_image": False,
        "commercial_playtesting_certified": False,
        "world_assets": "authored in source and generated with legal local procedural rules",
        "license_policy": "No external SDK, proprietary game data, or platform assets bundled",
        "content_hashes": {
            name: _sha(data) for name, data in sorted(contents.items())
        },
    }
    contents["original-world-portable-manifest.json"] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError("portable executable source budget exhausted")
    temporary = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9, strict_timestamps=True) as archive:
            for name in sorted(contents):
                entry = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                archive.writestr(entry, contents[name], compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=9)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "archive": str(output),
        "sha256": _sha(output.read_bytes()),
        "included_source_modules": len(modules),
        "bytes": output.stat().st_size,
        "format": "portable-python-zipapp",
        "native_exe": False,
        "self_contained_stdlib_and_code": True,
        "python_required": "3.11+",
        "provenance": SCHEMA,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build offline portable Python game studio")
    parser.add_argument("--source-root", type=Path,
                        default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        info = build_portable_app(args.source_root, args.output)
    except (ValueError, OSError, SyntaxError) as exc:
        parser.error(str(exc))
    print(json.dumps(info, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
