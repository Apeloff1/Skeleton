"""Deterministic encounter resolution with bounded stamina, defense and damage."""
from dataclasses import dataclass
from ..contracts.errors import ContractError

@dataclass(frozen=True)
class Combatant:
    id: str
    health: int
    attack: int
    defense: int
    stamina: int

def strike(attacker: Combatant, defender: Combatant, *, power: int=1) -> tuple[Combatant, dict]:
    if not 1 <= power <= 4 or not all((0 <= getattr(a, k) <= 1000 for a in (attacker, defender) for k in ('health', 'attack', 'defense', 'stamina'))):
        raise ContractError('invalid combat state')
    if attacker.health == 0 or attacker.stamina < power:
        raise ContractError('attacker exhausted or defeated')
    damage = max(1, attacker.attack * power - defender.defense)
    remaining = max(0, defender.health - damage)
    return (Combatant(defender.id, remaining, defender.attack, defender.defense, defender.stamina), {'damage': defender.health - remaining, 'defeated': remaining == 0, 'stamina_cost': power})
