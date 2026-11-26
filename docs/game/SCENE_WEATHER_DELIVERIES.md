# Weather caravan deliveries — playable original vertical

`python -m skeleton weather-deliveries demo` plays the original Lantern
Hollow caravan route. It collects the brass key, waits out a storm, travels
through canonical scene exits, delivers to the gate and sanctuary, and earns
only verified delivery rewards. Weather, movement, collision, inventory and
save lineage remain owned by the canonical scene/weather engines.

## Commands

```sh
python -m skeleton weather-deliveries demo
python -m skeleton weather-deliveries start --source-json '<authored source>'
python -m skeleton weather-deliveries advance --session-json '<save>' --action-json '<action>'
python -m skeleton weather-deliveries resume --session-json '<save>' --actions-json '<actions>'
python -m skeleton weather-deliveries verify --session-json '<save>'
python -m skeleton weather-deliveries summary --session-json '<save>'
python -m skeleton weather-deliveries pack --session-json '<save>'
python -m skeleton weather-deliveries unpack --package-json '<portable>'
```

The `skeleton.weather_deliveries.v1` source has a canonical `weather` source
and 1–16 authored `deliveries`. Each delivery defines a unique ID, valid
destination scene, collectible item, positive deadline and reward, and
earlier dependency IDs. Reaching a destination with its required item before
the deadline grants the reward once; expiry is irreversible. Unreached
deliveries are explicitly pending or unreachable. Rewards do not alter
canonical inventory, weather, or player currency.

Each action records the canonical weather state digest and earned changes.
Checkpoint verification replays every action through weather collision and
inventory rules, and portable import revalidates the complete manifest.
Payload sizes, action budgets, deadlines and rewards are bounded.
Digests detect corruption, not authorship; host authorization and device
qualification are separate release requirements.
