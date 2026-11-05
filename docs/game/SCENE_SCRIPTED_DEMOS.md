# Deterministic offline scripted demos

The existing `demo` mode remains a player-controlled interactive session.
EOF, invalid input, and turn-budget exhaustion preserve the current verified
checkpoint and never award an implicit ending.

For unattended install smoke tests and reproducible offline demonstrations,
use `demo-script`:

```sh
python -m skeleton scene-escort-play demo-script
python -m skeleton scene-survival-play demo-script
python -m skeleton scene-weather-play demo-script
python -m skeleton scene-survival-campaign-play demo-script
```

Each command drives the actual interactive reducer using an in-memory JSON-line
stream made from the original authored demonstration. Every action still passes
through source, legality, tick, replay, and bounded resource checks. The
completed checkpoint is replay-verifiable against the canonical batch reducer.
No external stdin, files, network, provider, or untrusted code execution are
required. Integrity digests do not authenticate publishers or licenses.

Focus checks: `skeleton/testing/test_scene_escort_script_demo.py`,
`test_scene_survival_script_demo.py`, `test_scene_weather_script_demo.py`,
and `test_scene_campaign_script_demo.py`.

These paths add offline functional evidence only. Passing the demos does not
certify consumer devices, ecosystem delivery, or a release.
