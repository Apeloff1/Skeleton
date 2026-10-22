"""Collect the real Jeeves game-source and native-asset regression suites in CI.

Keep each specification at its owning skeleton/testing location, but expose
it to the repository's root tests/ pytest job. Pytest discovers these imported
unittest.TestCase classes under their Test* aliases and runs them normally.
"""
from skeleton.testing.test_jeeves_studio_sprite_direction import (
    TestJeevesSpriteDirectionCompiler, TestJeevesSpriteDirectionGame,
)
from skeleton.testing.test_jeeves_studio_sprite_actor_binding import (
    OriginalPlayerSpriteBindingTests as TestJeevesOriginalPlayerAvatar,
)
from skeleton.testing.test_jeeves_studio_sprite_hitboxes import (
    ExactSpriteCollisionTests as TestJeevesExactSpriteCollision,
)
from skeleton.testing.test_jeeves_studio_sprite_variants import (
    DirectionalSpriteTests as TestJeevesDirectionalSprite,
)
from skeleton.testing.test_jeeves_studio_npc_cast_source import (
    OriginalNpcCastTests as TestJeevesOriginalNpcCast,
)
from skeleton.testing.test_jeeves_studio_sprite_npc_binding import (
    OriginalNpcSpriteBindingTests as TestJeevesOriginalNpcSprites,
    NpcSpriteGraphPreflightTests as TestJeevesNpcSpritePreflight,
)
from skeleton.testing.test_jeeves_studio_sprite_palette_variants import (
    OriginalPaletteVariantTests as TestJeevesOriginalPaletteVariants,
    PersistentPaletteSkinTests as TestJeevesPersistedPaletteSkins,
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
    "TestJeevesOriginalPaletteVariants", "TestJeevesPersistedPaletteSkins",
    "TestJeevesOriginalNpcCast", "TestJeevesOriginalNpcSprites",
    "TestJeevesNpcSpritePreflight",
    "TestJeevesDirectionalSprite",
    "TestJeevesSpriteDirectionCompiler", "TestJeevesSpriteDirectionGame",
    "TestJeevesExactSpriteCollision", "TestJeevesOriginalPlayerAvatar",
    "TestJeevesFrontierSource", "TestJeevesRealGodotSource",
    "TestJeevesCreatorSource", "TestJeevesNativePlanFreshness",
]
