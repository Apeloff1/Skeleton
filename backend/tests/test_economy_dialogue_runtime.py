import pytest

from core.dialogue_runtime import (
    DialogueChoice,
    DialogueContext,
    DialogueEffect,
    DialogueError,
    DialogueNode,
    DialogueRuntime,
)
from core.economy_runtime import CatalogItem, EconomyError, EconomyRuntime, Inventory, Wallet


def test_purchase_is_atomic_and_grants_unlocks():
    runtime = EconomyRuntime([
        CatalogItem("boat", {"coins": 100}, min_level=2, grants=("deep_water",), stackable=False),
    ])
    wallet = Wallet({"coins": 150})
    inventory = Inventory(capacity=4)

    receipt = runtime.purchase(
        item_id="boat", quantity=1, player_level=2, wallet=wallet, inventory=inventory
    )

    assert receipt.spent == {"coins": 100}
    assert wallet.balances == {"coins": 50}
    assert inventory.items == {"boat": 1}
    assert inventory.unlocks == {"deep_water"}


def test_failed_purchase_does_not_mutate_state():
    runtime = EconomyRuntime([CatalogItem("rod", {"coins": 200})])
    wallet = Wallet({"coins": 50})
    inventory = Inventory({"bait": 2}, {"pier"}, capacity=10)

    with pytest.raises(EconomyError, match="insufficient coins"):
        runtime.purchase(
            item_id="rod", quantity=1, player_level=1, wallet=wallet, inventory=inventory
        )

    assert wallet.balances == {"coins": 50}
    assert inventory.items == {"bait": 2}
    assert inventory.unlocks == {"pier"}


def test_inventory_capacity_and_non_stackable_are_fail_closed():
    runtime = EconomyRuntime([
        CatalogItem("map", {"coins": 0}, stackable=False),
        CatalogItem("bait", {"coins": 1}, quantity=2),
    ])
    wallet = Wallet({"coins": 10})
    inventory = Inventory({"map": 1}, capacity=2)

    with pytest.raises(EconomyError, match="already owned"):
        runtime.purchase(item_id="map", quantity=1, player_level=1, wallet=wallet, inventory=inventory)
    with pytest.raises(EconomyError, match="capacity"):
        runtime.purchase(item_id="bait", quantity=1, player_level=1, wallet=wallet, inventory=inventory)
    assert wallet.balances == {"coins": 10}


def test_sale_credits_wallet_and_removes_zero_stack():
    wallet = Wallet({"coins": 0})
    inventory = Inventory({"fish": 2})
    payout = EconomyRuntime.sell(
        item_id="fish", quantity=2, unit_value={"coins": 7}, wallet=wallet, inventory=inventory
    )
    assert payout == {"coins": 14}
    assert wallet.balances == {"coins": 14}
    assert "fish" not in inventory.items


def _dialogue() -> DialogueRuntime:
    return DialogueRuntime(
        [
            DialogueNode(
                "greeting",
                "Need work?",
                (
                    DialogueChoice(
                        "help",
                        "I can help.",
                        "work",
                        min_relationship=10,
                        required_stats=(("charm", 2),),
                        effect=DialogueEffect(
                            relationship_delta=5,
                            currency_delta=10,
                            grant_items=("token",),
                            grant_unlocks=("back_room",),
                            start_quests=("q1",),
                        ),
                    ),
                    DialogueChoice("leave", "Goodbye.", None),
                ),
            ),
            DialogueNode("work", "Then get moving.", ()),
        ],
        start_node="greeting",
    )


def test_dialogue_filters_choices_and_applies_consequences():
    runtime = _dialogue()
    context = DialogueContext(relationship=12, currency=5, stats={"charm": 2})

    assert {choice.id for choice in runtime.choices("greeting", context)} == {"help", "leave"}
    outcome = runtime.choose("greeting", "help", context)

    assert outcome.node_id == "work"
    assert context.relationship == 17
    assert context.currency == 15
    assert context.inventory == {"token": 1}
    assert context.unlocks == {"back_room"}
    assert context.quests == {"q1"}


def test_unavailable_dialogue_choice_is_side_effect_free():
    runtime = _dialogue()
    context = DialogueContext(relationship=0, currency=5, stats={"charm": 10})

    with pytest.raises(DialogueError, match="unavailable"):
        runtime.choose("greeting", "help", context)

    assert context.relationship == 0
    assert context.currency == 5
    assert context.inventory == {}


def test_dialogue_overdraft_rejects_before_mutation():
    runtime = DialogueRuntime(
        [
            DialogueNode(
                "start",
                "Pay?",
                (DialogueChoice("pay", "yes", None, effect=DialogueEffect(relationship_delta=5, currency_delta=-10)),),
            )
        ],
        start_node="start",
    )
    context = DialogueContext(relationship=1, currency=3)

    with pytest.raises(DialogueError, match="overdraw"):
        runtime.choose("start", "pay", context)
    assert context.relationship == 1
    assert context.currency == 3
