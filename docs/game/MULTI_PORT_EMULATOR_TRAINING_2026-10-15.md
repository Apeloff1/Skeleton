# Multi-port native controller training — October 15, 2026

Implemented within existing Jeeves native emulator host, worker, offline trace validator, replay mirror and operator qualification CLI. No standalone emulation engine or game fixture introduced.

## Actual capabilities

One native replay step can carry simultaneous input values for **up to four ports**: a 16-bit joypad mask; four signed analog axis values; a bounded set of keyboard codes; six mouse-axis/button values; and three pointer coordinates/touch flags. The canonical host `_controls` validates every vector before any native call. The worker delivers these controls through the actual `retro_input_state` callback of an operator-approved libretro binary, honoring the port's configured device identity. No generic lightgun or specific peripheral gameplay compatibility is inferred.

`EmulatorEnvironment.capture_controller_trace(controller_tape, seed=...)` performs the actual native input steps and emits existing `skeleton.game.trace.v1` records. The environment action domain now includes exactly one additional action, `controller_input`, yielding the bounded 32-action maximum. Raw controls are identified by the exact episode-level SHA-256 of the normalized tape plus per-step controller digests, not by pretending every possible controller combination is a separately declared policy action.

`compare_emulator_replays` checks the tape digest, core, content/firmware, action mode and controller topology before comparing actual frames, audio, counters, observations and transition hashes. Mixes of policy actions and controller_input in a single episode are rejected. Multi-port input rights, timing and gameplay correctness are still unverified until native qualification.

## Explicit operator usage

A JSON controller tape is a list of 1–64 frames. Each frame is a list of 1–4 port control objects. Every control object has exactly `buttons`, `axes`, `keys`, `mouse`, `pointer`. Zero values mean no activity; signed coordinates are bounded, and `none` ports reject nonzero input.

```json
[
  [
    {"buttons": 272, "axes": [0, 0, 0, 0], "keys": [], "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]},
    {"buttons": 0, "axes": [32767, 0, 0, 0], "keys": [], "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]}
  ],
  [
    {"buttons": 0, "axes": [0, 0, 0, 0], "keys": [], "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]},
    {"buttons": 0, "axes": [0, 0, 0, 0], "keys": [], "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]}
  ]
]
```

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/lawful-homebrew/example.nes \
  --controller-device joypad --controller-device analog \
  --controller-tape-json /srv/operator/controller-tape.json \
  --runs 3 --frames-per-step 1
```

This command is a sample invocation **only**. The file and binary must actually exist and be authorized by the operator. The CLI parses bounded JSON without duplicate keys or nonfinite values before native execution. If the core ignores an attached peripheral, the trace records what happened rather than claiming device support. The model does not train or promote weights from this code alone.

## Remaining gates

Build/approve actual binaries, qualify per-core controller support and callback behavior using lawful homebrew sources, validate controller/replay tests, and measure real learning gain in separately governed shadow weights before production promotion.
