"""Local model capability bridge v2 — 10× expanded for the 83-core console emulator fleet.

Governed, read-only, fail-closed access for the offline/local model.
Never loads native code, never downloads firmware, never executes retro_run.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from skeleton.jeeves.game_emulator_catalog import (
        EmulatorCatalogError,
        load_registry_from_env_or_path,
    )
except ImportError:  # sandbox / standalone
    EmulatorCatalogError = type("EmulatorCatalogError", (ValueError,), {})
    def load_registry_from_env_or_path(_path):  # type: ignore
        return None


CAPABILITY_SCHEMA = "skeleton.local_model.console_emulator_capability.v2"
MAX_PROMPT_CHARS = 16384
FLEET_DB_NAME = "fleet_database_v2.json"


@dataclass(frozen=True)
class CoreRecord:
    name: str
    hardware: tuple[str, ...]
    era: str
    category: str
    bios_required: bool
    accuracy: str
    notes: str
    installed: bool = False
    qualified: bool = False


class LocalModelConsoleCapabilityV2:
    """10× expanded bridge: query, filter, plan, export, and inject for the full fleet."""

    def __init__(self, db_path: str | Path | None = None, registry_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else Path(__file__).with_name(FLEET_DB_NAME)
        self._records: dict[str, CoreRecord] = {}
        self._registry = None
        self._load_static_db()
        self.load_registry(registry_path)

    def _load_static_db(self) -> None:
        if not self._db_path.exists():
            return
        data = json.loads(self._db_path.read_text(encoding="utf-8"))
        for name, info in data.get("cores", {}).items():
            self._records[name] = CoreRecord(
                name=name,
                hardware=tuple(info.get("hardware", (name,))),
                era=info.get("era", "unknown"),
                category=info.get("category", "unknown"),
                bios_required=bool(info.get("bios_required", False)),
                accuracy=info.get("accuracy", "unknown"),
                notes=info.get("notes", ""),
            )

    def load_registry(self, registry_path: str | Path | None = None) -> None:
        try:
            self._registry = load_registry_from_env_or_path(str(registry_path) if registry_path else None)
        except Exception:
            self._registry = None
        # Overlay live status if registry exposes cores (best-effort)
        if self._registry and hasattr(self._registry, "cores"):
            for name, core in getattr(self._registry, "cores", {}).items():
                if name in self._records:
                    rec = self._records[name]
                    self._records[name] = CoreRecord(
                        name=rec.name,
                        hardware=rec.hardware,
                        era=rec.era,
                        category=rec.category,
                        bios_required=rec.bios_required,
                        accuracy=rec.accuracy,
                        notes=rec.notes,
                        installed=bool(getattr(core, "installed", False) or getattr(core, "library_path", None)),
                        qualified=bool(getattr(core, "qualified", False)),
                    )

    # ── basic queries ──────────────────────────────────────────────
    def list_cores(self) -> list[str]:
        return sorted(self._records.keys())

    def get(self, name: str) -> CoreRecord | None:
        return self._records.get(name)

    def fleet_summary(self) -> dict[str, Any]:
        total = len(self._records)
        installed = sum(1 for r in self._records.values() if r.installed)
        qualified = sum(1 for r in self._records.values() if r.qualified)
        bios = sum(1 for r in self._records.values() if r.bios_required)
        by_era = defaultdict(int)
        by_cat = defaultdict(int)
        for r in self._records.values():
            by_era[r.era] += 1
            by_cat[r.category] += 1
        return {
            "schema": CAPABILITY_SCHEMA,
            "total_declared_cores": total,
            "installed_count": installed,
            "qualified_count": qualified,
            "bios_required_count": bios,
            "coverage_percent": round(100.0 * qualified / max(total, 1), 1),
            "by_era": dict(by_era),
            "by_category": dict(by_cat),
            "note": "Orchestrate-only until operator-approved registry marks cores installed/qualified.",
        }

    def validate_fleet(self) -> dict[str, Any]:
        cores = self.list_cores()
        return {
            "total": len(cores),
            "unique": len(set(cores)),
            "healthy": len(cores) >= 70 and len(cores) == len(set(cores)),
            "bios_required": sum(1 for r in self._records.values() if r.bios_required),
            "cycle_accurate": sum(1 for r in self._records.values() if "cycle" in r.accuracy),
        }

    # ── filtering & search ─────────────────────────────────────────
    def filter(
        self,
        era: str | None = None,
        category: str | None = None,
        bios_required: bool | None = None,
        accuracy: str | None = None,
        hardware_contains: str | None = None,
    ) -> list[CoreRecord]:
        result = list(self._records.values())
        if era:
            result = [r for r in result if r.era == era.lower()]
        if category:
            result = [r for r in result if r.category == category.lower()]
        if bios_required is not None:
            result = [r for r in result if r.bios_required == bios_required]
        if accuracy:
            result = [r for r in result if accuracy.lower() in r.accuracy.lower()]
        if hardware_contains:
            hw = hardware_contains.lower()
            result = [r for r in result if any(hw in h.lower() for h in r.hardware)]
        return sorted(result, key=lambda r: r.name)

    def search(self, query: str) -> list[CoreRecord]:
        q = query.lower()
        return [
            r for r in self._records.values()
            if q in r.name.lower() or any(q in h.lower() for h in r.hardware) or q in r.notes.lower()
        ]

    def by_era(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for r in self._records.values():
            groups[r.era].append(r.name)
        return {k: sorted(v) for k, v in groups.items()}

    def by_category(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for r in self._records.values():
            groups[r.category].append(r.name)
        return {k: sorted(v) for k, v in groups.items()}

    # ── planning & recommendations ─────────────────────────────────
    def recommend_for_learning(self, goal: str = "general", limit: int = 5) -> list[str]:
        goal = goal.lower()
        if "arcade" in goal:
            prefer = ["fbneo", "mame2003_plus", "mame2016", "neocd"]
        elif "handheld" in goal:
            prefer = ["mgba", "gambatte", "melonds", "ppsspp", "sameboy"]
        elif "accuracy" in goal or "cycle" in goal:
            prefer = ["bsnes", "mesen", "nestopia", "sameboy", "vice_x64sc"]
        elif "home" in goal or "computer" in goal:
            prefer = ["dosbox_pure", "vice_x64", "hatari", "fuse", "puae"]
        elif "16bit" in goal or "snes" in goal:
            prefer = ["snes9x", "bsnes", "genesis_plus_gx", "picodrive"]
        elif "8bit" in goal or "nes" in goal:
            prefer = ["fceumm", "nestopia", "mesen", "gambatte"]
        else:
            prefer = ["snes9x", "fceumm", "mgba", "gambatte", "genesis_plus_gx"]
        available = set(self.list_cores())
        return [c for c in prefer if c in available][:limit]

    def plan_session(
        self,
        hardware: str | None = None,
        max_steps: int = 1000,
        prefer_accuracy: bool = False,
    ) -> dict[str, Any]:
        candidates = self.filter(hardware_contains=hardware) if hardware else list(self._records.values())
        if prefer_accuracy:
            candidates = sorted(candidates, key=lambda r: (0 if "cycle" in r.accuracy else 1, r.name))
        names = [r.name for r in candidates[:8]]
        return {
            "schema": CAPABILITY_SCHEMA,
            "objective": "governed learning episode",
            "recommended_cores": names or self.recommend_for_learning("general"),
            "max_steps": max(1, min(max_steps, 10000)),
            "constraints": [
                "operator-approved registry only",
                "isolated worker owns all retro_run / serialize / memory",
                "no BIOS or firmware download",
                "content must pass catalog inspection (CRC, path, size)",
                "local model orchestrates only",
            ],
            "bios_warning": any(r.bios_required for r in candidates[:5]),
            "success_criteria": "episode evidence hashes present; no silent reference-sim fallback",
        }

    def curriculum(self, stages: int = 4) -> list[dict[str, Any]]:
        """Multi-stage learning curriculum ordered by complexity."""
        order = [
            ("handheld-simple", ["gambatte", "mgba"]),
            ("8bit-home", ["fceumm", "nestopia"]),
            ("16bit", ["snes9x", "genesis_plus_gx"]),
            ("accuracy", ["bsnes", "mesen"]),
            ("32bit", ["pcsx_rearmed", "flycast"]),
            ("arcade", ["fbneo", "mame2003"]),
            ("computer", ["dosbox_pure", "vice_x64"]),
        ]
        plan = []
        for i, (label, cores) in enumerate(order[:stages]):
            plan.append({
                "stage": i + 1,
                "label": label,
                "cores": [c for c in cores if c in self._records],
                "focus": "establish baseline evidence before advancing",
            })
        return plan

    # ── exports ────────────────────────────────────────────────────
    def emulator_console_choices(self) -> list[dict[str, Any]]:
        return [
            {
                "choice": f"emulator:{r.name}",
                "core": r.name,
                "hardware": list(r.hardware),
                "era": r.era,
                "category": r.category,
                "runtime_kind": "installed_libretro_emulator" if r.installed else "declared_only",
                "bios_required": r.bios_required,
            }
            for r in sorted(self._records.values(), key=lambda x: x.name)
        ]

    def qualification_matrix(self) -> list[dict[str, Any]]:
        return [
            {
                "core": r.name,
                "hardware": list(r.hardware),
                "era": r.era,
                "category": r.category,
                "accuracy": r.accuracy,
                "bios_required": r.bios_required,
                "installed": r.installed,
                "qualified": r.qualified,
                "capability_level": "native-isolated" if r.qualified else "orchestrate-only",
                "notes": r.notes,
            }
            for r in sorted(self._records.values(), key=lambda x: x.name)
        ]

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["core", "hardware", "era", "category", "accuracy", "bios_required", "installed", "qualified", "notes"])
        for r in sorted(self._records.values(), key=lambda x: x.name):
            writer.writerow([
                r.name, ";".join(r.hardware), r.era, r.category, r.accuracy,
                r.bios_required, r.installed, r.qualified, r.notes,
            ])
        return buf.getvalue()

    def to_markdown_table(self) -> str:
        lines = ["| Core | Hardware | Era | Category | Accuracy | BIOS | Status |",
                 "|------|----------|-----|----------|----------|------|--------|"]
        for r in sorted(self._records.values(), key=lambda x: x.name):
            status = "qualified" if r.qualified else ("installed" if r.installed else "declared")
            lines.append(
                f"| {r.name} | {', '.join(r.hardware)} | {r.era} | {r.category} | {r.accuracy} | "
                f"{'yes' if r.bios_required else 'no'} | {status} |"
            )
        return "\n".join(lines)

    # ── model-facing surfaces ──────────────────────────────────────
    def model_card(self, style: str = "compact") -> str:
        s = self.fleet_summary()
        base = (
            f"You have governed access to {s['total_declared_cores']} declared libretro cores "
            f"({s['qualified_count']} qualified). Use console_emulator_capability to list, filter, "
            f"plan, or export. Native execution stays in the isolated host. Never request BIOS downloads."
        )
        if style == "detailed":
            eras = ", ".join(f"{k}:{v}" for k, v in s["by_era"].items())
            return base + f" Eras: {eras}. BIOS required on {s['bios_required_count']} cores."
        return base

    def inject_into_prompt(self, base_prompt: str, style: str = "compact") -> str:
        card = f"[CONSOLE_EMULATOR_CAPABILITY schema={CAPABILITY_SCHEMA}]\n{self.model_card(style)}\n"
        combined = card + "\n" + base_prompt
        if len(combined) > MAX_PROMPT_CHARS:
            return card + base_prompt[: MAX_PROMPT_CHARS - len(card) - 50]
        return combined

    def build_model_tool_schema(self) -> dict[str, Any]:
        return {
            "name": "console_emulator_capability",
            "description": "Query, filter, plan, and export the 83-core operator-approved libretro fleet. Read-only; no native execution or downloads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list_cores", "fleet_summary", "validate_fleet", "get",
                            "filter", "search", "recommend_for_learning", "plan_session",
                            "curriculum", "qualification_matrix", "emulator_console_choices",
                            "by_era", "by_category", "model_card",
                        ],
                    },
                    "core_name": {"type": "string"},
                    "hardware": {"type": "string"},
                    "era": {"type": "string"},
                    "category": {"type": "string"},
                    "goal": {"type": "string"},
                    "query": {"type": "string"},
                    "max_steps": {"type": "integer"},
                    "style": {"type": "string"},
                },
                "required": ["action"],
            },
        }

    def dispatch(self, action: str, **kwargs: Any) -> Any:
        """Tool-dispatch entry point for local-model loops."""
        handlers = {
            "list_cores": lambda: self.list_cores(),
            "fleet_summary": lambda: self.fleet_summary(),
            "validate_fleet": lambda: self.validate_fleet(),
            "get": lambda: self.get(kwargs.get("core_name", "")),
            "filter": lambda: [r.__dict__ for r in self.filter(
                era=kwargs.get("era"), category=kwargs.get("category"),
                hardware_contains=kwargs.get("hardware"),
            )],
            "search": lambda: [r.__dict__ for r in self.search(kwargs.get("query", ""))],
            "recommend_for_learning": lambda: self.recommend_for_learning(kwargs.get("goal", "general")),
            "plan_session": lambda: self.plan_session(kwargs.get("hardware"), kwargs.get("max_steps", 1000)),
            "curriculum": lambda: self.curriculum(),
            "qualification_matrix": lambda: self.qualification_matrix(),
            "emulator_console_choices": lambda: self.emulator_console_choices(),
            "by_era": lambda: self.by_era(),
            "by_category": lambda: self.by_category(),
            "model_card": lambda: self.model_card(kwargs.get("style", "compact")),
        }
        fn = handlers.get(action)
        if fn is None:
            return {"error": "unknown_action", "available": list(handlers)}
        result = fn()
        if hasattr(result, "__dict__") and not isinstance(result, dict):
            return result.__dict__
        return result


def make_capability_v2(db_path: str | Path | None = None, registry_path: str | Path | None = None) -> LocalModelConsoleCapabilityV2:
    return LocalModelConsoleCapabilityV2(db_path, registry_path)
