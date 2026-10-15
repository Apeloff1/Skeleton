# Native libretro controller routing — 2026-10-15

This feature remains within the existing Jeeves sandboxed libretro worker.

The host now accepts an explicit `controller_devices` sequence (one through four entries), with the finite values `none`, `joypad`, `mouse`, `keyboard`, `analog`, `pointer`. Entries are padded to exactly four ports with `none`, while omission preserves four `joypad` ports for backwards compatibility. The host stores the four-port list in its hashed environment descriptor and sends it to the native worker.

On initialization, the worker validates the exact four entries and calls the real libretro `retro_set_controller_port_device(port, device_id)` for each port. It acknowledges the selected identities in the system-info return, and the host rejects a mismatch. The offline native training trace records the topology, and the replay mirror validator refuses mismatched port declarations even when the action sequence matches.

```python
from skeleton.jeeves.game_emulator_host import create_emulator_environment

# Requires an actually approved native core, lawful content and a working Linux sandbox:
env = create_emulator_environment(
    "dos_vga",
    controller_devices=("keyboard", "mouse", "joypad", "none"),
    # ... content=..., core_id=..., expected_registry_digest=...
)
# input_step still uses bounded exact buttons/axes/keys/mouse/pointer value vectors.
```

Supported device selection does not guarantee that a particular core emulates a mouse, analog mode or multitap, and it does not implement unqualified lightguns or vendor-specific input protocols. Runtime game tests and native input traces remain required before claiming support. No native binaries were compiled or trained in this change.
