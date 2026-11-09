#!/usr/bin/env python3
"""Build/install the repository wheel in isolation and verify canonical imports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LAYERS = Path("machine/python_package_layers.json")
MASTER = Path("machine/ai_master_plan.json")


class PackagedWheelError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackagedWheelError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise PackagedWheelError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackagedWheelError(f"{relative} must contain an object")
    return data


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PackagedWheelError(f"command failed to start/finish: {command!r}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 5000:
            detail = detail[-5000:]
        raise PackagedWheelError(
            f"command failed ({proc.returncode}): {' '.join(command)}\n{detail}"
        )
    return proc


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    layers = _load(root, LAYERS)
    master = _load(root, MASTER)

    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    volume = volumes.get("VOL-053")
    if not isinstance(volume, dict):
        raise PackagedWheelError("VOL-053 missing from masterplan")
    if "materialize packaged-wheel import test" not in volume.get("gaps", []):
        raise PackagedWheelError("VOL-053 packaged-wheel gap drift")

    bindings = {
        b.get("volume_ref"): b
        for b in layers.get("masterplan_bindings", [])
        if isinstance(b, dict)
    }
    binding = bindings.get("VOL-053")
    if not isinstance(binding, dict):
        raise PackagedWheelError("python package layers do not bind VOL-053")
    if "materialize packaged-wheel import test" not in binding.get("required_gap_texts", []):
        raise PackagedWheelError("package layer manifest does not preserve wheel-import obligation")

    probes = [
        "skeleton",
        "skeleton.kernel",
        "skeleton.contracts.operation",
        "skeleton.providers.contract",
        "skeleton.context",
        "skeleton.persistence",
        "skeleton.retrieval",
        "skeleton.memory",
        "skeleton.intelligence",
        "skeleton.frontier",
        "skeleton.skills",
        "skeleton.agents",
        "skeleton.jeeves",
        "skeleton.forge",
        "skeleton.pipelines",
        "skeleton.automation",
        "skeleton.api",
    ]

    with tempfile.TemporaryDirectory(prefix="skeleton-wheel-") as temp_raw:
        temp = Path(temp_raw)
        wheelhouse = temp / "wheelhouse"
        venv = temp / "venv"
        wheelhouse.mkdir(parents=True)

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-input",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheelhouse),
                str(root),
            ],
            cwd=root,
        )
        wheels = sorted(wheelhouse.glob("skeleton-*.whl"))
        if len(wheels) != 1:
            raise PackagedWheelError(
                f"expected exactly one skeleton wheel, found {[p.name for p in wheels]}"
            )
        wheel = wheels[0]

        _run([sys.executable, "-m", "venv", str(venv)], cwd=root)
        python = _venv_python(venv)
        if not python.is_file():
            raise PackagedWheelError("isolated virtualenv Python not created")

        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                str(wheel),
            ],
            cwd=temp,
        )

        source_shadow = temp / "shadow"
        source_shadow.mkdir()
        probe_code = (
            "import importlib, json; "
            f"mods={probes!r}; "
            "loaded={}; "
            "\nfor name in mods:\n"
            " m=importlib.import_module(name); "
            " loaded[name]=getattr(m, '__file__', None)\n"
            "print(json.dumps(loaded, sort_keys=True))"
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        proc = _run(
            [str(python), "-I", "-c", probe_code],
            cwd=source_shadow,
            env=env,
        )
        try:
            loaded = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise PackagedWheelError("isolated import probe did not emit JSON") from exc

        source_root = str(root)
        leaked = {
            name: path
            for name, path in loaded.items()
            if isinstance(path, str) and path.startswith(source_root)
        }
        if leaked:
            raise PackagedWheelError(f"wheel imports leaked to source tree: {leaked}")

        dist_info = list(venv.rglob("skeleton-*.dist-info"))
        if not dist_info:
            raise PackagedWheelError("installed wheel has no skeleton dist-info")

        shutil.rmtree(wheelhouse, ignore_errors=True)

    return {
        "status": "valid",
        "probe_count": len(probes),
        "probes": probes,
        "masterplan_binding": "VOL-053",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except PackagedWheelError as exc:
        print(f"packaged wheel imports: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"packaged wheel imports: OK ({result['probe_count']} probes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
