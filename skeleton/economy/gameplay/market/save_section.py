"""Market state as its own ``GameSavePlane`` section.

The market is saved next to the economy section written by
:mod:`skeleton.economy.gameplay.save_plane`: the economy section carries
balances and inventories (including the escrow account), the
``market@v<N>`` section carries the order book, claims, history, telemetry
and integrity state. Loading restores the economy first, rebuilds the market
over it and refuses the save unless the market audit balances.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping, Optional

from skeleton.economy.gameplay import save_plane
from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.market.exchange import PlayerMarket
from skeleton.economy.gameplay.save import SaveError
from skeleton.kernel.checkpoint import Checkpoint
from skeleton.kernel.game_save_plane import GameSavePlane

SECTION_NAME = "market"
MARKET_SAVE_VERSION = 1
_KEY_RE = re.compile(r"^(?P<name>[a-z_]+)@v(?P<version>\d+)$")


def _checksum(state: Mapping[str, Any]) -> str:
    blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def section_key(version: int = MARKET_SAVE_VERSION, name: str = SECTION_NAME) -> str:
    return f"{name}@v{version}"


def market_payload(market: PlayerMarket) -> dict[str, Any]:
    state = market.to_state()
    # round-trip through JSON so tuples/ints are canonical and the checksum is stable
    state = json.loads(json.dumps(state, sort_keys=True))
    return {
        "version": MARKET_SAVE_VERSION,
        "state": state,
        "checksum": _checksum(state),
    }


def market_section(
    market: PlayerMarket, name: str = SECTION_NAME
) -> dict[str, dict[str, Any]]:
    return {section_key(MARKET_SAVE_VERSION, name): market_payload(market)}


def find_market_section(
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
    if version != MARKET_SAVE_VERSION:
        raise SaveError(f"unknown {name!r} section version v{version}")
    state = payload.get("state")
    if not isinstance(state, Mapping) or payload.get("checksum") != _checksum(state):
        raise SaveError("market checksum mismatch")
    return state


def save_market(
    plane: GameSavePlane,
    slot: str,
    sequence: int,
    market: PlayerMarket,
    *,
    other_sections: Optional[Mapping[str, Mapping[str, Any]]] = None,
    name: str = SECTION_NAME,
) -> Checkpoint:
    """Write economy + market sections (plus any ``other_sections``) to one slot."""
    sections: dict[str, Mapping[str, Any]] = dict(other_sections or {})
    if any((m := _KEY_RE.match(k)) and m.group("name") == name for k in sections):
        raise SaveError(f"other_sections already holds a {name!r} section")
    market.require_conserved()
    sections.update(market_section(market, name))
    return save_plane.save_to_plane(
        plane, slot, sequence, market.econ, other_sections=sections
    )


def load_market(
    plane: GameSavePlane,
    slot: str,
    factory: Callable[[], GameplayEconomy],
    *,
    sequence: Optional[int] = None,
    name: str = SECTION_NAME,
) -> PlayerMarket:
    econ = save_plane.load_from_plane(plane, slot, factory, sequence=sequence)
    sections, _ = plane.restore(slot, sequence=sequence)
    state = find_market_section(sections, name)
    try:
        market = PlayerMarket.from_state(econ, state)
    except (KeyError, TypeError, ValueError) as exc:
        raise SaveError("malformed market state") from exc
    if not market.audit()["ok"]:
        raise SaveError("restored market books do not balance")
    return market


__all__ = [
    "MARKET_SAVE_VERSION",
    "SECTION_NAME",
    "find_market_section",
    "load_market",
    "market_payload",
    "market_section",
    "save_market",
    "section_key",
]
