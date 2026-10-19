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
var _native_capture_file: FileAccess
var _native_capture_tick: int = 0
var _native_capture_max_frames: int = 0
var _native_candidate_sha: String = ""
var _native_signed_gdd_sha: String = ""
var _native_actor_id: String = ""
var _native_actor_asset_sha: String = ""
var _native_capture_nodes: Array[Node3D] = []
var _native_capture_actors: Array = []
var _native_chunk_size_m: float = 32.0
var _native_controls_enabled: bool = false
var _native_test_drive_ticks: int = 0
var _native_last_action: Dictionary = {}
var _native_move_force_n: float = 240.0
var _native_max_horizontal_speed_mps: float = 8.0
var _native_jump_impulse_ns: float = 120.0

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
    _create_virtual_game_gps(data.get("virtual_game_gps", {}))
    _create_chunk_evidence_inspector(data.get("chunk_evidence_summary", {}))
    _create_clouds(data["clouds"])
    _create_environment(data["world"])
    _create_camera(data.get("projection", {}), data.get("world_variant", {}))
    _create_lighting(data.get("world_variant", {}),
                     data.get("photometric_3d", []), data.get("atmosphere", {}))
    _create_water(data.get("liquid", {}), data.get("tides", {}))
    _create_leaf_shadows(data.get("leaf_shadows", []))
    _create_biome_objects(data.get("biome_motion", {}))
    _create_advanced_character(data.get("advanced_physics", {}))
    _configure_native_capture(data.get("native_capture", {}))
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

func _create_chunk_evidence_inspector(proof: Dictionary) -> void:
    if proof.is_empty():
        return
    var ledger := CanvasLayer.new()
    ledger.name = "VerifiedChunkEvidenceInspector"
    var label := Label.new()
    label.name = "ChunkEvidenceReadout"
    label.position = Vector2(20, 420)
    label.text = "CHUNK EVIDENCE (SOURCE ONLY; NOT GPU PROOF)\\n"
    label.text += "Frame receipts: " + str(proof.get("frame_chunk_count", 0)) + "\\n"
    label.text += "Retired chunks: " + str(proof.get("retired_chunk_count", 0)) + "\\n"
    label.text += "Actor migrations: " + str(proof.get("cross_chunk_migrations", 0)) + "\\n"
    label.text += "GDD note receipts: " + str(proof.get("gdd_note_count", 0)) + "\\n"
    label.text += "A/B verified: " + str(proof.get("verifier_a", false)) + " / " + str(proof.get("verifier_b", false)) + "\\n"
    label.text += "Proof root: " + str(proof.get("receipt_digest", "")).substr(0, 24) + "…\\n"
    label.text += "Era mesh bundles: " + str(proof.get("era_mesh_receipts", 0)) + "\\n"
    ledger.add_child(label)
    add_child(ledger)

func _create_virtual_game_gps(nav: Dictionary) -> void:
    if nav.is_empty():
        return
    if bool(nav.get("device_location_used", true)):
        push_error("Virtual game map must not receive device GPS")
        return
    if str(nav.get("authority", "")) != "virtual_game_navigation_candidate_no_world_mutation":
        push_error("Untrusted game navigation source")
        return
    var hud := CanvasLayer.new()
    hud.name = "VirtualGameGPS"
    var label := Label.new()
    label.name = "VirtualMapCoordinateReadout"
    label.position = Vector2(20, 200)
    label.text = "VIRTUAL GAME GPS — FICTIONAL WORLD ONLY\\n"
    label.text += str(nav.get("world_id", "")) + " / " + str(nav.get("realm_id", "")) + "\\n"
    label.text += "XYZ(m): " + str(nav.get("world_xyz_m", [])) + "\\n"
    label.text += "Map tile: " + str(nav.get("map_tile_xy", [])) + "\\n"
    label.text += "Virtual accuracy(m): " + str(nav.get("horizontal_uncertainty_m", "?")) + "\\n"
    if typeof(nav.get("survey")) == TYPE_DICTIONARY:
        label.text += "Fictional surveyed fix: " + str(nav["survey"].get("world_xyz_m", [])) + "\\n"
    hud.add_child(label)
    var route: Variant = nav.get("route")
    if typeof(route) == TYPE_DICTIONARY:
        var tile_path: Array = route.get("tiles", [])
        var line := Line2D.new()
        line.name = "VirtualMinimapPath"
        line.width = 2
        line.default_color = Color(.2, .8, 1.0, 1.0)
        var cols: float = maxf(1.0, float(nav.get("map_width_tiles", 1)))
        var rows: float = maxf(1.0, float(nav.get("map_height_tiles", 1)))
        # Render a bounded path preview; routing remains game-map candidate.
        for index in range(min(128, tile_path.size())):
            var cell: Array = tile_path[index]
            line.add_point(Vector2(20 + (float(cell[0]) + .5) / cols * 160,
                                   340 + (float(cell[1]) + .5) / rows * 160))
        hud.add_child(line)
    add_child(hud)

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
    var strength: float = maxf(.03, float(variant.get("luminance", .7)) * 1.4)
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
        var view_distance: float = maxf(1.0, float(air["visibility_m"]))
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
    var water_level: float = maxf(0.0, float(depths[0]) + float(tides.get("water_height_m", 0.0)))
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
    var slip_risk: float = clampf(float(terrain_grip.get("slip_risk", 0.0)), 0.0, 1.0)
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

