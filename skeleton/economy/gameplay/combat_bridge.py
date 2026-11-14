"""B027 bridge: charge economy ability costs from the combat framework.

:class:`skeleton.simulation.game.combat_design.abilities.CombatSession` owns
cooldowns, effects and resolution. :class:`~skeleton.economy.gameplay.combat.AbilityBook`
owns money and reagent costs. :func:`bind_ability_book` connects them:

* a cast guard refuses (``reason="guard_refused"``) when the owner cannot pay,
  before any combat state changes;
* a cast listener pays through :meth:`AbilityBook.use` after a successful cast.

Abilities that are not in the book stay free. ``owner_of`` maps a combatant id
to its economy account, and by default the combatant id is the account.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from skeleton.economy.gameplay.combat import AbilityBook

OwnerOf = Callable[[str], Optional[str]]


def affordable(book: AbilityBook, owner: str, ability_id: str) -> Optional[str]:
    """Return ``None`` if ``owner`` can pay for ``ability_id``, otherwise a refusal detail."""

    spec = book.abilities.get(ability_id)
    if spec is None:
        return None
    cost = book.cost(ability_id)
    econ = book.econ
    if spec.sink_id is not None:
        currency = econ.sinks[spec.sink_id].currency
        if econ.balance(owner, currency) < cost["money"]:
            return f"insufficient funds for {ability_id}"
    if spec.reagent is not None and econ.inventory(owner).count(spec.reagent) < spec.reagent_qty:
        return f"missing reagents for {ability_id}"
    return None


def bind_ability_book(session: Any, book: AbilityBook, *, owner_of: Optional[OwnerOf] = None) -> List[Dict[str, Any]]:
    """Wire ``book`` into ``session``; return the list that receives each paid receipt."""

    resolve: OwnerOf = owner_of or (lambda combatant_id: combatant_id)
    receipts: List[Dict[str, Any]] = []

    def guard(actor: Any, ability: Any, target: Any) -> Optional[str]:
        owner = resolve(actor.combatant_id)
        if owner is None or ability.ability_id not in book.abilities:
            return None
        return affordable(book, owner, ability.ability_id)

    def pay(sess: Any, result: Any) -> None:
        owner = resolve(result.actor_id)
        if owner is None or result.ability_id not in book.abilities:
            return
        cost = book.use(owner, result.ability_id)
        receipts.append({"tick": result.tick, "owner": owner, "ability": result.ability_id, **cost})

    session.add_cast_guard(guard)
    session.on_cast(pay)
    return receipts


__all__ = ["affordable", "bind_ability_book"]
