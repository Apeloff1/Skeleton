"""Skeleton ECS: blueprint-to-ECS adapter and AST-sandboxed scripting (B023).

Builds on the deterministic live ECS core in :mod:`skeleton.simulation.ecs`
(extend-only): this package adds

* :mod:`.blueprint` — instantiate a Forge blueprint as a runnable
  ``LiveWorld`` + ``TickScheduler``;
* :mod:`.script_policy` / :mod:`.script_rewrite` / :mod:`.script_guard` /
  :mod:`.script` — three-layer AST sandbox for game-logic scripts;
* :mod:`.script_system` — scripts as access-checked scheduler systems.
"""
from .blueprint import *  # noqa: F403
from .script import *  # noqa: F403
from .script_policy import Violation, validate_source
from .script_system import *  # noqa: F403

__all__ = [  # noqa: F405
    "BlueprintAdapterError", "CompiledScript", "EcsBuild", "KIND_CATALOG", "NormalBlueprint",
    "ScriptInstance", "ScriptLimits", "ScriptResult", "ScriptSystem", "Violation",
    "build_api", "build_ecs", "check_script", "compile_script", "normalize_blueprint",
    "script_system", "to_script_value", "validate_source",
]
