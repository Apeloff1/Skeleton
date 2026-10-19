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
var _virtual_instrument_trace_file: FileAccess
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
var _native_gameplay_zones: Array = []
var _native_force_fields: Array = []
var _native_previous_field_steps: Array = []
var _native_field_visual_nodes: Array[MeshInstance3D] = []
var _native_field_preview_visible: bool = true
var _native_previous_zone_members: Array = []
var _native_preview_label: Label
var _native_recent_zone_events: Array[String] = []
var _native_follow_cam: bool = false
var _native_camera: Camera3D
var _native_debug_speed: float = 1.0
var _approved_gameplay_quests: Dictionary = {}
var _approved_gameplay_dispatch_digest: String = ""
var _approved_gameplay_flags: Dictionary = {}
var _approved_gameplay_inventory: Dictionary = {}
var _approved_local_health: int = 100
var _approved_local_effect_history: Array = []
var _approved_effect_history_label: Label
var _approved_effect_history_cursor: int = 0
var _approved_health_effect_kinds: Array[String] = []
var _approved_health_effect_meshes: Array[MeshInstance3D] = []
var _approved_gameplay_npc_emotions: Dictionary = {}
var _approved_npc_visuals: Array[String] = []
var _approved_inventory_visuals: Array[String] = []
var _approved_gameplay_cues: Array = []
var _approved_quest_objectives: Dictionary = {}
var _approved_quest_titles: Dictionary = {}
var _approved_branch_options: Dictionary = {}
var _approved_branch_label: Label
var _approved_branch_cursor: int = 0
var _approved_npc_proximity_label: Label
var _approved_npc_focus: String = ""
var _approved_npc_interaction_count: int = 0
var _approved_npc_interaction_status: Label
var _approved_inventory_focus: int = 0
var _approved_inventory_label: Label
var _approved_fx_nodes: Array[MeshInstance3D] = []
var _approved_fx_page_ids: Array[String] = []
var _approved_fx_clock: float = 0.0
var _approved_dialogue_queue: Array[String] = []
var _approved_dialogue_cursor: int = 0
var _approved_dialogue_panel: PanelContainer
var _approved_dialogue_label: Label
var _approved_gameplay_label: Label
var _approved_quest_history: Array = []
var _approved_quest_history_cursor: int = 0
var _approved_quest_history_label: Label
var _native_flight_instrument_label: Label
var _approved_instrument_focus: String = "none"
var _approved_instrument_focus_label: Label
var _native_flight_instruments_visible: bool = true
var _native_landing_risk_label: Label
var _native_landing_risk_meter: ProgressBar
var _game_route_waypoints: Array = []
var _game_route_cursor: int = 0
var _game_route_label: Label
var _virtual_source_fix_xyz: Vector3 = Vector3.ZERO
var _virtual_source_fix_available: bool = false
var _virtual_live_gps_label: Label
var _virtual_camera_mode: int = 0
var _virtual_camera_orbit_s: float = 0.0
var _virtual_camera_mode_label: Label
var _approved_cue_timeline: Array = []
var _approved_cue_cursor: int = 0
var _approved_cue_label: Label

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
    _create_virtual_route_book(data.get("virtual_game_gps", {}))
    _create_live_virtual_gps_delta(data.get("virtual_game_gps", {}))
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
    _create_native_flight_instruments()
    _create_native_landing_risk_inspector()
    _create_game_cinematic_camera_control()
    _load_approved_native_gameplay(data.get("native_capture", {}))
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

func _create_native_landing_risk_inspector() -> void:
    if _aero_character == null:
        return
    var overlay := CanvasLayer.new()
    overlay.name = "GameNativeLandingRiskInspector"
    var stack := VBoxContainer.new()
    stack.position = Vector2(20, 115)
    stack.custom_minimum_size = Vector2(280, 70)
    var label := Label.new()
    label.name = "GameLandingRiskReadout"
    label.add_theme_color_override("font_color", Color(1., .72, .32))
    stack.add_child(label)
    var meter := ProgressBar.new()
    meter.name = "GameLandingRiskFraction"
    meter.min_value = 0.0
    meter.max_value = 100.0
    meter.show_percentage = false
    stack.add_child(meter)
    overlay.add_child(stack)
    add_child(overlay)
    _native_landing_risk_label = label
    _native_landing_risk_meter = meter
    _update_native_landing_risk()


func _update_native_landing_risk() -> void:
    if _native_landing_risk_label == null or _aero_character == null:
        return
    # Physics-only risk preview: never changes actual game health/canon.
    var fall_speed: float = maxf(0.0, -_aero_character.linear_velocity.y)
    var mass_kg: float = maxf(.01, _aero_character.mass)
    var local_gravity: float = float(ProjectSettings.get_setting(
        "physics/3d/default_gravity", 9.8))
    var terminal_speed: float = sqrt(
        maxf(.001, 2.0 * mass_kg * local_gravity /
            maxf(.001, _aero_density * _aero_cd * _aero_area))
    )
    var danger: float = clampf(
        fall_speed / maxf(.01, terminal_speed), 0.0, 2.0
    )
    _native_landing_risk_meter.value = danger * 50.0
    _native_landing_risk_label.text = (
        "FICTIONAL GAME LANDING RISK (not health damage)\n" +
        "Descent: " + str(snappedf(fall_speed, .01)) +
        " m/s | modeled terminal: " +
        str(snappedf(terminal_speed, .01)) + " m/s"
    )


func _apply_approved_instrument_focus() -> void:
    if _native_flight_instrument_label == null:
        return
    if _native_landing_risk_label == null or _virtual_camera_mode_label == null:
        return
    var widgets: Dictionary = {
        "flight":_native_flight_instrument_label,
        "landing":_native_landing_risk_label,
        "camera":_virtual_camera_mode_label,
    }
    for instrument_id in widgets.keys():
        var widget: Label = widgets[instrument_id]
        widget.add_theme_font_size_override(
            "font_size", 22 if _approved_instrument_focus == instrument_id else 14
        )
    if _approved_instrument_focus_label == null:
        var hud := CanvasLayer.new()
        hud.name = "ApprovedInstrumentFocusDirector"
        var label := Label.new()
        label.name = "SourceAuthorizedInstrumentFocus"
        label.position = Vector2(20, 85)
        label.add_theme_color_override("font_color", Color(.96,.87,.52))
        hud.add_child(label)
        add_child(hud)
        _approved_instrument_focus_label = label
    _approved_instrument_focus_label.text = (
        "Approved instrument priority: " + _approved_instrument_focus
    )


func _create_native_flight_instruments() -> void:
    if _aero_character == null:
        return
    var overlay := CanvasLayer.new()
    overlay.name = "NativeVirtualFlightInstruments"
    var gauge := Label.new()
    gauge.name = "LiveGameAltimeterCompassVario"
    gauge.position = Vector2(20, 235)
    gauge.add_theme_color_override("font_color", Color(.35, .98, .93))
    overlay.add_child(gauge)
    add_child(overlay)
    _native_flight_instrument_label = gauge
    _update_native_flight_instruments()


func _update_native_flight_instruments() -> void:
    if _native_flight_instrument_label == null or _aero_character == null:
        return
    var pos: Vector3 = _aero_character.global_position
    var velocity: Vector3 = _aero_character.linear_velocity
    var airspeed: float = (velocity - _aero_wind).length()
    var groundspeed: float = Vector2(velocity.x, velocity.z).length()
    var bearing: float = fposmod(
        rad_to_deg(atan2(velocity.x, -velocity.z)), 360.0
    )
    # Scene Godot basis is x/east, -z/north, y/up. Entirely fictional GPS.
    _native_flight_instrument_label.text = (
        "GAME VIRTUAL FLIGHT INSTRUMENTS (H toggles; no device GPS)\n" +
        "Survey/game xyz (m): " + str(snappedf(pos.x, .01)) + " / " +
        str(snappedf(-pos.z, .01)) + " / " +
        str(snappedf(pos.y, .01)) + "\n" +
        "Altimeter (m): " + str(snappedf(pos.y, .01)) +
        " | Vario (m/s): " + str(snappedf(velocity.y, .01)) + "\n" +
        "Air-relative speed (m/s): " + str(snappedf(airspeed, .01)) +
        " | Ground speed (m/s): " + str(snappedf(groundspeed, .01)) + "\n" +
        "Virtual bearing (deg): " + str(snappedf(bearing, .1)) +
        " | Tick: " + str(_native_capture_tick)
    )


