"""
dna_domains
===========

Domain-specific configs for the generic ``dna_translator_core``.

Each domain corresponds to a 100-slider cockpit on the frontend:

    • ``builder``  — key prefix ``bdr_<cat>_<group>_<slot>``  (600 sliders total)
    • ``jeeves``   — key prefix ``jv_<group>_<slot>``         (100 sliders)
    • ``academy``  — key prefix ``ac_<group>_<slot>``         (100 sliders)

Slot label dictionaries mirror the frontend data files in
``frontend/state/{jeevesDnaData,academyDnaData,builderDnaData}.ts``.
"""

from __future__ import annotations

from .dna_translator_core import DnaDomain, register_domain


# ─── Builder (multi-category) ─────────────────────────────────────────
# bdr_<category>_<group>_<slot>  → split index 2 = group, 3+ = slot.

_BUILDER_GROUP_HEADERS = {
    "perf":     "Performance & scaling",
    "quality":  "Code quality & style",
    "testing":  "Testing strategy",
    "security": "Security & compliance",
    "deploy":   "Deployment & DevOps",
    "obs":      "Observability & logging",
    "ux":       "UX / DX polish",
    "docs":     "Documentation",
    "a11y":     "Accessibility & i18n",
    "maint":    "Maintainability & evolution",
}
_BUILDER_SLOT_LABELS = {
    "perf": {
        "p95": "p95 latency", "cold": "cold-start budget", "hot": "hot-path tuning",
        "cache": "caching layers", "batch": "batched IO", "concurrency": "concurrency",
        "memory": "memory footprint", "bundle": "bundle / binary size",
        "profiling": "profiling hooks", "sla": "SLO strictness",
    },
    "quality": {
        "terse": "terseness", "naming": "descriptive naming", "types": "type strictness",
        "fp": "functional bias", "decomp": "function decomposition",
        "side": "side-effect avoidance", "magic": "magic-number elimination",
        "lint": "lint strictness", "fmt": "formatter discipline",
        "comments": "inline comment density",
    },
    "testing": {
        "unit": "unit coverage", "integ": "integration tests", "e2e": "E2E tests",
        "mock": "mocking aggression", "snapshot": "snapshot tests", "fuzz": "fuzz tests",
        "property": "property tests", "contract": "contract tests",
        "chaos": "chaos drills", "smoke": "smoke checks",
    },
    "security": {
        "input": "input validation", "authn": "authentication strictness",
        "authz": "authorisation strictness", "secret": "secret handling",
        "dep": "dependency audit", "csp": "CSP / sandbox", "sqli": "injection guards",
        "gdpr": "privacy compliance", "audit": "audit trail", "polp": "least privilege",
    },
    "deploy": {
        "cicd": "CI/CD coverage", "iac": "Infra-as-Code", "containers": "containerisation",
        "rollback": "rollback ease", "canary": "canary rollouts",
        "flag": "feature-flag gating", "auto": "auto-scaling",
        "sec": "secret rotation", "env": "env parity", "monitor": "health probes",
    },
    "obs": {
        "log": "log verbosity", "struct": "structured logs", "metric": "metric coverage",
        "trace": "distributed traces", "sample": "sampling rate",
        "alert": "alert sensitivity", "sla": "SLO dashboards",
        "error": "error capture", "context": "log context", "retain": "log retention",
    },
    "ux": {
        "loading": "loading states", "empty": "empty states", "error": "error states",
        "micro": "micro-interactions", "haptic": "haptic / sound",
        "shortcut": "power-user shortcuts", "onboard": "onboarding",
        "help": "in-app help", "dx_log": "dev logging", "dx_doc": "DX docstrings",
    },
    "docs": {
        "readme": "README depth", "api": "API reference", "tutorial": "tutorials",
        "examples": "code examples", "adr": "ADR records", "diagram": "diagrams",
        "patterns": "pattern catalogue", "edge": "edge-case notes",
        "cl": "changelog automation", "inline": "inline comments",
    },
    "a11y": {
        "contrast": "contrast", "sr": "screen-reader", "keyboard": "keyboard nav",
        "motion": "reduce-motion", "font": "font scaling", "i18n": "i18n breadth",
        "rtl": "RTL support", "a11y_doc": "a11y docs",
        "colorblind": "colour-blind palette", "subtitle": "captions",
    },
    "maint": {
        "modular": "modularity", "ports": "ports & adapters",
        "di": "dependency injection", "migration": "migration friendliness",
        "dep_pin": "dependency pinning", "deprec": "deprecation hygiene",
        "compat": "backward compatibility", "plug": "plugin surface",
        "fork": "forkability", "license": "license clarity",
    },
}

