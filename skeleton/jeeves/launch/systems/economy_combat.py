"""Launch-ready economy and combat systems.

Operational transaction and encounter resolution for game sessions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Wallet:
    currency: str = "scrap"
    balance: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"currency": self.currency, "balance": self.balance}


class EconomySystem:
    """Handles currency, vendors, and item transactions."""

    def __init__(self) -> None:
        self.wallet = Wallet()
        self._vendors: Dict[str, List[Dict[str, Any]]] = {}
        self._log: List[Dict[str, Any]] = []

    def add_funds(self, amount: int) -> Dict[str, Any]:
        if amount <= 0:
            return {"ok": False, "reason": "bad_amount"}
        self.wallet.balance += amount
        self._log.append({"op": "add", "amount": amount, "balance": self.wallet.balance})
        return {"ok": True, "balance": self.wallet.balance}

    def spend(self, amount: int) -> Dict[str, Any]:
        if amount <= 0:
            return {"ok": False, "reason": "bad_amount"}
        if self.wallet.balance < amount:
            return {"ok": False, "reason": "insufficient", "balance": self.wallet.balance}
        self.wallet.balance -= amount
        self._log.append({"op": "spend", "amount": amount, "balance": self.wallet.balance})
        return {"ok": True, "balance": self.wallet.balance}

    def register_vendor(self, vendor_id: str, stock: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not vendor_id:
            return {"ok": False, "reason": "empty_id"}
        self._vendors[vendor_id] = stock
        return {"ok": True, "vendor": vendor_id, "items": len(stock)}

    def buy(self, vendor_id: str, item_id: str) -> Dict[str, Any]:
        stock = self._vendors.get(vendor_id)
        if not stock:
            return {"ok": False, "reason": "vendor_not_found"}
        item = next((i for i in stock if i.get("id") == item_id), None)
        if not item:
            return {"ok": False, "reason": "item_not_found"}
        cost = int(item.get("value", 0))
        spend = self.spend(cost)
        if not spend["ok"]:
            return spend
        stock.remove(item)
        self._log.append({"op": "buy", "item": item_id, "cost": cost})
        return {"ok": True, "item": item, "balance": self.wallet.balance}

    def snapshot(self) -> Dict[str, Any]:
        return {"wallet": self.wallet.to_dict(), "vendors": len(self._vendors), "transactions": len(self._log)}


class CombatSystem:
    """Resolves multi-entity combat exchanges."""

    def resolve_exchange(self, attacker: Dict[str, Any], defender: Dict[str, Any]) -> Dict[str, Any]:
        atk_dmg = int(attacker.get("damage", 5))
        def_armor = int(defender.get("armor", 0))
        def_hp = int(defender.get("health", 10))
        mitigated = max(0, atk_dmg - def_armor)
        new_hp = max(0, def_hp - mitigated)
        killed = new_hp <= 0
        return {
            "ok": True,
            "damage": mitigated,
            "defender_health": new_hp,
            "killed": killed,
            "attacker": attacker.get("id", "unknown"),
            "defender": defender.get("id", "unknown"),
        }

    def resolve_wave(self, player: Dict[str, Any], enemies: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        p_hp = int(player.get("health", 100))
        for e in enemies:
            if p_hp <= 0:
                break
            hit = self.resolve_exchange({"id": "player", "damage": player.get("damage", 8)}, e)
            results.append(hit)
            if not hit["killed"]:
                counter = self.resolve_exchange(e, {"id": "player", "health": p_hp, "armor": player.get("armor", 0)})
                results.append(counter)
                p_hp = counter["defender_health"]
        return {
            "ok": True,
            "player_health": p_hp,
            "exchanges": results,
            "cleared": p_hp > 0 and all(r.get("killed") for r in results if r.get("defender") != "player"),
        }