func _create_live_virtual_gps_delta(nav: Dictionary) -> void:
    # Fixed author-selected fictional map fix plus actual rigid body movement.
    # Never request Earth, hardware GPS or real-world geolocation.
    if (nav.is_empty() or bool(nav.get("device_location_used", true))
        or str(nav.get("authority", "")) !=
        "virtual_game_navigation_candidate_no_world_mutation"):
        return
    var xyz: Variant = nav.get("world_xyz_m")
    if typeof(xyz) != TYPE_ARRAY or xyz.size() != 3:
        return
    for coordinate in xyz:
        if not is_finite(float(coordinate)):
            push_error("Authored virtual game GPS has invalid coordinate")
            return
    _virtual_source_fix_xyz = _vec(xyz)
    _virtual_source_fix_available = true
    var hud := CanvasLayer.new()
    hud.name = "GodotLiveVirtualGPSDelta"
    var label := Label.new()
    label.name = "VerifiedGameLocationDelta"
    label.position = Vector2(20, 275)
    label.add_theme_color_override("font_color",Color(.45,.91,.98))
    hud.add_child(label)
    add_child(hud)
    _virtual_live_gps_label = label
    _update_live_virtual_gps_delta()


func _update_live_virtual_gps_delta() -> void:
    if (not _virtual_source_fix_available or _aero_character == null
        or _virtual_live_gps_label == null):
        return
    var offset: Vector3 = _aero_character.global_position - _virtual_source_fix_xyz
    var horizontal: float = Vector2(offset.x,offset.z).length()
    var azimuth: float = fposmod(rad_to_deg(atan2(offset.x,-offset.z)),360.0)
    _virtual_live_gps_label.text = (
        "LIVE FICTIONAL GAME GPS DRIFT (physics only)\n" +
        "Distance from authored fix: " + str(snappedf(horizontal,.01)) +
        " m horizontal / " + str(snappedf(offset.y,.01)) +
        " m vertical\nBearing of displacement: " +
        str(snappedf(azimuth,.1)) + " degrees"
    )


func _create_virtual_route_book(nav: Dictionary) -> void:
    if nav.is_empty() or bool(nav.get("device_location_used", true)):
        return
    if str(nav.get("authority", "")) != "virtual_game_navigation_candidate_no_world_mutation":
        return
    var route: Variant = nav.get("route")
    if typeof(route) != TYPE_DICTIONARY:
        return
    var tiles: Array = route.get("tiles", [])
    if tiles.is_empty() or tiles.size() > 4096:
        return
    _game_route_waypoints.clear()
    for tile in tiles:
        if typeof(tile) != TYPE_ARRAY or tile.size() != 2:
            return
        _game_route_waypoints.append({"tile_x":int(tile[0]),"tile_y":int(tile[1])})
    var overlay := CanvasLayer.new()
    overlay.name = "FictionalWorldRouteBook"
    var label := Label.new()
    label.name = "VirtualRouteWaypoint"
    label.position = Vector2(20, 302)
    label.add_theme_color_override("font_color", Color(.78, .93, 1.))
    overlay.add_child(label)
    add_child(overlay)
    _game_route_cursor = 0
    _game_route_label = label
    _show_virtual_route_waypoint()


func _show_virtual_route_waypoint() -> void:
    if _game_route_label == null or _game_route_waypoints.is_empty():
        return
    var waypoint: Dictionary = _game_route_waypoints[_game_route_cursor]
    _game_route_label.text = (
        "FICTIONAL WORLD ROUTE (M cycles, no device GPS)\n" +
        "Waypoint " + str(_game_route_cursor + 1) + "/" +
        str(_game_route_waypoints.size()) + " | map tile " +
        str(waypoint["tile_x"]) + "," + str(waypoint["tile_y"])
    )


func _cycle_virtual_route_waypoint() -> void:
    if _game_route_waypoints.is_empty():
        return
    _game_route_cursor = (_game_route_cursor + 1) % _game_route_waypoints.size()
    _show_virtual_route_waypoint()


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

func _create_game_cinematic_camera_control() -> void:
    if _native_camera == null or _aero_character == null:
        return
    var overlay := CanvasLayer.new()
    overlay.name = "GameCinematicCameraDirector"
    var label := Label.new()
    label.name = "GameCameraModeReadout"
    label.position = Vector2(20, 185)
    label.add_theme_color_override("font_color", Color(.99, .77, .5))
    overlay.add_child(label)
    add_child(overlay)
    _virtual_camera_mode_label = label
    _refresh_game_camera_mode()


func _refresh_game_camera_mode() -> void:
    if _virtual_camera_mode_label == null:
        return
    var modes := ["Scene authored", "Follow avatar", "Orbit cinematic",
                  "Overhead inspection"]
    _virtual_camera_mode_label.text = (
        "FICTIONAL CAMERA (C changes): " + modes[_virtual_camera_mode]
    )
    if _native_camera != null:
        _native_camera.projection = (
            Camera3D.PROJECTION_ORTHOGONAL if _virtual_camera_mode == 3
            else Camera3D.PROJECTION_PERSPECTIVE
        )
        if _virtual_camera_mode == 3:
            _native_camera.size = 21.0


func _cycle_game_cinematic_camera() -> void:
    if _native_camera == null:
        return
    _virtual_camera_mode = (_virtual_camera_mode + 1) % 4
    _refresh_game_camera_mode()


func _update_game_cinematic_camera(delta: float) -> void:
    if _native_camera == null or _aero_character == null:
        return
    if _virtual_camera_mode == 0 and not _native_follow_cam:
        return
    var target: Vector3 = _aero_character.global_position
    var offset := Vector3(9., 6., 16.)
    if _virtual_camera_mode == 2:
        _virtual_camera_orbit_s += minf(delta, .1)
        offset = Vector3(
            cos(_virtual_camera_orbit_s * .38)*15., 6.,
            sin(_virtual_camera_orbit_s * .38)*15.
        )
    elif _virtual_camera_mode == 3:
        offset = Vector3(.01, 21., .1)
    var lerp_fraction := minf(1., delta * 3.5)
    _native_camera.global_position = _native_camera.global_position.lerp(
        target + offset, lerp_fraction
    )
    if _virtual_camera_mode == 3:
        _native_camera.look_at(target, Vector3(0, 0, -1))
    else:
        _native_camera.look_at(target + Vector3(0., 1., 0.))


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
    _native_camera = camera

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
        _native_follow_cam = bool(control.get("camera_follow", false))
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
    _native_gameplay_zones = settings.get("gameplay_zones", [])
    _native_force_fields = settings.get("gameplay_force_fields", [])
    # These translucent debug meshes never collide or apply forces: only
    # _apply_native_gameplay_fields is authoritative for reference simulation.
    for field_item in _native_force_fields:
        var field: Dictionary = field_item
        var preview := MeshInstance3D.new()
        preview.name = "NativeGameForcePreview_" + str(field["id"])
        preview.position = _vec(field["center_xyz_m"])
        var sphere := SphereMesh.new()
        sphere.radius = float(field["radius_m"])
        sphere.height = 2.0 * sphere.radius
        preview.mesh = sphere
        var tint := StandardMaterial3D.new()
        tint.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        tint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        var kind: String = str(field["kind"])
        if kind == "updraft":
            tint.albedo_color = Color(.25, .85, .98, .11)
        elif kind == "downdraft":
            tint.albedo_color = Color(.98, .45, .20, .11)
        elif kind == "vortex":
            tint.albedo_color = Color(.80, .28, .98, .12)
        else:
            tint.albedo_color = Color(.32, .98, .48, .11)
        preview.material_override = tint
        add_child(preview)
        _native_field_visual_nodes.append(preview)
    if not _native_gameplay_zones.is_empty():
        _create_native_playtest_inspector()
    for zone_item in _native_gameplay_zones:
        var zone: Dictionary = zone_item
        # Real Godot Area3D preview and collision volume. Gameplay receipts
        # deliberately use center-point XYZ to avoid shape contact ambiguity.
        var region := Area3D.new()
        region.name = "AuthoredGameZone_" + str(zone["id"])
        region.position = _vec(zone["center_xyz_m"])
        region.monitorable = false
        region.collision_layer = 0
        region.collision_mask = 1
        var shape := SphereShape3D.new()
        shape.radius = float(zone["radius_m"])
        var hitbox := CollisionShape3D.new()
        hitbox.shape = shape
        region.add_child(hitbox)
        var preview := MeshInstance3D.new()
        var sphere := SphereMesh.new()
        sphere.radius = shape.radius
        sphere.height = shape.radius * 2.0
        preview.mesh = sphere
        var tint := StandardMaterial3D.new()
        tint.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        tint.albedo_color = Color(0.1, 0.75, 0.95, 0.13)
        tint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        preview.material_override = tint
        region.add_child(preview)
        add_child(region)
    # Fixed user:// destination, not a user-supplied external path.
    _native_capture_file = FileAccess.open("user://frontier_native_physics.jsonl", FileAccess.WRITE)
    if _native_capture_file == null:
        push_error("Native capture file could not be opened")
        return
    _virtual_instrument_trace_file = FileAccess.open(
        "user://frontier_virtual_instruments.jsonl", FileAccess.WRITE)
    if _virtual_instrument_trace_file == null:
        push_error("Independent native instrument telemetry could not be opened")

