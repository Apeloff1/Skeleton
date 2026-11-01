# Scene weather CLI acceptance

The canonical acceptance suite executes `python -m skeleton` dispatch
for weather authoring, movement and item-gated scene traversal, replay,
checkpoint resume, and rejection of tampered inventory. A weather gate
cannot override the canonical scene item's required-key rule. The
`scene-travel` JSON parser also rejects duplicate object keys and
nonfinite constants before authored source reaches the simulation.

Run `python -m pytest skeleton/testing/test_scene_weather.py
skeleton/testing/test_scene_weather_end_to_end.py
skeleton/testing/test_scene_travel.py -q` when the test executor is
available. Published tests are not proof of execution or CI qualification.
