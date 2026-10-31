"""Industry state as its own ``GameSavePlane`` section (``industry@v1``).

Written next to the economy section from
:mod:`skeleton.economy.gameplay.save_plane` (and, when a market is
attached, next to the ``market@v1`` section from
:mod:`skeleton.economy.gameplay.market.save_section`). Loading restores the
economy (and market) first, rebuilds industry over it, and refuses the save
unless the industry audit balances against the restored ledgers.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping, Optional

from skeleton.economy.gameplay import save_plane
from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.industry.engine import IndustrySystem
from skeleton.economy.gameplay.market import save_section as market_save
from skeleton.economy.gameplay.save import SaveError
from skeleton.kernel.checkpoint import Checkpoint
from skeleton.kernel.game_save_plane import GameSavePlane

SECTION_NAME = "industry"
INDUSTRY_SAVE_VERSION = 1
_KEY_RE = re.compile(r"^(?P<name>[a-z_]+)@v(?P<version>\d+)$")


def _checksum(state: Mapping[str, Any]) -> str:
    blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def section_key(version: int = INDUSTRY_SAVE_VERSION, name: str = SECTION_NAME) -> str:
    return f"{name}@v{version}"


def industry_payload(system: IndustrySystem) -> dict[str, Any]:
    state = json.loads(json.dumps(system.to_state(), sort_keys=True))
    return {
        "version": INDUSTRY_SAVE_VERSION,
        "state": state,
        "checksum": _checksum(state),
    }


def industry_section(
    system: IndustrySystem, name: str = SECTION_NAME
) -> dict[str, dict[str, Any]]:
    return {section_key(INDUSTRY_SAVE_VERSION, name): industry_payload(system)}


def find_industry_section(
    sections: Mapping[str, Any], name: str = SECTION_NAME
) -> Mapping[str, Any]:
    found = []
    for key, payload in sections.items():
        m = _KEY_RE.match(key)
        if m and m.group("name") == name:
            found.append((int(m.group("version")), payload))
    if not found:
        raise SaveError(f"save has no {name!r} section")
    if len(found) > 1:
        raise SaveError(f"save has more than one {name!r} section")
    version, payload = found[0]
    if not isinstance(payload, Mapping) or payload.get("version") != version:
        raise SaveError(f"{name!r} section key and payload disagree on version")
    if version != INDUSTRY_SAVE_VERSION:
        raise SaveError(f"unknown {name!r} section version v{version}")
    state = payload.get("state")
    if not isinstance(state, Mapping) or payload.get("checksum") != _checksum(state):
        raise SaveError("industry checksum mismatch")
    return state


def save_industry(
    plane: GameSavePlane,
    slot: str,
    sequence: int,
    system: IndustrySystem,
    *,
    other_sections: Optional[Mapping[str, Mapping[str, Any]]] = None,
    name: str = SECTION_NAME,
) -> Checkpoint:
    """Write economy (+ market) + industry sections to one slot."""
    sections: dict[str, Mapping[str, Any]] = dict(other_sections or {})
    if any((m := _KEY_RE.match(k)) and m.group("name") == name for k in sections):
        raise SaveError(f"other_sections already holds a {name!r} section")
    system.require_conserved()
    sections.update(industry_section(system, name))
    if system.market is not None:
        return market_save.save_market(
            plane, slot, sequence, system.market, other_sections=sections
        )
    return save_plane.save_to_plane(
        plane, slot, sequence, system.econ, other_sections=sections
    )


def load_industry(
    plane: GameSavePlane,
    slot: str,
    factory: Callable[[], GameplayEconomy],
    *,
    sequence: Optional[int] = None,
    with_market: bool = False,
    name: str = SECTION_NAME,
) -> IndustrySystem:
    if with_market:
        market = market_save.load_market(plane, slot, factory, sequence=sequence)
        econ = market.econ
    else:
        market = None
        econ = save_plane.load_from_plane(plane, slot, factory, sequence=sequence)
    sections, _ = plane.restore(slot, sequence=sequence)
    state = find_industry_section(sections, name)
    try:
        system = IndustrySystem.from_state(econ, state, market=market)
    except (KeyError, TypeError, ValueError) as exc:
        raise SaveError("malformed industry state") from exc
    if not system.audit()["ok"]:
        raise SaveError("restored industry books do not balance")
    return system


__all__ = [
    "INDUSTRY_SAVE_VERSION",
    "SECTION_NAME",
    "find_industry_section",
    "industry_payload",
    "industry_section",
    "load_industry",
    "save_industry",
    "section_key",
]