func _load_approved_native_gameplay(capture: Dictionary) -> void:
    var dispatch_settings: Dictionary = capture.get("native_gameplay_dispatch", {})
    if dispatch_settings.is_empty():
        return
    # Fixed res:// path; no LLM-generated executable script or user path.
    var path := "res://frontier/data/native_gameplay_dispatch.json"
    var expected_sha := str(dispatch_settings.get("file_sha256", ""))
    if expected_sha.length() != 64 or not FileAccess.file_exists(path):
        push_error("Approved game dispatcher source file/digest missing")
        return
    if FileAccess.get_sha256(path) != expected_sha:
        push_error("Approved game dispatcher source SHA does not match scene")
        return
    var bundle: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
    if typeof(bundle) != TYPE_DICTIONARY:
        push_error("Approved game dispatcher must be typed JSON")
        return
    if (str(bundle.get("schema", "")) != "skeleton.game.native_godot_dispatch.v1"
        or str(bundle.get("authority", "")) !=
            "local_gameplay_state_only_not_canonical_GDD_or_network_attestation"
        or str(bundle.get("scene_candidate_digest", "")) != _native_candidate_sha
        or str(bundle.get("signed_gdd_digest", "")) != _native_signed_gdd_sha
        or str(bundle.get("actor_id", "")) != _native_actor_id):
        push_error("Approved game dispatcher scene/GDD/actor mismatch")
        return
    var actions: Array = bundle.get("actions", [])
    if actions.size() > 65536 or typeof(bundle.get("initial_flags")) != TYPE_DICTIONARY:
        push_error("Approved game dispatcher action budget invalid")
        return
    var quest_edges: Dictionary = bundle.get("quest_edges", {})
    var quest_starts: Dictionary = bundle.get("quest_start_stages", {})
    var quest_objectives: Dictionary = bundle.get("quest_objectives", {})
    var quest_titles: Dictionary = bundle.get("quest_titles", {})
    var next_flags: Dictionary = bundle["initial_flags"].duplicate(true)
    var next_quests: Dictionary = {}
    var next_cues: Array = []
    var next_camera_mode: int = 0
    var next_instrument_focus: String = "none"
    var next_quest_history: Array = []
    var next_action_trace: Array = []
    var next_inventory: Dictionary = {}
    var next_health: int = 100
    var next_local_effect_history: Array = []
    var next_npc_emotions: Dictionary = {}
    var last_tick: int = -1
    for row_item in actions:
        if typeof(row_item) != TYPE_DICTIONARY:
            push_error("Approved game command row invalid")
            return
        var row: Dictionary = row_item
        var frame: int = int(row.get("frame", -1))
        if frame < last_tick or frame < 0 or frame > int(bundle.get("source_through_frame", 0)):
            push_error("Approved game command time ordering invalid")
            return
        last_tick = frame
        if str(row.get("target", "")) != _native_actor_id:
            push_error("Approved game command actor is not the authorized player")
            return
        var kind := str(row.get("kind", ""))
        var value := str(row.get("value", ""))
        if kind == "start_quest":
            if not quest_starts.has(value) or next_quests.has(value):
                push_error("Approved game quest start missing or duplicated")
                return
            var initial_stage: String = str(quest_starts[value])
            var edges: Dictionary = quest_edges[value]
            next_quests[value] = {
                "stage": initial_stage, "completed":edges[initial_stage].is_empty(),
                "last_transition_frame": frame,
            }
        elif kind == "advance_quest":
            var token := value.split(":")
            if token.size() != 2 or not next_quests.has(token[0]):
                push_error("Approved game quest branch not active")
                return
            var record: Dictionary = next_quests[token[0]]
            if bool(record["completed"]):
                push_error("Approved game quest has already completed")
                return
            var choices: Array = quest_edges[token[0]][record["stage"]]
            if not choices.has(token[1]):
                push_error("Approved game quest transition missing authored edge")
                return
            next_quests[token[0]] = {
                "stage":token[1],
                "completed":quest_edges[token[0]][token[1]].is_empty(),
                "last_transition_frame":frame,
            }
        elif kind == "craft_item":
            if value.is_empty() or value.length() > 128:
                push_error("Approved crafted item name invalid")
                return
            next_inventory[value] = int(next_inventory.get(value, 0)) + 1
            if int(next_inventory[value]) > 9999 or next_inventory.size() > 1024:
                push_error("Approved local inventory limit exceeded")
                return
        elif kind == "take_damage" or kind == "heal_health":
            var accepted_number: bool = (
                value.length() >= 1 and value.length() <= 3
                and not (value.length() > 1 and value.begins_with("0"))
            )
            for character in value:
                if not "0123456789".contains(character):
                    accepted_number = false
            if not accepted_number or int(value) < 1 or int(value) > 100:
                push_error("Approved local health delta is not canonical 1..100")
                return
            var delta: int = int(value)
            next_health = (
                maxi(0,next_health - delta) if kind == "take_damage"
                else mini(100,next_health + delta)
            )
            next_local_effect_history.append({
                "frame":frame,"page_id":str(row.get("page_id","")),
                "kind":kind,"value":value,"resulting_health":next_health,
                "source_frame_digest":str(row.get("native_frame_receipt_digest","")),
            })
        elif kind == "consume_item":
            if not next_inventory.has(value) or int(next_inventory[value]) < 1:
                push_error("Local approved item cannot be consumed before acquisition")
                return
            next_inventory[value] = int(next_inventory[value]) - 1
            if int(next_inventory[value]) == 0:
                next_inventory.erase(value)
            next_local_effect_history.append({
                "frame":frame,"page_id":str(row.get("page_id","")),
                "kind":kind,"value":value,"resulting_health":next_health,
                "source_frame_digest":str(row.get("native_frame_receipt_digest","")),
            })
        elif kind == "set_npc_emotion":
            var mood_parts := value.split(":")
            if mood_parts.size() != 2 or not [
                "calm", "alert", "friendly", "afraid", "hostile", "curious"
            ].has(mood_parts[1]):
                push_error("Approved NPC emotion command invalid")
                return
            next_npc_emotions[mood_parts[0]] = mood_parts[1]
        elif kind == "inspect_instrument":
            if not ["flight","landing","camera"].has(value):
                push_error("Unapproved instrument focus rejected")
                return
            next_instrument_focus = value
            next_cues.append({
                "kind":kind,"cue":value,"source_frame":frame,
                "page_id":str(row.get("page_id","")),
            })
        elif kind == "change_camera":
            var camera_modes := {
                "authored":0,"follow":1,"orbit":2,"overhead":3
            }
            if not camera_modes.has(value):
                push_error("Unapproved cinematic camera mode rejected")
                return
            next_camera_mode = int(camera_modes[value])
            next_cues.append({
                "kind":kind,"cue":value,"source_frame":frame,
                "page_id":str(row.get("page_id","")),
            })
        elif kind == "set_flag":
            var pair := value.split("=")
            if pair.size() != 2 or not ["true", "false"].has(pair[1]):
                push_error("Approved game quest flag must be boolean")
                return
            next_flags[pair[0]] = pair[1] == "true"
        elif ["show_dialogue", "play_cutscene", "play_music",
              "spatial_audio",
              "trigger_impact_fx", "trigger_foliage_fx"].has(kind):
            next_cues.append({
                "kind":kind, "cue":value, "source_frame":frame,
                "page_id":str(row.get("page_id","")),
            })
        else:
            # Inventory/world/NPC changes are NEVER inferred from proposals.
            # Only typed commands with an approved runtime gateway may run.
            push_error("Unsupported game world mutation rejected by dispatcher")
            return
        if kind == "start_quest" or kind == "advance_quest":
            var chunks := value.split(":")
            var quest_id: String = str(chunks[0])
            var stage_id: String = (
                str(quest_starts[quest_id]) if kind == "start_quest"
                else str(chunks[1])
            )
            var objective: Dictionary = quest_objectives[quest_id]
            if not objective.has(stage_id):
                push_error("Quest history stage lacks authored objective")
                return
            next_quest_history.append({
                "frame":frame,"page_id":str(row.get("page_id", "")),
                "quest_id":quest_id,"title":str(quest_titles[quest_id]),
                "stage_id":stage_id,"objective":str(objective[stage_id]),
                "completed":quest_edges[quest_id][stage_id].is_empty(),
                "source_frame_digest":str(row.get("native_frame_receipt_digest", "")),
            })
        next_action_trace.append({
            "frame":frame,"page_id":str(row.get("page_id", "")),
            "action_index":int(row.get("action_index", -1)),
            "kind":kind,
            "native_frame_receipt_digest":str(row.get("native_frame_receipt_digest", "")),
            "approved_event_evidence_digest":str(row.get("approved_event_evidence_digest", "")),
        })
    # Godot JSON.parse_string decodes JSON numeric fields as float. The
    # Python quest source defines transition ticks and inventory counts as
    # integers; normalize only these known typed keys before strict equality.
    var expected_quests: Dictionary = bundle.get("expected_quests", {}).duplicate(true)
    for qid in expected_quests.keys():
        var expected_stage: Dictionary = expected_quests[qid]
        var raw_tick: Variant = expected_stage.get("last_transition_frame", -1)
        if float(raw_tick) != floorf(float(raw_tick)):
            push_error("Nonintegral signed quest source tick")
            return
        expected_stage["last_transition_frame"] = int(raw_tick)
    var expected_inventory: Dictionary = bundle.get("expected_inventory", {}).duplicate(true)
    for item_id in expected_inventory.keys():
        var amount: Variant = expected_inventory[item_id]
        if float(amount) != floorf(float(amount)):
            push_error("Nonintegral signed inventory source count")
            return
        expected_inventory[item_id] = int(amount)
    var expected_trace: Array = bundle.get("expected_action_trace", []).duplicate(true)
    for trace_item in expected_trace:
        if typeof(trace_item) != TYPE_DICTIONARY:
            push_error("Approved source action trace row is not an object")
            return
        var trace_row: Dictionary = trace_item
        for numeric_key in ["frame", "action_index"]:
            var source_number: Variant = trace_row.get(numeric_key, -1)
            if float(source_number) < 0.0 or float(source_number) != floorf(float(source_number)):
                push_error("Approved source action trace index is not integral")
                return
            trace_row[numeric_key] = int(source_number)
    var expected_history: Array = bundle.get("expected_quest_history", []).duplicate(true)
    for history_item in expected_history:
        if typeof(history_item) != TYPE_DICTIONARY:
            push_error("Authored quest history row invalid")
            return
        var tick: Variant = history_item.get("frame", -1)
        if float(tick) < 0.0 or float(tick) != floorf(float(tick)):
            push_error("Authored quest history tick invalid")
            return
        history_item["frame"] = int(tick)
    var expected_effect_history: Array = (
        bundle.get("expected_local_effect_history", []).duplicate(true)
    )
    for effect_item in expected_effect_history:
        if typeof(effect_item) != TYPE_DICTIONARY:
            push_error("Expected local RPG effect receipt invalid")
            return
        var effect: Dictionary = effect_item
        for numeric_key in ["frame", "resulting_health"]:
            var numeric_value: Variant = effect.get(numeric_key, -1)
            if (float(numeric_value) < 0.0 or
                float(numeric_value) != floorf(float(numeric_value))):
                push_error("Expected local health receipt nonintegral")
                return
            effect[numeric_key] = int(numeric_value)
    if (next_flags != bundle.get("expected_flags", {})
        or next_quests != expected_quests
        or next_inventory != expected_inventory
        or next_health != int(bundle.get("expected_local_health", -1))
        or next_local_effect_history != expected_effect_history
        or next_npc_emotions != bundle.get("expected_npc_emotions", {})
        or next_action_trace != expected_trace
        or next_camera_mode != int(bundle.get("expected_camera_mode", -1))
        or next_instrument_focus != str(bundle.get("expected_instrument_focus", ""))
        or next_quest_history != expected_history):
        push_error("Engine RPG reducer diverged from independently replayed state")
        return
    for quest_id in next_quests.keys():
        var progress: Dictionary = next_quests[quest_id]
        if (not quest_objectives.has(quest_id)
            or not quest_titles.has(quest_id)
            or not quest_objectives[quest_id].has(progress["stage"])):
            push_error("Approved quest stage has no source-authored objective")
            return
    _approved_quest_history = next_quest_history
    _approved_instrument_focus = next_instrument_focus
    _apply_approved_instrument_focus()
    _virtual_camera_mode = next_camera_mode
    _refresh_game_camera_mode()
    _approved_gameplay_dispatch_digest = str(bundle.get("receipt_digest", ""))
    _approved_gameplay_quests = next_quests
    _approved_gameplay_flags = next_flags
    _approved_gameplay_inventory = next_inventory
    _approved_local_health = next_health
    _approved_local_effect_history = next_local_effect_history
    _approved_health_effect_kinds = _create_approved_health_visuals()
    _approved_inventory_visuals = _create_approved_inventory_objects(next_inventory)
    _approved_gameplay_npc_emotions = next_npc_emotions
    _approved_gameplay_cues = next_cues
    _approved_fx_page_ids = _create_approved_fx_meshes(next_cues)
    _approved_cue_timeline = next_cues.duplicate(true)
    _approved_cue_cursor = 0
    _approved_npc_visuals = _show_approved_npc_reactions(next_npc_emotions)
    if _approved_npc_visuals.size() != next_npc_emotions.size():
        push_error("Approved NPC reactions did not resolve to native source actors")
        return
    _approved_quest_objectives = quest_objectives
    _approved_quest_titles = quest_titles
    var next_branch_options: Dictionary = {}
    for quest_id in next_quests.keys():
        var current_stage: String = str(next_quests[quest_id]["stage"])
        var possibilities: Array = quest_edges[quest_id][current_stage]
        var candidates: Array = []
        for stage_id in possibilities:
            candidates.append({"stage_id":stage_id,
                               "objective":quest_objectives[quest_id][stage_id]})
        next_branch_options[quest_id] = candidates
    if next_branch_options != bundle.get("available_branch_options", {}):
        push_error("Authored branching preview mismatches replayed graph")
        return
    _approved_branch_options = next_branch_options
    # One atomic document recording the actual Godot dispatch outcome.
    # Canonical GDD and native physics frame evidence are never rewritten.
    var cue_ticks: Array = []
    for cue_item in next_cues:
        cue_ticks.append(int(cue_item["source_frame"]))
    var runtime_ui_modules: Array[String] = []
    if _native_flight_instrument_label != null:
        runtime_ui_modules.append("virtual_flight_instruments")
    if _native_landing_risk_label != null and _native_landing_risk_meter != null:
        runtime_ui_modules.append("native_landing_risk")
    if _virtual_camera_mode_label != null and _native_camera != null:
        runtime_ui_modules.append("cinematic_camera_director")
    if runtime_ui_modules.size() != 3:
        push_error("Required native Godot game interface is missing")
        return
    var accepted := {
        "schema":"skeleton.game.godot_approved_dispatch_receipt.v1",
        "dispatch_file_sha256":expected_sha,
        "dispatch_receipt_digest":bundle["receipt_digest"],
        "signed_gdd_digest":_native_signed_gdd_sha,
        "scene_candidate_digest":_native_candidate_sha,
        "actor_id":_native_actor_id,
        "source_through_frame":bundle["source_through_frame"],
        "actions_applied":actions.size(),
        "quests":next_quests,"flags":next_flags,
        "approved_camera_mode":next_camera_mode,
        "approved_instrument_focus":next_instrument_focus,
        "runtime_ui_modules":runtime_ui_modules,
        "quest_progression_history":next_quest_history,
        "inventory":next_inventory,"npc_emotions":next_npc_emotions,
        "local_health":next_health,"local_effect_history":next_local_effect_history,
        "visualized_health_effect_kinds":_approved_health_effect_kinds,
        "visualized_npc_ids":_approved_npc_visuals,
        "visualized_item_ids":_approved_inventory_visuals,
        "executed_action_trace":next_action_trace,
        "presentation_cues":next_cues,
        "cue_timeline_frame_index":cue_ticks,
        "read_only_branch_options":_approved_branch_options,
        "visualized_fx_page_ids":_approved_fx_page_ids,
        "authority":"approved_gameplay_runtime_local_state_not_canonical_world_promotion",
    }
    if not _persist_verified_gameplay_receipt(accepted):
        return
    _create_approved_gameplay_inspector(accepted)
    _create_approved_health_inspector()
    _create_approved_local_effect_history()
    _create_approved_dialogue_view()
    _create_approved_cue_timeline()
    _create_approved_branch_preview()
    _create_approved_npc_proximity_inspector()
    _create_approved_npc_interaction_status()
    _create_approved_inventory_inspector()
    _create_approved_quest_history_view()


