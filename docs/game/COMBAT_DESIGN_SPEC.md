# Combat Design Spec — damage, telegraphs, difficulty

Owner: Combat Design (Snappo). Code: `skeleton/simulation/game/combat_design/`.
Tests: `skeleton/testing/test_combat_design.py` (CI: `.github/workflows/combat-design.yml`).

Pillars: **clarity** (every threat is readable), **weight** (hits are consistent
and punishable), **fair escalation** (difficulty adds pressure, never cheapness).

## 1. Damage model (`damage.py`)

| Step | Rule |
|---|---|
| Variance | symmetric ±5 % band from `variance_roll` |
| Crit | `crit_roll < crit_chance` → × `crit_mult` (1–4) |
| Physical mitigation | `armor / (armor + 85·attacker_level + 400)`, cap 75 % |
| Elemental mitigation | flat resist, cap 75 % |
| Flat reduction | subtracted after mitigation, floor 0 |
| Vulnerability | × 0.5–1.5 debuff multiplier |
| TRUE damage | skips mitigation, flat reduction and vulnerability |

All rolls are passed in (use `SeededEntropy`), so combat is replayable.
`expected_damage` gives the analytic mean for balance spreadsheets;
`effective_health` converts HP + defenses to raw-damage EHP.

## 2. Telegraph readability (`telegraph.py`)

| Tier | Min windup | Channels | Max damage (% max HP) | Min recovery |
|---|---|---|---|---|
| MINOR | 300 ms | 1 | 15 % | — |
| MAJOR | 600 ms | 2 | 45 % | 30 % of windup |
| LETHAL | 1200 ms | 2 incl. **audio** | unbounded | 50 % of windup |

Extra rules:

* **Escapable**: `windup ≥ 250 ms reaction + escape_distance / move_speed`.
* **Active window** ≤ 1000 ms unless flagged `persistent_zone`.
* **One big threat at a time**: MAJOR+ windups may not overlap.
* **Breather**: nothing new starts within 400 ms after a LETHAL resolves.
* Damage above a tier's ceiling means the attack must be **promoted** (louder,
  longer windup), not just tuned.

Difficulty scaling may shorten windups but clamps at the tier floor; it never
masks an attack authored below its floor.

## 3. Difficulty (`difficulty.py`)

| Tier | Enemy HP | Enemy damage | Windup scale |
|---|---|---|---|
| STORY | ×0.6 | ×0.5 | ×1.4 |
| NORMAL | ×1.0 | ×1.0 | ×1.0 |
| HEROIC | ×1.4 | ×1.35 | ×0.9 |
| MYTHIC | ×2.0 | ×1.8 | ×0.8 |

HP is derived from **time-to-kill** bands (solo, core player at NORMAL):
trash 3–6 s, elite 12–20 s, miniboss 45–75 s, boss 180–360 s. A casual player
on STORY lands inside the same bands (pinned by tests).

Zone pacing is a **rising sawtooth** (`build_zone_curve` / `validate_curve`):
positive trend, no step > 0.35, no climb longer than 4 encounters without a
breather, boss is the strict peak. Encounter threat budget = `40 · intensity ·
(1 + 0.75·(party−1))` points; costs trash 1 / elite 4 / miniboss 10 / boss 30,
gated by intensity (elite ≥ 0.3, miniboss ≥ 0.6, boss ≥ 0.95).

## 4. Encounter simulator (`encounter_sim.py`)

Skill profiles (reaction mean / sd / DPS efficiency): casual 480/90/0.60,
core 330/60/0.80, expert 240/35/0.95. Each telegraph draws a reaction time;
the hit is avoided when reaction + escape (or a 150 ms dodge commit) fits in
the windup. `clear_rate(n, ...)` estimates clear probability over seeds.

Guaranteed properties (tested): deterministic digests; clear rate never drops
with more skill or easier tier; an unreadable lethal is unbeatable for every
profile; the reference boss is flawless for experts on NORMAL and ≥ 90 %
clearable by casuals on STORY.

## 5. Combat test plan

1. **Authoring gate**: every new attack runs `audit_telegraph`; every boss
   rotation runs `audit_pattern`. Zero violations to merge.
2. **Tier sweep**: `clear_rate` for casual/core/expert × 4 tiers; targets:
   casual STORY ≥ 90 %, core NORMAL ≥ 70 %, expert MYTHIC ≥ 40 %.
3. **TTK audit**: archetype HP comes from `archetype_hp`; hand-typed HP is a bug.
4. **Zone pacing**: `validate_curve` on each zone's intensity list.
5. **Balance diff**: `balance_table()` JSON is reviewed on every tuning PR.

## 6. Rollback

The package is extend-only (no existing module imports it). Reverting the
commit removes it with no migration.

## Measured designer balance report

The existing encounter owner exposes `evaluate_encounter_design(...)` and the
operator CLI below. It runs the same deterministic seed cohort for all twelve
combinations of story/normal/heroic/mythic and casual/core/expert. Reports give
clear/death/timeout counts, conditional mean/p95 clear time (null with no
clears), mean hits and remaining HP, exact per-trial identities and scaled
readability findings. The two-cycle audit includes the rotation seam. A high
clear rate does not erase an unreadable attack. The report never applies a
balance change or certifies fairness for real players.

```bash
python -m scripts.balance_combat_encounter --input ./encounter.json \
  --seeds 32 --deadline-ms 120000
```

Example input (explicit original encounter, no game/asset execution):

```json
{
  "schema": "combat.encounter_input.v1",
  "enemy_hp": 1000,
  "player_max_hp": 1000,
  "player_dps": 1000,
  "rotation": [
    {"name": "cleave", "tier": "minor", "windup_ms": 600,
     "active_ms": 300, "recovery_ms": 400,
     "channels": ["body_anim", "vfx_glow"], "damage_fraction": 0.1}
  ]
}
```

The 64-KiB input rejects links, changing file identity, duplicate JSON fields,
non-finite/bool stats, unknown fields and malformed attacks. Corpus size is at
most 64 attacks. Reports admit 1–128 seeds, 1–300000 ms per trial; the existing
individual simulator admits at most one hour. Numerical stats must be finite
and within 1e-6..1e9. Inputs/digest bind the actual profile parameters and every
attack, not just profile names and abbreviated reaction logs.

Simulation uses continuous player DPS and enemy damage at windup+active end.
A player kill is timed to the next whole millisecond within either the windup
or recovery, and wins an equal-time tie with attack resolution. No event can
occur after the deadline. Digest format is now `combat.encounter.v2`: older
simulation digests are not asserted equivalent. This is report identity, not
signed release or independent human evidence.

Construction/operations: L00–L02 keep the existing combat simulation owner and
add only an offline CLI/report schema. L03–L06 retain explicit bounded local
inputs and no provider, network, user-state or tenant authority. L07–L10 use
seed replay, reconciled cohort counts, deadline and input adversarial tests;
JSON reports provide reproducible inspection, not measured consumer p95 runtime
latency or player-experience certification. L11–L13 require exact-head combat
and wider repository gates; retain original encounter settings and rollback by
reverting this increment. No masterplan maturity or release rights are raised.
