"""Launch readiness verification.

Runs the full AI game studio pipeline end-to-end and asserts
that the system is immediately usable for app launch.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure skeleton is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from skeleton.jeeves.launch import launch_build, get_facade
from skeleton.jeeves.launch.ai.behaviors import BehaviorSelector, BossPhaseController, CombatResolver, Action


def verify() -> bool:
    print("=== Launch Readiness Verification ===\n")

    # 1. Full pipeline
    brief = "A dark metroidvania where the player absorbs defeated enemy abilities and must defeat a three-phase boss."
    print(f"Brief: {brief}\n")
    result = launch_build(brief)
    print(f"Pipeline ok: {result.get('ok')}")
    print(f"Fidelity: {result.get('fidelity')}")
    print(f"Ready for launch: {result.get('ready_for_launch')}")
    print(f"Stages: {len(result.get('stages', []))}")
    print(f"Cards distilled: {result.get('cards_distilled')}")
    print(f"Concrete pack ready: {result.get('concrete', {}).get('ok')}")
    print(f"Rooms: {result.get('concrete', {}).get('rooms', {}).get('count')}")
    print(f"Boss phases: {len(result.get('concrete', {}).get('boss', {}).get('phases', []))}\n")

    # 2. Behavior systems
    selector = BehaviorSelector()
    assert selector.select(0.1, 0.8) == Action.FLEE
    assert selector.select(0.9, 0.2, distance=10) == Action.PATROL
    print("BehaviorSelector: PASS")

    boss = BossPhaseController(3)
    p1 = boss.update(0.9)
    p3 = boss.update(0.2)
    assert p3["phase"] >= 2
    print(f"BossPhaseController: phase {p3['phase']}, enraged={p3['enraged']} PASS")

    resolver = CombatResolver()
    hit = resolver.resolve(25, 40, armor=5)
    assert hit["damage_dealt"] == 20
    assert hit["defender_health"] == 20
    print("CombatResolver: PASS\n")

    # 3. Facade health
    facade = get_facade()
    health = facade.health()
    print(f"Facade health: {health}")
    sessions = facade.list_sessions()
    print(f"Active sessions: {len(sessions)}")
    knowledge = facade.knowledge()
    print(f"Knowledge cards: {len(knowledge)}\n")

    # 4. Fail-closed checks
    try:
        facade.start("")
        print("FAIL: empty brief should raise")
        return False
    except ValueError:
        print("Fail-closed empty brief: PASS")

    overall = result.get("ready_for_launch") and result.get("ok")
    print(f"\n=== OVERALL: {'READY FOR LAUNCH' if overall else 'NOT READY'} ===")
    return bool(overall)


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
