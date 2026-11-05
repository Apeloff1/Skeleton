"""One original-project production frame for Jeeves and studio UI consumers."""
from __future__ import annotations
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    QuestSession, compile_quest_program, verify_quest_session,
    quest_progress,
)
from .studio_ecosystem_scene import scene_catalog
from .studio_ecosystem_objects import object_inventory
from .studio_ecosystem_social import compile_factions
from .studio_ecosystem_endings import ending_obligations
from .studio_ecosystem_manifest import source_manifest
from .studio_ecosystem_work import build_work_graph
from .studio_ecosystem_rights import release_requirements


def production_frame(documents: Mapping[str, Any],
                     session: QuestSession | None = None, *,
                     authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("studio production frame requires authorization")
    program=compile_quest_program(documents)
    if session is not None:
        verify_quest_session(session,documents,program=program)
    frame={
        "schema":"skeleton.game_builder.studio_production_frame.v1",
        "project_id":program.project_id,"source_digest":program.source_digest,
        "manifest":source_manifest(documents),
        "scene_bindings":list(scene_catalog(documents)),
        "object_inventory":object_inventory(documents),
        "authored_factions":[key for key,_ in compile_factions(documents).factions],
        "ending_obligations":ending_obligations(documents,session),
        "release_requirements":release_requirements(documents),
        "producer_work":build_work_graph(documents),
        "quest_progress":quest_progress(session,documents) if session is not None else None,
        "native_genre_runtime_verified":False,
        "rights_certified":False,"release_certified":False,
    }
    return frame
