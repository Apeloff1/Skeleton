"""Safe data-only Godot 4 overlay exporter for existing Jeeves frontier scenes.

Returns relative project files; canonical Forge materialisation must authorize
writes. This does NOT install Godot, execute model output, or ship a full game.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from skeleton.jeeves.game_frontier import FrontierSceneCandidate


class FrontierGodotError(ValueError):
    pass


_GDSCRIPT = r'''extends Node3D
## Fixed exporter script: no generated/model-supplied executable source.
var _cloud_visuals: Array[MeshInstance3D] = []
var _cloud_tracks: Array = []
var _cloud_elapsed: float = 0.0
var _cloud_step_s: float = 1.0
var _cloud_duration_s: float = 1.0
var _aero_character: RigidBody3D
var _aero_wind: Vector3 = Vector3.ZERO
var _aero_density: float = 1.2
var _aero_cd: float = 1.0
var _aero_area: float = 0.7

func _vec(data: Array) -> Vector3:
    return Vector3(float(data[0]), float(data[2]), -float(data[1]))

func _ready() -> void:
    var path := "res://frontier/data/scene.json"
    if not FileAccess.file_exists(path):
        push_error("Frontier data missing")
        return
    var data = JSON.parse_string(FileAccess.get_file_as_string(path))
    if typeof(data) != TYPE_DICTIONARY or data.get("schema") != "skeleton.game.frontier_godot_overlay.v1":
        push_error("Invalid frontier data")
        return
    Engine.max_fps = int(data["requested_fps"])
    var suite: Dictionary = data.get("character_suite", {})
    if typeof(suite.get("elastic_skin3d")) == TYPE_DICTIONARY:
        _create_elastic_body_skin(suite["elastic_skin3d"], data["geometry"])
    else:
        _create_character(data["geometry"], data["colliders"])
    _create_character_suite_inspector(suite)
    _create_clouds(data["clouds"])
    _create_environment(data["world"])
    _create_camera(data.get("projection", {}), data.get("world_variant", {}))
    _create_lighting(data.get("world_variant", {}),
                     data.get("photometric_3d", []), data.get("atmosphere", {}))
    _create_water(data.get("liquid", {}), data.get("tides", {}))
    _create_leaf_shadows(data.get("leaf_shadows", []))
    _create_biome_objects(data.get("biome_motion", {}))
    _create_advanced_character(data.get("advanced_physics", {}))
    _cloud_step_s = float(data["cloud_step_s"])
    _cloud_duration_s = float(data["cloud_duration_s"])

func _create_elastic_body_skin(info: Dictionary, geometry: Dictionary) -> void:
    # Real SoftBody3D preview path. Native solver acceptance, pin stability,
    # and accurate skin tissue biomechanics remain separate engine checks.
    var points: Array = info.get("positions_xyz", [])
    var triangles: Array = geometry.get("triangles", [])
    if points.is_empty() or triangles.is_empty():
        push_error("ElasticBodySkin3D missing mesh topology")
        return
    var pins: Array = info.get("pinned_vertices", [])
    # Preserve indexed adjacency in ArrayMesh. A non-indexed SurfaceTool
    # triangle soup breaks shared soft-body edges and produces disconnected
    # pieces under native simulation.
    var vertices := PackedVector3Array()
    for point in points:
        vertices.append(_vec(point))
    var normal_accum: Array[Vector3] = []
    normal_accum.resize(vertices.size())
    normal_accum.fill(Vector3.ZERO)
    var indices := PackedInt32Array()
    for face in triangles:
        if face.size() != 3:
            push_error("ElasticBodySkin3D non-triangle face")
            return
        var ia := int(face[0])
        var ib := int(face[1])
        var ic := int(face[2])
        if min(ia, min(ib, ic)) < 0 or max(ia, max(ib, ic)) >= points.size():
            push_error("ElasticBodySkin3D invalid mesh index")
            return
        indices.append_array(PackedInt32Array([ia, ib, ic]))
        var face_normal := (vertices[ib] - vertices[ia]).cross(
            vertices[ic] - vertices[ia])
        normal_accum[ia] += face_normal
        normal_accum[ib] += face_normal
        normal_accum[ic] += face_normal
    var normals := PackedVector3Array()
    for normal in normal_accum:
        normals.append(normal.normalized() if normal.length() > .00001 else Vector3.UP)
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = indices
    var native_mesh := ArrayMesh.new()
    native_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    var soft := SoftBody3D.new()
    soft.name = "ElasticBodySkin3D"
    soft.mesh = native_mesh
    soft.total_mass = max(.01, float(info.get("mass_per_vertex_kg", .04)) * float(points.size()))
    soft.linear_stiffness = clamp(float(info.get("shear_stiffness", 8.0)) / 100.0, .01, 1.0)
    soft.damping_coefficient = clamp(float(info.get("damping", 1.0)) / 50.0, 0.0, 1.0)
    soft.simulation_precision = 8
    soft.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
    add_child(soft)
    for point_index in pins:
        soft.set_point_pinned(int(point_index), true)

func _create_character_suite_inspector(suite: Dictionary) -> void:
    if suite.is_empty():
        return
    var mass: Variant = suite.get("weight_distribution")
    if typeof(mass) == TYPE_DICTIONARY:
        var marker := Marker3D.new()
        marker.name = "CenterOfMassCandidate"
        marker.position = _vec(mass["center_of_mass_xyz"])
        add_child(marker)
    var navigation: Variant = suite.get("instruments")
    var rpg: Variant = suite.get("rpg_events")
    var rows: Array = []
    if typeof(navigation) == TYPE_DICTIONARY:
        rows = navigation.get("readings", [])
    var proposed: Array = []
    if typeof(rpg) == TYPE_DICTIONARY:
        proposed = rpg.get("accepted", [])
    if rows.is_empty() and proposed.is_empty():
        return
    var panel := CanvasLayer.new()
    panel.name = "NavigationInstrumentInspector"
    var label := Label.new()
    label.name = "SimulatedInstrumentReadings"
    label.position = Vector2(16, 16)
    label.text = "SIMULATED INSTRUMENTS (NOT GPS)\\n"
    for record in rows:
        var fields: Dictionary = record.get("fields", {})
        label.text += str(record.get("type", "sensor")) + ": " + str(fields) + "\\n"
    if not proposed.is_empty():
        label.text += "RPG ENVIRONMENT PROPOSALS (NOT EXECUTED)\\n"
        for event in proposed:
            label.text += str(event.get("page", "event")) + ": " + str(event.get("actions", [])) + "\\n"
    panel.add_child(label)
    add_child(panel)

func _create_camera(spec: Dictionary, variant: Dictionary) -> void:
    var camera := Camera3D.new()
    camera.name = "FrontierCamera"
    var mode: String = str(spec.get("mode", "3d"))
    if mode == "top_down":
        camera.projection = Camera3D.PROJECTION_ORTHOGONAL
        camera.size = 16.0
        camera.position = Vector3(0, 18, .01)
        add_child(camera)
        camera.look_at(Vector3(0, 0, 0), Vector3(0, 0, -1))
    elif mode == "platformer":
        camera.projection = Camera3D.PROJECTION_ORTHOGONAL
        camera.size = 12.0
        camera.position = Vector3(0, 2.5, 16)
        add_child(camera)
        camera.look_at(Vector3(0, 2, 0))
    else:
        camera.projection = Camera3D.PROJECTION_PERSPECTIVE
        camera.position = Vector3(9, 6, 16)
        if mode.begins_with("2."):
            var depth_weight := float(mode.replace("2.", "").replace("d", "")) / 10.0
            camera.fov = lerp(43.0, 72.0, depth_weight)
            camera.position.z = lerp(20.0, 12.0, depth_weight)
        if str(variant.get("family", "")) == "lensed":
            camera.fov = clamp(camera.fov + 12.0 * float(variant.get("intensity", 0.0)),
                               20.0, 100.0)
        add_child(camera)
        camera.look_at(Vector3(0, 1, 0))
    camera.current = true

func _create_lighting(variant: Dictionary, ray_samples: Array, air: Dictionary) -> void:
    var sunlight := DirectionalLight3D.new()
    sunlight.rotation_degrees = Vector3(-45, 30, 0)
    sunlight.shadow_enabled = true
    var strength := max(.03, float(variant.get("luminance", .7)) * 1.4)
    # Atmospheric transmission is already measured by the source CPU rays.
    # Don't multiply by its geometric shadows again: the Godot shadow map
    # handles 3D cast geometry separately.
    if not ray_samples.is_empty():
        var sum_transmission := 0.0
        for sample in ray_samples:
            sum_transmission += clamp(float(sample.get("volumetric_transmission", 1)), 0, 1)
        strength *= max(.01, sum_transmission / float(ray_samples.size()))
    sunlight.light_energy = strength
    add_child(sunlight)
    if air.has("visibility_m"):
        var view_distance := max(1.0, float(air["visibility_m"]))
        var world_env := WorldEnvironment.new()
        world_env.environment = Environment.new()
        world_env.environment.fog_enabled = view_distance < 20000
        world_env.environment.fog_density = clamp(1.0 / view_distance, 0.0, .05)
        add_child(world_env)

func _create_water(liquid: Dictionary, tides: Dictionary) -> void:
    if liquid.is_empty():
        return
    var depths: Array = liquid.get("depths_m", [])
    if depths.is_empty():
        return
    var water_level := max(0.0, float(depths[0]) + float(tides.get("water_height_m", 0.0)))
    if water_level < .001:
        return
    var water := MeshInstance3D.new()
    water.name = "FrontierLiquidSurface"
    var plane := PlaneMesh.new()
    plane.size = Vector2(12, 12)
    water.mesh = plane
    water.position.y = water_level
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(.08, .35, .7, .72)
    material.metallic = .1
    material.roughness = .16
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    water.material_override = material
    add_child(water)

func _create_leaf_shadows(records: Array) -> void:
    for record in records:
        if not bool(record.get("double_verified", false)):
            push_warning("Leaf shadow coherence failed; suppress shadow polygon")
            continue
        var vertices: Array = record.get("polygon_xyz", [])
        if vertices.size() != 4:
            continue
        var builder := SurfaceTool.new()
        builder.begin(Mesh.PRIMITIVE_TRIANGLES)
        for index in [0, 1, 2, 0, 2, 3]:
            var point := _vec(vertices[index])
            point.y += .02
            builder.add_vertex(point)
        builder.generate_normals()
        var leaf_shadow := MeshInstance3D.new()
        leaf_shadow.name = "VerifiedLeafShadow"
        leaf_shadow.mesh = builder.commit()
        var material := StandardMaterial3D.new()
        material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        material.albedo_color = Color(0, .02, .03, .38)
        material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        material.cull_mode = BaseMaterial3D.CULL_DISABLED
        leaf_shadow.material_override = material
        leaf_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
        add_child(leaf_shadow)

func _create_biome_objects(biome: Dictionary) -> void:
    for shrub in biome.get("shrubs", []):
        var root := _vec(shrub["root"])
        var tip := _vec(shrub["tip"])
        var axis := tip - root
        if axis.length() < .01:
            continue
        var foliage := MeshInstance3D.new()
        foliage.name = "MotionAwareShrub"
        var shape := CylinderMesh.new()
        shape.top_radius = float(shrub["radius_m"]) * .7
        shape.bottom_radius = float(shrub["radius_m"])
        shape.height = axis.length()
        foliage.mesh = shape
        foliage.position = (root + tip) * .5
        foliage.quaternion = Quaternion(Vector3.UP, axis.normalized())
        var material := StandardMaterial3D.new()
        material.albedo_color = Color(.18, .5, .2)
        foliage.material_override = material
        foliage.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
        add_child(foliage)
    for rock in biome.get("rocks", []):
        var node := MeshInstance3D.new()
        node.name = "ImpactAwareRock"
        var mesh := SphereMesh.new()
        mesh.radius = float(rock["radius_m"])
        mesh.height = mesh.radius * 2
        node.mesh = mesh
        node.position = _vec(rock["position"])
        node.rotation.z = float(rock["rotation_radians"])
        node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
        add_child(node)

func _create_advanced_character(info: Dictionary) -> void:
    if info.is_empty() or str(info.get("authority", "")) != "candidate_only_no_native_mutation":
        return
    var body_data: Dictionary = info.get("body", {})
    var aero: Dictionary = info.get("aero_coefficients", {})
    if body_data.is_empty() or aero.is_empty():
        return
    var radius := float(body_data.get("radius_m", 0.5))
    var mass := float(body_data.get("mass_kg", 80.0))
    if radius <= 0 or mass <= 0:
        return
    var dynamic := RigidBody3D.new()
    dynamic.name = "AdvancedPhysicsReferenceBody"
    dynamic.mass = mass
    dynamic.position = _vec(body_data["position_xyz"])
    dynamic.linear_velocity = _vec(body_data["velocity_xyz"])
    dynamic.angular_velocity = _vec(body_data["angular_velocity_xyz"])
    var sphere := SphereShape3D.new()
    sphere.radius = radius
    var collider := CollisionShape3D.new()
    collider.shape = sphere
    dynamic.add_child(collider)
    var render := MeshInstance3D.new()
    var shape := SphereMesh.new()
    shape.radius = radius
    shape.height = radius * 2
    render.mesh = shape
    render.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
    dynamic.add_child(render)
    var physical := PhysicsMaterial.new()
    var terrain_grip: Dictionary = info.get("traction", {})
    var slip_risk := clamp(float(terrain_grip.get("slip_risk", 0.0)), 0.0, 1.0)
    # Wet/icy terrain reduces friction; do not amplify native grip above its
    # validated material coefficient. Real grip changes with surface contact
    # must later be handled by engine-authoritative contact callbacks.
    physical.friction = clamp(
        float(body_data.get("friction", .6)) * (1.0 - slip_risk * .8), 0.0, 1.0)
    physical.bounce = clamp(float(body_data.get("restitution", .1)), 0.0, 1.0)
    dynamic.physics_material_override = physical
    add_child(dynamic)
    _aero_character = dynamic
    _aero_wind = _vec(info["airflow_velocity_xyz"])
    _aero_density = clamp(float(info["air_density_kg_m3"]), .01, 10.0)
    _aero_cd = clamp(float(aero.get("drag_coefficient", 1.0)), .001, 5.0)
    _aero_area = clamp(float(aero.get("projected_area_m2", .7)), .001, 10000.0)

func _physics_process(delta: float) -> void:
    if _aero_character == null or delta < 0:
        return
    # Native solver updates the body after each fixed physics tick. Apply
    # quadratic air drag using *current* relative wind, not a stale impulse.
    var relative := _aero_character.linear_velocity - _aero_wind
    var speed := relative.length()
    var drag_n := -0.5 * _aero_density * _aero_cd * _aero_area * speed * relative
    _aero_character.apply_central_force(drag_n)

func _create_character(geometry: Dictionary, colliders: Array) -> void:
    var verts: Array = geometry["vertices"]
    var triangles: Array = geometry["triangles"]
    var builder := SurfaceTool.new()
    builder.begin(Mesh.PRIMITIVE_TRIANGLES)
    for triangle in triangles:
        for index in triangle:
            builder.add_vertex(_vec(verts[int(index)]))
    builder.generate_normals()
    var instance := MeshInstance3D.new()
    instance.mesh = builder.commit()
    var mat := StandardMaterial3D.new()
    mat.albedo_color = Color(0.53, 0.75, 0.88, 1)
    instance.material_override = mat
    add_child(instance)
    var body := StaticBody3D.new()
    body.name = "GeneratedSkeletonCollision"
    add_child(body)
    for item in colliders:
        var head := _vec(item["head"])
        var tail := _vec(item["tail"])
        var radius := float(item["radius_m"])
        var capsule := CapsuleShape3D.new()
        capsule.radius = radius
        capsule.height = max(radius * 2.0, head.distance_to(tail) + 2.0 * radius)
        var collision := CollisionShape3D.new()
        collision.shape = capsule
        collision.position = (head + tail) / 2.0
        collision.quaternion = Quaternion(Vector3.UP, (tail - head).normalized())
        body.add_child(collision)

func _create_clouds(tracks: Array) -> void:
    _cloud_tracks = tracks
    for track in tracks:
        var instance := MeshInstance3D.new()
        instance.name = "WindDrivenCloud"
        var sphere := SphereMesh.new()
        sphere.radius = 0.5
        sphere.height = 0.5
        instance.mesh = sphere
        var material := StandardMaterial3D.new()
        material.albedo_color = Color(0.89, 0.93, 1.0, float(track["opacity"]))
        material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
        instance.material_override = material
        instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
        add_child(instance)
        _cloud_visuals.append(instance)
    _update_clouds()

func _update_clouds() -> void:
    if _cloud_duration_s <= 0.0:
        return
    var position_s := fmod(_cloud_elapsed, _cloud_duration_s)
    var idx := int(floor(position_s / _cloud_step_s))
    var blend := (position_s - float(idx) * _cloud_step_s) / _cloud_step_s
    for i in range(_cloud_visuals.size()):
        var path: Array = _cloud_tracks[i]["samples"]
        var first: Dictionary = path[min(idx, path.size() - 1)]
        var second: Dictionary = path[min(idx + 1, path.size() - 1)]
        var cloud = _cloud_visuals[i]
        cloud.position = Vector3(
            lerp(float(first["x_m"]), float(second["x_m"]), blend) / 100.0,
            float(_cloud_tracks[i]["altitude_m"]) / 100.0,
            -lerp(float(first["y_m"]), float(second["y_m"]), blend) / 100.0
        )
        var stretch := lerp(float(first["stretch"]), float(second["stretch"]), blend)
        cloud.scale = Vector3(max(.1, stretch), .4, max(.1, stretch) * .8)
        cloud.rotation.y = lerp_angle(float(first["orientation_rad"]),
                                      float(second["orientation_rad"]), blend)

func _create_environment(data: Dictionary) -> void:
    var floor_mesh := BoxMesh.new()
    floor_mesh.size = Vector3(12, 0.2, 12)
    var floor_instance := MeshInstance3D.new()
    floor_instance.mesh = floor_mesh
    floor_instance.position.y = -0.5
    var mat := StandardMaterial3D.new()
    var humidity := float(data["humidity"])
    mat.albedo_color = Color(0.36 - humidity * .13, .44 + humidity * .22, .33)
    floor_instance.material_override = mat
    add_child(floor_instance)
    if bool(data["sky_island"]):
        var island := MeshInstance3D.new()
        var shape := BoxMesh.new()
        shape.size = Vector3(4, 0.8, 4)
        island.mesh = shape
        island.position = Vector3(5, 8, -8)
        island.material_override = mat
        add_child(island)

func _process(delta: float) -> void:
    if delta < 0:
        return
    _cloud_elapsed += min(delta, 0.25)
    _update_clouds()
'''


def emit_frontier_godot_overlay(
    candidate: FrontierSceneCandidate,
    *,
    cloud_path_duration_s: int = 30,
    cloud_step_s: int = 1,
) -> dict[str, str]:
    """Emit a Godot scene + fixed GDScript + snapshot and wind path JSON.

    No dynamic script is accepted. Frame motion follows source wind at export
    time; actual native render/playback is a separate acceptance gate.
    """
    if not isinstance(candidate, FrontierSceneCandidate) or candidate.approved_for_runtime:
        raise FrontierGodotError("unadmitted Jeeves scene candidate required")
    if (type(cloud_path_duration_s) is not int or not 1 <= cloud_path_duration_s <= 300
            or type(cloud_step_s) is not int or not 1 <= cloud_step_s <= 10
            or cloud_path_duration_s % cloud_step_s != 0):
        raise FrontierGodotError("invalid bounded cloud path duration and step")
    from skeleton.jeeves.game_frontier_dynamics import (
        WindField, WindLayer, WindVector, advect_clouds,
    )
    manifest = candidate.manifest
    actual = sha256(json.dumps(manifest, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if actual != candidate.manifest_digest or manifest.get("model_status") != "engine_candidate_only_no_proprietary_weights":
        raise FrontierGodotError("source candidate identity or status mismatch")
    triangles = candidate.geometry_triangles
    vertices = candidate.geometry_vertices
    if not vertices or not triangles or len(vertices) > 1_000_000 or len(triangles) > 2_000_000:
        raise FrontierGodotError("invalid or unbounded source geometry")
    for face in triangles:
        if len(face) != 3 or min(face) < 0 or max(face) >= len(vertices):
            raise FrontierGodotError("corrupt geometry triangle")
    layers = tuple(WindLayer(z["altitude_m"],
                             WindVector(z["east_mps"], z["north_mps"]),
                             z["turbulence_mps"], z["cell_size_m"]) for z in manifest["wind"])
    # Source seed is preserved to keep the seeded wind path repeatable.
    wind = WindField(layers, seed=int(manifest["wind_configuration"]["seed"]),
                     gust_period_s=manifest["wind_configuration"]["gust_period_s"])
    clouds = candidate.moved_clouds
    path = [[c] for c in clouds]
    at = float(manifest["simulation_time_s"])
    current = clouds
    for _ in range(cloud_path_duration_s // cloud_step_s):
        current = advect_clouds(current, wind, time_s=at,
                                elapsed_s=cloud_step_s)
        at += cloud_step_s
        for track, cloud in zip(path, current):
            track.append(cloud)
    cloud_tracks = [
        {
            "id": original.cloud_id, "altitude_m": original.altitude_m,
            "opacity": original.opacity,
            "samples": [
                {"x_m": c.x_m, "y_m": c.y_m, "stretch": c.stretch,
                 "orientation_rad": c.orientation_rad} for c in samples
            ],
        }
        for original, samples in zip(clouds, path)
    ]
    world = dict(manifest["world"]["cell"])
    variant = manifest.get("world_variant")
    if isinstance(variant, Mapping):
        for key in ("temperature", "humidity", "sky_island", "elevation"):
            if key in variant:
                world[key] = variant[key]
    payload = {
        "schema": "skeleton.game.frontier_godot_overlay.v1",
        "origin_candidate_digest": actual,
        "game_era": manifest["render"]["era"],
        "requested_fps": manifest["render"]["fps"],
        "world": world,
        "world_variant": variant if isinstance(variant, Mapping) else {},
        "projection": manifest.get("projection") or {},
        "character_physics": manifest.get("character_physics"),
        "ray_lighting": manifest.get("ray_lighting", []),
        "photometric_3d": manifest.get("photometric_3d", []),
        "leaf_shadows": manifest.get("leaf_shadows", []),
        "atmosphere": manifest.get("atmosphere") or {},
        "tides": manifest.get("tides") or {},
        "liquid": manifest.get("liquid") or {},
        "biome_motion": manifest.get("biome_motion") or {},
        "advanced_physics": manifest.get("advanced_physics") or {},
        "realism_audit": manifest.get("realism_audit") or {},
        "character_suite": manifest.get("character_suite") or {},
        "geometry": {
            "vertices": [[v.x, v.y, v.z] for v in vertices],
            "triangles": [list(face) for face in triangles],
        },
        "colliders": [
            {"head": [c.head.x, c.head.y, c.head.z],
             "tail": [c.tail.x, c.tail.y, c.tail.z],
             "radius_m": c.radius_m}
            for c in candidate.geometry_colliders
        ],
        "clouds": cloud_tracks,
        "cloud_duration_s": cloud_path_duration_s,
        "cloud_step_s": cloud_step_s,
        "admission": "candidate_only_not_godot_verified",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False)
    if len(encoded.encode()) > 24 * 1024 * 1024:
        raise FrontierGodotError("overlay payload too large")
    tscn = (
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://frontier/frontier_scene.gd" id="1"]\n\n'
        '[node name="FrontierWorld" type="Node3D"]\n'
        'script = ExtResource("1")\n'
    )
    return {
        "frontier/frontier_scene.tscn": tscn,
        "frontier/frontier_scene.gd": _GDSCRIPT,
        "frontier/data/scene.json": encoded + "\n",
    }


def attach_frontier_overlay(
    project_files: Mapping[str, str],
    candidate: FrontierSceneCandidate,
    *,
    cloud_path_duration_s: int = 30,
    cloud_step_s: int = 1,
) -> dict[str, str]:
    """Safely attach an emitted reference scene to an existing Forge Godot project.

    Pure mapping transform: does not overwrite the existing main level,
    authorization, save state, input, or materializer files. The caller must
    separately run the canonical static checker and a real Godot playtest.
    """
    if not isinstance(project_files, Mapping):
        raise FrontierGodotError("existing Godot project mapping required")
    if "project.godot" not in project_files:
        raise FrontierGodotError("cannot attach frontier scene without project.godot")
    if len(project_files) > 100_000:
        raise FrontierGodotError("project file budget exceeded")
    for path, content in project_files.items():
        if (type(path) is not str or type(content) is not str
                or not path or path.startswith("/") or
                ".." in path.split("/") or chr(92) in path):
            raise FrontierGodotError("invalid existing Godot project file")
    overlay = emit_frontier_godot_overlay(
        candidate, cloud_path_duration_s=cloud_path_duration_s,
        cloud_step_s=cloud_step_s,
    )
    conflicts = tuple(sorted(set(project_files).intersection(overlay)))
    if any(project_files[key] != overlay[key] for key in conflicts):
        raise FrontierGodotError("existing frontier project overlay would be overwritten")
    return {**project_files, **overlay}
