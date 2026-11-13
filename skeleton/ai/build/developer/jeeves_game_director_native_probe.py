"""Godot 4 SceneTree probe: actual native client requests a canonical quest action.

Runs only when invoked with a real Godot binary by the specialized native E2E
runner. It uses an isolated session, tests full Godot HTTP->Python direction,
and never writes user project saves or logs a bearer token.
"""
from __future__ import annotations

PROBE_SCRIPT = r'''extends SceneTree

var client: HTTPRequest
var port: int = 0
var token: String = ""
var expected_world: String = ""
var state_before: Dictionary = {}
var state_after: Dictionary = {}
var phase: int = 0

func _initialize() -> void:
    call_deferred("_begin")

func _fail(reason: String) -> void:
    push_error("Jeeves native gameplay probe failed: " + reason)
    quit(1)

func _headers() -> PackedStringArray:
    return PackedStringArray([
        "Authorization: Bearer " + token,
        "Content-Type: application/json",
    ])

func _address(path: String) -> String:
    return "http://127.0.0.1:" + str(port) + path

func _begin() -> void:
    var raw_port := OS.get_environment("SKELETON_DIRECTOR_PROBE_PORT")
    if not raw_port.is_valid_int():
        _fail("missing isolated test port")
        return
    port = int(raw_port)
    token = OS.get_environment("SKELETON_DIRECTOR_BRIDGE_TOKEN")
    expected_world = OS.get_environment("SKELETON_DIRECTOR_PROBE_WORLD")
    if port < 1024 or port > 65535 or token.length() < 32 or expected_world.length() != 64:
        _fail("malformed probe configuration")
        return
    client = HTTPRequest.new()
    root.add_child(client)
    client.timeout = 20.0
    client.request_completed.connect(_response)
    var code := client.request(_address("/v1/status"), _headers(), HTTPClient.METHOD_GET)
    if code != OK:
        _fail("Godot could not initiate loopback status read")

func _response(result: int, code: int, _headers_unused: PackedStringArray,
               data: PackedByteArray) -> void:
    if result != HTTPRequest.RESULT_SUCCESS or code != 200:
        _fail("canonical bridge rejected Godot HTTP request " + str(code))
        return
    var doc = JSON.parse_string(data.get_string_from_utf8())
    if not (doc is Dictionary) or doc.get("ok") != true or not (doc.get("snapshot") is Dictionary):
        _fail("invalid authoritative response body")
        return
    var state: Dictionary = doc["snapshot"]
    if str(state.get("world_sha256", "")) != expected_world:
        _fail("native probe contacted an unexpected Director world")
        return
    if phase == 0:
        if state.get("sequence", -1) != 0:
            _fail("probe session was not initialized at genesis")
            return
        state_before = state
        phase = 1
        var posted := JSON.stringify({
            "choice": "wait:wait",
            "expected_sequence": state["sequence"],
            "expected_state_sha256": state["current_state_sha256"],
        })
        var action_error := client.request(
            _address("/v1/actions"), _headers(), HTTPClient.METHOD_POST, posted
        )
        if action_error != OK:
            _fail("Godot could not submit legal quest action")
    elif phase == 1:
        if (state.get("sequence") != 1
                or state.get("turn") != int(state_before.get("turn", -1)) + 1
                or state.get("current_state_sha256") == state_before.get("current_state_sha256")):
            _fail("Director did not perform the genuine wait action")
            return
        state_after = state
        phase = 2
        var refresh_error := client.request(
            _address("/v1/status"), _headers(), HTTPClient.METHOD_GET
        )
        if refresh_error != OK:
            _fail("Godot failed journal recovery read")
    elif phase == 2:
        if (state.get("sequence") != 1
                or state.get("current_state_sha256") != state_after.get("current_state_sha256")
                or state.get("turn") != state_after.get("turn")):
            _fail("Godot retrieved a different restored quest state")
            return
        # This success marker never contains the secret or personal data.
        print("JEEVES_NATIVE_DIRECTOR_PROBE_OK")
        quit(0)
    else:
        _fail("unexpected native gameplay HTTP response phase")
'''
