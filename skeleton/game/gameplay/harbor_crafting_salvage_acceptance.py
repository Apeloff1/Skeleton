"""End-to-end salvage acceptance: source -> play -> journal -> package -> replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_salvage import build_salvage, verify_salvage
from .harbor_crafting_salvage_journal import (
    append_salvage_journal, create_salvage_journal, verify_salvage_journal,
)
from .harbor_crafting_salvage_package import (
    build_salvage_package, play_salvage_package, verify_salvage_package_play,
)

SCHEMA = "skeleton.game.harbor.salvage-acceptance.v1"
MAX_BYTES = 1048576
FIELDS = {"schema", "report", "journal", "package_play", "acceptance_digest"}


def accept_salvage(source: Any, board: Any, actions: Any) -> dict[str, Any]:
    report = build_salvage(source, board, actions, require_complete=True)
    status = verify_salvage(report, require_complete=True)
    package = build_salvage_package(source, board, package_id="lantern_quay_salvage")
    package_play = play_salvage_package(package, actions, require_complete=True)
    journal = create_salvage_journal(source, board)
    journal = append_salvage_journal(journal, actions, expected_tip=journal["tip"])
    journal_result = verify_salvage_journal(journal)
    package_status = verify_salvage_package_play(package_play, require_complete=True)
    if (journal_result["report"] != report or package_status != status
            or report["bundle"]["state"]["ending"] != "beacon"
            or len(report["state"]["secured"]) != len(board["sites"])):
        raise HarborError("salvage end-to-end acceptance disagreement")
    result = {"schema": SCHEMA, "report": report, "journal": journal,
              "package_play": package_play}
    result["acceptance_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("salvage acceptance exceeds byte budget")
    return result


def verify_salvage_acceptance(acceptance: Any) -> dict[str, Any]:
    _keys(acceptance, FIELDS, "salvage acceptance")
    if acceptance["schema"] != SCHEMA or len(canonical(acceptance)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage acceptance")
    if acceptance["acceptance_digest"] != digest({k: v for k, v in acceptance.items()
                                                  if k != "acceptance_digest"}):
        raise HarborError("salvage acceptance digest mismatch")
    report = acceptance["report"]
    status = verify_salvage(report, require_complete=True)
    rebuilt = accept_salvage(report["source"], report["board"], report["actions"])
    if rebuilt != acceptance:
        raise HarborError("salvage acceptance replay mismatch")
    return deepcopy(status)
