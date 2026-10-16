"""Godot 4 front-end for live, canonical Python Director sessions.

The viewport is deliberately data-only. Every quest and travel action uses the
authenticated loopback service; no client-supplied quest-completion state is
ever trusted and no bearer token is serialized in source or preferences.
"""
from __future__ import annotations

PLAYER_SCENE = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://director_player.gd" id="1_player"]

[node name="DirectorPlayer" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1_player")
'''

PLAYER_SCRIPT = r'''extends Control

var client: HTTPRequest
var port_input: SpinBox
var token_input: LineEdit
var status_text: Label
var view: VBoxContainer
var snapshot: Dictionary = {}
var last_presentation: Dictionary = {}
var world: Dictionary = {}
var scene_lookup: Dictionary = {}
var busy: bool = false
var stage
var previous_scene: String = ""
var action_choices: Array = []
var action_index: int = 0
var selection_label: Label

func _ready() -> void:
    var raw: String = FileAccess.get_file_as_string("res://director_world.json")
    var decoded = JSON.parse_string(raw)
    if not (decoded is Dictionary):
        push_error("Original Director scene data missing or malformed")
        return
    world = decoded
    for location in world.get("scenes", []):
        scene_lookup[str(location.get("key", ""))] = location
    client = HTTPRequest.new()
    add_child(client)
    client.request_completed.connect(_on_response)

    var layout := VBoxContainer.new()
    layout.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(layout)
    var title := Label.new()
    title.text = "Jeeves Director — live original-game quest session"
    title.add_theme_font_size_override("font_size", 22)
    layout.add_child(title)
    var connection := HBoxContainer.new()
    layout.add_child(connection)
    var port_title := Label.new()
    port_title.text = "Loopback port"
    connection.add_child(port_title)
    port_input = SpinBox.new()
    port_input.min_value = 1024
    port_input.max_value = 65535
    port_input.step = 1
    port_input.value = 8765
    connection.add_child(port_input)
    var token_title := Label.new()
    token_title.text = "Session token"
    connection.add_child(token_title)
    token_input = LineEdit.new()
    token_input.secret = true
    token_input.placeholder_text = "Paste the token set in the local server environment"
    token_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    connection.add_child(token_input)
    var connect := Button.new()
    connect.text = "Connect / refresh"
    connect.pressed.connect(_refresh)
    connection.add_child(connect)
    var atlas := Button.new()
    atlas.text = "Scene atlas"
    atlas.pressed.connect(func(): get_tree().change_scene_to_file("res://main.tscn"))
    connection.add_child(atlas)
    status_text = Label.new()
    status_text.text = "Start the Jeeves loopback server, then connect."
    layout.add_child(status_text)
    stage = load("res://director_stage.gd").new()
    stage.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    layout.add_child(stage)
    var gamepad_bar := HBoxContainer.new()
    layout.add_child(gamepad_bar)
    var previous := Button.new()
    previous.text = "◀ Previous action"
    previous.pressed.connect(func(): _select_action(-1))
    gamepad_bar.add_child(previous)
    selection_label = Label.new()
    selection_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    selection_label.text = "Controller: choose a legal action below"
    gamepad_bar.add_child(selection_label)
    var next := Button.new()
    next.text = "Next action ▶"
    next.pressed.connect(func(): _select_action(1))
    gamepad_bar.add_child(next)
    var activate := Button.new()
    activate.text = "Act / A"
    activate.pressed.connect(_activate_selected)
    gamepad_bar.add_child(activate)
    var legend := Label.new()
    legend.text = "Controller: D-pad changes choices • A interacts • B skips scene • Start pauses • X refreshes"
    layout.add_child(legend)
    var playback := HBoxContainer.new()
    layout.add_child(playback)
    for speed in [0.25, 1.0, 2.0, 4.0]:
        var speed_button := Button.new()
        speed_button.text = "Cue x" + str(speed)
        speed_button.pressed.connect(stage.set_playback_speed.bind(speed))
        playback.add_child(speed_button)
    var pause_cues := Button.new()
    pause_cues.text = "Pause / resume cues"
    pause_cues.pressed.connect(stage.toggle_pause)
    playback.add_child(pause_cues)
    var skip := Button.new()
    skip.text = "Skip presentation"
    skip.pressed.connect(stage.skip_timeline)
    playback.add_child(skip)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    layout.add_child(scroll)
    view = VBoxContainer.new()
    view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(view)

func _unhandled_input(event: InputEvent) -> void:
    # Controller/keyboard navigation does not consume input from credentials.
    if token_input.has_focus() or port_input.has_focus() or busy:
        return
    if event.is_action_pressed("ui_up") or event.is_action_pressed("ui_left"):
        _select_action(-1)
        get_viewport().set_input_as_handled()
    elif event.is_action_pressed("ui_down") or event.is_action_pressed("ui_right"):
        _select_action(1)
        get_viewport().set_input_as_handled()
    elif event is InputEventJoypadButton and event.pressed:
        match event.button_index:
            JOY_BUTTON_A:
                _activate_selected()
            JOY_BUTTON_B:
                stage.skip_timeline()
            JOY_BUTTON_START:
                stage.toggle_pause()
            JOY_BUTTON_X:
                _refresh()
            _:
                return
        get_viewport().set_input_as_handled()


func _select_action(step: int) -> void:
    if action_choices.is_empty():
        return
    action_index = posmod(action_index + step, action_choices.size())
    _selection_text()


func _selection_text() -> void:
    if selection_label == null:
        return
    if action_choices.is_empty():
        selection_label.text = "No legal actions loaded"
    else:
        var selected: Dictionary = action_choices[action_index]
        selection_label.text = str(action_index + 1) + "/" + str(action_choices.size()) + " • " + str(selected.get("description", selected.get("choice", "")))


func _activate_selected() -> void:
    if busy or action_choices.is_empty():
        return
    _choose(str(action_choices[action_index].get("choice", "")))


func _line(value: String) -> void:
    var item := Label.new()
    item.text = value
    item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    view.add_child(item)

func _refresh() -> void:
    _request("", false)

func _choose(choice: String) -> void:
    _request(choice, true)

func _request(choice: String, is_action: bool) -> void:
    if busy:
        return
    var token: String = token_input.text
    if token.length() < 32:
        status_text.text = "Missing local bearer token (at least 32 characters)."
        return
    var port: int = int(port_input.value)
    var url: String = "http://127.0.0.1:" + str(port)
    var headers := PackedStringArray([
        "Authorization: Bearer " + token, "Content-Type: application/json"
    ])
    var error_code: int = 0
    if is_action:
        if snapshot.is_empty():
            status_text.text = "Connect and load the live session before acting."
            return
        var request_body := JSON.stringify({
            "choice": choice,
            "expected_sequence": snapshot["sequence"],
            "expected_state_sha256": snapshot["current_state_sha256"],
        })
        error_code = client.request(url + "/v1/actions", headers,
                                   HTTPClient.METHOD_POST, request_body)
    else:
        error_code = client.request(url + "/v1/status", headers, HTTPClient.METHOD_GET)
    if error_code != OK:
        status_text.text = "Unable to contact local Director: " + str(error_code)
        return
    busy = true
    status_text.text = "Awaiting canonical Director response..."

func _on_response(result: int, status_code: int, _headers: PackedStringArray,
                  data: PackedByteArray) -> void:
    busy = false
    if result != HTTPRequest.RESULT_SUCCESS:
        status_text.text = "Loopback transport unavailable: " + str(result)
        return
    var parsed = JSON.parse_string(data.get_string_from_utf8())
    if not (parsed is Dictionary):
        status_text.text = "Local Director returned invalid JSON"
        return
    if not parsed.get("ok", false):
        status_text.text = "Director rejected input (" + str(status_code) + "): " + str(parsed.get("error", "unknown"))
        if parsed.has("snapshot"):
            snapshot = parsed["snapshot"]
            _draw()
        return
    if not parsed.has("snapshot") or not (parsed["snapshot"] is Dictionary):
        status_text.text = "Director did not provide a canonical state"
        return
    snapshot = parsed["snapshot"]
    last_presentation = {}
    if parsed.get("presentation") is Dictionary:
        last_presentation = parsed["presentation"]
    status_text.text = "Canonical turn " + str(snapshot.get("turn", 0)) + " | actions " + str(snapshot.get("sequence", 0))
    _draw()
    if not last_presentation.is_empty():
        stage.enqueue_presentation(last_presentation)

func _draw() -> void:
    for item in view.get_children():
        item.queue_free()
        view.remove_child(item)
    var here: String = str(snapshot.get("scene", ""))
    var region = scene_lookup.get(here, {})
    if here != previous_scene:
        previous_scene = here
        stage.apply_scene(region)
    _line("Location: " + str(snapshot.get("scene_title", here)))
    _line(str(region.get("setting", snapshot.get("scene_setting", ""))))
    _line("Cast: " + str(snapshot.get("cast", [])))
    _line("Weather: " + str(snapshot.get("weather", "")) +
          " | Lighting: " + str(snapshot.get("lighting", "")) +
          " | Score cue: " + str(snapshot.get("music_cue", "")))
    _line("Quest progress:")
    for quest in snapshot.get("quests", []):
        var qline: String = str(quest["title"]) + " (" + str(quest["stage_index"]) + "/" + str(quest["stage_total"]) + ")"
        if quest.get("completed", false):
            qline += " COMPLETE"
        elif not quest.get("blocked_by", []).is_empty():
            qline += " — awaiting " + str(quest["blocked_by"])
        _line(qline)
    _line("Authorized gameplay actions:")
    if snapshot.get("complete", false):
        _line("Campaign logic completed. Continue reviewing endings and replay evidence.")
    action_choices = snapshot.get("actions", []).duplicate(true)
    action_index = clampi(action_index, 0, max(action_choices.size() - 1, 0))
    _selection_text()
    for action in action_choices:
        var button := Button.new()
        button.text = str(action.get("description", action.get("choice", "")))
        button.pressed.connect(_choose.bind(str(action.get("choice", ""))))
        view.add_child(button)
    _line("Completed story events:")
    for event in snapshot.get("quest_stage_results", []):
        _line(str(event.get("quest", "")) + " / " + str(event.get("stage", "")) +
              " — " + str(event.get("approach", "")) +
              " — " + str(event.get("consequence", "")))
    _line("Narrative outcomes: " + str(snapshot.get("narrative_flags", [])))
    if not last_presentation.is_empty():
        _line("New canonical narrative and cinematic presentation cues:")
        for outcome in last_presentation.get("new_story_results", []):
            _line("  Outcome: " + str(outcome.get("quest", "")) + " / " +
                  str(outcome.get("stage", "")) + " — " + str(outcome.get("consequence", "")))
        for cinematic in last_presentation.get("presentation_timelines", []):
            _line("  Timeline: " + str(cinematic.get("title", "")) +
                  " | " + str(cinematic.get("trigger_reason", "")))
            for cue in cinematic.get("cues", []):
                _line("    " + str(cue.get("at", 0)) + "ms " +
                      str(cue.get("kind", "")) + ": " + str(cue.get("value", "")))
    _line("State digest: " + str(snapshot.get("current_state_sha256", "")))
    _line("These are authoritative Python Director actions through a local server. Rendered world/asset quality is not certified.")
'''
