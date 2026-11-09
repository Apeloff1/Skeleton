import asyncio

from skeleton.frontier.events import DomainEvent, EventBus


def test_event_bus_delivers_in_subscription_order():
    async def scenario():
        bus = EventBus()
        seen = []

        async def first(event):
            seen.append(("first", event.payload["value"]))

        async def second(event):
            seen.append(("second", event.payload["value"]))

        await bus.subscribe("runtime.completed", first)
        await bus.subscribe("runtime.completed", second)
        event = DomainEvent.create("runtime.completed", {"value": 7})
        assert await bus.publish(event) == 2
        assert seen == [("first", 7), ("second", 7)]
        assert event.occurred_at.tzinfo is not None

    asyncio.run(scenario())


def test_unknown_topic_is_a_noop():
    async def scenario():
        assert await EventBus().publish(DomainEvent.create("missing", {})) == 0

    asyncio.run(scenario())
