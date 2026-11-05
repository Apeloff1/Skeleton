"""B025 versioned economy saves with forward migrations.

Save format history:

* **v1** – ``{"version": 1, "balances": {owner: {currency: amount}},
  "inventories": {owner: {item: qty}}}`` (owner-major, no slots, no flows).
* **v2** – currency-major ``balances`` that include the burn account, and
  inventories carry ``slots``.
* **v3** (current) – adds money and item ``flows``, ``bound`` holdings,
  ``max_weight`` per owner and a sha256 ``checksum`` over the state.

:func:`migrate` lifts any older save to v3 one step at a time; each step is
pure and total. :func:`load` verifies the checksum, rebuilds a
:class:`GameplayEconomy` from a caller factory (specs live in code, not in
saves) and refuses the save unless the rebuilt books audit clean.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy, _ItemFlows
from skeleton.simulation.economy.sim import BURN_ACCOUNT, EconomySimError, _Flows

SAVE_VERSION = 3
RESTORE_PROVENANCE = "save-restore"
MIGRATION_SOURCE = "migration"


class SaveError(EconomySimError):
    code = "ECO.SAVE"


def _checksum(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(econ: GameplayEconomy) -> dict[str, Any]:
    with econ._lock:
        snap = econ.snapshot()
        state = {
            "balances": snap["balances"],
            "inventories": snap["inventories"],
            "bound": snap["bound"],
            "max_weight": {o: econ.max_weight(o) for o in econ.owners()},
            "flows": {
                cid: {
                    "minted": f.minted,
                    "burned": f.burned,
                    "by_faucet": dict(sorted(f.by_faucet.items())),
                    "by_sink": dict(sorted(f.by_sink.items())),
                }
                for cid, f in sorted(econ._flows.items())
            },
            "item_flows": {
                iid: {
                    "minted": f.minted,
                    "burned": f.burned,
                    "by_source": dict(sorted(f.by_source.items())),
                    "by_sink": dict(sorted(f.by_sink.items())),
                }
                for iid, f in sorted(econ._item_flows.items())
            },
        }
    return {"version": SAVE_VERSION, "state": state, "checksum": _checksum(state)}


def _v1_to_v2(data: Mapping[str, Any]) -> dict[str, Any]:
    balances: dict[str, dict[str, int]] = {}
    for owner, per in data.get("balances", {}).items():
        for cid, amount in per.items():
            balances.setdefault(cid, {BURN_ACCOUNT: 0})[owner] = amount
    inventories = {
        owner: {"owner": owner, "slots": None, "stacks": dict(stacks)}
        for owner, stacks in data.get("inventories", {}).items()
    }
    for per in balances.values():
        for owner in per:
            if owner != BURN_ACCOUNT:
                inventories.setdefault(owner, {"owner": owner, "slots": None, "stacks": {}})
    return {"version": 2, "balances": balances, "inventories": inventories}


def _v2_to_v3(data: Mapping[str, Any]) -> dict[str, Any]:
    # Pre-v3 saves never recorded provenance: attribute all existing money and
    # items to a single "migration" source so the audit invariant holds.
    flows = {}
    for cid, per in data["balances"].items():
        burned = per.get(BURN_ACCOUNT, 0)
        held = sum(v for k, v in per.items() if k != BURN_ACCOUNT)
        minted = held + burned
        flows[cid] = {
            "minted": minted,
            "burned": burned,
            "by_faucet": {MIGRATION_SOURCE: minted} if minted else {},
            "by_sink": {MIGRATION_SOURCE: burned} if burned else {},
        }
    item_totals: dict[str, int] = {}
    for inv in data["inventories"].values():
        for item_id, qty in inv["stacks"].items():
            item_totals[item_id] = item_totals.get(item_id, 0) + qty
    item_flows = {
        iid: {"minted": n, "burned": 0, "by_source": {MIGRATION_SOURCE: n}, "by_sink": {}}
        for iid, n in sorted(item_totals.items())
    }
    state = {
        "balances": data["balances"],
        "inventories": data["inventories"],
        "bound": {},
        "max_weight": {},
        "flows": flows,
        "item_flows": item_flows,
    }
    return {"version": 3, "state": state, "checksum": _checksum(state)}


MIGRATIONS: dict[int, Callable[[Mapping[str, Any]], dict[str, Any]]] = {1: _v1_to_v2, 2: _v2_to_v3}


def migrate(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise SaveError("save must be an object")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SaveError("save has no valid version")
    if version > SAVE_VERSION:
        raise SaveError("save is from a newer build")
    current: dict[str, Any] = dict(data)
    while current["version"] < SAVE_VERSION:
        try:
            current = MIGRATIONS[current["version"]](current)
        except (KeyError, TypeError, AttributeError) as exc:
            raise SaveError(f"malformed v{current['version']} save") from exc
    return current


def load(data: Mapping[str, Any], factory: Callable[[], GameplayEconomy]) -> GameplayEconomy:
    """Migrate, verify and rebuild. The factory must return an *empty* economy."""
    current = migrate(data)
    state = current.get("state")
    if not isinstance(state, Mapping) or current.get("checksum") != _checksum(state):
        raise SaveError("checksum mismatch")
    econ = factory()
    if econ.owners():
        raise SaveError("factory must return an empty economy")
    try:
        with econ._lock:
            for owner, inv in sorted(state["inventories"].items()):
                econ.open_account(owner, slots=inv.get("slots"), max_weight=state["max_weight"].get(owner))
            for cid, per in state["balances"].items():
                if cid not in econ.currencies:
                    raise SaveError(f"save references unknown currency {cid!r}")
                treasury = econ._treasuries[cid]
                for owner, amount in sorted(per.items()):
                    if amount:
                        if owner != BURN_ACCOUNT and owner not in econ._inventories:
                            econ.open_account(owner)
                        treasury.mint(owner, amount, RESTORE_PROVENANCE, memo="restore")
                f = state["flows"].get(cid, {})
                econ._flows[cid] = _Flows(
                    minted=f.get("minted", 0),
                    burned=f.get("burned", 0),
                    by_faucet=dict(f.get("by_faucet", {})),
                    by_sink=dict(f.get("by_sink", {})),
                )
            for owner, inv in state["inventories"].items():
                for item_id, qty in inv["stacks"].items():
                    if item_id not in econ.items:
                        raise SaveError(f"save references unknown item {item_id!r}")
                    econ._inventories[owner].stacks[item_id] = qty
                inv_obj = econ._inventories[owner]
                if inv_obj.slots_used(econ.items) > inv_obj.slots:
                    raise SaveError(f"inventory of {owner!r} exceeds its slots")
            for item_id, f in state["item_flows"].items():
                if item_id not in econ.items:
                    raise SaveError(f"save references unknown item {item_id!r}")
                econ._item_flows[item_id] = _ItemFlows(
                    minted=f["minted"], burned=f["burned"],
                    by_source=dict(f["by_source"]), by_sink=dict(f["by_sink"]),
                )
            for owner, bound in state["bound"].items():
                econ._bound[owner] = dict(bound)
    except (KeyError, TypeError, AttributeError) as exc:
        raise SaveError("malformed save state") from exc
    if not econ.audit()["ok"] or not econ.item_audit()["ok"]:
        raise SaveError("restored books do not balance")
    return econ


__all__ = ["MIGRATIONS", "SAVE_VERSION", "SaveError", "load", "migrate", "save"]
