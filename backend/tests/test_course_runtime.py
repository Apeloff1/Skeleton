import math

import pytest

from core.course_runtime import Course, CourseTracker, Ring, Spawn, build_ring_path, crossed_ring


def test_build_ring_path_closes_loop_and_normalizes_normals():
    rings = build_ring_path(
        [
            (0.0, 0.0, 0.0, 5.0),
            (10.0, 0.0, 0.0, 5.0),
            (10.0, 0.0, 10.0, 5.0),
        ],
        closed=True,
    )
    assert len(rings) == 3
    for ring in rings:
        assert math.sqrt(ring.nx**2 + ring.ny**2 + ring.nz**2) == pytest.approx(1.0)


def test_crossing_requires_forward_plane_passage_and_radius():
    ring = Ring(0, 0, 0, 0, 0, 1, 3)
    assert crossed_ring((0, 0, -2), (0, 0, 2), ring) is True
    assert crossed_ring((5, 0, -2), (5, 0, 2), ring) is False
    assert crossed_ring((0, 0, 2), (0, 0, -2), ring) is False


def test_tracker_enforces_order_and_finishes():
    course = Course(
        id="test",
        name="Test",
        par_seconds=10,
        start=Spawn(0, 0, -5, 0),
        rings=(
            Ring(0, 0, 0, 0, 0, 1, 3),
            Ring(0, 0, 10, 0, 0, 1, 3),
        ),
    )
    tracker = CourseTracker(course)
    tracker.step(1.0, (0, 0, -2), (0, 0, 2))
    assert tracker.progress.next_ring == 1
    assert tracker.progress.finished is False
    tracker.step(1.0, (0, 0, 8), (0, 0, 12))
    assert tracker.progress.finished is True
    assert tracker.progress.completed_rings == 2


def test_medal_bands_are_deterministic():
    course = Course("c", "C", 10, Spawn(0, 0, 0, 0), (Ring(0, 0, 0, 0, 0, 1, 3),))
    tracker = CourseTracker(course)
    tracker.step(8.0, (0, 0, -1), (0, 0, 1))
    assert tracker.medal_band() == "elite"

    tracker = CourseTracker(course)
    tracker.step(10.0, (0, 0, -1), (0, 0, 1))
    assert tracker.medal_band() == "gold"

    tracker = CourseTracker(course)
    tracker.step(11.5, (0, 0, -1), (0, 0, 1))
    assert tracker.medal_band() == "silver"

    tracker = CourseTracker(course)
    tracker.step(13.5, (0, 0, -1), (0, 0, 1))
    assert tracker.medal_band() == "bronze"


def test_empty_course_never_auto_finishes():
    tracker = CourseTracker(Course("free", "Free", 0, Spawn(0, 0, 0, 0), ()))
    tracker.step(5.0, (0, 0, 0), (1, 1, 1))
    assert tracker.progress.finished is False
    assert tracker.medal_band() == "none"


def test_negative_dt_rejected():
    tracker = CourseTracker(Course("c", "C", 1, Spawn(0, 0, 0, 0), ()))
    with pytest.raises(ValueError):
        tracker.step(-0.1, (0, 0, 0), (0, 0, 0))
