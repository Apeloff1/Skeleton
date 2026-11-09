from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_lab import (
    ERA_PROFILES,
    REQUIRED_PATHS,
    Body,
    EngineEra,
    GameEngineEraLab,
    GameEngineLabError,
    NumericMode,
    SandboxPatch,
    Vec2,
    VirtualFileTree,
    build_engine_file_tree,
    engine_era_profile,
    list_engine_eras,
)


def test_era_ladder_is_chronological_from_pong_to_next() -> None:
    profiles = list_engine_eras()
    assert profiles[0].era is EngineEra.PONG
    assert profiles[0].start_year == 1972
    assert profiles[-1].era is EngineEra.NEXT
    assert profiles[-1].end_year is None
    assert len(profiles) == len(EngineEra) == len(ERA_PROFILES)
    assert [p.start_year for p in profiles] == sorted(p.start_year for p in profiles)


@pytest.mark.parametrize("era", list(EngineEra))
def test_each_era_builds_corresponding_complete_file_tree(era: EngineEra) -> None:
    tree = build_engine_file_tree(era, gameplay_dialect="soulslike")
    assert REQUIRED_PATHS <= set(tree.files)
    profile = engine_era_profile(era)
    manifest = json.loads(tree.read("engine/manifest.json"))
    assert manifest["engine_era"] == era.value
    assert manifest["gameplay_dialect"] == "soulslike"
    assert manifest["tick_hz"] == profile.tick_hz
    assert manifest["numeric_mode"] == profile.numeric_mode.value
    assert manifest["budgets"]["entities"] == profile.entity_budget
    assert f'ENGINE_ERA = "{era.value}"' in tree.read("engine/runtime.py")


def test_engine_technology_axis_is_orthogonal_to_gameplay_dialect() -> None:
    lab = GameEngineEraLab()
    a = lab.create(EngineEra.EIGHT_BIT, "metroidvania")
    b = lab.create(EngineEra.EIGHT_BIT, "jrpg")
    assert a.profile == b.profile
    assert a.gameplay_dialect != b.gameplay_dialect
    assert a.tree.digest != b.tree.digest


def test_tree_rejects_path_traversal_and_stale_patch() -> None:
    with pytest.raises(GameEngineLabError):
        VirtualFileTree({"../escape": "x"})
    tree = VirtualFileTree({"safe/file.txt": "v1"})
    with pytest.raises(GameEngineLabError, match="stale patch"):
        tree.apply([SandboxPatch("safe/file.txt", "v2", "0" * 64)])
    assert tree.read("safe/file.txt") == "v1"


def test_tree_snapshot_roundtrip_and_tamper_rejection() -> None:
    tree = build_engine_file_tree(EngineEra.PONG)
    snap = tree.snapshot(EngineEra.PONG, 0)
    restored = VirtualFileTree.restore(snap)
    assert restored.digest == tree.digest

    files = list(snap.files)
    path, content = files[0]
    files[0] = (path, content + "forged")
    forged = type(snap)(
        snap.schema_version, snap.era, snap.sequence, snap.parent_digest,
        snap.tree_digest, tuple(files)
    )
    with pytest.raises(GameEngineLabError, match="digest mismatch"):
        VirtualFileTree.restore(forged)


@pytest.mark.parametrize("era", list(EngineEra))
def test_runtime_replay_is_deterministic_for_every_era(era: EngineEra) -> None:
    sandbox = GameEngineEraLab().create(era)

    def run() -> str:
        runtime = sandbox.runtime(320, 200)
        runtime.spawn(Body("ball", Vec2(20, 30), Vec2(160, 95), Vec2(2, 2)))
        runtime.spawn(Body("wall", Vec2(160, 100), Vec2(0, 0), Vec2(5, 30), static=True))
        runtime.step(300)
        return runtime.fingerprint()

    assert run() == run()


def test_old_numeric_mode_quantizes_more_than_modern() -> None:
    lab = GameEngineEraLab()
    old = lab.create(EngineEra.PONG).runtime(100, 100)
    modern = lab.create(EngineEra.MODERN).runtime(100, 100)
    old.spawn(Body("b", Vec2(10.25, 10.75), Vec2(1.5, 2.5)))
    modern.spawn(Body("b", Vec2(10.25, 10.75), Vec2(1.5, 2.5)))
    assert old.profile.numeric_mode is NumericMode.INTEGER
    assert modern.profile.numeric_mode is NumericMode.FLOAT32
    assert old.bodies[0].position == Vec2(10.0, 11.0)
    assert modern.bodies[0].position != old.bodies[0].position