func _configure_native_capture(settings: Dictionary) -> void:
    if not bool(settings.get("enabled", false)):
        return
    if _aero_character == null:
        push_error("Native physics capture requires an actual RigidBody3D")
        return
    _native_capture_max_frames = int(settings.get("max_frames", 0))
    if _native_capture_max_frames < 1 or _native_capture_max_frames > 1000000:
        push_error("Invalid native capture frame budget")
        return
    _native_candidate_sha = str(settings.get("candidate_digest", ""))
    _native_signed_gdd_sha = str(settings.get("gdd_digest", ""))
    _native_actor_id = str(settings.get("actor_id", ""))
    _native_actor_asset_sha = str(settings.get("actor_asset_digest", ""))
    if _native_candidate_sha.length() != 64 or _native_signed_gdd_sha.length() != 64 or _native_actor_asset_sha.length() != 64:
        push_error("Native capture provenance digests required")
        return
    if _native_actor_id.is_empty():
        push_error("Native capture actor ID required")
        return
    Engine.physics_ticks_per_second = int(settings.get("fps", 60))
    _native_chunk_size_m = float(settings.get("chunk_size_m", 32.0))
    var sources: Array = settings.get("actors", [])
    if sources.is_empty():
        sources = [{
            "id": _native_actor_id, "source_digest": _native_actor_asset_sha,
            "source_kind": "native_rigid_reference",
        }]
    if sources.size() > 64 or _native_chunk_size_m < .1:
        push_error("Native actors or chunk size exceed capture budget")
        return
    # The first controlled body belongs to the existing scene. Additional
    # probes use actual native Godot physics bodies, but are explicitly
    # identified as generated reference proxies rather than full NPCs.
    _native_capture_nodes.clear()
    _native_capture_actors.clear()
    var found_primary := false
    for index in range(sources.size()):
        var spec: Dictionary = sources[index]
        var id := str(spec.get("id", ""))
        var actor_node: Node3D
        if id == _native_actor_id:
            if found_primary:
                push_error("Native source contains duplicate primary actor")
                return
            found_primary = true
            actor_node = _aero_character
        else:
            var source_velocity: Vector3 = _vec(spec.get("velocity_xyz_mps", [0, 0, 0]))
            if source_velocity.length() > 0.0001:
                var body := RigidBody3D.new()
                body.name = "NativePhysicsSourceProxy" + str(index)
                body.gravity_scale = 0.0
                body.linear_velocity = source_velocity
                body.contact_monitor = true
                body.max_contacts_reported = 8
                actor_node = body
            else:
                var body := StaticBody3D.new()
                body.name = "NativeStaticSourceProxy" + str(index)
                actor_node = body
            actor_node.position = _vec(spec.get("position_xyz_m", [0, 0, 0]))
            var collider := CollisionShape3D.new()
            var shape := SphereShape3D.new()
            shape.radius = 0.2
            collider.shape = shape
            actor_node.add_child(collider)
            add_child(actor_node)
        _native_capture_nodes.append(actor_node)
        _native_capture_actors.append(spec)
    if not found_primary:
        push_error("Native actor sources omit the scene's actual physics body")
        return
    _aero_character.contact_monitor = true
    _aero_character.max_contacts_reported = 8
    var control: Dictionary = settings.get("reference_controls", {})
    if bool(control.get("enabled", false)):
        _native_move_force_n = float(control.get("move_force_n", 240.0))
        _native_max_horizontal_speed_mps = float(control.get("max_speed_mps", 8.0))
        _native_jump_impulse_ns = float(control.get("jump_impulse_ns", 120.0))
        _native_test_drive_ticks = int(control.get("headless_fixture_ticks", 0))
        if (_native_move_force_n <= 0.0 or _native_move_force_n > 5000.0
            or _native_max_horizontal_speed_mps < 0.1 or _native_max_horizontal_speed_mps > 50.0
            or _native_jump_impulse_ns < 0.0 or _native_jump_impulse_ns > 2000.0
            or _native_test_drive_ticks < 0 or _native_test_drive_ticks > 64):
            push_error("Invalid reference controls")
            return
        _native_controls_enabled = true
    # Fixed user:// destination, not a user-supplied external path.
    _native_capture_file = FileAccess.open("user://frontier_native_physics.jsonl", FileAccess.WRITE)
    if _native_capture_file == null:
        push_error("Native capture file could not be opened")

