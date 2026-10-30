"""Immutable resource-conservation simulation for original studio production briefs.

Operator-provided starting quantity is a *sandbox premise*, never externally
verified supply; no action adds resources, including after replay or restore.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode("ascii")).hexdigest()


def resource_label(documents: Mapping[str, Any]) -> str:
    quest = documents.get("quest")
    if not isinstance(quest, dict) or quest.get("release_certified") is not False:
        raise StudioQuestError("missing unqualified resource contract")
    contracts = [key for key in ("resource_constraints", "resource_economy", "economy")
                 if key in quest]
    if len(contracts) != 1:
        raise StudioQuestError("ambiguous or absent scarce-resource source")
    key = contracts[0]
    source = quest[key]
    field = {"resource_constraints": "resource", "resource_economy": "currency",
             "economy": "scarce_resource"}[key]
    name = source.get(field) if isinstance(source, dict) else None
    if not isinstance(name, str) or not name or len(name) > 256:
        raise StudioQuestError("invalid authored resource identity")
    if key == "resource_constraints" and (type(source.get("max_mint_without_source")) is not int or source.get("max_mint_without_source") != 0):
        raise StudioQuestError("source permits unearned resource mint")
    if key == "resource_economy" and source.get("no_mint_without_supply") is not True:
        raise StudioQuestError("source fails closed on resource minting")
    if key == "economy" and source.get("unlimited_rewards") is not False:
        raise StudioQuestError("source has unlimited rewards")
    return name


@dataclass(frozen=True, slots=True)
class ResourceSession:
    project_id: str
    resource_name: str
    initial_quantity: int
    balances: tuple[tuple[str, int], ...]
    transactions: tuple[tuple[str, str, int], ...]
    digest: str


def _replay(project: str, resource: str, quantity: int,
            transactions: tuple[tuple[str, str, int], ...]) -> ResourceSession:
    balance = {"reserve": quantity, "spent": 0}
    for source, target, amount in transactions:
        if (source not in balance or target not in balance or source == target
                or type(amount) is not int or amount <= 0 or amount > balance[source]):
            raise StudioQuestError("overdraft or invalid resource transfer")
        balance[source] -= amount
        balance[target] += amount
    payload = {"project": project, "resource": resource, "starting": quantity,
               "transactions": transactions, "balances": balance}
    return ResourceSession(project, resource, quantity, tuple(sorted(balance.items())),
                           transactions, _hash(payload))


def start_resources(documents: Mapping[str, Any], *, starting_quantity: int,
                    authorized: bool) -> ResourceSession:
    if not authorized:
        raise PermissionError("resource simulation needs operator authorization")
    if type(starting_quantity) is not int or starting_quantity < 0:
        raise StudioQuestError("quantity must be a nonnegative integer")
    quest = documents["quest"]
    return _replay(quest["project_id"], resource_label(documents), starting_quantity, ())


def verify_resources(session: ResourceSession, documents: Mapping[str, Any]) -> None:
    if (not isinstance(session, ResourceSession) or
            session.project_id != documents["quest"]["project_id"] or
            session.resource_name != resource_label(documents) or
            session != _replay(session.project_id, session.resource_name,
                               session.initial_quantity, session.transactions)):
        raise StudioQuestError("resource session failed replay validation")


def transfer_resources(session: ResourceSession, documents: Mapping[str, Any], *,
                       source: str, target: str, quantity: int,
                       authorized: bool) -> ResourceSession:
    if not authorized:
        raise PermissionError("resource transfer needs operator authorization")
    verify_resources(session, documents)
    return _replay(session.project_id, session.resource_name, session.initial_quantity,
                   session.transactions + ((source, target, quantity),))


def resource_receipt(session: ResourceSession, documents: Mapping[str, Any]) -> dict[str, object]:
    verify_resources(session, documents)
    return {"schema": "skeleton.game_builder.studio_resource_replay.v1",
            "project_id": session.project_id, "resource": session.resource_name,
            "balances": dict(session.balances), "transaction_count": len(session.transactions),
            "resource_digest": session.digest, "quantity_conserved": True,
            "initial_supply_externally_verified": False, "release_certified": False}
