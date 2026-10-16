"""Generated Godot 4 procedural stage and authored-cue playback.

A renderer of original, source-defined *placeholder geometry*. It does not
borrow external image/audio files or infer professional visual quality. The
quest-state transitions remain exclusively server-authoritative.
"""
from __future__ import annotations

STAGE_SCRIPT = r'''extends Control

# Original procedural stage. Never eval authored strings or load arbitrary paths.
var scene_data: Dictionary = {}
var media_catalog: Dictionary = {}
var backdrop: Texture2D
var score_player: AudioStreamPlayer
var music_enabled: bool = true
var current_score: String = ""
var environment_seconds: float = 0.0
var environment_redraw_accumulator: float = 0.0
var environment_quality: int = 2
var shift: float = 0.0
var camera_scale: float = 1.0
var actors: Array = []
var cue_text: String = ""
var environmental_tint: Color = Color(0.13, 0.25, 0.40)
var active_cues: Array = []
var pending_timelines: Array = []
var cue_index: int = 0
var elapsed_ms: float = 0.0
var timeline_end_ms: float = 0.0
var playback_speed: float = 1.0
var is_paused: bool = false
var playing: bool = false
var timeline_skippable: bool = true
var cue_label: Label
var runtime_label: Label
var motion_tweens: Array[Tween] = []
var last_completed_timeline: String = ""
var supported_cues: Dictionary = {
    "camera_cut": true, "camera_pan": true, "camera_track": true,
    "camera_dolly": true, "camera_zoom": true, "camera_shake": true,
    "subtitle": true, "dialogue": true, "voice_cue": true,
    "lighting": true, "weather": true, "color_grade": true,
    "fade": true, "actor_enter": true, "actor_exit": true,
    "actor_move": true, "actor_pose": true, "actor_emote": true,
    "animation": true, "music_cue": true, "sound_cue": true,
    "ambient_cue": true, "particle": true, "focus": true,
    "prop_state": true, "ui_prompt": true, "objective_reveal": true,
    "choice_prompt": true, "slow_motion": true, "pause": true,
    "resume": true, "hud_visibility": true, "wipe": true
}

func _ready() -> void:
    var source := FileAccess.get_file_as_string("res://media_catalog.json")
    var parsed = JSON.parse_string(source)
    if parsed is Dictionary and parsed.get("scenes") is Dictionary:
        media_catalog = parsed["scenes"]
    score_player = AudioStreamPlayer.new()
    score_player.volume_db = -18.0
    add_child(score_player)
    custom_minimum_size = Vector2(450, 310)
    clip_contents = true
    cue_label = Label.new()
    cue_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
    cue_label.offset_top = -90
    cue_label.offset_bottom = -45
    cue_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    cue_label.add_theme_color_override("font_color", Color.WHITE)
    add_child(cue_label)
    runtime_label = Label.new()
    runtime_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
    runtime_label.offset_top = -39
    runtime_label.add_theme_color_override("font_color", Color.WHITE)
    add_child(runtime_label)
    resized.connect(queue_redraw)
    queue_redraw()

func apply_scene(data: Dictionary) -> void:
    scene_data = data
    var binding: Dictionary = media_catalog.get(str(data.get("key", "")), {})
    backdrop = null
    var image_path: String = str(binding.get("backdrop", ""))
    if image_path.begins_with("res://media/") and ResourceLoader.exists(image_path):
        var image_resource = load(image_path)
        if image_resource is Texture2D:
            backdrop = image_resource
    var music_path: String = str(binding.get("music", ""))
    if music_path != current_score:
        score_player.stop()
        current_score = music_path
        if music_path.begins_with("res://media/") and ResourceLoader.exists(music_path):
            var soundtrack = load(music_path)
            if soundtrack is AudioStream:
                if soundtrack is AudioStreamWAV:
                    soundtrack.loop_mode = AudioStreamWAV.LOOP_FORWARD
                score_player.stream = soundtrack
                if music_enabled:
                    score_player.play()
    actors = data.get("cast", []).duplicate()
    cue_text = str(data.get("title", ""))
    environmental_tint = _scene_tint(str(data.get("weather", "")))
    shift = 0.0
    camera_scale = 1.0
    _labels()
    queue_redraw()

func _scene_tint(weather: String) -> Color:
    var normalized := weather.to_lower()
    if normalized.contains("rain") or normalized.contains("storm"):
        return Color(0.10, 0.16, 0.26)
    if normalized.contains("snow"):
        return Color(0.36, 0.47, 0.56)
    if normalized.contains("sun") or normalized.contains("clear"):
        return Color(0.15, 0.33, 0.51)
    return Color(0.20, 0.24, 0.37)

func _draw() -> void:
    var w: float = size.x
    var h: float = size.y
    if w <= 0.0 or h <= 0.0:
        return
    draw_rect(Rect2(Vector2.ZERO, size), environmental_tint)
    if backdrop != null:
        draw_texture_rect(backdrop, Rect2(Vector2.ZERO, size), false)
    if environment_quality > 0:
        var wind: float = sin(environment_seconds * 0.85) * 7.0
        for i in range(environment_quality * 14):
            var px: float = fposmod(float(i * 67 + 13) + environment_seconds * 11.0, max(w, 1.0))
            var py: float = h * 0.50 + float((i * 29) % 53)
            draw_line(Vector2(px, py), Vector2(px + wind, py - 3.0),
                      Color(0.34, 0.63, 0.41, 0.48), 1.6)
    draw_circle(Vector2(w * 0.80, h * 0.22), 22.0, Color(0.96, 0.87, 0.56))
    var camera_offset: float = shift
    var ground_y: float = h * 0.70
    draw_rect(Rect2(Vector2(0.0, ground_y), Vector2(w, h - ground_y)), Color(0.11, 0.21, 0.22))
    # Original layered silhouettes for atmosphere and camera parallax.
    for i in range(9):
        var px: float = float(i) * w / 8.0 - 24.0 - camera_offset * 0.20
        var tall: float = float((i * 7 + 3) % 5) * 17.0
        draw_rect(Rect2(px, ground_y - 40.0 - tall, 35.0, 40.0 + tall), Color(0.12, 0.27, 0.31))
    for i in range(6):
        var px: float = float(i) * w / 5.0 - camera_offset * 0.40
        var tower_h: float = 45.0 + float((i * 13) % 4) * 19.0
        draw_rect(Rect2(px, ground_y - tower_h, 25.0, tower_h), Color(0.18, 0.25, 0.29))
        draw_rect(Rect2(px + 5.0, ground_y - tower_h + 12.0, 6.0, 7.0), Color(0.91, 0.67, 0.34))
    var weather_name: String = str(scene_data.get("weather", "")).to_lower()
    if environment_quality > 0 and (weather_name.contains("rain") or weather_name.contains("storm")):
        for index in range(environment_quality * 24):
            var rain_x: float = fposmod(float(index * 47 + 17) +
                environment_seconds * (35.0 + float(index % 6) * 11.0), max(w, 1.0))
            var rain_y: float = fposmod(float(index * 31) +
                environment_seconds * 133.0, max(h, 1.0))
            draw_line(Vector2(rain_x, rain_y), Vector2(rain_x - 5.0, rain_y + 13.0),
                      Color(0.72, 0.81, 0.94, 0.56), 1.0)
    elif environment_quality > 0 and weather_name.contains("snow"):
        for index in range(environment_quality * 28):
            var snow_x: float = fposmod(float(index * 37 + 19) +
                environment_seconds * 13.0, max(w, 1.0))
            var snow_y: float = fposmod(float(index * 17 + 3) +
                environment_seconds * 23.0, max(h, 1.0))
            draw_circle(Vector2(snow_x, snow_y), 1.5, Color(0.93, 0.96, 0.99, 0.7))
    var spacing: float = min(95.0, max(52.0, w / float(max(actors.size() + 1, 2))))
    var origin_x: float = (w - spacing * float(max(actors.size() - 1, 0))) * 0.5
    for i in range(actors.size()):
        var px: float = (origin_x + float(i) * spacing - camera_offset) * camera_scale
        var py: float = ground_y - 17.0
        draw_circle(Vector2(px, py - 28.0), 10.0, Color(0.95, 0.77, 0.56))
        draw_rect(Rect2(Vector2(px - 10.0, py - 18.0), Vector2(20.0, 27.0)),
                  Color(0.28 + float(i % 3) * 0.15, 0.55, 0.61))
        draw_line(Vector2(px - 8.0, py + 8.0), Vector2(px - 12.0, py + 23.0),
                  Color(0.85, 0.86, 0.79), 3.0)
        draw_line(Vector2(px + 8.0, py + 8.0), Vector2(px + 12.0, py + 23.0),
                  Color(0.85, 0.86, 0.79), 3.0)
        if get_theme_default_font() != null:
            draw_string(get_theme_default_font(), Vector2(px - 23.0, py - 45.0),
                        str(actors[i]), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color.WHITE)
    if get_theme_default_font() != null:
        draw_string(get_theme_default_font(), Vector2(12.0, 22.0),
                    str(scene_data.get("region", "Original world")),
                    HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color.WHITE)

func enqueue_presentation(receipt: Dictionary) -> void:
    for item in receipt.get("presentation_timelines", []):
        if item is Dictionary:
            pending_timelines.append(item.duplicate(true))
    if not playing:
        _next_timeline()

func _next_timeline() -> void:
    if pending_timelines.is_empty():
        playing = false
        _labels()
        return
    var next: Dictionary = pending_timelines.pop_front()
    timeline_skippable = next.get("skippable", false) == true
    active_cues = next.get("cues", []).duplicate(true)
    cue_index = 0
    elapsed_ms = 0.0
    timeline_end_ms = 0.0
    for cue in active_cues:
        timeline_end_ms = max(timeline_end_ms,
            float(cue.get("at", 0)) + float(cue.get("duration", 0)))
    playing = true
    is_paused = false
    last_completed_timeline = str(next.get("title", ""))
    cue_text = "Playing: " + last_completed_timeline
    _labels()

func _process(delta: float) -> void:
    environment_seconds += min(delta, 0.15)
    environment_redraw_accumulator += min(delta, 0.15)
    if environment_quality > 0 and environment_redraw_accumulator >= 1.0 / 24.0:
        environment_redraw_accumulator = 0.0
        queue_redraw()
    if not playing or is_paused:
        return
    elapsed_ms += min(delta, 0.15) * 1000.0 * playback_speed
    while cue_index < active_cues.size():
        var cue: Dictionary = active_cues[cue_index]
        if float(cue.get("at", 0)) > elapsed_ms:
            break
        _execute_cue(cue)
        cue_index += 1
    if cue_index >= active_cues.size() and elapsed_ms >= timeline_end_ms:
        _next_timeline()
    else:
        _labels()
    # Custom drawn environments need an explicit redraw during camera tweens.
    queue_redraw()

func _execute_cue(cue: Dictionary) -> void:
    motion_tweens = motion_tweens.filter(func(t): return t != null and t.is_valid())
    var kind: String = str(cue.get("kind", ""))
    var value: String = str(cue.get("value", ""))
    var duration_ms: float = clamp(float(cue.get("duration", 0)), 0.0, 120000.0)
    if not supported_cues.has(kind):
        cue_text = "Unrendered cue: " + kind
        return
    match kind:
        "camera_cut":
            shift = 0.0
            camera_scale = 1.0
        "camera_pan", "camera_track", "camera_dolly", "camera_shake":
            # Native camera presentation, not a fabricated 3D camera path.
            var tween := create_tween()
            motion_tweens.append(tween)
            tween.set_speed_scale(playback_speed)
            tween.tween_property(self, "shift", min(90.0, size.x * 0.12),
                                 max(0.1, duration_ms / 1000.0))
            tween.tween_property(self, "shift", 0.0, 0.3)
        "camera_zoom":
            var tween := create_tween()
            motion_tweens.append(tween)
            tween.set_speed_scale(playback_speed)
            tween.tween_property(self, "camera_scale", 1.08,
                                 max(0.1, duration_ms / 1000.0))
            tween.tween_property(self, "camera_scale", 1.0, 0.3)
        "lighting", "color_grade", "weather":
            if kind == "weather":
                environmental_tint = _scene_tint(value)
        "slow_motion":
            set_playback_speed(0.25)
        "pause":
            is_paused = true
        "resume":
            is_paused = false
        "actor_enter", "actor_exit":
            var actor: String = str(cue.get("target", ""))
            if kind == "actor_enter" and not actors.has(actor):
                actors.append(actor)
            if kind == "actor_exit":
                actors.erase(actor)
    cue_text = kind.replace("_", " ").capitalize() + ": " + value.left(160)
    queue_redraw()
    _labels()

func set_environment_quality(value: int) -> void:
    environment_quality = clampi(value, 0, 3)
    queue_redraw()


func toggle_music() -> void:
    music_enabled = not music_enabled
    if not music_enabled:
        score_player.stop()
    elif score_player.stream != null:
        score_player.play()
    cue_text = "Original generated score: " + ("playing" if music_enabled else "muted")
    _labels()


func toggle_pause() -> void:
    is_paused = not is_paused
    for tween in motion_tweens:
        if tween != null and tween.is_valid():
            if is_paused:
                tween.pause()
            else:
                tween.play()
    _labels()

func skip_timeline() -> void:
    if not playing:
        return
    if not timeline_skippable:
        cue_text = "This authored cinematic is not skippable"
        _labels()
        return
    # Only the local presentation is skipped; no Director quest action is sent.
    active_cues.clear()
    for tween in motion_tweens:
        if tween != null and tween.is_valid():
            tween.kill()
    motion_tweens.clear()
    _next_timeline()

func set_playback_speed(value: float) -> void:
    playback_speed = clamp(value, 0.1, 8.0)
    for tween in motion_tweens:
        if tween != null and tween.is_valid():
            tween.set_speed_scale(playback_speed)
    _labels()

func _labels() -> void:
    if cue_label != null:
        cue_label.text = cue_text
    if runtime_label != null:
        runtime_label.text = ("Cue clock: %.0f ms | x%.2f | %s" %
            [elapsed_ms, playback_speed, "paused" if is_paused else "running"])
'''