func _native_chunk_less(a: Dictionary, b: Dictionary) -> bool:
    var first: Array = a["chunk_xy"]
    var second: Array = b["chunk_xy"]
    if int(first[0]) != int(second[0]):
        return int(first[0]) < int(second[0])
    return int(first[1]) < int(second[1])

func _record_native_physics() -> void:
    if _native_capture_file == null:
        return
    if _native_capture_tick >= _native_capture_max_frames:
        _native_capture_file.close()
        _native_capture_file = null
        return
    var recorded: Array = []
    var cells: Dictionary = {}
    for index in range(_native_capture_nodes.size()):
        var actor: Node3D = _native_capture_nodes[index]
        var src: Dictionary = _native_capture_actors[index]
        var p: Vector3 = actor.global_position
        var v := Vector3.ZERO
        var contacts := 0
        var dynamics: Dictionary = {}
        if actor is RigidBody3D:
            var rigid := actor as RigidBody3D
            v = rigid.linear_velocity
            var collisions: Array[Node3D] = rigid.get_colliding_bodies()
            contacts = collisions.size()
            var peer_ids: Array[String] = []
            for collision in collisions:
                var peer_index: int = _native_capture_nodes.find(collision)
                if peer_index >= 0 and peer_index != index:
                    peer_ids.append(str(_native_capture_actors[peer_index]["id"]))
            peer_ids.sort()
            var material: PhysicsMaterial = rigid.physics_material_override
            var friction: float = 1.0
            var restitution: float = 0.0
            if material != null:
                friction = material.friction
                restitution = material.bounce
            dynamics = {
                "mode": "rigid", "mass_kg": rigid.mass,
                "friction": friction, "restitution": restitution,
                "kinetic_energy_j": 0.5 * rigid.mass * v.length_squared(),
                "contact_actor_ids": peer_ids,
                "external_contact_count": maxi(0, contacts - peer_ids.size()),
            }
        else:
            dynamics = {
                "mode": "static", "mass_kg": 0.0,
                "friction": 1.0, "restitution": 0.0,
                "kinetic_energy_j": 0.0, "contact_actor_ids": [],
                "external_contact_count": 0,
            }
        var xyz: Array = [p.x, -p.z, p.y]
        var cell: Array = [
            int(floor(float(xyz[0]) / _native_chunk_size_m)),
            int(floor(float(xyz[1]) / _native_chunk_size_m))
        ]
        recorded.append({
            "id": str(src["id"]),
            "source_digest": str(src["source_digest"]),
            "source_kind": str(src.get("source_kind", "generated_source_proxy")),
            "contact_count": contacts,
            "physics_body": dynamics,
            "world_xyz_m": xyz,
            "velocity_xyz_mps": [v.x, -v.z, v.y],
        })
        var cell_id := str(cell[0]) + ":" + str(cell[1])
        if not cells.has(cell_id):
            cells[cell_id] = {"chunk_xy": cell, "actor_ids": []}
        cells[cell_id]["actor_ids"].append(str(src["id"]))
    var chunks: Array = []
    for key in cells:
        var entry: Dictionary = cells[key]
        entry["actor_ids"].sort()
        chunks.append(entry)
    chunks.sort_custom(_native_chunk_less)
    var row := {
        "schema": "skeleton.game.native_physics_observation.v1",
        "native_dynamics_schema": "skeleton.game.native_actor_dynamics.v1",
        "native_engine": "godot4_physics",
        "authority": "untrusted_native_candidate_observation_not_attested",
        "scene_candidate_digest": _native_candidate_sha,
        "signed_gdd_digest": _native_signed_gdd_sha,
        "native_tick": _native_capture_tick,
        "ticks_usec": Time.get_ticks_usec(),
        "fps": Engine.physics_ticks_per_second,
        "actors": recorded,
        "native_chunk_size_m": _native_chunk_size_m,
        "native_chunks": chunks,
    }
    if _native_controls_enabled:
        row["previous_step_control"] = _native_last_action.duplicate(true)
    _native_capture_file.store_line(JSON.stringify(row))
    _native_capture_file.flush()
    _native_capture_tick += 1

