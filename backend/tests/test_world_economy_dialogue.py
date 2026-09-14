from core.dialogue_runtime import DialogueChoice, DialogueEffect, DialogueNode, DialogueRuntime
from core.economy_runtime import CatalogItem, EconomyRuntime, Inventory, Wallet
from core.world_agents import AgentSchedule, NavigationGraph, ScheduleEntry, WorldAgent, WorldNode
from core.world_runtime import WorldRuntime


def _world() -> WorldRuntime:
    graph = NavigationGraph([
        WorldNode("square", 0, 0, connections=("shop",)),
        WorldNode("shop", 1, 0, connections=("square",)),
    ])
    merchant = WorldAgent(
        "merchant",
        "shop",
        AgentSchedule((ScheduleEntry(0, "sell", "shop"),)),
    )
    dialogue = DialogueRuntime(
        [
            DialogueNode(
                "hello",
                "Looking for work?",
                (
                    DialogueChoice(
                        "accept",
                        "Yes.",
                        None,
                        effect=DialogueEffect(
                            relationship_delta=8,
                            currency_delta=5,
                            grant_items=("merchant_token",),
                            grant_unlocks=("backroom",),
                        ),
                    ),
                ),
            ),
        ],
        start_node="hello",
    )
    return WorldRuntime(
        graph=graph,
        agents=[merchant],
        economy=EconomyRuntime([
            CatalogItem("compass", {"coins": 20}, grants=("navigation",), stackable=False),
        ]),
        wallet=Wallet({"coins": 30}),
        economy_inventory=Inventory(capacity=8),
        dialogues={"merchant": dialogue},
    )


def test_world_purchase_and_dialogue_flow_into_authoritative_snapshot():
    world = _world()

    receipt = world.purchase_item("compass")
    assert receipt.spent == {"coins": 20}
    assert world.wallet.balances["coins"] == 10

    outcome = world.choose_dialogue("merchant", "hello", "accept")
    assert outcome.relationship == 8
    assert world.relationship("merchant").relationship == 8
    assert world.wallet.balances["coins"] == 15

    snapshot = world.snapshot()
    assert snapshot["economy"]["balances"] == {"coins": 15}
    assert snapshot["economy"]["items"] == {"compass": 1, "merchant_token": 1}
    assert snapshot["economy"]["unlocks"] == ["backroom", "navigation"]
    assert snapshot["relationships"]["merchant"]["relationship"] == 8


def test_world_save_contains_integrated_economy_and_relationship_state():
    world = _world()
    world.purchase_item("compass")
    world.choose_dialogue("merchant", "hello", "accept")

    encoded = world.encode_save()
    decoded = world.save_codec.decode(encoded)

    assert decoded["economy"]["balances"]["coins"] == 15
    assert decoded["economy"]["items"]["merchant_token"] == 1
    assert decoded["relationships"]["merchant"]["tier"] == "acquaintance"