@pytest.mark.parametrize("era", list(EngineEra))
def test_bounds_and_collision_hold_across_eras(era: EngineEra) -> None:
    runtime = GameEngineEraLab().create(era).runtime(100, 100)
    runtime.spawn(Body("a", Vec2(45, 50), Vec2(30, 0), Vec2(6, 6)))
    runtime.spawn(Body("b", Vec2(55, 50), Vec2(-30, 0), Vec2(6, 6)))
    runtime.spawn(Body("edge", Vec2(95, 95), Vec2(500, 500), Vec2(2, 2)))
    runtime.step(20)
    for body in runtime.bodies:
        assert body.half_extent.x <= body.position.x <= runtime.width - body.half_extent.x
        assert body.half_extent.y <= body.position.y <= runtime.height - body.half_extent.y


@pytest.mark.parametrize("era", list(EngineEra))
def test_adversarial_suite_passes_canonical_engine_for_every_era(era: EngineEra) -> None:
    lab = GameEngineEraLab()
    report = lab.evaluate(lab.create(era, "arcade_golden_age"))
    assert report.passed
    assert report.score == 1.0
    assert report.failed == ()
    assert {"tree", "manifest", "snapshot", "tamper", "stale_patch", "replay", "bounds", "collision"} == {
        p.name for p in report.probes
    }


def test_corrupt_manifest_is_repaired_snapshotted_and_promoted() -> None:
    lab = GameEngineEraLab()
    sandbox = lab.create(EngineEra.SIXTEEN_BIT, "roguelike")
    baseline_snapshots = len(sandbox.snapshots)
    path = "engine/manifest.json"
    manifest = json.loads(sandbox.tree.read(path))
    manifest["engine_era"] = EngineEra.NEXT.value
    broken = sandbox.apply([
        SandboxPatch(
            path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            sandbox.tree.file_digest(path),
        )
    ])
    before = lab.evaluate(broken)
    assert not before.passed
    assert "manifest" in before.failed

    result = lab.adversarial_improve(broken, target=1.0, max_rounds=4)
    assert result.promoted
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert len(result.sandbox.snapshots) == baseline_snapshots + 1
    repaired = json.loads(result.sandbox.tree.read(path))
    assert repaired["engine_era"] == EngineEra.SIXTEEN_BIT.value
    assert repaired["gameplay_dialect"] == "roguelike"


def test_regressing_ai_proposal_is_not_promoted() -> None:
    lab = GameEngineEraLab()
    sandbox = lab.create(EngineEra.HD)
    path = "engine/manifest.json"
    manifest = json.loads(sandbox.tree.read(path))
    manifest["tick_hz"] = 999
    broken = sandbox.apply([
        SandboxPatch(path, json.dumps(manifest), sandbox.tree.file_digest(path))
    ])
    assert not lab.evaluate(broken).passed

    def bad_improver(current, report):
        del report
        return (
            SandboxPatch(
                "engine/physics.json",
                None,
                current.tree.file_digest("engine/physics.json"),
            ),
        )

    result = lab.adversarial_improve(broken, target=1.0, improver=bad_improver)
    assert not result.promoted
    assert len(result.rounds) == 1
    assert not result.rounds[0].accepted
    assert result.sandbox.tree.digest == broken.tree.digest


def test_snapshot_restore_recovers_prior_tree() -> None:
    sandbox = GameEngineEraLab().create(EngineEra.EARLY_3D)
    original = sandbox.tree.digest
    path = "game/main.scene.json"
    mutated = sandbox.apply([
        SandboxPatch(path, sandbox.tree.read(path) + "\n", sandbox.tree.file_digest(path))
    ]).snapshot()
    assert mutated.tree.digest != original
    assert mutated.restore(0).tree.digest == original


def test_pong_entity_budget_is_enforced() -> None:
    sandbox = GameEngineEraLab().create(EngineEra.PONG)
    runtime = sandbox.runtime(100, 100)
    for index in range(sandbox.profile.entity_budget):
        runtime.spawn(Body(f"b{index}", Vec2(1 + index * 2, 20), half_extent=Vec2(0.25, 0.25)))
    with pytest.raises(GameEngineLabError, match="entity budget"):
        runtime.spawn(Body("overflow", Vec2(1, 1)))


def test_live_model_cannot_bypass_patch_and_promotion_boundary() -> None:
    lab = GameEngineEraLab()
    assert not hasattr(lab, "ingest_model_output")
    assert not hasattr(lab, "self_modify")
    sandbox = lab.create(EngineEra.NEXT)
    assert sandbox.snapshots[-1].tree_digest == sandbox.tree.digest