func _persist_verified_gameplay_receipt(state: Dictionary) -> bool:
    # Second process start must NOT overwrite a changed game save. The
    # existing bytes are revalidated against the fully re-reduced, SHA-bound
    # approved source. This is local file integrity, not server authentication.
    var path := "user://frontier_approved_gameplay_receipt.json"
    var canonical := JSON.stringify(state) + "\n"
    if FileAccess.file_exists(path):
        var previous := FileAccess.get_file_as_string(path)
        if previous != canonical:
            push_error("Existing approved game save differs from replay; explicit recovery required")
            return false
        return true
    var output := FileAccess.open(path, FileAccess.WRITE)
    if output == null:
        push_error("Native approved gameplay save cannot be created")
        return false
    output.store_string(canonical)
    output.flush()
    output.close()
    if not FileAccess.file_exists(path) or FileAccess.get_file_as_string(path) != canonical:
        push_error("Approved gameplay save did not survive readback")
        return false
    return true


func _create_approved_health_visuals() -> Array[String]:
    var output: Array[String] = []
    if _aero_character == null:
        return output
    for event in _approved_local_effect_history:
        var kind: String = str(event.get("kind", ""))
        if kind != "take_damage" and kind != "heal_health":
            continue
        if output.size() >= 32:
            break
        var light := MeshInstance3D.new()
        light.name = "SourceApprovedHealthEffect_" + str(output.size())
        var sphere := SphereMesh.new()
        sphere.radius = .52 + .06 * float(output.size())
        sphere.height = sphere.radius * 2.0
        light.mesh = sphere
        var tint := StandardMaterial3D.new()
        tint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        tint.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        tint.albedo_color = (
            Color(1., .13, .16, .22) if kind == "take_damage"
            else Color(.20, 1., .35, .22)
        )
        light.material_override = tint
        light.position = Vector3(0., .25, 0.)
        _aero_character.add_child(light)
        _approved_health_effect_meshes.append(light)
        output.append(kind)
    return output