BUILDER_DOMAIN = DnaDomain(
    name="builder",
    key_prefix="bdr_",
    group_headers=_BUILDER_GROUP_HEADERS,
    slot_labels=_BUILDER_SLOT_LABELS,
    key_group_index=2,
    key_slot_start=3,
    group_order=tuple(_BUILDER_GROUP_HEADERS),
    blurb="**Build DNA preferences** (cockpit drift):",
)


# ─── Jeeves (single namespace) ─────────────────────────────────────────
# jv_<group>_<slot>  → split index 1 = group, 2+ = slot.

_JEEVES_GROUP_HEADERS = {
    "style":  "Code style",
    "arch":   "Architecture bias",
    "test":   "Testing rigor",
    "sec":    "Security paranoia",
    "perf":   "Performance bias",
    "doc":    "Documentation richness",
    "ref":    "Refactor aggressiveness",
    "voice":  "Reviewer voice",
    "tool":   "Tooling preferences",
    "errn":   "Error narrative",
}
_JEEVES_SLOT_LABELS = {
    "style": {
        "terseness": "terseness", "comments": "comment density",
        "naming": "descriptive naming", "decomp": "decomposition",
        "types": "type strictness", "err": "error handling",
        "sideeffects": "side-effect avoidance", "immutable": "immutability",
        "linewidth": "line width", "doc": "doc strings",
    },
    "arch": {
        "monolith": "monolith bias", "layers": "layered separation",
        "di": "dependency injection", "event": "event-driven",
        "rest": "REST-first", "bus": "message bus", "repo": "repository pattern",
        "hex": "hexagonal", "screaming": "screaming arch", "ddd": "DDD bias",
    },
    "test": {
        "unit": "unit coverage", "integ": "integration depth",
        "mock": "mocking strategy", "snapshot": "snapshot tests",
        "e2e": "E2E weight", "contract": "contract tests",
        "fuzz": "fuzz tests", "property": "property tests",
        "smoke": "smoke checks", "chaos": "chaos drills",
    },
    "sec": {
        "input": "input validation", "auth": "auth strictness",
        "secret": "secret handling", "dep": "dep audit",
        "sandbox": "sandbox bias", "csp": "CSP enforcement",
        "csrf": "CSRF protection", "sqli": "SQL-injection wall",
        "ssrf": "SSRF guards", "polp": "least privilege",
    },
    "perf": {
        "latency": "latency focus", "batching": "batch operations",
        "cache": "caching layers", "lazy": "lazy loading",
        "bundle": "bundle size", "fp": "functional purity",
        "coldstart": "cold-start budget", "hotpath": "hot-path tuning",
        "profile": "auto profiling", "opt_aggro": "optimisation aggression",
    },
    "doc": {
        "api": "API reference", "readme": "README quality",
        "adr": "architecture decisions", "examples": "code examples",
        "diagram": "diagrams", "tutorial": "tutorial walks",
        "inline": "inline comments", "changelog": "changelog auto",
        "patterns": "pattern catalogue", "edge": "edge-case notes",
    },
    "ref": {
        "rename": "rename freely", "extract": "extract functions",
        "dedupe": "dedupe", "magicnum": "magic-number kill",
        "dead": "dead code removal", "format": "reformat",
        "lint": "lint fix", "smell": "code-smell radar",
        "recursion": "recursion vs loop", "pattern": "pattern match",
    },
    "voice": {
        "friendly": "friendliness", "blunt": "bluntness",
        "depth": "depth of reply", "examples": "examples included",
        "altsol": "alt solutions", "citing": "code citation",
        "blocker": "blocker tagging", "ranking": "priority ranking",
        "freq": "comment frequency", "mentor": "mentorship tone",
    },
    "tool": {
        "ts": "TypeScript bias", "py": "Python bias", "rust": "Rust bias",
        "agnostic": "framework-agnostic", "latest": "bleeding edge",
        "monorepo": "monorepo bias", "polyrepo": "polyrepo bias",
        "ci": "CI automation", "oss": "OSS bias", "ide": "IDE plug-ins",
    },
    "errn": {
        "stack": "stack verbosity", "context": "context messages",
        "recovery": "recovery tips", "antipat": "anti-pattern call",
        "diff": "diff annotation", "blame": "blame integration",
        "rootcause": "root-cause depth", "log": "log richness",
        "telemetry": "telemetry capture", "panic": "panic vs graceful",
    },
}

JEEVES_DOMAIN = DnaDomain(
    name="jeeves",
    key_prefix="jv_",
    group_headers=_JEEVES_GROUP_HEADERS,
    slot_labels=_JEEVES_SLOT_LABELS,
    key_group_index=1,
    key_slot_start=2,
    group_order=tuple(_JEEVES_GROUP_HEADERS),
    blurb="**Jeeves DNA preferences** (cockpit drift):",
)


