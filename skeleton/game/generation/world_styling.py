"""Independent authored style dimensions for cross-era world realization.

These axes NEVER count as separate authored world laws. Platform tags are
requests for adapters, not evidence of licensed toolchain or executable ROMs.
Realism/fidelity and emotional comfort are independent; a comforting game
may use physically advanced simulation, while horror may use eight-bit art.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

_CATALOGS = {
    "eras": {
        "primordial-earth": "Pre-sentient geology, oceans and tectonics dominate",
        "early-life": "Single-celled and early multicellular ecological systems",
        "paleolithic": "Mobile gathering communities and handcrafted stone technology",
        "mesolithic": "Changing forager ecologies and region-specific adaptations",
        "neolithic": "Early farming, villages and complex land stewardship",
        "copper-age": "Proto-metallurgy and specialized settlements",
        "bronze-age": "Bronze-age cities, trade and sacred statecraft",
        "iron-age": "Ironworking, regional polities and expanding transport",
        "classical-antiquity": "Urban ancient polities and philosophical traditions",
        "late-antiquity": "Transitioning institutions, faiths and imperial networks",
        "early-medieval": "Postclassical local cultures and dispersed authority",
        "high-medieval": "Developing towns, guilds and interregional exchange",
        "late-medieval": "Intensified civic, maritime and technical change",
        "renaissance": "Early modern arts, science and merchant networks",
        "early-modern": "Printing, oceanic trade and diverse state systems",
        "age-of-sail": "Long-distance maritime logistics and exploration",
        "enlightenment": "Scientific methods, debate and public institutions",
        "early-industrial": "Mechanized production, coal power and factories",
        "steam-age": "Rail, steam transport and dense industry",
        "electrical-age": "Electrical grids, new media and urban systems",
        "early-20c": "Mechanical aviation and rapidly changing social life",
        "interwar": "Changing politics, art and industrial modernization",
        "mid-20c": "Analog electronics and mass industrial production",
        "space-age": "Rocket engineering, orbital exploration and computing",
        "microcomputer": "Microprocessor and personal computing proliferation",
        "digital-network": "Global digital communication and software infrastructures",
        "early-ai": "Modern AI systems and increasingly autonomous tools",
        "near-future": "Plausible extrapolated technological and social changes",
        "post-scarcity": "Hypothetical abundant-resource coordination societies",
        "solarpunk": "Community-scale sustainable technologies and ecological design",
        "dieselpunk": "Alternative machine-heavy mechanical industrial future",
        "clockpunk": "Precision clockwork systems in an alternative technical history",
        "atompunk": "Retro-futurist atomic optimism and alternative space systems",
        "biopunk": "Biotechnological institutions and adapted organisms",
        "nanotech-age": "Hypothetical scalable material and molecular engineering",
        "interplanetary": "Multiworld settlement and planetary logistics",
        "interstellar": "Slower-than-light star systems with deep travel durations",
        "posthuman": "Plural personhood and radically altered embodiment",
        "deep-future": "Very distant technological and cultural outcomes",
        "cosmic-epoch": "Astronomical and cosmological time beyond civilization"
    },
    "chronologies": [
        "remote-past",
        "known-history",
        "fictional-history",
        "alternate-history",
        "parallel-present",
        "contemporary",
        "near-future",
        "medium-future",
        "far-future",
        "deep-time",
        "before-time",
        "cyclical-time",
        "branching-time",
        "reversed-time",
        "simultaneous-eras",
        "fractured-time",
        "frozen-time",
        "unequal-time-rates",
        "subjective-time",
        "accelerated-evolution",
        "generational-timespan",
        "one-night-story",
        "evergreen-persistent",
        "endless-frontier",
        "post-collapse-recovery",
        "time-loop",
        "post-victory-continuation",
        "self-rewriting-history",
        "multi-epoch-campaign",
        "nonlinear-temporal-world",
        "timeless-myth",
        "asynchronous-worlds"
    ],
    "theologies": {
        "none": "No required theology; metaphysics may remain undefined",
        "secular-material": "Materialist culture whose claims can be independently examined",
        "atheist-world": "No deities exist under declared setting laws",
        "agnostic-open": "Existence of supernatural agents remains an unresolved question",
        "monotheistic-invented": "One invented deity with explicitly authored local doctrine",
        "polytheistic-invented": "Plural fictional deities with distinct bounded authorities",
        "dualistic-invented": "Two metaphysical forces with nonbinary civic interpretations",
        "animist-invented": "Spirits inhabit places, organisms or tools; participation is optional",
        "ancestor-veneration": "Consented rituals and remembrance govern ancestor relationships",
        "deistic-invented": "Creator is inactive or not directly intervening",
        "pantheistic-invented": "Sacredness applies to all existence under a fictional rule",
        "panentheistic-invented": "World and divine whole overlap without being identical",
        "non-theistic-spiritual": "Sacred practices without personified deity claims",
        "nature-sacred": "Sacred sites and ecological caretaking define institutions",
        "cosmic-mythic": "Celestial entities influence reality under invented mythic laws",
        "ritual-mechanical": "Ritual works by public, testable, setting-specific procedures",
        "oracular": "Oracles make uncertain predictions that require verification",
        "syncretic-invented": "Multiple voluntarily combined fictional traditions",
        "theological-pluralism": "Coexisting faiths with differing interpretations and safeguards",
        "divinity-evolving": "Divine agents learn or change their bounded roles",
        "faith-as-power": "Belief alters specific physical rules with explicit costs",
        "belief-ineffective": "Belief affects society but not physical causality",
        "post-divine": "Deities once existed but left historical traces only",
        "machine-sacred": "Machine agents are objects of original sacred institutions"
    },
    "themes": [
        "comfort",
        "care",
        "cooperation",
        "friendship",
        "family",
        "belonging",
        "community",
        "domestic-life",
        "mystery",
        "discovery",
        "awe",
        "exploration",
        "pioneering",
        "science",
        "epistemology",
        "education",
        "survival",
        "hardship",
        "crafting",
        "industry",
        "politics",
        "diplomacy",
        "freedom",
        "resistance",
        "law",
        "justice",
        "ethics",
        "trade",
        "economics",
        "ecology",
        "conservation",
        "evolution",
        "loss",
        "grief",
        "reconciliation",
        "mortality",
        "legacy",
        "divinity",
        "ritual",
        "folklore",
        "cosmic-horror",
        "psychological-horror",
        "terror",
        "wonder",
        "comedy",
        "satire",
        "romance",
        "betrayal",
        "military",
        "peacebuilding",
        "reconstruction",
        "civilization",
        "mythic-epic",
        "small-town",
        "post-apocalyptic",
        "alternate-history",
        "space-opera",
        "slice-of-life",
        "generational-saga",
        "dreamlike",
        "puzzlebox",
        "detective",
        "stealth",
        "sport",
        "architecture",
        "art",
        "performance",
        "music",
        "language",
        "time-travel",
        "parallel-worlds",
        "utopia",
        "dystopia",
        "science-fantasy",
        "hard-science",
        "fantasy",
        "low-fantasy",
        "high-fantasy",
        "urban-fantasy",
        "solarpunk",
        "biopunk"
    ],
    "visual_styles": [
        "monochrome-pixel",
        "four-shade-handheld",
        "tile-8bit",
        "tile-16bit",
        "handheld-sprite",
        "pixel-hd",
        "voxel-miniature",
        "voxel-realistic",
        "isometric-diorama",
        "low-poly-flat",
        "low-poly-lit",
        "polygon-retro-3d",
        "ps1-style-jitter",
        "ps2-style-lit",
        "cel-shaded",
        "comic-ink",
        "storybook-painted",
        "watercolor",
        "paper-craft",
        "stop-motion-inspired",
        "clay-like",
        "illustrated-2d",
        "vector-geometric",
        "miniature-photography",
        "stylized-pbr",
        "naturalistic-pbr",
        "cinematic-pbr",
        "photogrammetric-inspired",
        "high-fidelity-realism",
        "photorealistic-target",
        "abstract-symbolic",
        "terminal-ascii"
    ],
    "tones": {
        "ultra-snuggly": "No punitive failure loop; warmth, voluntary play and accessible comfort",
        "plush-and-playful": "Playful, soft, cheerful interactions with mild obstacles",
        "gentle-domestic": "Home, care, friendship and tactile everyday activities",
        "serene": "Quiet natural and social systems emphasizing rest and curiosity",
        "whimsical": "Curiosity and friendly surprise; absurdity need not be threatening",
        "hopeful": "Meaningful challenge with robust chances for renewal",
        "bittersweet": "Warmth coexisting with loss, difficult choices and remembrance",
        "adventurous": "Mild danger alongside discovery and active agency",
        "heroic": "Strong challenge and stakes with clear restoration paths",
        "dramatic": "Significant social or environmental conflict",
        "tense": "Ambiguity, uncertainty and resource pressure",
        "somber": "Cautious atmosphere acknowledging irreversible harm",
        "eerie": "Unsettling ambiguity without mandatory explicit violence",
        "uncanny": "Familiar patterns behave unexpectedly",
        "grim": "Hard consequences with constrained optimism",
        "dread-filled": "Pervasive threat and uncertain safety",
        "harrowing": "Intense risk and emotional pressure with safety controls",
        "nightmarish": "Extreme surreal threat without mandatory gore",
        "tragic": "Irreversible sacrifice and consequence-heavy endings",
        "existential": "Meaning and uncertainty without guaranteed answers",
        "nihilistic-fiction": "A fictional world where institutions fail to provide inherent purpose",
        "reflective": "Inner life and long-term consequences over excitement",
        "satirical": "Humor used to examine institutions critically",
        "uplifting": "Hope rewarded without eliminating believable difficulty"
    },
    "simulation": {
        "symbolic": "State graph and symbols; no continuous physical simulation",
        "boardlike": "Discrete game actions, bounded entities, simple resource accounting",
        "arcade": "Intentional abstraction for responsiveness and fun",
        "systemic-lite": "Deterministic discrete subsystems and simplified interactions",
        "systems-sim": "Meaningful agent, resource and environment interactions",
        "simulation-heavy": "Multi-domain continuous and discrete simulations within strict budgets",
        "physical-consistent": "Declared conservation rules with reproducible physics approximations",
        "material-sim": "Material response, environmental changes, validated numerical bounds",
        "environmental-sim": "Detailed atmosphere, terrain, ecology and thermal interactions",
        "agent-sim": "Detailed autonomy, schedules, relationships and economies",
        "high-fidelity-sim": "Adaptive simulation fidelity with measured error tolerances",
        "hyperrealism-target": "High fidelity only when validated against declared domain models; prohibit unsupported magic realism claim"
    },
    "platforms": [
        "atari-vcs",
        "zx-spectrum",
        "commodore-64",
        "nes",
        "master-system",
        "game-boy",
        "sega-genesis",
        "snes",
        "game-gear",
        "neo-geo",
        "playstation-1",
        "sega-saturn",
        "nintendo-64",
        "game-boy-color",
        "dreamcast",
        "playstation-2",
        "gamecube",
        "original-xbox",
        "game-boy-advance",
        "nintendo-ds",
        "psp",
        "wii",
        "xbox-360",
        "playstation-3",
        "nintendo-3ds",
        "ps-vita",
        "wii-u",
        "nintendo-switch",
        "playstation-4",
        "xbox-one",
        "playstation-5",
        "xbox-series",
        "pc-dos",
        "pc-windows",
        "pc-linux",
        "pc-macos",
        "steam-deck",
        "browser",
        "mobile-android",
        "mobile-ios",
        "custom-homebrew"
    ]
}

ERAS = MappingProxyType(_CATALOGS["eras"])
CHRONOLOGIES = tuple(_CATALOGS["chronologies"])
THEOLOGIES = MappingProxyType(_CATALOGS["theologies"])
THEMES = tuple(_CATALOGS["themes"])
VISUAL_STYLES = tuple(_CATALOGS["visual_styles"])
TONES = MappingProxyType(_CATALOGS["tones"])
SIMULATION_REALISM = MappingProxyType(_CATALOGS["simulation"])
HARDWARE_TARGETS = tuple(_CATALOGS["platforms"])


@dataclass(frozen=True)
class WorldStyling:
    era: str = "near-future"
    chronology: str = "fictional-history"
    theology: str = "none"
    themes: tuple[str, ...] = ("exploration",)
    visual_style: str = "stylized-pbr"
    tone: str = "adventurous"
    simulation_realism: str = "systemic-lite"
    comfort: int = 50
    realism: int = 50
    hardware_target: str = "pc-windows"

    def __post_init__(self) -> None:
        checks = (
            ("era", ERAS), ("chronology", CHRONOLOGIES),
            ("theology", THEOLOGIES), ("visual_style", VISUAL_STYLES),
            ("tone", TONES), ("simulation_realism", SIMULATION_REALISM),
            ("hardware_target", HARDWARE_TARGETS),
        )
        for name, possibilities in checks:
            if getattr(self, name) not in possibilities:
                raise ValueError(f"unknown world styling {name}")
        if not isinstance(self.themes, tuple) or not self.themes or len(self.themes) > 8:
            raise ValueError("themes must be nonempty tuple of at most eight")
        if len(set(self.themes)) != len(self.themes) or any(x not in THEMES for x in self.themes):
            raise ValueError("unknown or duplicate theme")
        for name in ("comfort", "realism"):
            x = getattr(self, name)
            if isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= 100:
                raise ValueError(f"{name} must be integer 0 to 100")

    @property
    def requires_scientific_validation(self) -> bool:
        # This is a fidelity request, not proof of scientific correctness.
        # Independent physics/domain validation remains mandatory.
        return self.simulation_realism in {
            "physical-consistent", "material-sim", "environmental-sim",
            "high-fidelity-sim", "hyperrealism-target",
        }

    def as_dict(self) -> dict:
        return {
            "era": self.era, "chronology": self.chronology,
            "theology": self.theology, "themes": list(self.themes),
            "visual_style": self.visual_style, "tone": self.tone,
            "simulation_realism": self.simulation_realism,
            "comfort": self.comfort, "realism": self.realism,
            "hardware_target": self.hardware_target,
        }
