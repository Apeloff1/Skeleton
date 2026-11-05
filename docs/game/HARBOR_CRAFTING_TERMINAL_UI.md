# Lantern Quay — human-playable terminal interface

The original Lantern Quay campaign can be played as a visible grid game,
not only as a prewritten JSON action list:

    python -m scripts.game.harbor_crafting play-live

Commands: north, south, east, west, gather, craft ID, trade ID, deliver,
signal, shelter, wait, save, help and quit. The display renders walls,
resources, the merchant, dock and player along with inventory, coins,
reputation, tick budget and quest state. Input is strictly bounded and
parsed through allowlisted commands; no Python code or shell commands
are evaluated.

Each legal action uses the same canonical deterministic game transition
engine as the JSON CLI and solver. Rejected moves or crafts do not change
state. The save command emits a portable replay-verifiable JSON checkpoint.
EOF or quit before an earned ending emits a recoverable checkpoint and
returns status 2, not a false success. A won game emits its replay-verified
terminal digest and complete portable checkpoint with exit status 0.

The visible terminal grid is an interactive UI, not a graphical engine
or device-qualified installed consumer experience. For a reproducible
scripted terminal demonstration, pipe the human-readable commands
equivalent to demo_actions() into play-live.

Focused acceptance:

    pytest -q skeleton/testing/test_harbor_crafting_ui.py
