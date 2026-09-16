"""Capability lifecycle contracts for the Galaxy federation plane."""

from __future__ import annotations

from skeleton.galaxy import GalaxyNode, NodeRegistry


def test_registry_copies_capability_sets_and_updates_explicitly():
    registry = NodeRegistry()
    source = {"retrieval"}

    identity = registry.register(
        "node-a",
        "node-a.example",
        capabilities=source,
    )
    source.add("planner")

    assert identity.capabilities == {"retrieval"}
    assert [node.node_id for node in registry.discover(capability="retrieval")] == [
        "node-a"
    ]
    assert registry.discover(capability="planner") == []

    assert registry.update_capabilities("node-a", {"planner", "retrieval"})
    assert [node.node_id for node in registry.discover(capability="planner")] == [
        "node-a"
    ]
    assert not registry.update_capabilities("missing", {"planner"})


def test_started_node_syncs_add_remove_and_replace_capabilities():
    node = GalaxyNode(node_id="node-a")
    node.add_capability("retrieval")
    node.start()

    assert [item.node_id for item in node._registry.discover(capability="retrieval")] == [
        "node-a"
    ]

    node.add_capability("planner")
    assert [item.node_id for item in node._registry.discover(capability="planner")] == [
        "node-a"
    ]

    assert node.remove_capability("retrieval")
    assert not node.remove_capability("retrieval")
    assert node._registry.discover(capability="retrieval") == []

    node.set_capabilities({"memory"})
    assert node._registry.discover(capability="planner") == []
    assert [item.node_id for item in node._registry.discover(capability="memory")] == [
        "node-a"
    ]


def test_capabilities_property_is_a_defensive_copy():
    node = GalaxyNode(node_id="node-a")
    node.set_capabilities({"retrieval"})

    advertised = node.capabilities
    advertised.add("external-mutation")

    assert node.capabilities == {"retrieval"}
