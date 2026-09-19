"""AI shell manifest and redaction tests."""

from __future__ import annotations

import sys

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.manifest import AI_SHELL_MANIFEST_VERSION, build_manifest
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def test_ai_manifest_binds_catalog_effects_and_schema():
    catalog = CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec(
                    "python",
                    sys.executable,
                    tags=frozenset({"test"}),
                ),
                ArgumentPolicy.allow_any(),
                description="test tool",
            ),
        )
    )
    effects = EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            ),
        )
    )
    manifest = build_manifest(AIToolCatalog(catalog), effects)
    assert manifest.version == AI_SHELL_MANIFEST_VERSION
    assert len(manifest.digest) == 64
    assert manifest.tools[0]["name"] == "python"
    assert manifest.tools[0]["effects"] == ["read_filesystem"]
    assert manifest.tools[0]["idempotent"] is True
    assert manifest.tools[0]["reversible"] is True


def test_ai_manifest_never_exports_executable_path():
    catalog = CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
            ),
        )
    )
    manifest = build_manifest(AIToolCatalog(catalog), EffectRegistry())
    assert sys.executable not in str(manifest.to_dict())


def test_ai_manifest_unknown_effect_requires_human_review_hint():
    catalog = CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
            ),
        )
    )
    manifest = build_manifest(AIToolCatalog(catalog), EffectRegistry())
    tool = manifest.tools[0]
    assert tool["effects"] == []
    assert tool["human_approval_recommended"] is True
