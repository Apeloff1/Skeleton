# Offline weather caravan market

The `weather-market` command adds original trade contracts to playable
weather-gated caravan deliveries. It uses the canonical weather engine for
movement, collision, inventory, weather changes and clock ticks, and the
canonical delivery engine for deadlines, dependencies and earned gross rewards.

## Play, save, replay, export

```bash
python -m skeleton weather-market demo
python -m skeleton weather-market start --source-json "$MARKET_SOURCE"
python -m skeleton weather-market advance --session-json "$SAVE" --action-json "$ACTION"
python -m skeleton weather-market resume --session-json "$SAVE" --actions-json "$ACTIONS"
python -m skeleton weather-market verify --session-json "$SAVE"
python -m skeleton weather-market summary --session-json "$SAVE"
python -m skeleton weather-market pack --session-json "$SAVE"
python -m skeleton weather-market unpack --package-json "$PORTABLE"
```

A market source embeds a versioned weather-delivery source and exactly one
contract per delivery. Contracts define a commission in basis points (0–5000),
an early-arrival threshold in ticks (1–64), and an early-delivery reputation
bonus (0–100). They do not grant money. When the canonical delivery engine
confirms an arrival, gross is the *already earned* delivery reward; commission
is integer floor(gross × basis_points / 10000); net is gross minus commission.
An expired delivery earns zero. Early reputation is awarded only for an
on-time delivered contract with sufficient remaining deadline ticks.

Every accepted weather action creates a deterministic market settlement entry
and chained save digest. Verification independently replays every action and
the nested canonical weather and delivery states. The portable package includes
the full save, a gross/fee/net/reputation manifest and an integrity receipt.
Edited payout, delivery status, weather, journal, or source fails closed.

Market sessions are bounded to 64 actions, at most 16 authored delivery
contracts, and the shared serialized output budget. Invalid or incompatible
input exits nonzero without a payout. Digests provide integrity, not author
signatures, payment authority or external provenance. Real-money transactions
are outside this offline game mechanic and require separate controls.
