from skeleton.frontier.worldsim.navigation import NavGrid, find_path, reachability_report
from skeleton.frontier.worldsim.streaming import StreamBudget, plan_tick
from skeleton.frontier.worldsim.world_time import WorldClock, ScheduleEntry, resolve_world, transitions


def test_nav_path_and_dynamic_obstacle():
    g = NavGrid.from_rows(["....", ".##.", "...."])
    p = find_path(g, (0, 0), (3, 2))
    assert p[0] == (0, 0) and p[-1] == (3, 2) and len(p) == 6
    g.set_obstacles({(1, 0), (0, 1)})
    assert find_path(g, (0, 0), (3, 2)) is None
    assert reachability_report(g, (0, 0), [(3, 2)])["unreachable"] == [(3, 2)]


def test_streaming_budget():
    sizes = {(x, y): 10 for x in range(-2, 3) for y in range(-2, 3)}
    p = plan_tick((0, 0), [(2, 2)], sizes, StreamBudget(memory_bytes=40, max_loads_per_tick=3, radius=1))
    assert p.load[0] == (0, 0) and len(p.load) == 3 and p.unload == ((2, 2),)
    assert p.resident_bytes <= 40 and len(p.deferred) == 6


def test_world_time_schedules_deterministic_and_save_compatible():
    s = {"smith": [ScheduleEntry(8, "work", "forge"), ScheduleEntry(20, "sleep", "home")]}
    c = WorldClock().advance(60 * 7)
    assert resolve_world(c, s)["smith"]["activity"] == "sleep"
    n = c.advance(60)
    assert transitions(c, n, s)[0]["to"]["activity"] == "work"
    assert WorldClock.from_dict(n.to_dict()) == n and n.day == 0 and n.hour == 8
