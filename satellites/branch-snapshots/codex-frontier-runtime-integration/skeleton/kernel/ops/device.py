"""Device probe. CUDA / HIP / CPU. Never pretends a GPU is present."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def probe() -> Dict[str, Any]:
    kind = "cpu"
    name = "host"
    if Path("/dev/nvidia0").exists() or os.environ.get("CUDA_VISIBLE_DEVICES") not in {None, "", "-1"}:
        kind = "cuda"
        name = "nvidia"
    elif Path("/dev/kfd").exists():
        kind = "hip"
        name = "amd"
    elif Path("/dev/dri/renderD128").exists():
        kind = "drm"
        name = "render"
    return {
        "kind": "device",
        "device": kind,
        "name": name,
        "cuda": kind == "cuda",
        "stored_prose": 0,
    }
