"""Local model capability bridge for the 70+ console emulator catalog.

Gives the offline/local model governed access to query, plan, and orchestrate
the operator-approved libretro cores without violating isolation, no-download,
or fail-closed rules. Catalog inspection remains native-code-free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from skeleton.jeeves.game_emulator_catalog import (
    GameEmulatorRegistry,
    EmulatorCatalogError,
    load_registry_from_env_or_path,
)


CAPABILITY_SCHEMA = "skeleton.local_model.console_emulator_capability.v1"
MAX_PROMPT_CHARS = 8192


@dataclass(frozen=True)
class CoreStatus:
    name: str
    hardware_targets: tuple[str, ...]
    installed: bool
    qualified: bool
    notes: str


@dataclass
class LocalModelConsoleCapability:
    """Bridge so a local model can fully reason over the emulator fleet.

    All methods are pure or read-only on the approved registry. No native
    execution, no network, no firmware fetch. Suitable for tool-calling or
    prompt injection into the offline chat session.
    """

    registry: GameEmulatorRegistry | None = None
    catalog_path: Path | None = None
    _status_cache: dict[str, CoreStatus] = field(default_factory=dict, init=False)

    def load(self, registry_path: str | Path | None = None) -> None:
        """Load the operator-approved registry. Falls back to env or catalog."""
        if registry_path:
            self.catalog_path = Path(registry_path)
            # Use the existing loader that never executes native code
            try:
                self.registry = load_registry_from_env_or_path(str(self.catalog_path))
            except EmulatorCatalogError as exc:
                raise RuntimeError(f"catalog load failed: {exc.code} {exc.message}") from exc
        else:
            try:
                self.registry = load_registry_from_env_or_path(None)
            except EmulatorCatalogError:
                self.registry = None

    # Static hardware map for the 83 bootstrap cores (operator-approved catalog)
    # Used when the live registry is not loaded. Never claims installation.
    _HARDWARE_MAP: dict[str, tuple[str, ...]] = {
        "gambatte": ("Game Boy", "Game Boy Color"),
        "fceumm": ("NES", "Famicom", "Famicom Disk System"),
        "genesis_plus_gx": ("Sega Genesis", "Mega Drive", "Sega CD", "32X"),
        "snes9x": ("SNES", "Super Famicom"),
        "mgba": ("Game Boy Advance", "Game Boy", "Game Boy Color"),
        "pcsx_rearmed": ("PlayStation",),
        "stella2014": ("Atari 2600",),
        "prosystem": ("Atari 7800",),
        "handy": ("Atari Lynx",),
        "mednafen_ngp": ("Neo Geo Pocket", "Neo Geo Pocket Color"),
        "bsnes": ("SNES", "Super Famicom"),
        "mame2003": ("Arcade",),
        "flycast": ("Dreamcast", "Naomi"),
        "ppsspp": ("PlayStation Portable",),
        "melonds": ("Nintendo DS", "DSi"),
        "desmume": ("Nintendo DS",),
        "nestopia": ("NES", "Famicom"),
        "mesen": ("NES", "Famicom"),
        "picodrive": ("Sega Genesis", "Mega Drive", "32X", "Sega CD"),
        "fbneo": ("Neo Geo", "Arcade"),
        "dosbox_pure": ("DOS", "PC"),
        "vice_x64": ("Commodore 64",),
        "atari800": ("Atari 8-bit",),
        "bluemsx": ("MSX", "MSX2"),
        "cap32": ("Amstrad CPC",),
        "fuse": ("ZX Spectrum",),
        "hatari": ("Atari ST", "Atari STE"),
        "virtualjaguar": ("Atari Jaguar",),
        "yabause": ("Sega Saturn",),
        "swanstation": ("PlayStation",),
        "parallel_n64": ("Nintendo 64",),
        "mupen64plus_next": ("Nintendo 64",),
        "gpsp": ("Game Boy Advance",),
        "tgbdual": ("Game Boy", "Game Boy Color"),
        "sameboy": ("Game Boy", "Game Boy Color"),
        "gearboy": ("Game Boy", "Game Boy Color"),
        "gearcoleco": ("ColecoVision",),
        "gearsystem": ("Sega Master System", "Game Gear"),
        "smsplus_gx": ("Sega Master System", "Game Gear"),
        "mednafen_pce_fast": ("PC Engine", "TurboGrafx-16"),
        "mednafen_psx": ("PlayStation",),
        "mednafen_saturn": ("Sega Saturn",),
        "mednafen_wswan": ("WonderSwan", "WonderSwan Color"),
        "mednafen_vb": ("Virtual Boy",),
        "mednafen_lynx": ("Atari Lynx",),
        "mednafen_supafaust": ("SNES", "Super Famicom"),
        "opera": ("3DO",),
        "np2kai": ("PC-98",),
        "px68k": ("Sharp X68000",),
        "quasi88": ("PC-88",),
        "eightyone": ("ZX81",),
        "freeintv": ("Intellivision",),
        "vecx": ("Vectrex",),
        "pokemini": ("Pokemon Mini",),
        "neocd": ("Neo Geo CD",),
        "crocods": ("Amstrad CPC",),
        "fmsx": ("MSX",),
        "meteor": ("Game Boy Advance",),
        "vba_next": ("Game Boy Advance",),
        "snes9x2002": ("SNES",),
        "snes9x2005": ("SNES",),
        "snes9x2010": ("SNES",),
        "bsnes_mercury_accuracy": ("SNES",),
        "bsnes_mercury_balanced": ("SNES",),
        "bsnes_mercury_performance": ("SNES",),
        "genesis_plus_gx_wide": ("Sega Genesis",),
        "fbalpha2012_neogeo": ("Neo Geo",),
        "mame2003_plus": ("Arcade",),
        "mame2016": ("Arcade",),
        "dosbox_core": ("DOS",),
        "dosbox_svn": ("DOS",),
        "blastem": ("Sega Genesis",),
        "bnes": ("NES",),
        "puae": ("Amiga",),
        "vice_x128": ("Commodore 128",),
        "vice_x64sc": ("Commodore 64",),
        "vice_xpet": ("Commodore PET",),
        "vice_xplus4": ("Commodore Plus/4",),
        "vice_xvic": ("Commodore VIC-20",),
        "a5200": ("Atari 5200",),
    }

    def list_cores(self) -> list[str]:
        """Return sorted names of all declared cores in the catalog bootstrap."""
        # Prefer live registry; fall back to known bootstrap set of 83
        if self.registry and hasattr(self.registry, "cores"):
            return sorted(getattr(self.registry, "cores", {}).keys())
        # Static fallback drawn from current catalog bootstrap_pins (70-83 range)
        return sorted([
            "gambatte", "fceumm", "genesis_plus_gx", "snes9x", "mgba",
            "pcsx_rearmed", "stella2014", "prosystem", "handy", "mednafen_ngp",
            "bsnes", "mame2003", "flycast", "ppsspp", "melonds", "desmume",
            "nestopia", "mesen", "picodrive", "fbneo", "dosbox_pure",
            "vice_x64", "atari800", "bluemsx", "cap32", "fuse", "hatari",
            "virtualjaguar", "yabause", "swanstation", "parallel_n64",
            "mupen64plus_next", "gpsp", "tgbdual", "sameboy", "gearboy",
            "gearcoleco", "gearsystem", "smsplus_gx", "mednafen_pce_fast",
            "mednafen_psx", "mednafen_saturn", "mednafen_wswan", "mednafen_vb",
            "mednafen_lynx", "mednafen_supafaust", "opera", "np2kai", "px68k",
            "quasi88", "eightyone", "freeintv", "vecx", "pokemini", "neocd",
            "crocods", "fmsx", "meteor", "vba_next", "snes9x2002", "snes9x2005",
            "snes9x2010", "bsnes_mercury_accuracy", "bsnes_mercury_balanced",
            "bsnes_mercury_performance", "genesis_plus_gx_wide", "fbalpha2012_neogeo",
            "mame2003_plus", "mame2016", "dosbox_core", "dosbox_svn", "blastem",
            "bnes", "puae", "vice_x128", "vice_x64sc", "vice_xpet", "vice_xplus4",
            "vice_xvic", "a5200",
        ])

    def get_status(self, core_name: str) -> CoreStatus:
        """Report installation and qualification status without loading the core."""
        if core_name in self._status_cache:
            return self._status_cache[core_name]
        installed = False
        qualified = False
        targets: tuple[str, ...] = self._HARDWARE_MAP.get(core_name, (core_name,))
        notes = "declared in catalog; requires operator-approved install for native use"
        if self.registry:
            # Real registry would expose ApprovedEmulatorCore entries
            cores = getattr(self.registry, "cores", {})
            if core_name in cores:
                core = cores[core_name]
                installed = bool(getattr(core, "library_path", None) or getattr(core, "installed", False))
                qualified = bool(getattr(core, "qualified", False))
                targets = tuple(getattr(core, "hardware_targets", ()) or self._HARDWARE_MAP.get(core_name, (core_name,)))
                notes = "live registry entry"
        status = CoreStatus(
            name=core_name,
            hardware_targets=targets or (core_name,),
            installed=installed,
            qualified=qualified,
            notes=notes,
        )
        self._status_cache[core_name] = status
        return status

    def fleet_summary(self) -> dict[str, Any]:
        """High-level fleet view suitable for local-model context injection."""
        cores = self.list_cores()
        installed = sum(1 for c in cores if self.get_status(c).installed)
        qualified = sum(1 for c in cores if self.get_status(c).qualified)
        return {
            "schema": CAPABILITY_SCHEMA,
            "total_declared_cores": len(cores),
            "installed_count": installed,
            "qualified_count": qualified,
            "coverage_percent": round(100.0 * qualified / max(len(cores), 1), 1),
            "note": "Full native capability requires operator-approved libretro install + isolated worker. Local model can plan, query, and orchestrate only.",
        }

    def build_model_tool_schema(self) -> dict[str, Any]:
        """JSON schema for tool-calling that a local model can use."""
        return {
            "name": "console_emulator_capability",
            "description": "Query and plan over the operator-approved 70+ console emulator fleet (libretro cores). Never executes native code or downloads firmware.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list_cores", "fleet_summary", "get_status", "plan_session"],
                    },
                    "core_name": {"type": "string", "description": "Required for get_status"},
                    "hardware": {"type": "string", "description": "Optional target for plan_session"},
                },
                "required": ["action"],
            },
        }

    def plan_session(self, hardware: str | None = None, max_steps: int = 1000) -> dict[str, Any]:
        """Produce a governed learning-session plan the local model can follow."""
        cores = self.list_cores()
        candidates = [
            c for c in cores
            if not hardware or hardware.lower() in c.lower() or any(
                hardware.lower() in t.lower() for t in self.get_status(c).hardware_targets
            )
        ]
        if not candidates:
            candidates = cores[:3]
        return {
            "schema": CAPABILITY_SCHEMA,
            "objective": "governed game-learning episode on approved core",
            "recommended_cores": candidates[:5],
            "max_steps": max(1, min(max_steps, 10000)),
            "constraints": [
                "operator-approved registry only",
                "isolated worker for any native retro_run",
                "no BIOS/firmware download",
                "content must be exact multi-file bundles under MAX_CONTENT_BYTES",
                "local model may only orchestrate; never bypass fail-closed gates",
            ],
            "success_criteria": "episode completed with evidence hashes; no silent fallback to reference sim",
        }

    def qualification_matrix(self) -> list[dict[str, Any]]:
        """Return a compact matrix the local model can reason over.

        Status is always 'operator-gated' unless a live registry proves otherwise.
        This is not a production certification.
        """
        matrix = []
        for name in self.list_cores():
            st = self.get_status(name)
            matrix.append({
                "core": name,
                "hardware": list(st.hardware_targets),
                "installed": st.installed,
                "qualified": st.qualified,
                "capability_level": "orchestrate-only" if not st.qualified else "native-isolated",
                "notes": st.notes,
            })
        return matrix

    def recommend_for_learning(self, goal: str = "general") -> list[str]:
        """Suggest a small set of cores for a learning objective.

        goal examples: 'general', 'accuracy', 'arcade', 'handheld', 'home-computer'
        """
        goal = goal.lower()
        if "arcade" in goal:
            prefer = ["fbneo", "mame2003", "mame2003_plus"]
        elif "handheld" in goal:
            prefer = ["gambatte", "mgba", "melonds", "ppsspp"]
        elif "accuracy" in goal:
            prefer = ["bsnes", "mesen", "nestopia", "mgba"]
        elif "home" in goal or "computer" in goal:
            prefer = ["dosbox_pure", "vice_x64", "hatari", "fuse"]
        else:
            prefer = ["snes9x", "fceumm", "gambatte", "mgba", "genesis_plus_gx"]
        available = set(self.list_cores())
        return [c for c in prefer if c in available][:5]

    def validate_fleet(self) -> dict[str, Any]:
        """Sanity-check the declared fleet for the local model.

        Returns a small report; never raises on missing registry.
        """
        cores = self.list_cores()
        unique = len(set(cores))
        mapped = sum(1 for c in cores if c in self._HARDWARE_MAP)
        return {
            "total": len(cores),
            "unique": unique,
            "hardware_mapped": mapped,
            "unmapped": len(cores) - mapped,
            "healthy": unique == len(cores) and mapped >= 70,
        }

    def model_card(self) -> str:
        """One-paragraph card suitable for system prompt or model context."""
        s = self.fleet_summary()
        return (
            f"You have access to a governed console emulator capability covering "
            f"{s['total_declared_cores']} declared libretro cores "
            f"({s['qualified_count']} currently qualified). "
            f"Use the console_emulator_capability tool to list cores, get status, "
            f"plan learning sessions, or obtain emulator: choices. "
            f"Native execution always stays in the isolated host; you only orchestrate. "
            f"Never request BIOS downloads or bypass fail-closed gates."
        )

    def emulator_console_choices(self) -> list[dict[str, str]]:
        """Generate the explicit emulator:<id> choices the console catalog expects.

        Matches the console_integration contract: truthful entry for every declared core.
        """
        choices = []
        for name in self.list_cores():
            st = self.get_status(name)
            choices.append({
                "choice": f"emulator:{name}",
                "core": name,
                "hardware": ", ".join(st.hardware_targets),
                "runtime_kind": "installed_libretro_emulator" if st.installed else "declared_only",
            })
        return choices

    def inject_into_prompt(self, base_prompt: str) -> str:
        """Prepend a compact capability card so the local model knows it can use the fleet."""
        summary = self.fleet_summary()
        card = (
            f"[CONSOLE_EMULATOR_CAPABILITY schema={CAPABILITY_SCHEMA}]\n"
            f"Fleet: {summary['total_declared_cores']} declared cores, "
            f"{summary['qualified_count']} qualified. "
            f"Tool available: console_emulator_capability. "
            f"Use for planning only; native execution stays in isolated host.\n"
        )
        combined = card + "\n" + base_prompt
        if len(combined) > MAX_PROMPT_CHARS:
            return card + base_prompt[: MAX_PROMPT_CHARS - len(card) - 100]
        return combined


def make_capability(registry_path: str | Path | None = None) -> LocalModelConsoleCapability:
    cap = LocalModelConsoleCapability()
    cap.load(registry_path)
    return cap
