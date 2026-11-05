"""Guard the backend container's dependency-supported Python and runtime cleanup.

A previous automated base-image bump to Python 3.15 passed a Dockerfile
pin update but failed at the explicit <3.15 dependency guard during E2E.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "backend" / "Dockerfile"


def test_backend_image_stages_share_supported_digest_pinned_python():
    source = DOCKERFILE.read_text(encoding="utf-8")
    stages = re.findall(r"^FROM (python:[^\s]+) AS (builder|runtime-source|production)$", source, re.M)
    assert len(stages) == 3, stages
    images = {image for image, _ in stages}
    assert len(images) == 1, images
    image = images.pop()
    assert re.fullmatch(r"python:3\.14-alpine@sha256:[0-9a-f]{64}", image), image
    assert "sys.version_info[:2] < (3, 15)" in source


def test_prod_pip_removal_follows_installed_interpreter_and_is_fail_closed():
    source = DOCKERFILE.read_text(encoding="utf-8")
    assert 'sysconfig.get_path("purelib")' in source
    assert 'is_relative_to(pathlib.Path("/usr/local/lib"))' in source
    assert 'shutil.rmtree(site / "pip"' in source
    assert '/usr/local/lib/python3.14/site-packages/pip' not in source
    assert '/usr/local/lib/python3.15/site-packages/pip' not in source
