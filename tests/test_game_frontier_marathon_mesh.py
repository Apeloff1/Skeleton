"""GF-P1-08 and GF-P1-22: deterministic mesh LOD and skin-weight transfer."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from skeleton.frontier_mesh import (
    SEAM_POSITION_EPSILON,
    FrontierMeshError,
    Vec3,
    closest_point,
    directed_hausdorff,
    from_era_mesh,
    from_skinned_mesh,
    make_mesh,
    make_vertex,
    retarget,
    simplify_lod,
    vertex_digest,
)
from skeleton.jeeves.game_frontier_mesh_evolution import EraMesh
from skeleton.jeeves.game_frontier_production import (
    Bone,
    CharacterSkeleton,
    SkinnedMesh,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skeleton" / "frontier_mesh"


def _vertex(position, normal, uv, weights):
    return make_vertex(position, normal, uv, weights)


def _quad():
    """Two coplanar triangles. Edge (0, 1) is the deterministic first collapse."""
    vertices = (
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("knee", 1.0),)),
        _vertex((0, 1, 0), (0, 0, 1), (0.0, 1.0), (("hip", 1.0),)),
        _vertex((1, 1, 0), (0, 0, 1), (1.0, 1.0), (("knee", 0.25), ("hip", 0.75))),
    )
    return make_mesh(vertices, (((0, 1, 3), "cloth"), ((0, 3, 2), "cloth")))


def _pyramid():
    height = math.sqrt(3.0) / 2.0
    vertices = (
        _vertex((0.0, 0.0, 0.0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1.0, 0.0, 0.0), (0, 0, 1), (1.0, 0.0), (("knee", 1.0),)),
        _vertex((0.5, height, 0.0), (0, 0, 1), (0.5, 1.0), (("hip", 0.5), ("knee", 0.5))),
        _vertex((0.5, height / 3.0, 1.0), (0, 1, 0), (0.5, 0.5), (("hip", 0.25), ("knee", 0.75))),
    )
    faces = (
        ((0, 1, 3), "stone"),
        ((1, 2, 3), "stone"),
        ((2, 0, 3), "stone"),
        ((0, 1, 2), "stone"),
    )
    return make_mesh(vertices, faces)


def _seam_sheet():
    """Cloth and skin share the x=1 edge as duplicated vertices."""
    vertices = (
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("hip", 1.0),)),
        _vertex((0, 1, 0), (0, 0, 1), (0.0, 1.0), (("knee", 1.0),)),
        _vertex((1, 1, 0), (0, 0, 1), (1.0, 1.0), (("knee", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 1, 0), (0, 0, 1), (1.0, 1.0), (("knee", 1.0),)),
        _vertex((2, 0, 0), (0, 0, 1), (2.0, 0.0), (("hip", 1.0),)),
        _vertex((2, 1, 0), (0, 0, 1), (2.0, 1.0), (("knee", 1.0),)),
    )
    faces = (
        ((0, 1, 3), "cloth"),
        ((0, 3, 2), "cloth"),
        ((4, 6, 5), "skin"),
        ((6, 7, 5), "skin"),
    )
    return make_mesh(vertices, faces)


def _table(vertex):
    return {entry.bone_name: entry.weight for entry in vertex.weights}


def _expected_weights(position, source, allowed=None):
    hit = closest_point(position, source)
    corners = tuple(source.vertices[index] for index in source.triangles[hit.triangle_index].indices)
    mixed: dict[str, float] = {}
    for bary, corner in zip(hit.barycentric, corners, strict=True):
        for entry in corner.weights:
            if allowed is not None and entry.bone_name not in allowed:
                continue
            mixed[entry.bone_name] = mixed.get(entry.bone_name, 0.0) + bary * entry.weight
    total = math.fsum(mixed.values())
    return {name: value / total for name, value in mixed.items()}


def test_seam_epsilon_is_documented_and_used():
    text = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assert SEAM_POSITION_EPSILON == 1e-6
    assert "SEAM_POSITION_EPSILON" in text
    assert "1e-6" in text
    assert "bone name" in text.lower()


def test_closest_point_barycentric_and_distance_are_measured():
    mesh = _quad()
    centroid = Vec3(1.0 / 3.0, 1.0 / 3.0, 0.0)
    # The quad's first triangle is (0, 1, 3): (0,0,0), (1,0,0), (1,1,0).
    hit = closest_point(Vec3(0.5, 0.0, 2.0), mesh)
    assert hit.triangle_index == 0
    assert hit.distance == pytest.approx(2.0)
    assert hit.barycentric[2] == pytest.approx(0.0)
    assert hit.barycentric[0] == pytest.approx(0.5)
    assert hit.barycentric[1] == pytest.approx(0.5)
    above = directed_hausdorff((Vec3(0.5, 0.0, 2.0), Vec3(0.0, 0.0, 0.0)), mesh)
    assert above == pytest.approx(2.0)
    assert closest_point(centroid, _single_triangle()).distance == pytest.approx(0.0)


def _single_triangle():
    vertices = (
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("knee", 1.0),)),
        _vertex((0, 1, 0), (0, 0, 1), (0.0, 1.0), (("hip", 0.5), ("knee", 0.5))),
    )
    return make_mesh(vertices, (((0, 1, 2), "cloth"),))


def test_centroid_weights_follow_barycentric_coordinates():
    mesh = _single_triangle()
    hit = closest_point(Vec3(1.0 / 3.0, 1.0 / 3.0, 0.0), mesh)
    assert hit.distance == pytest.approx(0.0, abs=1e-8)
    assert hit.barycentric == pytest.approx((1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), abs=1e-8)


def test_lod_reaches_budget_and_is_deterministic():
    mesh = _pyramid()
    first = simplify_lod(mesh, 2)
    second = simplify_lod(mesh, 2)
    assert first.mesh.face_count <= 2
    assert first.mesh.face_count == second.mesh.face_count == 2
    assert first.vertex_digest == second.vertex_digest
    assert first.vertex_digest == vertex_digest(first.mesh)
    assert first.hausdorff_max == second.hausdorff_max
    assert first.seam_position_delta == second.seam_position_delta
    untouched = simplify_lod(mesh, 4)
    assert untouched.mesh.face_count == 4
    assert untouched.vertex_digest != first.vertex_digest
    assert simplify_lod(mesh, 4).vertex_digest == untouched.vertex_digest


def test_same_source_and_budget_match_through_retarget():
    mesh = _pyramid()
    lodged = simplify_lod(mesh, 2)
    forwarded = retarget(
        mesh,
        target_bones=("hip", "knee"),
        uv_scale=(1.0, 1.0),
        position_scale=1.0,
        face_budget=2,
    )
    again = retarget(
        mesh,
        target_bones=("knee", "hip"),
        uv_scale=(1.0, 1.0),
        position_scale=1.0,
        face_budget=2,
    )
    assert lodged.vertex_digest == forwarded.vertex_digest == again.vertex_digest


def test_weights_are_transferred_from_the_closest_source_point():
    source = _quad()
    lodged = simplify_lod(source, 1)
    assert lodged.mesh.face_count == 1
    moved = next(
        vertex
        for vertex in lodged.mesh.vertices
        if not any(
            abs(vertex.position.x - original.position.x) < 1e-8
            and abs(vertex.position.y - original.position.y) < 1e-8
            and abs(vertex.position.z - original.position.z) < 1e-8
            for original in source.vertices
        )
    )
    assert moved.position.x == pytest.approx(0.5)
    assert moved.position.y == pytest.approx(0.0)
    assert moved.position.z == pytest.approx(0.0)
    assert _table(moved)["hip"] == pytest.approx(0.5)
    assert _table(moved)["knee"] == pytest.approx(0.5)
    for vertex in lodged.mesh.vertices:
        expected = _expected_weights(vertex.position, source)
        observed = _table(vertex)
        names = set(observed) | {name for name, value in expected.items() if value > 1e-8}
        assert set(observed) == names
        for name in names:
            assert observed[name] == pytest.approx(expected[name], abs=1e-6)
        assert sum(observed.values()) == pytest.approx(1.0)
        length = math.sqrt(vertex.normal.dot(vertex.normal))
        assert length == pytest.approx(1.0)


def test_hausdorff_is_computed_per_vertex_and_is_not_a_constant():
    flat = simplify_lod(_quad(), 1)
    peaked = simplify_lod(_pyramid(), 2)
    flat_measured = directed_hausdorff(
        [vertex.position for vertex in flat.mesh.vertices],
        _quad(),
    )
    peaked_measured = directed_hausdorff(
        [vertex.position for vertex in peaked.mesh.vertices],
        _pyramid(),
    )
    assert flat.hausdorff_max == pytest.approx(flat_measured)
    assert peaked.hausdorff_max == pytest.approx(peaked_measured)
    assert flat.hausdorff_max == pytest.approx(0.0, abs=1e-8)
    assert peaked.hausdorff_max > 1e-3
    assert flat.hausdorff_max != peaked.hausdorff_max


def test_seam_copies_keep_matching_positions():
    source = _seam_sheet()
    lodged = simplify_lod(source, 3)
    assert lodged.mesh.face_count == 3
    assert lodged.seam_position_delta <= SEAM_POSITION_EPSILON
    assert lodged.seam_position_delta == pytest.approx(0.0, abs=1e-9)
    moved = [
        vertex.position
        for vertex in lodged.mesh.vertices
        if abs(vertex.position.x - 0.5) < 1e-8 and abs(vertex.position.y) < 1e-8
    ]
    assert len(moved) == 2
    assert distance_pair(moved[0], moved[1]) <= SEAM_POSITION_EPSILON
    materials = {triangle.material for triangle in lodged.mesh.triangles}
    assert materials == {"cloth", "skin"}


def distance_pair(a, b):
    delta = a - b
    return math.sqrt(delta.dot(delta))


def test_shared_seam_vertex_has_zero_delta():
    vertices = (
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("knee", 1.0),)),
        _vertex((0, 1, 0), (0, 0, 1), (0.0, 1.0), (("hip", 1.0),)),
        _vertex((1, 0, 1), (0, 1, 0), (1.0, 1.0), (("knee", 1.0),)),
    )
    mesh = make_mesh(
        vertices,
        (
            ((0, 1, 2), "cloth"),
            ((0, 2, 3), "skin"),
        ),
    )
    lodged = simplify_lod(mesh, 2)
    assert lodged.seam_position_delta == pytest.approx(0.0, abs=1e-12)
    assert lodged.mesh.face_count == 2


def test_retarget_scales_positions_uvs_and_keeps_unit_normals():
    source = _quad()
    result = retarget(
        source,
        target_bones=("hip", "knee"),
        uv_scale=(2.0, 0.5),
        position_scale=3.0,
    )
    assert result.mesh.face_count == source.face_count
    for before, after in zip(source.vertices, result.mesh.vertices, strict=True):
        assert after.position.x == pytest.approx(before.position.x * 3.0)
        assert after.position.y == pytest.approx(before.position.y * 3.0)
        assert after.position.z == pytest.approx(before.position.z * 3.0)
        assert after.uv[0] == pytest.approx(before.uv[0] * 2.0)
        assert after.uv[1] == pytest.approx(before.uv[1] * 0.5)
        assert math.sqrt(after.normal.dot(after.normal)) == pytest.approx(1.0)
        assert after.normal.z == pytest.approx(1.0)
    flipped = retarget(
        source,
        target_bones=("hip", "knee"),
        uv_scale=(1.0, 1.0),
        position_scale=-1.0,
    )
    for vertex in flipped.mesh.vertices:
        assert vertex.normal.z == pytest.approx(-1.0)
        assert math.sqrt(vertex.normal.dot(vertex.normal)) == pytest.approx(1.0)
    assert flipped.vertex_digest == retarget(
        source,
        target_bones=("hip", "knee"),
        uv_scale=(1.0, 1.0),
        position_scale=-1.0,
    ).vertex_digest


def test_retarget_rejects_target_bones_outside_the_source():
    source = _quad()
    with pytest.raises(FrontierMeshError, match="not a subset of the source"):
        retarget(source, target_bones=("hip", "tail"), uv_scale=(1.0, 1.0))


def test_retarget_rejects_non_finite_coordinates():
    with pytest.raises(FrontierMeshError, match="non-finite coordinate"):
        _vertex((float("nan"), 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),))
    with pytest.raises(FrontierMeshError, match="non-finite coordinate"):
        _vertex((0, 0, 0), (0, 0, 1), (float("inf"), 0.0), (("hip", 1.0),))
    source = _quad()
    with pytest.raises(FrontierMeshError, match="non-finite coordinate"):
        retarget(source, target_bones=("hip",), uv_scale=(float("nan"), 1.0))
    with pytest.raises(FrontierMeshError, match="non-finite coordinate"):
        retarget(source, target_bones=("hip", "knee"), uv_scale=(1.0, 1.0), position_scale=float("inf"))


def test_retarget_rejects_zero_area_triangles():
    vertices = (
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 1.0),)),
        _vertex((1, 0, 0), (0, 0, 1), (1.0, 0.0), (("hip", 1.0),)),
        _vertex((2, 0, 0), (0, 0, 1), (2.0, 0.0), (("hip", 1.0),)),
    )
    with pytest.raises(FrontierMeshError, match="zero-area triangle"):
        make_mesh(vertices, (((0, 1, 2), "cloth"),))
    with pytest.raises(FrontierMeshError, match="zero-area triangle"):
        retarget(_quad(), target_bones=("hip", "knee"), uv_scale=(1.0, 1.0), position_scale=0.0)


def test_weight_table_must_sum_to_one_before_and_after_transfer():
    with pytest.raises(FrontierMeshError, match="weight table does not sum to 1"):
        _vertex((0, 0, 0), (0, 0, 1), (0.0, 0.0), (("hip", 0.2), ("knee", 0.2)))
    source = _quad()
    with pytest.raises(FrontierMeshError, match="weight table does not sum to 1"):
        retarget(source, target_bones=("knee",), uv_scale=(1.0, 1.0))


def test_retarget_onto_target_topology_uses_source_weights_by_bone_name():
    source = _quad()
    lifted = []
    for vertex in source.vertices:
        lifted.append(
            _vertex(
                (vertex.position.x, vertex.position.y, vertex.position.z + 0.3),
                (0, 0, 1),
                vertex.uv,
                tuple((entry.bone_name, entry.weight) for entry in vertex.weights),
            )
        )
    target = make_mesh(
        lifted,
        tuple((triangle.indices, triangle.material) for triangle in source.triangles),
    )
    result = retarget(source, target_mesh=target, uv_scale=(4.0, 1.0), position_scale=1.0)
    assert result.hausdorff_max == pytest.approx(0.3, abs=1e-6)
    measured = directed_hausdorff([vertex.position for vertex in result.mesh.vertices], source)
    assert result.hausdorff_max == pytest.approx(measured)
    for before, after in zip(source.vertices, result.mesh.vertices, strict=True):
        assert after.uv[0] == pytest.approx(before.uv[0] * 4.0)
        assert _table(after) == pytest.approx(_table(before))
        assert math.sqrt(after.normal.dot(after.normal)) == pytest.approx(1.0)
    hostile = make_mesh(
        (
            _vertex((0, 0, 0.3), (0, 0, 1), (0.0, 0.0), (("tail", 1.0),)),
            _vertex((1, 0, 0.3), (0, 0, 1), (1.0, 0.0), (("hip", 1.0),)),
            _vertex((0, 1, 0.3), (0, 0, 1), (0.0, 1.0), (("knee", 1.0),)),
        ),
        (((0, 1, 2), "cloth"),),
    )
    with pytest.raises(FrontierMeshError, match="not a subset of the source"):
        retarget(source, target_mesh=hostile, uv_scale=(1.0, 1.0))


def test_from_skinned_mesh_reuses_vec3_and_bone_names():
    skeleton = CharacterSkeleton(
        (
            Bone("hip", -1, Vec3(0, 0, 0), Vec3(0, 1, 0), 0.2),
            Bone("knee", 0, Vec3(0, 1, 0), Vec3(0, 2, 0), 0.15),
        )
    )
    skinned = SkinnedMesh(
        (Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)),
        ((0, 1, 2), (0, 2, 3)),
        (0, 1, 0, 1),
        (),
        "shader",
        1.0,
    )
    surface = from_skinned_mesh(
        skinned,
        skeleton,
        face_materials=("cloth", "skin"),
    )
    assert all(isinstance(vertex.position, Vec3) for vertex in surface.vertices)
    assert _table(surface.vertices[0]) == {"hip": 1.0}
    assert _table(surface.vertices[1]) == {"knee": 1.0}
    assert _table(surface.vertices[3]) == {"knee": 1.0}
    assert {triangle.material for triangle in surface.triangles} == {"cloth", "skin"}
    lodged = simplify_lod(surface, 2)
    assert lodged.mesh.face_count <= 2
    assert lodged.vertex_digest == simplify_lod(surface, 2).vertex_digest
    for vertex in lodged.mesh.vertices:
        assert set(_table(vertex)) <= {"hip", "knee"}
        assert sum(_table(vertex).values()) == pytest.approx(1.0)


def test_from_era_mesh_reuses_normals_and_source_pixels_without_decoding():
    era = EraMesh(
        source_digest="ab" * 32,
        era="shader",
        vertices=(Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)),
        triangles=((0, 1, 2),),
        vertex_normals=(Vec3(0, 0, 2), Vec3(0, 0, 2), Vec3(0, 0, 2)),
        source_pixels=((0, 0), (2, 0), (0, 2)),
        source_width=2,
        source_height=2,
        pixel_resolution=1,
        depth_m=0.1,
    )
    surface = from_era_mesh(era, bone_name="hip")
    assert surface.vertices[1].uv == pytest.approx((1.0, 0.0))
    assert surface.vertices[2].uv == pytest.approx((0.0, 1.0))
    assert surface.vertices[0].normal.z == pytest.approx(1.0)
    assert _table(surface.vertices[0]) == {"hip": 1.0}


def test_package_has_no_stubs_image_decode_or_gpu():
    banned = ("NotImplemented", "PIL", "torch", "cuda", "cv2", "imageio", "wgpu")
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "pass\n" not in text
        for token in banned:
            assert token not in text


def test_face_budget_that_cannot_be_reached_is_rejected():
    with pytest.raises(FrontierMeshError, match="face budget unreachable"):
        simplify_lod(_pyramid(), 1)
    with pytest.raises(FrontierMeshError, match="face budget must be a positive integer"):
        simplify_lod(_quad(), 0)