func _animate_approved_health_effects(delta: float) -> void:
    if _approved_health_effect_meshes.is_empty():
        return
    # Purely cosmetic and bounded: no physics forces or unapproved harm.
    var tick: float = float(Time.get_ticks_msec()) * .001
    for i in range(_approved_health_effect_meshes.size()):
        var node: MeshInstance3D = _approved_health_effect_meshes[i]
        node.scale = Vector3.ONE * (
            .94 + .11 * sin(tick * 2.0 + float(i) * .7)
        )


func _create_approved_local_effect_history() -> void:
    if _approved_local_effect_history.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedRPGBattleAndCraftHistory"
    var label := Label.new()
    label.name = "SourceBoundLocalEffectPage"
    label.position = Vector2(20, 745)
    label.add_theme_color_override("font_color",Color(1.,.82,.44))
    overlay.add_child(label)
    add_child(overlay)
    _approved_effect_history_label = label
    _approved_effect_history_cursor = 0
    _show_approved_local_effect_history()


func _show_approved_local_effect_history() -> void:
    if _approved_effect_history_label == null:
        return
    var receipt: Dictionary = _approved_local_effect_history[_approved_effect_history_cursor]
    _approved_effect_history_label.text = (
        "SOURCE-APPROVED COMBAT / ITEM LOG (K to cycle)\n" +
        str(_approved_effect_history_cursor+1) + "/" +
        str(_approved_local_effect_history.size()) +
        " | frame " + str(receipt["frame"]) +
        " | " + str(receipt["kind"]) + " " + str(receipt["value"]) +
        " | remaining health " + str(receipt["resulting_health"]) +
        "\nSource: " + str(receipt["source_frame_digest"]).substr(0,16)
    )


func _cycle_approved_local_effect_history() -> void:
    if _approved_local_effect_history.is_empty():
        return
    _approved_effect_history_cursor = (
        _approved_effect_history_cursor+1
    ) % _approved_local_effect_history.size()
    _show_approved_local_effect_history()


func _create_approved_health_inspector() -> void:
    var overlay := CanvasLayer.new()
    overlay.name = "SourceApprovedGameHealth"
    var stack := VBoxContainer.new()
    stack.name = "ApprovedHealthMeterAndHistory"
    stack.position = Vector2(20, 35)
    stack.custom_minimum_size = Vector2(310, 46)
    var label := Label.new()
    label.name = "ApprovedLocalHealthLabel"
    label.text = ("Approved local RPG health: " +
                  str(_approved_local_health) + " / 100")
    stack.add_child(label)
    var meter := ProgressBar.new()
    meter.name = "ApprovedLocalHealthMeter"
    meter.min_value = 0
    meter.max_value = 100
    meter.value = _approved_local_health
    stack.add_child(meter)
    overlay.add_child(stack)
    add_child(overlay)


func _create_approved_inventory_objects(items: Dictionary) -> Array[String]:
    # A simple low-resource visual on the actual controlled RigidBody3D.
    # Never invent unapproved loot and never instantiate thousands of meshes.
    var created: Array[String] = []
    if _aero_character == null:
        return created
    var known_ids: Array = items.keys()
    known_ids.sort()
    for index in range(mini(24, known_ids.size())):
        var item_name: String = str(known_ids[index])
        var token := MeshInstance3D.new()
        token.name = "ApprovedInventoryToken_" + item_name
        var cube := BoxMesh.new()
        cube.size = Vector3(.2,.2,.2)
        token.mesh = cube
        var radians := float(index) * TAU / 24.0
        token.position = Vector3(cos(radians)*.8, .7, sin(radians)*.8)
        var mat := StandardMaterial3D.new()
        mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        mat.albedo_color = Color.from_hsv(float(index % 24)/24., .75, .95)
        token.material_override = mat
        _aero_character.add_child(token)
        created.append(item_name)
    return created


func _show_approved_npc_reactions(moods: Dictionary) -> Array[String]:
    # Render an actual mood beacon on the native scene node. A signed
    # captured source ID, not a free-form label, decides the target.
    var affected: Array[String] = []
    var palette := {
        "calm":Color(.35,.65,.95),
        "alert":Color(1.,.65,.10),
        "friendly":Color(.18,.95,.42),
        "afraid":Color(.86,.65,1.),
        "hostile":Color(1.,.12,.12),
        "curious":Color(.92,.82,.24),
    }
    for npc_id in moods.keys():
        var selected: Node3D
        for source_index in range(_native_capture_actors.size()):
            var spec: Dictionary = _native_capture_actors[source_index]
            if str(spec.get("id", "")) == str(npc_id) and str(npc_id) != _native_actor_id:
                selected = _native_capture_nodes[source_index]
                break
        if selected == null or not palette.has(str(moods[npc_id])):
            push_error("Source NPC reaction lacks target or mood")
            return []
        var marker := MeshInstance3D.new()
        marker.name = "ApprovedNPCMood_" + str(npc_id)
        marker.position = Vector3(0., .8, 0.)
        var sphere := SphereMesh.new()
        sphere.radius = .27
        sphere.height = .54
        marker.mesh = sphere
        var material := StandardMaterial3D.new()
        material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        material.albedo_color = palette[str(moods[npc_id])]
        marker.material_override = material
        selected.add_child(marker)
        affected.append(str(npc_id))
    affected.sort()
    return affected


func _create_approved_gameplay_inspector(record: Dictionary) -> void:
    var hud := CanvasLayer.new()
    hud.name = "NativeApprovedGameplayHUD"
    var inspector := Label.new()
    inspector.name = "ApprovedQuestState"
    inspector.position = Vector2(20, 770)
    inspector.add_theme_color_override("font_color",Color(.95,.84,.35))
    var content: Array[String] = [
        "Approved Godot game session | local gameplay, not canon promotion",
        "Frames 0 - " + str(record["source_through_frame"]) +
            " | verified RPG actions " + str(record["actions_applied"]),
    ]
    for id in _approved_gameplay_quests.keys():
        var state: Dictionary = _approved_gameplay_quests[id]
        content.append(str(_approved_quest_titles[id]) + " : " + str(state["stage"]) +
            (" (completed)" if bool(state["completed"]) else " (in progress)"))
        content.append("Objective: " +
            str(_approved_quest_objectives[id][state["stage"]]))
    for item in _approved_gameplay_inventory.keys():
        content.append("Inventory: " + str(item) + " x" + str(_approved_gameplay_inventory[item]))
    for actor in _approved_gameplay_npc_emotions.keys():
        content.append("NPC reaction: " + str(actor) + " / " + str(_approved_gameplay_npc_emotions[actor]))
    for cue in _approved_gameplay_cues:
        if cue["kind"] == "show_dialogue":
            content.append("Dialogue: " + str(cue["cue"]))
    inspector.text = "\n".join(content)
    hud.add_child(inspector)
    add_child(hud)
    _approved_gameplay_label = inspector