# ─── Academy ───────────────────────────────────────────────────────────
# ac_<group>_<slot>

_ACADEMY_GROUP_HEADERS = {
    "voice":  "Voice prosody",
    "pace":   "Pacing strategy",
    "code":   "Code reading",
    "ux":     "Audiobook UX",
    "comp":   "Comprehension aids",
    "disp":   "Display & legibility",
    "diff":   "Difficulty tuning",
    "eng":    "Engagement loops",
    "rev":    "Adaptive review",
    "a11y":   "Accessibility",
}
_ACADEMY_SLOT_LABELS = {
    "voice": {
        "rate_fine": "rate fine-tune", "pitch_fine": "pitch fine-tune",
        "emphasis": "emphasis", "breath": "breath audibility",
        "pauses": "pause length", "intonation": "intonation arc",
        "formal": "formality", "energy": "energy",
        "warmth": "warmth", "accent": "regional accent",
    },
    "pace": {
        "chapter": "chapter pace", "paragraph": "paragraph pace",
        "sentence": "sentence pace", "beat": "beat pause",
        "character": "character/sec", "quote": "quote breath",
        "dialog": "dialog pace", "narration": "narration pace",
        "suspense": "suspense stretch", "accel": "acceleration",
    },
    "code": {
        "verbose": "verbose code read", "syntax": "syntax names",
        "indent": "indent depth", "comment": "comment read",
        "langtag": "language tag", "brackets": "brackets read",
        "ident": "identifiers explained", "linenums": "line numbers",
        "multiline": "multi-line split", "focus": "focus mode",
    },
    "ux": {
        "autoadv": "auto-advance", "chime": "chapter chime",
        "bookmark": "bookmark depth", "replay": "replay last",
        "sleep": "sleep timer", "phones": "headphone detect",
        "duck": "audio ducking", "gesture": "gesture controls",
        "headtrack": "head-tracking", "eq": "EQ curve",
    },
    "comp": {
        "recap": "recap snippets", "quiz": "quizlets",
        "term": "term definitions", "glossary": "glossary push",
        "mnemonic": "mnemonics", "example": "examples",
        "translate": "parallel translate", "paraphr": "paraphrase",
        "xlink": "cross-links", "footnote": "footnote read",
    },
    "disp": {
        "fontsize": "font size", "contrast": "contrast",
        "lineheight": "line height", "letter": "letter spacing",
        "word": "word spacing", "paragraph": "paragraph spacing",
        "syntax": "syntax highlight", "focusdim": "focus dim",
        "halo": "hover halo", "colorshift": "colour shift",
    },
    "diff": {
        "vocab": "vocabulary level", "syntax": "syntax complexity",
        "length": "sentence length", "idiom": "idioms allowed",
        "jargon": "technical jargon", "abstract": "abstraction depth",
        "math": "math notation", "proof": "formal proofs",
        "code": "code density", "latency": "response latency",
    },
    "eng": {
        "xp": "XP curve", "level": "level cadence",
        "badge": "badge frequency", "streak": "streak weight",
        "celebrate": "celebration", "ambient": "ambient music",
        "weekly": "weekly recap", "daily": "daily push",
        "drop": "surprise drops", "cohort": "cohort spotlight",
    },
    "rev": {
        "sr": "spaced repetition", "errfocus": "error focus",
        "drill": "weak-spot drill", "dwell": "dwell-time bias",
        "reexplain": "re-explain trigger", "hint": "hint frequency",
        "scaffold": "scaffolding", "mastery": "mastery threshold",
        "retry": "retry cadence", "forget": "forgetting curve",
    },
    "a11y": {
        "contrast": "high contrast", "dyslexia": "dyslexia font",
        "motion": "motion reduce", "srecho": "screen-reader echo",
        "subtitle": "subtitle sync", "audiodesc": "audio descriptions",
        "haptic": "haptic cues", "slowdown": "slow-down hotkey",
        "keyboard": "keyboard nav", "magnify": "magnifier",
    },
}

ACADEMY_DOMAIN = DnaDomain(
    name="academy",
    key_prefix="ac_",
    group_headers=_ACADEMY_GROUP_HEADERS,
    slot_labels=_ACADEMY_SLOT_LABELS,
    key_group_index=1,
    key_slot_start=2,
    group_order=tuple(_ACADEMY_GROUP_HEADERS),
    blurb="**Academy DNA preferences** (cockpit drift):",
)


# Register on import.
register_domain(BUILDER_DOMAIN)
register_domain(JEEVES_DOMAIN)
register_domain(ACADEMY_DOMAIN)


DOMAINS = {
    "builder": BUILDER_DOMAIN,
    "jeeves":  JEEVES_DOMAIN,
    "academy": ACADEMY_DOMAIN,
}