func _exit_tree() -> void:
    if _native_capture_file != null:
        _native_capture_file.close()
        _native_capture_file = null

func _apply_reference_controls() -> void:
    if not _native_controls_enabled or _native_capture_tick > _native_capture_max_frames:
        return
    var command_tick: int = _native_capture_tick - 1
    var axis: Vector2 = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    var kind: String = "human_input" if axis.length_squared() > 0.0 else "none"
    if command_tick < _native_test_drive_ticks:
        axis = Vector2.RIGHT
        kind = "headless_fixture"
    var force: Vector3 = Vector3.ZERO
    var horizontal_speed: float = Vector2(
        _aero_character.linear_velocity.x, _aero_character.linear_velocity.z).length()
    if axis.length_squared() > 0.0 and horizontal_speed < _native_max_horizontal_speed_mps:
        force = _vec([axis.x, -axis.y, 0.0]) * _native_move_force_n
        _aero_character.apply_central_force(force)
    var jumped: bool = false
    if kind != "headless_fixture":
        jumped = (Input.is_action_just_pressed("ui_accept")
            and _aero_character.get_colliding_bodies().size() > 0)
    if jumped:
        _aero_character.apply_central_impulse(Vector3.UP * _native_jump_impulse_ns)
    _native_last_action = {
        "schema": "skeleton.game.native_reference_input.v1",
        "actor_id": _native_actor_id,
        "command_tick": command_tick,
        "input_kind": kind,
        "input_axis_xy": [axis.x, axis.y],
        "force_world_xyz_n": [force.x, -force.z, force.y],
        "jump_impulse_ns": _native_jump_impulse_ns if jumped else 0.0,
        "bounded_reference_controller_not_NPC_AI": true,
    }