func _create_approved_fx_meshes(cues: Array) -> Array[String]:
    # Approved cue previews are cosmetics only: no collisions or GDD mutation.
    var result: Array[String] = []
    if _aero_character == null:
        return result
    for cue_item in cues:
        var cue: Dictionary = cue_item
        var kind: String = str(cue.get("kind", ""))
        if kind != "trigger_impact_fx" and kind != "trigger_foliage_fx":
            continue
        if result.size() >= 64:
            push_error("Approved VFX preview exceeds mesh budget")
            return []
        var visual := MeshInstance3D.new()
        visual.name = "ApprovedCueFX_" + str(result.size())
        var sphere := SphereMesh.new()
        sphere.radius = .45
        sphere.height = .9
        visual.mesh = sphere
        visual.position = Vector3(0., .4 + float(result.size())*.08, 0.)
        var material := StandardMaterial3D.new()
        material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        material.albedo_color = (
            Color(.99,.42,.18,.35) if kind == "trigger_impact_fx"
            else Color(.25,.96,.42,.35)
        )
        visual.material_override = material
        _aero_character.add_child(visual)
        _approved_fx_nodes.append(visual)
        result.append(str(cue.get("page_id", "")))
    return result


func _animate_approved_fx(delta: float) -> void:
    if _approved_fx_nodes.is_empty():
        return
    _approved_fx_clock += maxf(0., delta)
    for i in range(_approved_fx_nodes.size()):
        var scalar := .7 + .16 * sin(_approved_fx_clock * 1.5 + float(i))
        _approved_fx_nodes[i].scale = Vector3.ONE * scalar


func _create_approved_quest_history_view() -> void:
    if _approved_quest_history.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedQuestHistoryViewer"
    var label := Label.new()
    label.name = "VerifiedQuestHistory"
    label.position = Vector2(20, 365)
    label.add_theme_color_override("font_color", Color(.85, .82, .98))
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    overlay.add_child(label)
    add_child(overlay)
    _approved_quest_history_label = label
    _approved_quest_history_cursor = 0
    _show_approved_quest_history()


func _show_approved_quest_history() -> void:
    if _approved_quest_history_label == null or _approved_quest_history.is_empty():
        return
    var row: Dictionary = _approved_quest_history[_approved_quest_history_cursor]
    _approved_quest_history_label.text = (
        "Verified quest history (J): " + str(_approved_quest_history_cursor + 1) +
        "/" + str(_approved_quest_history.size()) +
        " | frame " + str(row["frame"]) +
        "\n" + str(row["title"]) + " / " + str(row["stage_id"]) +
        ": " + str(row["objective"]) +
        (" [completed]" if bool(row["completed"]) else "")
    )


func _next_approved_quest_history() -> void:
    if _approved_quest_history.is_empty():
        return
    _approved_quest_history_cursor = (
        _approved_quest_history_cursor + 1
    ) % _approved_quest_history.size()
    _show_approved_quest_history()


func _create_approved_inventory_inspector() -> void:
    if _approved_gameplay_inventory.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedInventoryBrowser"
    var label := Label.new()
    label.name = "ApprovedInventorySelectedItem"
    label.position = Vector2(20, 440)
    label.add_theme_color_override("font_color", Color(.8, .99, .5))
    overlay.add_child(label)
    add_child(overlay)
    _approved_inventory_label = label
    _approved_inventory_focus = 0
    _show_approved_inventory()


func _show_approved_inventory() -> void:
    if _approved_inventory_label == null:
        return
    var available: Array = _approved_gameplay_inventory.keys()
    available.sort()
    if available.is_empty():
        _approved_inventory_label.text = "Inventory: no approved items"
        return
    var chosen: String = str(available[_approved_inventory_focus % available.size()])
    _approved_inventory_label.text = (
        "Game inventory " + str(_approved_inventory_focus + 1) +
        "/" + str(available.size()) + " (I to inspect)\n" +
        chosen + " x" + str(_approved_gameplay_inventory[chosen]) +
        " | inspect only, no unapproved consumption"
    )


func _cycle_approved_inventory() -> void:
    if _approved_gameplay_inventory.is_empty():
        return
    _approved_inventory_focus = (
        _approved_inventory_focus + 1
    ) % _approved_gameplay_inventory.size()
    _show_approved_inventory()


func _create_approved_npc_proximity_inspector() -> void:
    if _approved_gameplay_npc_emotions.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedNPCProximityInspector"
    var label := Label.new()
    label.name = "ApprovedNearbyNPC"
    label.position = Vector2(20, 495)
    label.add_theme_color_override("font_color", Color(.95, .85, .5))
    overlay.add_child(label)
    add_child(overlay)
    _approved_npc_proximity_label = label
    _inspect_approved_npc_proximity()


func _inspect_approved_npc_proximity() -> void:
    if _approved_npc_proximity_label == null or _aero_character == null:
        return
    var best_distance := INF
    var best_id := ""
    for i in range(_native_capture_actors.size()):
        var spec: Dictionary = _native_capture_actors[i]
        var npc_id := str(spec.get("id", ""))
        if not _approved_gameplay_npc_emotions.has(npc_id):
            continue
        var actor_node: Node3D = _native_capture_nodes[i]
        if actor_node == null:
            continue
        var distance := _aero_character.global_position.distance_to(actor_node.global_position)
        if distance < best_distance:
            best_distance = distance
            best_id = npc_id
    _approved_npc_focus = best_id if best_distance <= 6.0 else ""
    if _approved_npc_focus.is_empty():
        _approved_npc_proximity_label.text = "NPC interaction: none within 6 game metres"
    else:
        _approved_npc_proximity_label.text = (
            "Nearby NPC " + _approved_npc_focus + " | " +
            str(_approved_gameplay_npc_emotions[_approved_npc_focus]) +
            " | " + str(snappedf(best_distance, .01)) + " game metres" +
            " (N to inspect)"
        )


func _create_approved_npc_interaction_status() -> void:
    if _approved_gameplay_npc_emotions.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedNPCInteractionFeedback"
    var label := Label.new()
    label.name = "ApprovedNPCInteractionStatus"
    label.position = Vector2(20, 525)
    label.add_theme_color_override("font_color", Color(.9,.94,.55))
    label.text = "E: interact with source-verified NPC within 6 game metres"
    overlay.add_child(label)
    add_child(overlay)
    _approved_npc_interaction_status = label


func _interact_approved_npc() -> void:
    # An operator/player presses E in actual Godot. This is a *local*
    # interaction receipt, not a proposal to change AI-driven NPC canon.
    if (_approved_npc_focus.is_empty() or _aero_character == null
        or not _approved_gameplay_npc_emotions.has(_approved_npc_focus)):
        return
    var near: Node3D
    for i in range(_native_capture_actors.size()):
        if str(_native_capture_actors[i].get("id", "")) == _approved_npc_focus:
            near = _native_capture_nodes[i]
            break
    if near == null:
        return
    var distance: float = _aero_character.global_position.distance_to(near.global_position)
    if distance > 6.0:
        return
    var receipt := {
        "schema":"skeleton.game.native_npc_player_interaction.v1",
        "authority":"local_user_interaction_not_canonical_NPC_world_action",
        "scene_candidate_digest":_native_candidate_sha,
        "signed_gdd_digest":_native_signed_gdd_sha,
        "actor_id":_native_actor_id,
        "npc_source_id":_approved_npc_focus,
        "approved_npc_mood":_approved_gameplay_npc_emotions[_approved_npc_focus],
        "game_frame":_native_capture_tick,
        "game_distance_m":snappedf(distance,.001),
        "dispatch_receipt_digest":_approved_gameplay_dispatch_digest,
    }
    if _approved_npc_interaction_count >= 4096:
        push_error("Bounded local NPC interaction log exhausted")
        return
    var path := "user://frontier_local_npc_interactions.jsonl"
    var output := FileAccess.open(path, FileAccess.READ_WRITE)
    if output == null and not FileAccess.file_exists(path):
        output = FileAccess.open(path, FileAccess.WRITE_READ)
    if output == null:
        push_error("NPC interaction receipt could not be opened")
        return
    output.seek_end()
    output.store_string(JSON.stringify(receipt) + "\n")
    output.flush()
    output.close()
    _approved_npc_interaction_count += 1
    if _approved_npc_interaction_status != null:
        _approved_npc_interaction_status.text = (
            "Interacted with " + _approved_npc_focus + " [" +
            str(_approved_gameplay_npc_emotions[_approved_npc_focus]) +
            "] | " + str(_approved_npc_interaction_count) + " local receipts"
        )


func _inspect_approved_npc_focus() -> void:
    if _approved_npc_proximity_label == null or _approved_npc_focus.is_empty():
        return
    _approved_npc_proximity_label.text = (
        "Source NPC " + _approved_npc_focus + " / " +
        str(_approved_gameplay_npc_emotions[_approved_npc_focus]) +
        "\nObserved proximity only: no unsanctioned NPC actions."
    )


