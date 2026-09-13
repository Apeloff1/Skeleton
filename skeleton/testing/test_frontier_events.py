import asyncio
import pytest

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


@pytest.mark.asyncio
async def test_failure_does_not_starve_later_handlers_or_mutate_their_payload():
    bus = EventBus()
    seen = []

    async def broken(event):
        event.payload["values"].append(2)
        raise ValueError("first subscriber failed")

    async def healthy(event):
        seen.append(event.payload["values"])
        assert event.correlation_id == "request"
        assert event.causation_id == "parent"

    await bus.subscribe("topic ", broken)
    await bus.subscribe("topic", healthy)
    event = DomainEvent.create(" topic", {"values": [1]}, correlation_id="request", causation_id="parent")
    with pytest.raises(ExceptionGroup) as error:
        await bus.publish(event)
    assert len(error.value.exceptions) == 1
    assert seen == [[1]]


@pytest.mark.asyncio
async def test_subscriptions_are_bounded_idempotent_and_removable():
    bus = EventBus(max_subscriptions=1)

    async def handler(event):
        pass

    await bus.subscribe("x", handler)
    await bus.subscribe("x", handler)
    with pytest.raises(OverflowError):
        await bus.subscribe("y", handler)
    assert await bus.unsubscribe("x", handler)
    assert not await bus.unsubscribe("x", handler)
    await bus.subscribe("y", handler)
