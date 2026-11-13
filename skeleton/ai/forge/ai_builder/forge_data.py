"""Plan -> forge data via forge's existing materialise + structured verify."""
from __future__ import annotations

from typing import Any, Mapping

PLAN_DATA_SCHEMA = "skeleton.forge.ai_builder.forge_data.v1"


def forge_plan_data(spec: Mapping[str, Any], *, target: str = "json", name: str = "design_spec",
                    max_rounds: int = 2, root: Any = None) -> dict[str, Any]:
    """Encode the committed spec through MaterialisationRegistry and verify it.

    Uses ``structured_verify_until_green`` (which itself encodes via
    ``encode_structured_files``) - no second materialise path.
    """
    from skeleton.forge.structured_verify import structured_verify_until_green

    loop = structured_verify_until_green(dict(spec), target=target, name=name,
                                         request=str(spec.get("brief", "")), root=root, max_rounds=max_rounds)
    return {
        "schema": PLAN_DATA_SCHEMA,
        "spec_id": spec.get("spec_id"),
        "target": target,
        "files": dict(loop.get("files") or {}),
        "accepted": bool(loop.get("accepted")),
        "stopped_reason": loop.get("stopped_reason"),
        "verification": loop.get("verification"),
    }
