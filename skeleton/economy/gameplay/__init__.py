"""Gameplay economy layer for #807 B021–B030 (extends ``skeleton.simulation.economy.sim``).

Modules, by #807 batch item:

* B021 :mod:`.replay` – hash-chained command log and deterministic replay contract
* B022 :mod:`.components` – ECS upkeep (sink) and income (faucet) systems
* B023 :mod:`.rules` – sandboxed integer price-rule scripting
* B024 :mod:`.intents` – untrusted player input validation, auth, dedupe, rate limit
* B025 :mod:`.save` – versioned saves with v1→v3 migrations and audit on load
* B026 :mod:`.core` – item faucets/sinks, weight limits, binding, item audit
* B027 :mod:`.combat` – ability costs as sinks, deterministic loot faucets with diminishing returns
* B028 :mod:`.quests` – governed quest-reward faucet with prerequisites and repeat windows
* B029 :mod:`.market`, :mod:`.inflation` – market integrity guard and anti-inflation tax controller
* B030 :mod:`.genres` – genre presets, composition and economy design lint
"""

from __future__ import annotations

from skeleton.economy.gameplay.core import GameplayEconomy

__all__ = ["GameplayEconomy"]
