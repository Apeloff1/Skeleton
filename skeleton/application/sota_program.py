"""Issue #807 SOTA game-creation program map.

Curated lane registry for the B001-B100 concurrent-batch program.
A discovered module is structural evidence only. A completed batch is
not proof of SOTA readiness. Competitive claims need versioned evals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Final, Mapping


SOTA_PROGRAM_VERSION: Final = 1
SOTA_PROGRAM_ISSUE: Final = 807


@dataclass(frozen=True, slots=True)
class SotaLane:
    """One ten-batch lane in the #807 program."""

    id: str
    first_batch: str
    last_batch: str
    owner_issue: int
    status: str
    evidence: str
    module: str
    next_contract: str


LANES: Final[tuple[SotaLane, ...]] = (
    SotaLane(
        id="build",
        first_batch="B001",
        last_batch="B010",
        owner_issue=940,
        status="contract",
        evidence="structural",
        module="skeleton.application",
        next_contract="content-addressed graph + reproducible release gate",
    ),
    SotaLane(
        id="creator",
        first_batch="B011",
        last_batch="B020",
        owner_issue=942,
        status="contract",
        evidence="structural",
        module="skeleton.developer",
        next_contract="intent compiler + approval boundary",
    ),
    SotaLane(
        id="gameplay",
        first_batch="B021",
        last_batch="B030",
        owner_issue=943,
        status="contract",
        evidence="structural",
        module="skeleton.game.session",
        next_contract="deterministic mechanics + replay #936",
    ),
    SotaLane(
        id="ai",
        first_batch="B031",
        last_batch="B040",
        owner_issue=944,
        status="contract",
        evidence="structural",
        module="skeleton.game.ai_policy",
        next_contract="tool capability security + eval arena",
    ),
    SotaLane(
        id="world",
        first_batch="B041",
        last_batch="B050",
        owner_issue=945,
        status="blocked",
        evidence="structural",
        module="skeleton.galaxy",
        next_contract="wait on gameplay replay contract",
    ),
    SotaLane(
        id="assets",
        first_batch="B051",
        last_batch="B060",
        owner_issue=946,
        status="blocked",
        evidence="structural",
        module="skeleton.content",
        next_contract="manifest/provenance + rights release gate",
    ),
    SotaLane(
        id="network",
        first_batch="B061",
        last_batch="B070",
        owner_issue=947,
        status="blocked",
        evidence="structural",
        module="skeleton.swarm",
        next_contract="wait on deterministic time + replay",
    ),
    SotaLane(
        id="quality",
        first_batch="B071",
        last_batch="B080",
        owner_issue=948,
        status="contract",
        evidence="structural",
        module="skeleton.game.replay",
        next_contract="replay evidence + flake lifecycle",
    ),
    SotaLane(
        id="security",
        first_batch="B081",
        last_batch="B090",
        owner_issue=949,
        status="contract",
        evidence="structural",
        module="skeleton.vault.tool_fence",
        next_contract="generated-code sandbox + prompt/tool injection",
    ),
    SotaLane(
        id="platform",
        first_batch="B091",
        last_batch="B100",
        owner_issue=950,
        status="blocked",
        evidence="structural",
        module="skeleton.forge",
        next_contract="Godot artifact plane #1008 then B100 arena",
    ),
)

LANES_BY_ID: Final[Mapping[str, SotaLane]] = MappingProxyType(
    {lane.id: lane for lane in LANES}
)

_ALLOWED_STATUS: Final = frozenset({"structural", "contract", "evidence", "blocked"})
_ALLOWED_EVIDENCE: Final = frozenset({"structural", "eval", "none"})


def get_lane(lane_id: str) -> SotaLane:
    """Return one program lane by stable id."""

    if not isinstance(lane_id, str):
        raise TypeError("lane_id must be a string")
    normalized = lane_id.strip().lower()
    if not normalized:
        raise ValueError("lane_id must not be empty")
    try:
        return LANES_BY_ID[normalized]
    except KeyError as exc:
        raise KeyError(f"unknown sota lane: {normalized}") from exc


def sota_program() -> dict[str, object]:
    """Return the versioned, JSON-serializable SOTA program map."""

    ready = sum(1 for lane in LANES if lane.evidence == "eval")
    return {
        "schema_version": SOTA_PROGRAM_VERSION,
        "issue": SOTA_PROGRAM_ISSUE,
        "law": "batch_complete_is_not_sota",
        "sota_ready": False,
        "lanes_with_eval_evidence": ready,
        "lane_count": len(LANES),
        "lanes": [asdict(lane) for lane in LANES],
        "high_leverage": [
            "B021/B071/B072 deterministic mechanics + replay",
            "B082/B086 generated-code sandbox + injection boundary",
            "B006/B091 Godot binary off git onto artifact plane",
            "B100 only after major lanes have eval evidence",
        ],
    }