func _create_approved_branch_preview() -> void:
    var choices: Array[String] = []
    for quest_id in _approved_branch_options.keys():
        var next_stages: Array = _approved_branch_options[quest_id]
        for stage in next_stages:
            choices.append(
                str(_approved_quest_titles[quest_id]) +
                " -> " + str(stage["stage_id"]) + ": " +
                str(stage["objective"])
            )
    if choices.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedQuestBranchPreview"
    var title := Label.new()
    title.name = "ReadOnlyApprovedQuestOptions"
    title.position = Vector2(20, 550)
    title.add_theme_color_override("font_color",Color(.35,.8,.98))
    overlay.add_child(title)
    add_child(overlay)
    _approved_branch_label = title
    _approved_branch_cursor = 0
    _show_approved_branch(choices)


func _show_approved_branch(choices: Array[String]) -> void:
    if _approved_branch_label == null or choices.is_empty():
        return
    _approved_branch_label.text = (
        "Authored future branch (preview only, B cycles):\n" +
        choices[_approved_branch_cursor % choices.size()]
    )


func _cycle_approved_branch() -> void:
    var choices: Array[String] = []
    for quest_id in _approved_branch_options.keys():
        for stage in _approved_branch_options[quest_id]:
            choices.append(
                str(_approved_quest_titles[quest_id]) +
                " -> " + str(stage["stage_id"]) + ": " +
                str(stage["objective"])
            )
    if choices.is_empty():
        return
    _approved_branch_cursor = (_approved_branch_cursor + 1) % choices.size()
    _show_approved_branch(choices)


func _create_approved_cue_timeline() -> void:
    if _approved_cue_timeline.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedCinematicTimeline"
    var panel := PanelContainer.new()
    panel.name = "ApprovedCinematicCuePanel"
    panel.position = Vector2(20, 625)
    panel.custom_minimum_size = Vector2(330, 95)
    var content := VBoxContainer.new()
    var label := Label.new()
    label.name = "ApprovedCinematicCue"
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(label)
    var advance := Button.new()
    advance.name = "NextApprovedCue"
    advance.text = "Next approved cue (T)"
    advance.pressed.connect(_next_approved_cue)
    content.add_child(advance)
    panel.add_child(content)
    overlay.add_child(panel)
    add_child(overlay)
    _approved_cue_label = label
    _show_approved_cue()


func _show_approved_cue() -> void:
    if _approved_cue_label == null:
        return
    var cue: Dictionary = _approved_cue_timeline[_approved_cue_cursor]
    _approved_cue_label.text = (
        "Authored game cue " + str(_approved_cue_cursor + 1) +
        "/" + str(_approved_cue_timeline.size()) +
        " | evidence frame " + str(cue["source_frame"]) +
        "\n" + str(cue["kind"]) + ": " + str(cue["cue"]).substr(0, 160)
    )


func _next_approved_cue() -> void:
    if _approved_cue_timeline.is_empty():
        return
    _approved_cue_cursor = (_approved_cue_cursor + 1) % _approved_cue_timeline.size()
    _show_approved_cue()


func _create_approved_dialogue_view() -> void:
    _approved_dialogue_queue.clear()
    _approved_dialogue_cursor = 0
    for cue_item in _approved_gameplay_cues:
        var cue: Dictionary = cue_item
        if cue.get("kind", "") == "show_dialogue":
            _approved_dialogue_queue.append(str(cue.get("cue", "")).substr(0, 1024))
    if _approved_dialogue_queue.is_empty():
        return
    var overlay := CanvasLayer.new()
    overlay.name = "ApprovedGameDialogueOverlay"
    var panel := PanelContainer.new()
    panel.name = "ApprovedGameDialogueCard"
    panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
    panel.offset_left = 20
    panel.offset_right = -20
    panel.offset_top = -180
    panel.offset_bottom = -20
    var stack := VBoxContainer.new()
    var line := Label.new()
    line.name = "ApprovedDialogueText"
    line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    line.custom_minimum_size = Vector2(320, 68)
    line.add_theme_font_size_override("font_size", 20)
    stack.add_child(line)
    var advance_button := Button.new()
    advance_button.name = "ContinueApprovedDialogue"
    advance_button.text = "Continue (Enter / Space)"
    advance_button.pressed.connect(_advance_approved_dialogue)
    stack.add_child(advance_button)
    panel.add_child(stack)
    overlay.add_child(panel)
    add_child(overlay)
    _approved_dialogue_panel = panel
    _approved_dialogue_label = line
    _show_approved_dialogue()


func _show_approved_dialogue() -> void:
    if _approved_dialogue_label == null:
        return
    if _approved_dialogue_cursor >= _approved_dialogue_queue.size():
        _approved_dialogue_panel.hide()
        return
    _approved_dialogue_label.text = (
        "Verified dialogue " + str(_approved_dialogue_cursor + 1) + " / " +
        str(_approved_dialogue_queue.size()) + "\n" +
        _approved_dialogue_queue[_approved_dialogue_cursor]
    )


func _advance_approved_dialogue() -> void:
    if _approved_dialogue_cursor >= _approved_dialogue_queue.size():
        return
    _approved_dialogue_cursor += 1
    _show_approved_dialogue()


func _native_chunk_less(a: Dictionary, b: Dictionary) -> bool:
    var first: Array = a["chunk_xy"]
    var second: Array = b["chunk_xy"]
    if int(first[0]) != int(second[0]):
        return int(first[0]) < int(second[0])
    return int(first[1]) < int(second[1])

func _create_native_playtest_inspector() -> void:
    var overlay := CanvasLayer.new()
    overlay.name = "NativeGameplayEventInspector"
    var text_label := Label.new()
    text_label.name = "LiveGameplayProposals"
    text_label.position = Vector2(20, 530)
    text_label.add_theme_color_override("font_color", Color(0.74, 0.98, 0.84))
    text_label.text = "Godot gameplay preview | pending physics capture"
    overlay.add_child(text_label)
    add_child(overlay)
    _native_preview_label = text_label

func _native_zone_event(member: Dictionary, transition: String) -> Dictionary:
    for zone_item in _native_gameplay_zones:
        var zone: Dictionary = zone_item
        if str(zone["id"]) == str(member["zone_id"]):
            return {
                "zone_id": member["zone_id"],
                "actor_id": member["actor_id"],
                "transition": transition,
                "event_page_id": zone["event_page_id"],
                "action_kind": zone["action_kind"],
                "authority": "proposal_only_no_world_mutation",
            }
    return {}

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
    if not _native_force_fields.is_empty():
        row["native_force_field_schema"] = "skeleton.game.native_force_fields.v1"
        row["native_force_fields"] = _native_force_fields
        row["previous_step_field_forces"] = _native_previous_field_steps.duplicate(true)
    if not _native_gameplay_zones.is_empty():
        var occupants: Array = []
        for zone_item in _native_gameplay_zones:
            var zone: Dictionary = zone_item
            for actor_item in recorded:
                var actor: Dictionary = actor_item
                if str(actor["id"]) != str(zone["actor_id"]):
                    continue
                var point: Vector3 = _vec(actor["world_xyz_m"])
                var center: Vector3 = _vec(zone["center_xyz_m"])
                var radius: float = float(zone["radius_m"])
                if point.distance_squared_to(center) <= radius * radius:
                    occupants.append({
                        "zone_id": zone["id"], "actor_id": zone["actor_id"],
                    })
        var changes: Array = []
        for item in occupants:
            if not _native_previous_zone_members.has(item):
                changes.append(_native_zone_event(item, "enter"))
        for item in _native_previous_zone_members:
            if not occupants.has(item):
                changes.append(_native_zone_event(item, "exit"))
        changes.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            if str(a["zone_id"]) != str(b["zone_id"]):
                return str(a["zone_id"]) < str(b["zone_id"])
            if str(a["actor_id"]) != str(b["actor_id"]):
                return str(a["actor_id"]) < str(b["actor_id"])
            return str(a["transition"]) < str(b["transition"]))
        row["native_zone_schema"] = "skeleton.game.native_zones.v1"
        row["gameplay_zones"] = _native_gameplay_zones
        row["native_zone_occupancy"] = occupants
        row["native_zone_events"] = changes
        _native_previous_zone_members = occupants.duplicate(true)
        for event_item in changes:
            var ev: Dictionary = event_item
            _native_recent_zone_events.append(str(ev["transition"]) +
                " / " + str(ev["event_page_id"]) + " / " + str(ev["action_kind"]))
        while _native_recent_zone_events.size() > 5:
            _native_recent_zone_events.pop_front()
        if _native_preview_label != null:
            var lines: Array[String] = [
                "Godot RPG game zones | candidate actions, not canon",
                "Tick " + str(_native_capture_tick) + "  |  " +
                    str(Engine.physics_ticks_per_second) + " Hz fixed solver",
                "Zones " + str(_native_gameplay_zones.size()) +
                    " | occupants " + str(occupants.size()) +
                    " | field forces " + str(_native_force_fields.size()) +
                    " | preview speed x" + str(_native_debug_speed),
                "P pause/resume | - slower | = faster | F fields",
            ]
            lines.append_array(_native_recent_zone_events)
            _native_preview_label.text = "\n".join(lines)
    if _virtual_instrument_trace_file != null:
        for actor_sample in recorded:
            if str(actor_sample["id"]) != _native_actor_id:
                continue
            var av: Vector3 = _vec(actor_sample["velocity_xyz_mps"])
            var player_xyz: Array = actor_sample["world_xyz_m"]
            var player_velocity: Array = actor_sample["velocity_xyz_mps"]
            var speed: float = Vector2(av.x,av.z).length()
            var absolute_heading: float = (
                fposmod(rad_to_deg(atan2(av.x,-av.z)),360.0)
                if speed > .0000001 else 0.0
            )
            var instrument := {
                "schema":"skeleton.game.godot_native_instrument_sample.v1",
                "authority":"independent_native_instrument_observation_not_attested",
                "scene_candidate_digest":_native_candidate_sha,
                "signed_gdd_digest":_native_signed_gdd_sha,
                "actor_id":_native_actor_id,
                "native_tick":_native_capture_tick,
                "fps":Engine.physics_ticks_per_second,
                "world_xyz_m":player_xyz,
                "velocity_xyz_mps":player_velocity,
                "ground_speed_mps":speed,
                "vertical_rate_mps":av.y,
                "heading_deg":absolute_heading,
                "airflow_xyz_mps":[_aero_wind.x,-_aero_wind.z,_aero_wind.y],
                "air_relative_speed_mps":(av-_aero_wind).length(),
                "contact_count":actor_sample["contact_count"],
            }
            _virtual_instrument_trace_file.store_line(JSON.stringify(instrument))
            _virtual_instrument_trace_file.flush()
            break
    _native_capture_file.store_line(JSON.stringify(row))
    _native_capture_file.flush()
    _native_capture_tick += 1

