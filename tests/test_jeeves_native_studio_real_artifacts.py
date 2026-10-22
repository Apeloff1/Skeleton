"""Collect the real Jeeves game-source and native-asset regression suites in CI.

Keep each specification at its owning skeleton/testing location, but expose
it to the repository's root tests/ pytest job. Pytest discovers these imported
unittest.TestCase classes under their Test* aliases and runs them normally.
"""
from skeleton.testing.test_jeeves_studio_sprite_actor_binding import (
    OriginalPlayerSpriteBindingTests as TestJeevesOriginalPlayerAvatar,
)
from skeleton.testing.test_jeeves_studio_sprite_variants import (
    DirectionalSpriteTests as TestJeevesDirectionalSprite,
)
from skeleton.testing.test_jeeves_studio_sprite_quality import (
    SpriteQualityTests as TestJeevesSpriteQuality,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import (
    SpriteForgeTests as TestJeevesSpriteForge,
    PersistentSpriteExportTests as TestJeevesPersistedSprites,
)
from skeleton.testing.test_jeeves_studio_frontier_source_compile import (
    FrontierSourceCompileTests as TestJeevesFrontierSource,
    RealGodotSourceBuildTests as TestJeevesRealGodotSource,
)
from skeleton.testing.test_jeeves_studio_creator_source import (
    CreatorSourceTests as TestJeevesCreatorSource,
    NativePlanSourceFreshnessTests as TestJeevesNativePlanFreshness,
)

__all__ = [
    "TestJeevesSpriteForge", "TestJeevesPersistedSprites",
    "TestJeevesSpriteQuality",
    "TestJeevesDirectionalSprite", "TestJeevesOriginalPlayerAvatar",
    "TestJeevesFrontierSource", "TestJeevesRealGodotSource",
    "TestJeevesCreatorSource", "TestJeevesNativePlanFreshness",
]
