from skeleton.acquired.gaming import (
    CourseTracker,
    Point3,
    RingGate,
    orient_ring_path,
    segment_crosses_ring,
)
from skeleton.kernel.events import EventBus


def test_segment_crosses_ring_through_aperture():
    ring = RingGate(0, 0, 0, 0, 0, -1, 5)
    crossing = segment_crosses_ring(
        Point3(0, 0, 2),
        Point3(0, 0, -2),
        ring,
    )

    assert crossing.crossed is True
    assert crossing.t == 0.5
    assert crossing.radial_distance == 0.0


def test_segment_outside_aperture_does_not_score():
    ring = RingGate(0, 0, 0, 0, 0, -1, 2)
    crossing = segment_crosses_ring(
        Point3(4, 0, 2),
        Point3(4, 0, -2),
        ring,
    )

    assert crossing.crossed is False
    assert crossing.radial_distance == 4.0


def test_wrong_direction_does_not_score():
    ring = RingGate(0, 0, 0, 0, 0, -1, 5)
    crossing = segment_crosses_ring(
        Point3(0, 0, -2),
        Point3(0, 0, 2),
        ring,
    )
    assert crossing.crossed is False


def test_orient_ring_path_uses_next_waypoint_and_preserves_open_final_heading():
    rings = orient_ring_path(
        [Point3(0, 0, 0), Point3(0, 0, 10), Point3(10, 0, 10)],
        radius=3,
        closed=False,
    )

    assert len(rings) == 3
    assert rings[0].normal == (0.0, 0.0, 1.0)
    assert rings[1].normal == (1.0, 0.0, 0.0)
    assert rings[2].normal == (1.0, 0.0, 0.0)


def test_course_tracker_advances_in_order_and_emits_finish():
    rings = [
        RingGate(0, 0, 0, 0, 0, -1, 5),
        RingGate(0, 0, -10, 0, 0, -1, 5),
    ]
    bus = EventBus()
    events = []
    bus.subscribe("acquired.gaming.course.*", events.append)
    tracker = CourseTracker(rings, margin=0, bus=bus, course_id="test")

    tracker.reset(Point3(0, 0, 2))
    first = tracker.update(Point3(0, 0, -2))
    assert first is not None
    assert first["rings_done"] == 1
    assert first["completed"] is False

    tracker.update(Point3(0, 0, -8))
    second = tracker.update(Point3(0, 0, -12))
    assert second is not None
    assert second["rings_done"] == 2
    assert second["completed"] is True
    assert tracker.progress()["progress"] == 1.0

    topics = [event.topic for event in events]
    assert topics == [
        "acquired.gaming.course.reset",
        "acquired.gaming.course.gate",
        "acquired.gaming.course.gate",
        "acquired.gaming.course.finished",
    ]


def test_segment_intersection_prevents_fast_movement_tunnelling():
    ring = RingGate(0, 0, 0, 0, 0, -1, 2)
    crossing = segment_crosses_ring(
        Point3(0.5, 0, 100),
        Point3(0.5, 0, -100),
        ring,
    )
    assert crossing.crossed is True