func _exit_tree() -> void:
    if _native_capture_file != null:
        _native_capture_file.close()
        _native_capture_file = null
    if _virtual_instrument_trace_file != null:
        _virtual_instrument_trace_file.close()
        _virtual_instrument_trace_file = null

func _apply_native_gameplay_fields() -> void:
    if _native_force_fields.is_empty() or _aero_character == null:
        return
    if _native_capture_tick > _native_capture_max_frames:
        return
    var point := _aero_character.global_position
    var game_xyz: Array = [point.x, -point.z, point.y]
    var steps: Array = []
    for field_item in _native_force_fields:
        var field: Dictionary = field_item
        var center: Array = field["center_xyz_m"]
        var dx: float = float(game_xyz[0]) - float(center[0])
        var dy: float = float(game_xyz[1]) - float(center[1])
        var dz: float = float(game_xyz[2]) - float(center[2])
        var radius: float = float(field["radius_m"])
        var distance_squared: float = dx * dx + dy * dy + dz * dz
        var taper: float = maxf(0.0, 1.0 - distance_squared / (radius * radius))
        var kind: String = str(field["kind"])
        var direction: Vector3 = Vector3.ZERO
        if kind == "updraft":
            direction = Vector3.UP
        elif kind == "downdraft":
            direction = Vector3.DOWN
        elif kind == "eastward_current":
            direction = Vector3.RIGHT
        elif kind == "vortex":
            var planar: float = sqrt(dx * dx + dy * dy)
            if planar > 0.000000001:
                direction = _vec([-dy / planar, dx / planar, 0.0])
        var applied: Vector3 = direction * _aero_character.mass * (
            float(field["acceleration_mps2"]) * taper)
        _aero_character.apply_central_force(applied)
        steps.append({
            "field_id": field["id"],
            "actor_id": field["actor_id"],
            "command_tick": _native_capture_tick - 1,
            "source_position_xyz_m": game_xyz,
            "force_world_xyz_n": [applied.x, -applied.z, applied.y],
        })
    _native_previous_field_steps = steps

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

func _unhandled_key_input(event: InputEvent) -> void:
    if not (event is InputEventKey):
        return
    var key := event as InputEventKey
    if not key.pressed or key.echo:
        return
    if key.physical_keycode == KEY_C and _native_camera != null:
        _cycle_game_cinematic_camera()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_M and not _game_route_waypoints.is_empty():
        _cycle_virtual_route_waypoint()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_H and _native_flight_instrument_label != null:
        _native_flight_instruments_visible = not _native_flight_instruments_visible
        _native_flight_instrument_label.visible = _native_flight_instruments_visible
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_J and not _approved_quest_history.is_empty():
        _next_approved_quest_history()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_K and not _approved_local_effect_history.is_empty():
        _cycle_approved_local_effect_history()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_I and not _approved_gameplay_inventory.is_empty():
        _cycle_approved_inventory()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_E and not _approved_npc_focus.is_empty():
        _interact_approved_npc()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_N and not _approved_npc_focus.is_empty():
        _inspect_approved_npc_focus()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_B and _approved_branch_label != null:
        _cycle_approved_branch()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode == KEY_T and not _approved_cue_timeline.is_empty():
        _next_approved_cue()
        get_viewport().set_input_as_handled()
        return
    if key.physical_keycode in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE] and _approved_dialogue_panel != null and _approved_dialogue_panel.visible:
        _advance_approved_dialogue()
        get_viewport().set_input_as_handled()
        return
    if not _native_controls_enabled:
        return
    if key.physical_keycode == KEY_F:
        _native_field_preview_visible = not _native_field_preview_visible
        for preview_node in _native_field_visual_nodes:
            preview_node.visible = _native_field_preview_visible
    elif key.physical_keycode == KEY_P:
        _native_debug_speed = 1.0 if _native_debug_speed == 0.0 else 0.0
        Engine.time_scale = _native_debug_speed
    elif key.physical_keycode == KEY_MINUS:
        _native_debug_speed = maxf(.25, _native_debug_speed * .5)
        Engine.time_scale = _native_debug_speed
    elif key.physical_keycode == KEY_EQUAL:
        _native_debug_speed = minf(4.,maxf(.25,_native_debug_speed) * 2.)
        Engine.time_scale = _native_debug_speed

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
    _apply_native_gameplay_fields()
    _apply_reference_controls()
    _inspect_approved_npc_proximity()
    _update_native_flight_instruments()
    _update_native_landing_risk()
    _update_live_virtual_gps_delta()

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
    _animate_approved_fx(delta)
    _animate_approved_health_effects(delta)
    _update_game_cinematic_camera(delta)
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
    native_gameplay_zones: tuple[Mapping, ...] = (),
    native_camera_follow: bool = False,
    native_gameplay_force_fields: tuple[Mapping, ...] = (),
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
    from skeleton.jeeves.game_frontier_native_zones import (
        normalize_gameplay_zones, NativeZoneError,
    )
    from skeleton.jeeves.game_frontier_native_fields import (
        normalize_native_force_fields, NativeForceFieldError,
    )
    if (native_gameplay_zones or native_gameplay_force_fields) and not enable_native_capture:
        raise FrontierGodotError("authored gameplay zones/force fields require native capture")
    if type(native_camera_follow) is not bool or (
        native_camera_follow and not enable_native_reference_controls):
        raise FrontierGodotError("native camera follow requires explicit reference controls")
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
        try:
            signed_gameplay_zones = normalize_gameplay_zones(
                native_gameplay_zones,
                allowed_actors={item["id"] for item in sources})
        except NativeZoneError as exc:
            raise FrontierGodotError("invalid or unauthorized authored game zones") from exc
        try:
            signed_gameplay_forces = normalize_native_force_fields(
                native_gameplay_force_fields, allowed_actors={actor_id})
        except NativeForceFieldError as exc:
            raise FrontierGodotError("native field may only target proven rigid reference actor") from exc
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
            "gameplay_zones": signed_gameplay_zones,
            "gameplay_force_fields": signed_gameplay_forces,
            "reference_controls": {
                "enabled": enable_native_reference_controls,
                "move_force_n": 240., "max_speed_mps": 8.,
                "jump_impulse_ns": 120.,
                "headless_fixture_ticks": native_reference_test_drive_ticks,
                "camera_follow": native_camera_follow,
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
    native_gameplay_zones: tuple[Mapping, ...] = (),
    native_camera_follow: bool = False,
    native_gameplay_force_fields: tuple[Mapping, ...] = (),
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
        native_gameplay_zones=native_gameplay_zones,
        native_camera_follow=native_camera_follow,
        native_gameplay_force_fields=native_gameplay_force_fields,
    )
    conflicts = tuple(sorted(set(project_files).intersection(overlay)))
    if any(project_files[key] != overlay[key] for key in conflicts):
        raise FrontierGodotError("existing frontier project overlay would be overwritten")
    return {**project_files, **overlay}
