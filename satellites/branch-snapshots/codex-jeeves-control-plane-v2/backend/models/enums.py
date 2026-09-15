"""
models/enums.py — All str-Enum types shared across the backend.

Extracted from server.py (Feb 2026 Phase-10). Centralising these enums
breaks the circular import chain that previously blocked
``models/code_runtime.py`` and ``models/compiler_pipeline.py`` from
being safely re-extracted (Pydantic v1 needs enum-default resolution at
class-body time, but server.py imported the model modules BEFORE the
enums were defined inside server.py — chicken-and-egg).

Now every consumer (server.py, models/code_runtime, models/compiler_pipeline,
services/*) imports enums from THIS module, which has no other backend
deps. Boot order is therefore deterministic.

server.py keeps back-compat shims so callers that do
``from server import LanguageType, ExecutionStatus, ...`` continue to
work unchanged.
"""
from __future__ import annotations

from enum import Enum


class LanguageType(str, Enum):
    PYTHON = "python"
    HTML = "html"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    CPP = "cpp"
    C = "c"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    CSHARP = "csharp"
    PHP = "php"
    RUBY = "ruby"
    PERL = "perl"
    LUA = "lua"
    R = "r"
    SCALA = "scala"
    HASKELL = "haskell"
    ELIXIR = "elixir"
    CLOJURE = "clojure"
    DART = "dart"
    ZIG = "zig"
    NIM = "nim"
    CRYSTAL = "crystal"
    JULIA = "julia"
    CSS = "css"
    SCSS = "scss"
    LESS = "less"
    JSON_LANG = "json"
    YAML = "yaml"
    TOML = "toml"
    XML = "xml"
    MARKDOWN = "markdown"
    SQL = "sql"
    GRAPHQL = "graphql"
    SHELL = "shell"
    POWERSHELL = "powershell"
    DOCKERFILE = "dockerfile"
    TERRAFORM = "terraform"
    SOLIDITY = "solidity"
    WASM = "wasm"
    CUSTOM = "custom"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PENDING = "pending"
    RUNNING = "running"
    KILLED = "killed"
    MEMORY_EXCEEDED = "memory_exceeded"
    SECURITY_VIOLATION = "security_violation"
    COMPILATION_ERROR = "compilation_error"
    RUNTIME_ERROR = "runtime_error"
    QUEUED = "queued"


class AIAssistantMode(str, Enum):
    EXPLAIN = "explain"
    DEBUG = "debug"
    OPTIMIZE = "optimize"
    COMPLETE = "complete"
    REFACTOR = "refactor"
    DOCUMENT = "document"
    TEST_GEN = "test_gen"
    SECURITY_AUDIT = "security_audit"
    CONVERT = "convert"
    TEACH = "teach"
    REVIEW = "review"
    ARCHITECTURE = "architecture"


class CodeComplexity(str, Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"
    EXTREME = "extreme"


class SecurityLevel(str, Enum):
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"
    SANDBOX = "sandbox"


class TooltipCategory(str, Enum):
    EDITOR = "editor"
    EXECUTION = "execution"
    AI = "ai"
    FILES = "files"
    SETTINGS = "settings"
    ADVANCED = "advanced"
    LANGUAGE = "language"
    SHORTCUTS = "shortcuts"


class TutorialStep(str, Enum):
    WELCOME = "welcome"
    SELECT_LANGUAGE = "select_language"
    WRITE_CODE = "write_code"
    USE_TEMPLATES = "use_templates"
    RUN_CODE = "run_code"
    VIEW_OUTPUT = "view_output"
    SAVE_FILE = "save_file"
    USE_AI = "use_ai"
    ANALYZE_CODE = "analyze_code"
    ADVANCED_FEATURES = "advanced_features"
    CUSTOM_LANGUAGES = "custom_languages"
    COMPLETE = "complete"


class FeatureFlag(str, Enum):
    TEACHING_MODE = "teaching_mode"
    ADVANCED_PANEL = "advanced_panel"
    AI_SUGGESTIONS = "ai_suggestions"
    CUSTOM_LANGUAGES = "custom_languages"
    EXPANSION_DOCK = "expansion_dock"
    EXPERIMENTAL = "experimental"
    BETA_FEATURES = "beta_features"
    STREAMING_OUTPUT = "streaming_output"
    COLLABORATIVE = "collaborative"
    CLOUD_SYNC = "cloud_sync"


class DockStatus(str, Enum):
    AVAILABLE = "available"
    INSTALLED = "installed"
    PENDING = "pending"
    ERROR = "error"
    DEPRECATED = "deprecated"
    COMING_SOON = "coming_soon"


class HotfixPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ENHANCEMENT = "enhancement"


class SanitizerType(str, Enum):
    MEMORY = "memory"
    THREAD = "thread"
    UNDEFINED = "undefined"
    ADDRESS = "address"
    BEHAVIOR = "behavior"
    LEAK = "leak"


class OptimizerType(str, Enum):
    LTO = "lto"
    PGO = "pgo"
    SIMD = "simd"
    INLINE = "inline"
    LOOP = "loop"
    DEAD_CODE = "dead_code"
    CONSTANT_PROP = "constant_prop"
    TAIL_CALL = "tail_call"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROK = "grok"


class ExpansionCategory(str, Enum):
    LANGUAGE = "language"
    COMPILER = "compiler"
    TOOL = "tool"
    THEME = "theme"
    AI = "ai"
    INTEGRATION = "integration"
    ALGORITHM = "algorithm"


class ExpansionStatus(str, Enum):
    AVAILABLE = "available"
    INSTALLED = "installed"
    INSTALLING = "installing"
    UPDATE_AVAILABLE = "update_available"
    DEPRECATED = "deprecated"


__all__ = [
    "LanguageType", "ExecutionStatus", "AIAssistantMode", "CodeComplexity",
    "SecurityLevel", "TooltipCategory", "TutorialStep", "FeatureFlag",
    "DockStatus", "HotfixPriority", "SanitizerType", "OptimizerType",
    "LLMProvider", "ExpansionCategory", "ExpansionStatus",
]