func _physics_process(delta: float) -> void:
    if _aero_character == null or delta < 0:
        return
    # Snapshot the solver output before applying forces for the next tick.
    # Physics observations are not GPU pixel observations or attestation.
    _record_native_physics()
    # Native solver updates the body after each fixed physics tick. Apply
    # quadratic air drag using *current* relative wind, not a stale impulse.
    var relative := _aero_character.linear_velocity - _aero_wind
    var speed := relative.length()
    var drag_n := -0.5 * _aero_density * _aero_cd * _aero_area * speed * relative
    _aero_character.apply_central_force(drag_n)
    _apply_reference_controls()

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
        var stretch: float = lerpf(float(first["stretch"]), float(second["stretch"]), blend)
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
    enable_native_capture: bool = False,
    native_capture_max_frames: int = 6000,
    native_capture_all_actors: bool = False,
    enable_native_reference_controls: bool = False,
    native_reference_test_drive_ticks: int = 0,
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
    if type(enable_native_capture) is not bool or type(native_capture_all_actors) is not bool or (
        type(native_capture_max_frames) is not int or
        not 1 <= native_capture_max_frames <= 1_000_000):
        raise FrontierGodotError("bounded explicit native capture opt-in required")
    if (type(enable_native_reference_controls) is not bool or
        type(native_reference_test_drive_ticks) is not int or
        not 0<=native_reference_test_drive_ticks<=64 or
        enable_native_reference_controls and not enable_native_capture or
        native_reference_test_drive_ticks and not enable_native_reference_controls):
        raise FrontierGodotError("bounded native reference controller opt-in required")
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
    native_config = {"enabled": False}
    if enable_native_capture:
        advanced = manifest.get("advanced_physics")
        frame = manifest.get("frame_progress")
        proof = manifest.get("frame_chunk_evidence")
        if not isinstance(advanced, Mapping) or not isinstance(frame, Mapping) or not isinstance(proof, Mapping):
            raise FrontierGodotError("real native capture requires an advanced rigid body, signed GDD frame and verified chunk evidence")
        actor_id = advanced["body"]["id"]
        mapped = [source for row in proof["receipts"]
                  for entity,source in zip(row["source_entities"],row["source_asset_digests"])
                  if entity == actor_id]
        if len(mapped) != 1 or proof.get("verifier_a") is not True or proof.get("verifier_b") is not True:
            raise FrontierGodotError("native body ID must match exactly one double verified source actor")
        sources = [{
            "id": actor_id, "source_digest": mapped[0],
            "source_kind": "native_rigid_reference",
        }]
        if native_capture_all_actors:
            frame_sources = manifest.get("frame_actor_sources", [])
            observed = {row["id"]: row for row in frame_sources}
            authenticated = {
                entity: source
                for chunk in proof["receipts"]
                for entity, source in zip(
                    chunk["source_entities"], chunk["source_asset_digests"])
            }
            if (not isinstance(frame_sources, list) or
                len(frame_sources) < 1 or len(frame_sources) > 64 or
                len(observed) != len(frame_sources) or
                set(observed) != set(authenticated) or
                any(row["source_digest"] != authenticated[row["id"]]
                    for row in frame_sources)):
                raise FrontierGodotError("multi-actor capture requires exact proven frame entities")
            if actor_id not in observed:
                raise FrontierGodotError("source frame does not contain physics reference")
            sources = []
            for row in sorted(frame_sources, key=lambda item: item["id"]):
                x = dict(row)
                x["source_kind"] = (
                    "native_rigid_reference" if row["id"] == actor_id
                    else "generated_source_proxy")
                sources.append(x)
        # Bind native measurements to the signed scene's original body.
        # The source is candidate-only, not authority over a finished game.
        body = advanced["body"]
        traction = advanced.get("traction") or {}
        slip = min(1., max(0., float(traction.get("slip_risk", 0.))))
        primary_source_dynamics = {
            "mass_kg": float(body["mass_kg"]),
            "friction": min(1., max(0.,
                float(body.get("friction", .6)) * (1. - slip * .8))),
            "restitution": min(1., max(0.,
                float(body.get("restitution", .1)))),
        }
        native_config = {
            "enabled": True, "max_frames": native_capture_max_frames,
            "primary_source_dynamics": primary_source_dynamics,
            "reference_controls": {
                "enabled": enable_native_reference_controls,
                "move_force_n": 240., "max_speed_mps": 8.,
                "jump_impulse_ns": 120.,
                "headless_fixture_ticks": native_reference_test_drive_ticks,
            },
            "candidate_digest": candidate.manifest_digest,
            "gdd_digest": frame["gdd_digest"], "fps": frame["fps"],
            "actor_id": actor_id, "actor_asset_digest": mapped[0],
            "chunk_size_m": 32., "actors": sources,
        }
    payload = {
        "schema": "skeleton.game.frontier_godot_overlay.v1",
        "origin_candidate_digest": actual,
        "native_capture": native_config,
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
        "virtual_game_gps": manifest.get("virtual_game_gps") or {},
        "chunk_evidence_summary": ({
            "frame_chunk_count": (manifest["frame_chunk_evidence"]["chunk_count"]
                if manifest.get("frame_chunk_evidence") else 0),
            "retired_chunk_count": (manifest["frame_chunk_evidence"]["retired_chunk_count"]
                if manifest.get("frame_chunk_evidence") else 0),
            "cross_chunk_migrations": (manifest["frame_chunk_evidence"]["cross_chunk_migrations"]
                if manifest.get("frame_chunk_evidence") else 0),
            "gdd_note_count": (manifest["frame_chunk_evidence"]["source_note_count"]
                if manifest.get("frame_chunk_evidence") else 0),
            "receipt_digest": (manifest["frame_chunk_evidence"]["receipt_digest"]
                if manifest.get("frame_chunk_evidence") else ""),
            "verifier_a": (manifest["frame_chunk_evidence"]["verifier_a"]
                if manifest.get("frame_chunk_evidence") else False),
            "verifier_b": (manifest["frame_chunk_evidence"]["verifier_b"]
                if manifest.get("frame_chunk_evidence") else False),
            "era_mesh_receipts": len(manifest.get("mesh_chunk_evidence") or []),
        } if manifest.get("frame_chunk_evidence") or manifest.get("mesh_chunk_evidence")
          else {}),

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
    enable_native_capture: bool = False,
    native_capture_max_frames: int = 6000,
    native_capture_all_actors: bool = False,
    enable_native_reference_controls: bool = False,
    native_reference_test_drive_ticks: int = 0,
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
        enable_native_capture=enable_native_capture,
        native_capture_max_frames=native_capture_max_frames,
        native_capture_all_actors=native_capture_all_actors,
        enable_native_reference_controls=enable_native_reference_controls,
        native_reference_test_drive_ticks=native_reference_test_drive_ticks,
    )
    conflicts = tuple(sorted(set(project_files).intersection(overlay)))
    if any(project_files[key] != overlay[key] for key in conflicts):
        raise FrontierGodotError("existing frontier project overlay would be overwritten")
    return {**project_files, **overlay}
