"""Static social/economic risk matrix for an original reviewed Director world.

The audit is read-only and source-bound. It can identify authored anomalies,
not independently certify human enjoyment, AI character intelligence or a
physically complete game. Runtime softlocks require actual playthrough proof.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_society import (
    legal_actions, phase, residents_here,
)
from skeleton.ai.game_builder.quest_scene_engine import director_initial
from skeleton.developer.jeeves_game_director_session import _hash
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.society_assurance.v1"


def analyze(world: Any) -> dict[str, Any]:
    if world.dynamics is None or world.dynamics.society is None:
        raise ValueError("no original NPC-society source to inspect")
    rules = world.dynamics.society
    initial = director_initial(world)
    roster = {npc.key: npc for npc in rules.residents}
    commerce = {shop.key: shop for shop in rules.shops}
    residents = []
    issues: list[dict[str, Any]] = []
    phase_counts = Counter()
    region_by_scene = {scene.key: scene.region for scene in world.scenes}
    for person in rules.residents:
        per_scene = Counter(person.schedule)
        for scene, count in per_scene.items():
            phase_counts[scene] += count
        dormant = person.key not in {
            npc.key for npc in residents_here(rules, world.starting_scene, 0)}
        residents.append({
            "key": person.key, "name": person.name,
            "faction": person.faction,
            "dawn_scene": person.schedule[0],
            "day_scene": person.schedule[1],
            "dusk_scene": person.schedule[2],
            "night_scene": person.schedule[3],
            "distinct_locations": len(per_scene),
            "region_coverage": sorted({
                region_by_scene[scene] for scene in person.schedule
            }),
            "initial_trust": person.initial_trust,
            "trust_gain_per_conversation": person.trust_gain,
            "min_trust_for_flag": person.unlock_at_trust,
            "can_eventually_gain_required_trust_by_dialogue": (
                person.initial_trust >= person.unlock_at_trust or
                person.trust_gain > 0),
            "initially_outside_starting_scene": dormant,
        })
        if (person.unlock_world_flag is not None
                and person.initial_trust < person.unlock_at_trust
                and person.trust_gain <= 0):
            issues.append({
                "severity": "high", "kind": "impossible_positive_trust_unlock",
                "resident": person.key,
                "flag": person.unlock_world_flag,
                "reason": "Required trust cannot be reached through authored NPC dialogue",
            })
        if person.trust_gain < 0 and person.reputation_gain > 0:
            issues.append({
                "severity": "review", "kind": "conflicting_npc_rewards",
                "resident": person.key,
                "reason": "Conversation harms personal trust but raises faction standing",
            })
        if len(set(person.schedule)) == 1:
            issues.append({
                "severity": "review", "kind": "stationary_npc",
                "resident": person.key,
                "reason": "Character remains in a single scene all four calendar phases",
            })
    merchants = []
    goods = set()
    for shop in rules.shops:
        npc = roster[shop.keeper]
        open_periods = [
            name for name, place in zip(("dawn", "day", "dusk", "night"), npc.schedule)
            if place == shop.scene
        ]
        products = []
        for good in shop.goods:
            goods.add(good.key)
            if good.starting_stock == 0:
                issues.append({
                    "severity": "review", "kind": "empty_shop_good",
                    "shop": shop.key, "good": good.key,
                    "reason": "Goods require resale or new authoring to become available",
                })
            if good.sell_price == good.buy_price:
                issues.append({
                    "severity": "review", "kind": "zero_spread_trade",
                    "shop": shop.key, "good": good.key,
                    "reason": "The good can be sold back for its full purchase price",
                })
            products.append({
                "key": good.key, "name": good.name,
                "starting_stock": good.starting_stock,
                "price": good.buy_price, "resale_value": good.sell_price,
                "initially_affordable": good.buy_price <= rules.starting_balance,
                "eventually_available": good.starting_stock > 0,
            })
        merchants.append({
            "key": shop.key, "name": shop.name,
            "keeper": shop.keeper, "scene": shop.scene,
            "open_periods": open_periods,
            "goods": products,
        })
    requirements = []
    for rule_type, records in (
            ("walk", world.dynamics.gates),
            ("transit", world.dynamics.passages)):
        for record in records:
            if not record.requirements.trust and not (
                    set(record.requirements.items) & goods):
                continue
            needs = [
                {"resident": condition.resident,
                 "at_least": condition.at_least,
                 "at_most": condition.at_most,
                 "starting_trust": roster[condition.resident].initial_trust}
                for condition in record.requirements.trust
            ]
            requirement = {
                "type": rule_type, "source": record.source,
                "destination": record.destination,
                "name": record.key if rule_type == "transit" else record.label,
                "trust_requirements": needs,
                "market_goods_required": sorted(
                    set(record.requirements.items) & goods
                ),
                "initially_open": False,  # computed using exact starting state
            }
            from skeleton.ai.game_builder.quest_world_dynamics import permits
            requirement["initially_open"] = permits(record.requirements, initial)
            requirements.append(requirement)
            for item in needs:
                npc = roster[item["resident"]]
                if (npc.initial_trust < item["at_least"]
                        and npc.trust_gain <= 0):
                    issues.append({
                        "severity": "high", "kind": "unattainable_route_trust",
                        "route": requirement["name"],
                        "resident": npc.key,
                    })
            for required_good in requirement["market_goods_required"]:
                supplier = next(
                    shop for shop in rules.shops
                    if any(g.key == required_good for g in shop.goods))
                product = next(g for g in supplier.goods if g.key == required_good)
                if product.starting_stock == 0:
                    issues.append({
                        "severity": "high", "kind": "unavailable_transit_ticket",
                        "route": requirement["name"], "good": required_good,
                    })
                if (product.buy_price > rules.starting_balance
                        and not any(g.sell_price > 0 for shop in rules.shops
                                    for g in shop.goods)):
                    issues.append({
                        "severity": "review", "kind": "expensive_transit_ticket",
                        "route": requirement["name"], "good": required_good,
                        "reason": "Wallet cannot cover initial fare; investigate other income",
                    })
    initial_actions = [
        kind + ":" + key for kind, key in legal_actions(rules, initial)
    ]
    details = {
        "schema": SCHEMA,
        "project": world.project_id, "world_sha256": world.digest,
        "phase_turns": rules.phase_turns,
        "clock_periods": 4, "NPC_count": len(rules.residents),
        "shop_count": len(rules.shops),
        "tradeable_item_count": len(goods),
        "starting_wallet": rules.starting_balance,
        "author_defined_residents": residents,
        "author_defined_merchants": merchants,
        "scene_schedule_occupancy": dict(sorted(phase_counts.items())),
        "conditional_society_links": requirements,
        "actual_initial_NPC_market_actions": initial_actions,
        "structural_review_items": issues,
        "structural_review_item_count": len(issues),
        "NPC_behavior_independent_AI_verified": False,
        "player_choice_depth_creatively_certified": False,
        "physical_engine_performance_verified": False,
        "campaign_path_feasibility_proven_by_this_audit": False,
    }
    details["assurance_sha256"] = _hash(details)
    return details


def audit(root: Path, *, source: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha256 = _load_world(root, source)
    analysis = analyze(world)
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha256:
        raise ValueError("original NPC source changed during social scrutiny")
    return {
        "ok": True, "action": "director-society-audit",
        "source_sha256": source_sha256,
        "analysis": analysis, "source_bound": True,
        "source_modified": False, "gameplay_actions_executed": False,
    }
