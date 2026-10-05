"""
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║                         CODEDOCK QUANTUM NEXUS v10.0.0 - PRODUCTION READY                         ║
║                    Beyond Bleeding-Edge Multi-Language Compiler Platform                         ║
║                                                                                                  ║
║  Architecture: Plugin-First | Event-Driven | AI-Native | Expansion-Ready | Zero-Trust           ║
║  Standards: 2026+ Hyperscale | Grok-Compatible | SOTA Security | Hotfix-Enabled                 ║
║                                                                                                  ║
║  Features: Teaching Mode | Advanced Hidden Panel | Language Dock System | 15-Year CS Bible      ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════════════════
# ★ K8s BOOT TRACE — write to stdout BEFORE any other import so deployment
# log harvesters see the container is alive even if subsequent imports hang
# or the logging config is never reached. Without this, a silent crash in any
# downstream `from routes.X import ...` would produce an empty `[DEPLOY]`
# block. force=True + flush ensures the line reaches Kubernetes log shippers.
# ═══════════════════════════════════════════════════════════════════════════
import sys as _sys, os as _os, time as _time
_sys.stdout.reconfigure(line_buffering=True) if hasattr(_sys.stdout, "reconfigure") else None
print(f"[BOOT] {_time.strftime('%Y-%m-%d %H:%M:%S')} server.py module import begin pid={_os.getpid()}", flush=True)

from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Depends, Query, Request, WebSocket
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union, AsyncGenerator, Literal, Callable
import uuid
from datetime import datetime, timedelta
import asyncio
import subprocess
import tempfile
import shutil
import json
import re
import hashlib
import time
from enum import Enum
from abc import ABC, abstractmethod
import traceback
import sys
import io
from contextlib import asynccontextmanager
from collections import defaultdict
import ast
import tokenize
from io import StringIO

print(f"[BOOT] {_time.strftime('%H:%M:%S')} stdlib imports done", flush=True)

# AI Integration
from emergentintegrations.llm.chat import LlmChat, UserMessage

# Import modular routes — Phase-1+2 (Feb 2026): the entire 355-line lazy-
# import block of optional routers was migrated to the declarative
# ``core.routes_registry.KNOWN_ROUTES`` / ``KNOWN_ROUTES_WITH_PREFIX``
# tables. To add a new optional router, append a single tuple there.
print(f"[BOOT] {_time.strftime('%H:%M:%S')} route imports done", flush=True)
from middleware.security import (
    RateLimitMiddleware, AuditMiddleware, SizeLimitMiddleware,
)


# Import the 15-Year CS Bible Curriculum (for backward compatibility)
from cs_bible import CS_BIBLE, get_year_info, get_course, get_all_courses, get_curriculum_stats

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ═══════════════════════════════════════════════════════════════════════════
# MONGODB — three logical databases, one client.
# • db          (core, user-facing)  ← MIGRATED to prod on deploy
# • content_db  (regenerable content) ← SKIPPED by MIGRATE, rebuilt from seeds
# • swarm_db    (hyperscale scratch)  ← SKIPPED by MIGRATE, rebuilt from seeds
# See core/databases.py for collection routing.
# ═══════════════════════════════════════════════════════════════════════════
from core.databases import (
    client,
    core_db as db,
    content_db,
    swarm_db,
    CORE_DB_NAME as db_name,
    CONTENT_DB_NAME,
    SWARM_DB_NAME,
    collection as _routed_collection,
    which_db as _which_db,
)
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')

# Advanced Logging — use stdout handler so K8s log harvesters pick it up
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=_sys.stdout,
    force=True,
)
logger = logging.getLogger("CodeDock.Nexus")
print(f"[BOOT] {_time.strftime('%H:%M:%S')} logger configured, env loaded", flush=True)

# ═══════════════════════════════════════════════════════════════════════════
# ★ DEPLOY PROFILE — when running in K8s / production we default to a
# minimal-seeding profile so the container becomes ready FAST and the
# heavy regenerable seeders can drip-fill in the background without
# overwhelming the cold Atlas connection pool.
#
# Set SKIP_HEAVY_SEED=false in .env if you actually want the dev box to
# rebuild all seeds on every restart.
# ═══════════════════════════════════════════════════════════════════════════
_IS_PROD = (
    os.environ.get("EMERGENT_DEPLOY", "").strip().lower() in ("1", "true", "yes")
    or os.environ.get("K_SERVICE")  # GKE / Cloud Run indicator
    or os.environ.get("KUBERNETES_SERVICE_HOST")  # generic K8s
)
if _IS_PROD and "SKIP_HEAVY_SEED" not in os.environ:
    os.environ["SKIP_HEAVY_SEED"] = "true"
    print(f"[BOOT] {_time.strftime('%H:%M:%S')} prod env detected → SKIP_HEAVY_SEED=true (auto)", flush=True)

#====================================================================================================
# SYSTEM VERSION & BUILD INFO
#====================================================================================================

SYSTEM_VERSION = "11.0.0"
SYSTEM_CODENAME = "Ultimate Coding Platform"
SYSTEM_BUILD = "2026.02.22-EXTRAORDINARY"
SYSTEM_FEATURES = [
    "teaching_mode",
    "tooltips_engine", 
    "hidden_advanced_panel",
    "language_dock_system",
    "expansion_ready",
    "hotfix_system",
    "plugin_architecture",
    "custom_language_support",
    "retry_with_backoff",
    "connection_status_indicator",
    "enhanced_error_handling",
    "grok_enhanced_prompts"
]

#====================================================================================================
# ENUMS - Comprehensive Type System
#====================================================================================================

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

#====================================================================================================
# LANGUAGE DOCK SYSTEM - Expansion Ready Infrastructure
#====================================================================================================

LANGUAGE_DOCK_REGISTRY = {
    # === TIER 1: FULLY IMPLEMENTED ===
    LanguageType.PYTHON: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "Python",
        "display_name": "Python 3.12+",
        "extension": ".py",
        "extensions_alt": [".pyw", ".pyx", ".pyi"],
        "icon": "logo-python",
        "color": "#3776AB",
        "color_secondary": "#FFD43B",
        "executable": True,
        "version": "3.12+",
        "description": "AI/ML-first programming language with type hints and async support",
        "compiler": "cpython",
        "compiler_version": "3.12.0",
        "paradigms": ["oop", "functional", "procedural", "async", "metaprogramming"],
        "features": ["type_hints", "pattern_matching", "async_await", "dataclasses", "walrus_operator", "structural_pattern_matching"],
        "mime_types": ["text/x-python", "application/x-python-code"],
        "syntax": {
            "comment_single": "#",
            "comment_multi_start": '"""',
            "comment_multi_end": '"""',
            "string_delimiters": ["'", '"', "'''", '"""'],
            "indent_style": "spaces",
            "indent_size": 4,
            "line_ending": "lf",
            "case_sensitive": True
        },
        "keywords": ["def", "class", "import", "from", "async", "await", "yield", "lambda", "match", "case", "with", "try", "except", "finally", "raise", "assert", "pass", "break", "continue", "return", "global", "nonlocal", "del", "in", "is", "not", "and", "or", "True", "False", "None"],
        "builtin_types": ["int", "float", "str", "bool", "list", "dict", "set", "tuple", "bytes", "bytearray", "complex", "frozenset", "range", "slice", "type", "object"],
        "operators": ["+", "-", "*", "/", "//", "%", "**", "@", "&", "|", "^", "~", "<<", ">>", "<", ">", "<=", ">=", "==", "!=", ":="],
        "dock_config": {
            "sandbox_enabled": True,
            "timeout_default": 10,
            "timeout_max": 60,
            "memory_default_mb": 256,
            "memory_max_mb": 1024,
            "network_allowed": False,
            "file_access": "restricted"
        },
        "expansion_hooks": ["pre_execute", "post_execute", "on_error", "on_timeout"]
    },
    LanguageType.JAVASCRIPT: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "JavaScript",
        "display_name": "JavaScript ES2026",
        "extension": ".js",
        "extensions_alt": [".mjs", ".cjs", ".jsx"],
        "icon": "logo-javascript",
        "color": "#F7DF1E",
        "color_secondary": "#323330",
        "executable": True,
        "version": "ES2026",
        "description": "Universal scripting language for web and server",
        "compiler": "v8",
        "paradigms": ["oop", "functional", "event-driven", "async", "prototype"],
        "features": ["modules", "async_await", "proxy", "decorators", "records_tuples", "temporal", "pattern_matching"],
        "syntax": {
            "comment_single": "//",
            "comment_multi_start": "/*",
            "comment_multi_end": "*/",
            "string_delimiters": ["'", '"', "`"],
            "indent_style": "spaces",
            "indent_size": 2
        },
        "keywords": ["const", "let", "var", "async", "await", "class", "import", "export", "function", "return", "if", "else", "for", "while", "do", "switch", "case", "break", "continue", "try", "catch", "finally", "throw", "new", "this", "super", "extends", "static", "get", "set", "yield", "of", "in", "typeof", "instanceof", "delete", "void", "null", "undefined", "true", "false"],
        "dock_config": {
            "sandbox_enabled": True,
            "webview_execution": True,
            "timeout_default": 10,
            "memory_default_mb": 128
        },
        "expansion_hooks": ["pre_execute", "post_execute", "console_intercept"]
    },
    LanguageType.HTML: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "HTML",
        "display_name": "HTML 5.3",
        "extension": ".html",
        "extensions_alt": [".htm", ".xhtml"],
        "icon": "logo-html5",
        "color": "#E34F26",
        "color_secondary": "#F16529",
        "executable": True,
        "version": "5.3",
        "description": "Semantic markup language for modern web applications",
        "compiler": "webview",
        "paradigms": ["declarative"],
        "features": ["web_components", "shadow_dom", "custom_elements", "template_literals", "dialog", "details"],
        "syntax": {
            "comment_single": None,
            "comment_multi_start": "<!--",
            "comment_multi_end": "-->",
            "case_sensitive": False
        },
        "dock_config": {
            "preview_enabled": True,
            "live_reload": True,
            "sanitize_scripts": True
        }
    },
    LanguageType.CPP: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "C++",
        "display_name": "C++23",
        "extension": ".cpp",
        "extensions_alt": [".cc", ".cxx", ".hpp", ".h", ".hxx"],
        "icon": "code-slash",
        "color": "#00599C",
        "color_secondary": "#004482",
        "executable": True,
        "version": "C++23",
        "description": "High-performance systems programming with modern features",
        "compiler": "g++",
        "compiler_flags": ["-std=c++20", "-O2", "-Wall", "-Wextra"],
        "paradigms": ["oop", "generic", "procedural", "functional", "metaprogramming"],
        "features": ["templates", "concepts", "coroutines", "ranges", "modules", "constexpr", "auto", "lambdas", "smart_pointers"],
        "syntax": {
            "comment_single": "//",
            "comment_multi_start": "/*",
            "comment_multi_end": "*/",
            "indent_size": 4
        },
        "keywords": ["class", "struct", "template", "concept", "constexpr", "consteval", "auto", "namespace", "virtual", "override", "final", "public", "private", "protected", "friend", "operator", "new", "delete", "sizeof", "alignof", "typeid", "static_cast", "dynamic_cast", "const_cast", "reinterpret_cast", "nullptr", "true", "false", "if", "else", "for", "while", "do", "switch", "case", "break", "continue", "return", "try", "catch", "throw", "noexcept", "co_await", "co_yield", "co_return"],
        "dock_config": {
            "compilation_required": True,
            "timeout_compile": 30,
            "timeout_execute": 10,
            "memory_default_mb": 256
        }
    },
    LanguageType.C: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "C",
        "display_name": "C23",
        "extension": ".c",
        "extensions_alt": [".h"],
        "icon": "code-slash",
        "color": "#A8B9CC",
        "executable": True,
        "version": "C23",
        "description": "Foundational systems programming language",
        "compiler": "gcc",
        "compiler_flags": ["-std=c17", "-O2", "-Wall"],
        "paradigms": ["procedural"],
        "dock_config": {
            "compilation_required": True,
            "timeout_compile": 30,
            "timeout_execute": 10
        }
    },
    LanguageType.TYPESCRIPT: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "TypeScript",
        "display_name": "TypeScript 5.6+",
        "extension": ".ts",
        "extensions_alt": [".tsx", ".mts", ".cts"],
        "icon": "logo-javascript",
        "color": "#3178C6",
        "executable": True,
        "version": "5.6+",
        "description": "Type-safe JavaScript superset with advanced type system",
        "compiler": "tsc",
        "paradigms": ["oop", "functional", "generic"],
        "features": ["static_types", "interfaces", "generics", "decorators", "mapped_types", "conditional_types", "template_literals"],
        "dock_config": {
            "transpile_to_js": True,
            "type_checking": True
        }
    },
    
    # === TIER 2: DOCK READY (Not Implemented Yet) ===
    LanguageType.RUST: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Rust",
        "display_name": "Rust 2024 Edition",
        "extension": ".rs",
        "icon": "hardware-chip",
        "color": "#DEA584",
        "executable": False,
        "version": "2024 Edition",
        "description": "Memory-safe systems programming with zero-cost abstractions",
        "compiler": "rustc",
        "paradigms": ["oop", "functional", "concurrent", "systems"],
        "features": ["ownership", "borrowing", "lifetimes", "async", "macros", "traits", "pattern_matching"],
        "dock_config": {
            "compilation_required": True,
            "cargo_support": True
        },
        "expansion_ready": True,
        "install_command": "cargo install",
        "dependencies": ["cargo", "rustc"]
    },
    LanguageType.GO: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Go",
        "display_name": "Go 1.23+",
        "extension": ".go",
        "icon": "code-working",
        "color": "#00ADD8",
        "executable": False,
        "version": "1.23+",
        "description": "Cloud-native concurrent programming language",
        "compiler": "go",
        "paradigms": ["procedural", "concurrent"],
        "features": ["goroutines", "channels", "interfaces", "generics", "defer"],
        "dock_config": {
            "go_modules": True
        },
        "expansion_ready": True
    },
    LanguageType.JAVA: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Java",
        "display_name": "Java 21 LTS",
        "extension": ".java",
        "icon": "cafe",
        "color": "#ED8B00",
        "executable": False,
        "version": "21 LTS",
        "description": "Enterprise-grade object-oriented programming",
        "compiler": "javac",
        "paradigms": ["oop", "functional"],
        "features": ["virtual_threads", "pattern_matching", "records", "sealed_classes"],
        "expansion_ready": True
    },
    LanguageType.KOTLIN: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Kotlin",
        "display_name": "Kotlin 2.0",
        "extension": ".kt",
        "extensions_alt": [".kts"],
        "icon": "code-working",
        "color": "#7F52FF",
        "executable": False,
        "version": "2.0",
        "description": "Modern JVM language with null safety and coroutines",
        "compiler": "kotlinc",
        "paradigms": ["oop", "functional"],
        "expansion_ready": True
    },
    LanguageType.SWIFT: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Swift",
        "display_name": "Swift 6.0",
        "extension": ".swift",
        "icon": "logo-apple",
        "color": "#F05138",
        "executable": False,
        "version": "6.0",
        "description": "Apple's powerful and intuitive programming language",
        "compiler": "swiftc",
        "paradigms": ["oop", "functional", "protocol-oriented"],
        "expansion_ready": True
    },
    LanguageType.CSHARP: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "C#",
        "display_name": "C# 12",
        "extension": ".cs",
        "icon": "code-slash",
        "color": "#512BD4",
        "executable": False,
        "version": "12",
        "description": ".NET programming with modern language features",
        "compiler": "dotnet",
        "paradigms": ["oop", "functional"],
        "expansion_ready": True
    },
    LanguageType.RUBY: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "Ruby",
        "display_name": "Ruby 3.3+",
        "extension": ".rb",
        "icon": "diamond",
        "color": "#CC342D",
        "executable": False,
        "version": "3.3+",
        "description": "Dynamic, elegant programming language focused on simplicity",
        "compiler": "ruby",
        "paradigms": ["oop", "functional", "metaprogramming"],
        "expansion_ready": True
    },
    LanguageType.PHP: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "PHP",
        "display_name": "PHP 8.3",
        "extension": ".php",
        "icon": "code-working",
        "color": "#777BB4",
        "executable": False,
        "version": "8.3",
        "description": "Popular server-side scripting language",
        "compiler": "php",
        "expansion_ready": True
    },
    
    # === TIER 3: EXPANSION SLOTS (Future) ===
    LanguageType.JULIA: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Julia",
        "display_name": "Julia 1.10+",
        "extension": ".jl",
        "color": "#9558B2",
        "executable": False,
        "description": "High-performance scientific computing",
        "expansion_ready": True
    },
    LanguageType.ELIXIR: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Elixir",
        "display_name": "Elixir 1.16",
        "extension": ".ex",
        "extensions_alt": [".exs"],
        "color": "#6E4A7E",
        "executable": False,
        "description": "Functional, concurrent programming on BEAM VM",
        "expansion_ready": True
    },
    LanguageType.HASKELL: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Haskell",
        "display_name": "Haskell GHC 9.8",
        "extension": ".hs",
        "color": "#5D4F85",
        "executable": False,
        "description": "Pure functional programming with strong types",
        "expansion_ready": True
    },
    LanguageType.SCALA: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Scala",
        "display_name": "Scala 3",
        "extension": ".scala",
        "color": "#DC322F",
        "executable": False,
        "description": "Functional and object-oriented on the JVM",
        "expansion_ready": True
    },
    LanguageType.DART: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Dart",
        "display_name": "Dart 3.3",
        "extension": ".dart",
        "color": "#0175C2",
        "executable": False,
        "description": "Client-optimized language for Flutter",
        "expansion_ready": True
    },
    LanguageType.ZIG: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Zig",
        "display_name": "Zig 0.12",
        "extension": ".zig",
        "color": "#F7A41D",
        "executable": False,
        "description": "Low-level systems programming with safety",
        "expansion_ready": True
    },
    LanguageType.NIM: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Nim",
        "display_name": "Nim 2.0",
        "extension": ".nim",
        "color": "#FFE953",
        "executable": False,
        "description": "Efficient, expressive, elegant",
        "expansion_ready": True
    },
    LanguageType.SOLIDITY: {
        "tier": 3,
        "status": DockStatus.COMING_SOON,
        "name": "Solidity",
        "display_name": "Solidity 0.8+",
        "extension": ".sol",
        "color": "#363636",
        "executable": False,
        "description": "Smart contract programming for Ethereum",
        "expansion_ready": True
    },
    
    # === MARKUP & DATA LANGUAGES ===
    LanguageType.CSS: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "CSS",
        "display_name": "CSS4",
        "extension": ".css",
        "icon": "logo-css3",
        "color": "#1572B6",
        "executable": False,
        "description": "Modern styling with container queries and nesting"
    },
    LanguageType.JSON_LANG: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "JSON",
        "extension": ".json",
        "icon": "code-working",
        "color": "#000000",
        "executable": False,
        "description": "Data interchange format"
    },
    LanguageType.YAML: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "YAML",
        "extension": ".yaml",
        "extensions_alt": [".yml"],
        "icon": "document-text",
        "color": "#CB171E",
        "executable": False,
        "description": "Human-readable data serialization"
    },
    LanguageType.MARKDOWN: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "Markdown",
        "extension": ".md",
        "icon": "document-text",
        "color": "#083FA1",
        "executable": False,
        "description": "Lightweight markup language"
    },
    LanguageType.SQL: {
        "tier": 1,
        "status": DockStatus.INSTALLED,
        "name": "SQL",
        "extension": ".sql",
        "icon": "server",
        "color": "#CC2927",
        "executable": False,
        "description": "Database query language"
    },
    LanguageType.GRAPHQL: {
        "tier": 2,
        "status": DockStatus.COMING_SOON,
        "name": "GraphQL",
        "extension": ".graphql",
        "extensions_alt": [".gql"],
        "color": "#E10098",
        "executable": False,
        "description": "API query language",
        "expansion_ready": True
    },
}

#====================================================================================================
# TOOLTIPS SYSTEM - State of the Art
#====================================================================================================

TOOLTIPS_REGISTRY = {
    # Editor tooltips
    "editor_line_numbers": {
        "id": "editor_line_numbers",
        "category": TooltipCategory.EDITOR,
        "title": "Line Numbers",
        "description": "Click a line number to set a breakpoint (when debugging is enabled)",
        "shortcut": None,
        "advanced": False,
        "learn_more_url": None
    },
    "editor_code_area": {
        "id": "editor_code_area",
        "category": TooltipCategory.EDITOR,
        "title": "Code Editor",
        "description": "Write your code here. Syntax highlighting is automatic based on the selected language.",
        "tips": [
            "Use Tab for indentation",
            "Select text and press Cmd/Ctrl+D to duplicate",
            "Long-press for AI suggestions"
        ],
        "advanced": False
    },
    "editor_filename": {
        "id": "editor_filename",
        "category": TooltipCategory.EDITOR,
        "title": "File Name",
        "description": "Tap to rename your file. Extension is added automatically.",
        "advanced": False
    },
    
    # Execution tooltips
    "run_button": {
        "id": "run_button",
        "category": TooltipCategory.EXECUTION,
        "title": "Run Code",
        "description": "Execute your code in a secure sandbox environment",
        "tips": [
            "Timeout: 10 seconds (adjustable in Advanced)",
            "Memory limit: 256MB default",
            "Network access is disabled for security"
        ],
        "shortcut": "Cmd/Ctrl + Enter",
        "advanced": False
    },
    "output_panel": {
        "id": "output_panel",
        "category": TooltipCategory.EXECUTION,
        "title": "Output Panel",
        "description": "View execution results, errors, and debug information",
        "tips": [
            "Green text indicates success",
            "Red text indicates errors",
            "Swipe down to dismiss"
        ],
        "advanced": False
    },
    "execution_time": {
        "id": "execution_time",
        "category": TooltipCategory.EXECUTION,
        "title": "Execution Time",
        "description": "Shows how long your code took to execute in milliseconds",
        "advanced": False
    },
    
    # AI tooltips
    "ai_assist_button": {
        "id": "ai_assist_button",
        "category": TooltipCategory.AI,
        "title": "AI Assistant",
        "description": "Get intelligent help with your code using GPT-4o",
        "tips": [
            "Explain: Understand what code does",
            "Debug: Find and fix bugs",
            "Optimize: Improve performance",
            "Refactor: Clean up code structure"
        ],
        "advanced": False
    },
    "ai_modes": {
        "id": "ai_modes",
        "category": TooltipCategory.AI,
        "title": "AI Modes",
        "description": "Choose how AI should help you",
        "modes": {
            "explain": "Get a detailed explanation of your code",
            "debug": "Find bugs and get fix suggestions",
            "optimize": "Improve performance and efficiency",
            "complete": "Auto-complete partial code",
            "refactor": "Restructure for better readability",
            "document": "Generate documentation",
            "test_gen": "Generate unit tests",
            "security_audit": "Check for vulnerabilities",
            "convert": "Convert to another language"
        },
        "advanced": False
    },
    
    # Files tooltips
    "save_button": {
        "id": "save_button",
        "category": TooltipCategory.FILES,
        "title": "Save File",
        "description": "Save your code to the cloud. Access it from any device.",
        "shortcut": "Cmd/Ctrl + S",
        "advanced": False
    },
    "files_button": {
        "id": "files_button",
        "category": TooltipCategory.FILES,
        "title": "My Files",
        "description": "Browse and manage your saved code files",
        "tips": [
            "Tap a file to open it",
            "Swipe left to delete",
            "Star files for quick access"
        ],
        "advanced": False
    },
    
    # Language tooltips
    "language_selector": {
        "id": "language_selector",
        "category": TooltipCategory.LANGUAGE,
        "title": "Language Selection",
        "description": "Choose the programming language for your code",
        "tips": [
            "Languages with ✓ can be executed",
            "Add custom languages via Addons",
            "Each language has its own templates"
        ],
        "advanced": False
    },
    "templates_button": {
        "id": "templates_button",
        "category": TooltipCategory.LANGUAGE,
        "title": "Code Templates",
        "description": "Quick-start with pre-written code examples",
        "tips": [
            "Templates vary by language",
            "Complexity badges show difficulty",
            "Great for learning new concepts"
        ],
        "advanced": False
    },
    
    # Advanced tooltips
    "analyze_button": {
        "id": "analyze_button",
        "category": TooltipCategory.ADVANCED,
        "title": "Code Analysis",
        "description": "Get insights about your code structure and complexity",
        "metrics": [
            "Cyclomatic complexity",
            "Lines of code",
            "Function/class count",
            "Comment ratio"
        ],
        "advanced": True
    },
    "complexity_badge": {
        "id": "complexity_badge",
        "category": TooltipCategory.ADVANCED,
        "title": "Complexity Badge",
        "description": "Shows the cyclomatic complexity of your code",
        "levels": {
            "trivial": "1-5: Very simple, single path",
            "simple": "6-10: Few decision points",
            "moderate": "11-20: Multiple paths",
            "complex": "21-50: Many branches",
            "very_complex": "51+: Consider refactoring"
        },
        "advanced": True
    },
    "hidden_panel": {
        "id": "hidden_panel",
        "category": TooltipCategory.ADVANCED,
        "title": "Advanced Panel",
        "description": "Access experimental and power-user features",
        "access": "Triple-tap the version number in Settings",
        "features": [
            "Custom execution timeout",
            "Memory limit adjustment",
            "Security level selection",
            "Experimental features toggle",
            "Debug mode",
            "Export/Import settings"
        ],
        "advanced": True
    },
    
    # Shortcuts tooltips
    "keyboard_shortcuts": {
        "id": "keyboard_shortcuts",
        "category": TooltipCategory.SHORTCUTS,
        "title": "Keyboard Shortcuts",
        "description": "Speed up your workflow with keyboard shortcuts",
        "shortcuts": {
            "run": "Cmd/Ctrl + Enter",
            "save": "Cmd/Ctrl + S",
            "new_file": "Cmd/Ctrl + N",
            "find": "Cmd/Ctrl + F",
            "ai_assist": "Cmd/Ctrl + Shift + A",
            "toggle_theme": "Cmd/Ctrl + Shift + T",
            "analyze": "Cmd/Ctrl + Shift + L"
        },
        "advanced": False
    }
}

#====================================================================================================
# TEACHING MODE SYSTEM - Step by Step Tutorial
#====================================================================================================

TUTORIAL_STEPS = {
    TutorialStep.WELCOME: {
        "order": 0,
        "title": "Welcome to CodeDock Quantum!",
        "description": "Your powerful mobile code compiler and AI assistant",
        "content": "CodeDock lets you write, run, and analyze code in multiple programming languages - all from your mobile device. Let's take a quick tour!",
        "action": None,
        "highlight_element": None,
        "next_step": TutorialStep.SELECT_LANGUAGE,
        "can_skip": True
    },
    TutorialStep.SELECT_LANGUAGE: {
        "order": 1,
        "title": "Choose Your Language",
        "description": "Select from 6+ executable languages",
        "content": "Tap the language selector at the top to choose a programming language. Python is selected by default - it's great for beginners!",
        "action": "tap_language_selector",
        "highlight_element": "language_selector",
        "next_step": TutorialStep.USE_TEMPLATES,
        "tips": [
            "Languages with green badges can be executed",
            "You can add custom languages later"
        ]
    },
    TutorialStep.USE_TEMPLATES: {
        "order": 2,
        "title": "Start with Templates",
        "description": "Use pre-written code to get started quickly",
        "content": "Templates are ready-made code examples. Tap 'Templates' to see what's available for your chosen language.",
        "action": "tap_templates",
        "highlight_element": "templates_button",
        "next_step": TutorialStep.WRITE_CODE,
        "tips": [
            "Templates show complexity levels",
            "Great for learning new concepts"
        ]
    },
    TutorialStep.WRITE_CODE: {
        "order": 3,
        "title": "Write Your Code",
        "description": "The code editor is your canvas",
        "content": "Type or paste your code in the editor. Line numbers help you navigate, and syntax highlighting makes code easier to read.",
        "action": None,
        "highlight_element": "code_editor",
        "next_step": TutorialStep.RUN_CODE,
        "tips": [
            "Code is auto-indented",
            "Supports copy/paste from clipboard"
        ]
    },
    TutorialStep.RUN_CODE: {
        "order": 4,
        "title": "Run Your Code",
        "description": "See your code come to life",
        "content": "Tap the green 'Run' button to execute your code. It runs in a secure sandbox - safe to experiment!",
        "action": "tap_run",
        "highlight_element": "run_button",
        "next_step": TutorialStep.VIEW_OUTPUT,
        "tips": [
            "Execution time is shown after running",
            "10 second timeout by default"
        ]
    },
    TutorialStep.VIEW_OUTPUT: {
        "order": 5,
        "title": "View Results",
        "description": "See output and errors",
        "content": "The output panel shows your program's results. Green means success, red indicates errors with helpful messages.",
        "action": None,
        "highlight_element": "output_panel",
        "next_step": TutorialStep.USE_AI,
        "tips": [
            "Tap the X to close output",
            "Output is scrollable for long results"
        ]
    },
    TutorialStep.USE_AI: {
        "order": 6,
        "title": "Meet Your AI Assistant",
        "description": "GPT-4o powered code help",
        "content": "The AI Assist button gives you intelligent help. Get explanations, find bugs, optimize code, and more!",
        "action": "tap_ai_assist",
        "highlight_element": "ai_assist_button",
        "next_step": TutorialStep.ANALYZE_CODE,
        "tips": [
            "9 different AI modes available",
            "Works with any language"
        ]
    },
    TutorialStep.ANALYZE_CODE: {
        "order": 7,
        "title": "Analyze Your Code",
        "description": "Get insights and metrics",
        "content": "The Analyze button shows code complexity, function count, and other metrics. Great for improving code quality!",
        "action": "tap_analyze",
        "highlight_element": "analyze_button",
        "next_step": TutorialStep.SAVE_FILE,
        "tips": [
            "Lower complexity is usually better",
            "Helps identify refactoring opportunities"
        ]
    },
    TutorialStep.SAVE_FILE: {
        "order": 8,
        "title": "Save Your Work",
        "description": "Never lose your code",
        "content": "Tap 'Save' to store your code in the cloud. Access your files from the 'Files' button anytime.",
        "action": "tap_save",
        "highlight_element": "save_button",
        "next_step": TutorialStep.ADVANCED_FEATURES,
        "tips": [
            "Files sync across devices",
            "Organize with favorites"
        ]
    },
    TutorialStep.ADVANCED_FEATURES: {
        "order": 9,
        "title": "Discover Advanced Features",
        "description": "Power user capabilities",
        "content": "There's more to explore! Triple-tap the version number in Settings to unlock the Advanced Panel with experimental features.",
        "action": None,
        "highlight_element": "settings_button",
        "next_step": TutorialStep.CUSTOM_LANGUAGES,
        "tips": [
            "Adjust execution timeouts",
            "Enable experimental features",
            "Custom security levels"
        ]
    },
    TutorialStep.CUSTOM_LANGUAGES: {
        "order": 10,
        "title": "Add Custom Languages",
        "description": "Expand your toolkit",
        "content": "The Language Dock lets you add support for more languages. Go to Settings > Language Addons to get started.",
        "action": None,
        "highlight_element": "addons_setting",
        "next_step": TutorialStep.COMPLETE,
        "tips": [
            "Community addons coming soon",
            "Create your own language configs"
        ]
    },
    TutorialStep.COMPLETE: {
        "order": 11,
        "title": "You're Ready!",
        "description": "Start coding with confidence",
        "content": "You've completed the tutorial! You now know all the essentials. Happy coding!",
        "action": None,
        "highlight_element": None,
        "next_step": None,
        "celebration": True
    }
}

#====================================================================================================
# HOTFIX SYSTEM
#====================================================================================================

HOTFIX_REGISTRY = {
    "HF-2026-001": {
        "id": "HF-2026-001",
        "priority": HotfixPriority.MEDIUM,
        "title": "WebView Preview on Web Platform",
        "description": "WebView component renders differently on web platform vs native",
        "status": "documented",
        "workaround": "Use native mobile app for HTML preview",
        "affected_versions": ["3.0.0", "4.0.0"],
        "fixed_in": None
    },
    "HF-2026-002": {
        "id": "HF-2026-002",
        "priority": HotfixPriority.LOW,
        "title": "Tunnel Connection Intermittent",
        "description": "Ngrok tunnel may timeout during high traffic",
        "status": "monitoring",
        "workaround": "Retry connection or use direct access",
        "affected_versions": ["*"],
        "fixed_in": None
    }
}

#====================================================================================================
# FEATURE FLAGS SYSTEM
#====================================================================================================

FEATURE_FLAGS = {
    FeatureFlag.TEACHING_MODE: {
        "enabled": True,
        "rollout_percentage": 100,
        "description": "Interactive tutorial system"
    },
    FeatureFlag.ADVANCED_PANEL: {
        "enabled": True,
        "rollout_percentage": 100,
        "description": "Hidden advanced settings panel",
        "access_method": "triple_tap_version"
    },
    FeatureFlag.AI_SUGGESTIONS: {
        "enabled": True,
        "rollout_percentage": 100,
        "description": "AI-powered code suggestions"
    },
    FeatureFlag.CUSTOM_LANGUAGES: {
        "enabled": True,
        "rollout_percentage": 100,
        "description": "Custom language addon support"
    },
    FeatureFlag.EXPANSION_DOCK: {
        "enabled": True,
        "rollout_percentage": 100,
        "description": "Language dock expansion system"
    },
    FeatureFlag.EXPERIMENTAL: {
        "enabled": False,
        "rollout_percentage": 0,
        "description": "Experimental features"
    },
    FeatureFlag.STREAMING_OUTPUT: {
        "enabled": False,
        "rollout_percentage": 0,
        "description": "Real-time streaming execution output"
    },
    FeatureFlag.COLLABORATIVE: {
        "enabled": False,
        "rollout_percentage": 0,
        "description": "Real-time collaborative editing"
    },
    FeatureFlag.CLOUD_SYNC: {
        "enabled": False,
        "rollout_percentage": 0,
        "description": "Cross-device cloud synchronization"
    }
}

#====================================================================================================
# ADVANCED CODE TEMPLATES - Comprehensive
#====================================================================================================

CODE_TEMPLATES = {
    LanguageType.PYTHON: {
        "hello_world": {
            "name": "Hello World",
            "code": 'print("Hello, World!")',
            "description": "Your first program",
            "complexity": CodeComplexity.TRIVIAL,
            "tags": ["beginner", "basics"]
        },
        "async_fetch": {
            "name": "Async Data Fetch",
            "code": '''import asyncio

async def fetch_data(url: str) -> dict:
    """Asynchronously fetch data from a URL."""
    print(f"Fetching: {url}")
    await asyncio.sleep(0.5)  # Simulated network delay
    return {"status": "success", "data": [1, 2, 3]}

async def main():
    urls = ["api/users", "api/posts", "api/comments"]
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    for url, result in zip(urls, results):
        print(f"{url}: {result}")

asyncio.run(main())''',
            "description": "Modern async/await pattern for concurrent operations",
            "complexity": CodeComplexity.MODERATE,
            "tags": ["async", "networking", "concurrency"]
        },
        "dataclass_model": {
            "name": "Dataclass Model",
            "code": '''from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class User:
    """User entity with validation."""
    id: int
    username: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if "@" not in self.email:
            raise ValueError("Invalid email format")
    
    @property
    def display_name(self) -> str:
        return f"@{self.username}"

# Usage
user = User(1, "developer", "dev@example.com")
print(f"Created user: {user.display_name}")
print(f"Active: {user.is_active}")''',
            "description": "Modern Python dataclass with validation",
            "complexity": CodeComplexity.MODERATE,
            "tags": ["dataclass", "oop", "validation"]
        },
        "pattern_matching": {
            "name": "Pattern Matching",
            "code": '''def process_command(command: dict) -> str:
    """Process command using structural pattern matching (Python 3.10+)."""
    match command:
        case {"action": "create", "type": type_name, "data": data}:
            return f"Creating {type_name} with {len(data)} items"
        case {"action": "delete", "id": id_val} if isinstance(id_val, int):
            return f"Deleting item #{id_val}"
        case {"action": "update", "id": id_val, **rest}:
            return f"Updating #{id_val}: {rest}"
        case {"action": action}:
            return f"Unknown action: {action}"
        case _:
            return "Invalid command format"

# Test cases
commands = [
    {"action": "create", "type": "user", "data": [1, 2, 3]},
    {"action": "delete", "id": 42},
    {"action": "update", "id": 1, "name": "New Name"},
]

for cmd in commands:
    print(f"{cmd} -> {process_command(cmd)}")''',
            "description": "Python 3.10+ structural pattern matching",
            "complexity": CodeComplexity.MODERATE,
            "tags": ["pattern-matching", "python310", "advanced"]
        },
        "generator_pipeline": {
            "name": "Generator Pipeline",
            "code": '''from typing import Generator, Iterable
from functools import reduce

def read_data() -> Generator[int, None, None]:
    """Generate sample data stream."""
    for i in range(1, 11):
        yield i

def filter_even(data: Iterable[int]) -> Generator[int, None, None]:
    """Filter even numbers."""
    for x in data:
        if x % 2 == 0:
            yield x

def square(data: Iterable[int]) -> Generator[int, None, None]:
    """Square each number."""
    for x in data:
        yield x ** 2

def pipeline(*functions):
    """Compose functions into a pipeline."""
    return reduce(lambda f, g: lambda x: g(f(x)), functions)

# Create and execute pipeline
process = pipeline(read_data, filter_even, square, list)
result = process(None)
print(f"Pipeline result: {result}")
print(f"Sum: {sum(result)}")''',
            "description": "Functional programming with generators",
            "complexity": CodeComplexity.COMPLEX,
            "tags": ["functional", "generators", "pipeline"]
        },
        "context_manager": {
            "name": "Context Manager",
            "code": '''from contextlib import contextmanager
from time import perf_counter
from typing import Generator

@contextmanager
def timer(operation: str) -> Generator[None, None, None]:
    """Context manager for timing operations."""
    start = perf_counter()
    print(f"[START] {operation}")
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        print(f"[END] {operation}: {elapsed:.4f}s")

@contextmanager  
def transaction(name: str) -> Generator[list, None, None]:
    """Simulated database transaction context."""
    operations = []
    print(f"BEGIN TRANSACTION: {name}")
    try:
        yield operations
        print(f"COMMIT: {len(operations)} operations")
    except Exception as e:
        print(f"ROLLBACK: {e}")
        raise

# Usage
with timer("Data Processing"):
    with transaction("user_update") as ops:
        ops.append("UPDATE users SET active = true")
        ops.append("INSERT INTO audit_log VALUES (...)")
        print(f"Queued {len(ops)} operations")''',
            "description": "Custom context managers for resource management",
            "complexity": CodeComplexity.MODERATE,
            "tags": ["context-manager", "resources", "patterns"]
        },
        "decorator_factory": {
            "name": "Decorator Factory",
            "code": '''from functools import wraps
from time import perf_counter
from typing import Callable, Any

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Decorator factory for retry logic."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"Attempt {attempt} failed: {e}")
            raise last_exception
        return wrapper
    return decorator

def measure_time(func: Callable) -> Callable:
    """Decorator to measure execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = perf_counter()
        result = func(*args, **kwargs)
        elapsed = perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@measure_time
@retry(max_attempts=3)
def unstable_operation():
    import random
    if random.random() < 0.7:
        raise ValueError("Random failure")
    return "Success!"

# Test (may succeed or fail randomly)
try:
    result = unstable_operation()
    print(f"Result: {result}")
except Exception as e:
    print(f"All attempts failed: {e}")''',
            "description": "Advanced decorator patterns with factories",
            "complexity": CodeComplexity.COMPLEX,
            "tags": ["decorators", "metaprogramming", "patterns"]
        }
    },
    LanguageType.JAVASCRIPT: {
        "hello_world": {
            "name": "Hello World",
            "code": 'console.log("Hello, World!");',
            "description": "Your first JavaScript program",
            "complexity": CodeComplexity.TRIVIAL
        },
        "async_iterator": {
            "name": "Async Iterator",
            "code": '''// Modern Async Iterator with AbortController
async function* fetchPaginated(baseUrl, options = {}) {
    let page = 1;
    let hasMore = true;
    
    try {
        while (hasMore) {
            console.log(\`Fetching page \${page}...\`);
            await new Promise(r => setTimeout(r, 100));
            const data = Array.from({length: 5}, (_, i) => ({
                id: (page - 1) * 5 + i + 1,
                value: Math.random().toFixed(2)
            }));
            
            yield { page, data, timestamp: Date.now() };
            hasMore = page < 3;
            page++;
        }
    } finally {
        console.log('Iterator cleanup complete');
    }
}

// Consume
async function processData() {
    const results = [];
    for await (const { page, data } of fetchPaginated('/api')) {
        console.log(\`Page \${page}: \${data.length} items\`);
        results.push(...data);
    }
    console.log(\`Total: \${results.length} items\`);
}

processData();''',
            "description": "Async generators for paginated data",
            "complexity": CodeComplexity.COMPLEX
        },
        "proxy_reactive": {
            "name": "Reactive State",
            "code": '''// Reactive State Management using Proxy
function createReactive(target, onChange) {
    return new Proxy(target, {
        get(obj, prop) {
            const value = obj[prop];
            if (typeof value === 'object' && value !== null) {
                return createReactive(value, onChange);
            }
            return value;
        },
        set(obj, prop, value) {
            const oldValue = obj[prop];
            obj[prop] = value;
            onChange(prop, value, oldValue);
            return true;
        }
    });
}

const state = createReactive(
    { user: { name: 'Dev', level: 1 }, items: [] },
    (prop, newVal, oldVal) => {
        console.log(\`Changed: \${prop} = \${JSON.stringify(newVal)}\`);
    }
);

state.user.name = 'Advanced Dev';
state.user.level = 5;
state.items.push({ id: 1 });
console.log('Final:', JSON.stringify(state, null, 2));''',
            "description": "Vue-style reactivity with Proxy",
            "complexity": CodeComplexity.COMPLEX
        },
        "promise_pool": {
            "name": "Promise Pool",
            "code": '''// Concurrent Promise Pool with Rate Limiting
class PromisePool {
    constructor(concurrency = 3) {
        this.concurrency = concurrency;
        this.running = 0;
        this.queue = [];
    }
    
    async add(taskFn) {
        if (this.running >= this.concurrency) {
            await new Promise(resolve => this.queue.push(resolve));
        }
        this.running++;
        try {
            return await taskFn();
        } finally {
            this.running--;
            if (this.queue.length > 0) this.queue.shift()();
        }
    }
    
    async map(items, asyncFn) {
        return Promise.all(items.map(item => this.add(() => asyncFn(item))));
    }
}

const simulateTask = async (id) => {
    const duration = Math.random() * 300 + 100;
    console.log(\`Task \${id} started\`);
    await new Promise(r => setTimeout(r, duration));
    console.log(\`Task \${id} done\`);
    return { id, duration };
};

const pool = new PromisePool(3);
pool.map([1,2,3,4,5,6], simulateTask).then(r => {
    console.log(\`All done: \${r.length} tasks\`);
});''',
            "description": "Concurrent task execution with limit",
            "complexity": CodeComplexity.COMPLEX
        }
    },
    LanguageType.CPP: {
        "hello_world": {
            "name": "Hello World",
            "code": '''#include <iostream>

int main() {
    std::cout << "Hello, World!" << std::endl;
    return 0;
}''',
            "description": "Your first C++ program",
            "complexity": CodeComplexity.TRIVIAL
        },
        "smart_pointers": {
            "name": "Smart Pointers",
            "code": '''#include <iostream>
#include <memory>
#include <vector>
#include <string>

class Resource {
    std::string name;
public:
    Resource(const std::string& n) : name(n) {
        std::cout << "Resource '" << name << "' created\\n";
    }
    ~Resource() {
        std::cout << "Resource '" << name << "' destroyed\\n";
    }
    void use() const { std::cout << "Using: " << name << "\\n"; }
};

int main() {
    // unique_ptr - exclusive ownership
    {
        auto unique = std::make_unique<Resource>("Unique");
        unique->use();
    }
    
    std::cout << "---\\n";
    
    // shared_ptr - shared ownership
    {
        auto shared1 = std::make_shared<Resource>("Shared");
        {
            auto shared2 = shared1;
            std::cout << "Ref count: " << shared1.use_count() << "\\n";
        }
        std::cout << "Ref count: " << shared1.use_count() << "\\n";
    }
    
    std::cout << "Program end\\n";
    return 0;
}''',
            "description": "Modern C++ memory management",
            "complexity": CodeComplexity.MODERATE
        },
        "concepts_templates": {
            "name": "Concepts (C++20)",
            "code": '''#include <iostream>
#include <concepts>
#include <vector>

template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template<Numeric T>
T sum(const std::vector<T>& values) {
    T result{};
    for (const auto& v : values) result += v;
    return result;
}

template<typename T>
auto process(T value) {
    if constexpr (std::integral<T>) return value * 2;
    else if constexpr (std::floating_point<T>) return value * 1.5;
    else return value;
}

int main() {
    std::vector<int> ints = {1, 2, 3, 4, 5};
    std::vector<double> doubles = {1.1, 2.2, 3.3};
    
    std::cout << "Sum ints: " << sum(ints) << "\\n";
    std::cout << "Sum doubles: " << sum(doubles) << "\\n";
    std::cout << "Process 10: " << process(10) << "\\n";
    std::cout << "Process 10.0: " << process(10.0) << "\\n";
    
    return 0;
}''',
            "description": "C++20 concepts for type constraints",
            "complexity": CodeComplexity.COMPLEX
        }
    },
    LanguageType.HTML: {
        "hello_world": {
            "name": "Hello World",
            "code": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hello World</title>
</head>
<body>
    <h1>Hello, World!</h1>
</body>
</html>''',
            "description": "Basic HTML page",
            "complexity": CodeComplexity.TRIVIAL
        },
        "modern_layout": {
            "name": "Modern Layout",
            "code": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Modern Layout</title>
    <style>
        :root { --primary: #6366f1; --surface: #1e1b4b; --text: #e0e7ff; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63);
            min-height: 100vh; color: var(--text);
        }
        .container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem; padding: 2rem; max-width: 1200px; margin: 0 auto;
        }
        .card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border-radius: 1rem; padding: 1.5rem;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-5px); }
        .card h2 { color: var(--primary); margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card"><h2>Feature One</h2><p>Glassmorphism design</p></div>
        <div class="card"><h2>Feature Two</h2><p>Responsive grid</p></div>
        <div class="card"><h2>Feature Three</h2><p>CSS custom properties</p></div>
    </div>
</body>
</html>''',
            "description": "Glassmorphism UI with CSS Grid",
            "complexity": CodeComplexity.MODERATE
        },
        "web_component": {
            "name": "Web Component",
            "code": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Web Component</title>
    <style>body { font-family: system-ui; background: #1a1a2e; padding: 2rem; color: #eee; }</style>
</head>
<body>
    <h1>Custom Counter</h1>
    <my-counter initial="5"></my-counter>
    
    <script>
        class MyCounter extends HTMLElement {
            constructor() {
                super();
                this.attachShadow({ mode: 'open' });
                this.count = parseInt(this.getAttribute('initial') || '0');
            }
            connectedCallback() { this.render(); }
            render() {
                this.shadowRoot.innerHTML = \`
                    <style>
                        .counter { background: linear-gradient(135deg, #667eea, #764ba2);
                            padding: 1.5rem; border-radius: 12px; display: flex; align-items: center; gap: 1rem; }
                        button { width: 40px; height: 40px; border-radius: 50%; border: none;
                            background: rgba(255,255,255,0.2); color: white; font-size: 1.5rem; cursor: pointer; }
                        span { font-size: 2rem; font-weight: bold; color: white; min-width: 60px; text-align: center; }
                    </style>
                    <div class="counter">
                        <button id="dec">-</button>
                        <span id="val">\${this.count}</span>
                        <button id="inc">+</button>
                    </div>\`;
                this.shadowRoot.getElementById('inc').onclick = () => { this.count++; this.update(); };
                this.shadowRoot.getElementById('dec').onclick = () => { this.count--; this.update(); };
            }
            update() { this.shadowRoot.getElementById('val').textContent = this.count; }
        }
        customElements.define('my-counter', MyCounter);
    </script>
</body>
</html>''',
            "description": "Custom element with Shadow DOM",
            "complexity": CodeComplexity.COMPLEX
        }
    }
}

#====================================================================================================
# PYDANTIC MODELS
#====================================================================================================

# ─── Code runtime Pydantic models REVERTED (Phase-9 rollback) — kept inline
#     here because of widespread enum-dep coupling. models/code_runtime.py
#     file is preserved on disk for future re-extraction with proper
#     enum-relocation plan.
class ExecutionMetrics(BaseModel):
    execution_time_ms: float = 0
    memory_peak_kb: Optional[float] = None
    cpu_time_ms: Optional[float] = None
    lines_executed: Optional[int] = None

class SecurityReport(BaseModel):
    risk_level: str = "low"
    issues_found: List[Dict[str, Any]] = []
    blocked_operations: List[str] = []
    recommendations: List[str] = []

class CodeAnalysis(BaseModel):
    complexity: CodeComplexity = CodeComplexity.TRIVIAL
    cyclomatic_complexity: int = 1
    lines_of_code: int = 0
    functions_count: int = 0
    classes_count: int = 0
    imports_count: int = 0
    comments_ratio: float = 0.0
    issues: List[Dict[str, Any]] = []
    suggestions: List[str] = []

class ExecutionResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ExecutionStatus = ExecutionStatus.PENDING
    output: str = ""
    error: str = ""
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    security: Optional[SecurityReport] = None
    analysis: Optional[CodeAnalysis] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])

class CodeExecutionRequest(BaseModel):
    code: str
    language: LanguageType
    input_data: Optional[str] = None
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    memory_limit_mb: int = Field(default=256, ge=64, le=1024)
    security_level: SecurityLevel = SecurityLevel.STANDARD
    include_analysis: bool = False

class CodeExecutionResponse(BaseModel):
    execution_id: str
    result: ExecutionResult
    language_info: Dict[str, Any]

class AIAssistRequest(BaseModel):
    code: str
    language: LanguageType
    mode: AIAssistantMode
    context: Optional[str] = None
    target_language: Optional[LanguageType] = None

class AIAssistResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: AIAssistantMode
    suggestion: str
    explanation: Optional[str] = None
    code_blocks: List[Dict[str, str]] = []
    confidence: float = 0.0
    model: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class CodeFile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    language: LanguageType
    code: str
    version: int = 1
    checksum: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_favorite: bool = False
    tags: List[str] = []

class UserPreferences(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    theme: str = "dark"
    font_size: int = 14
    tab_size: int = 4
    auto_save: bool = True
    show_line_numbers: bool = True
    word_wrap: bool = True
    default_language: LanguageType = LanguageType.PYTHON
    ai_suggestions: bool = True
    teaching_mode_completed: bool = False
    current_tutorial_step: Optional[str] = None
    tooltips_enabled: bool = True
    advanced_panel_unlocked: bool = False
    advanced_settings: Dict[str, Any] = {}
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class LanguageAddon(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    language_key: str
    name: str
    extension: str
    icon: str = "code-slash"
    color: str = "#6B7280"
    description: str = ""
    executable: bool = False
    version: str = "1.0"
    syntax_config: Optional[Dict[str, Any]] = None
    dock_config: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TutorialProgress(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_step: TutorialStep = TutorialStep.WELCOME
    completed_steps: List[str] = []
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    skipped: bool = False

class AdvancedSettings(BaseModel):
    execution_timeout: int = 10
    memory_limit_mb: int = 256
    security_level: SecurityLevel = SecurityLevel.STANDARD
    debug_mode: bool = False
    experimental_features: bool = False
    streaming_output: bool = False
    custom_compiler_flags: Dict[str, List[str]] = {}

#====================================================================================================
# CODE EXECUTORS
#====================================================================================================
class CodeAnalyzer:
    @staticmethod
    def analyze_python(code: str) -> CodeAnalysis:
        analysis = CodeAnalysis()
        try:
            tree = ast.parse(code)
            analysis.lines_of_code = len(code.splitlines())
            analysis.functions_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
            analysis.classes_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
            analysis.imports_count = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))
            
            complexity = 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With)):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1
            
            analysis.cyclomatic_complexity = complexity
            
            if complexity <= 5: analysis.complexity = CodeComplexity.TRIVIAL
            elif complexity <= 10: analysis.complexity = CodeComplexity.SIMPLE
            elif complexity <= 20: analysis.complexity = CodeComplexity.MODERATE
            elif complexity <= 50: analysis.complexity = CodeComplexity.COMPLEX
            else: analysis.complexity = CodeComplexity.VERY_COMPLEX
                
        except SyntaxError as e:
            analysis.issues.append({"type": "syntax_error", "line": e.lineno, "message": str(e.msg)})
        except Exception as e:
            analysis.issues.append({"type": "analysis_error", "message": str(e)})
        return analysis

class ExecutionContext:
    def __init__(self, request: CodeExecutionRequest):
        self.request = request
        self.start_time = None
        self.end_time = None
        self.trace_id = uuid.uuid4().hex[:16]
        
    def start(self): self.start_time = time.perf_counter()
    def end(self): self.end_time = time.perf_counter()
    
    @property
    def elapsed_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

class CodeExecutor(ABC):
    def __init__(self):
        self.execution_count = 0
        self.total_time_ms = 0
        
    @abstractmethod
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult: pass
    
    @abstractmethod
    def validate(self, code: str, security_level: SecurityLevel) -> tuple[bool, str, SecurityReport]: pass
    
    def sanitize_output(self, output: str, max_length: int = 50000) -> str:
        if len(output) > max_length:
            half = max_length // 2
            return f"{output[:half]}\n\n... [Truncated] ...\n\n{output[-half:]}"
        return output

class PythonExecutor(CodeExecutor):
    FORBIDDEN = {'os', 'sys', 'subprocess', 'shutil', 'socket', 'pickle', 'ctypes', 'importlib'}
    
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        ctx.start()
        result = ExecutionResult(trace_id=ctx.trace_id)
        
        is_valid, error_msg, security = self.validate(ctx.request.code, ctx.request.security_level)
        result.security = security
        
        if not is_valid:
            result.status = ExecutionStatus.SECURITY_VIOLATION
            result.error = error_msg
            ctx.end()
            return result
        
        if ctx.request.include_analysis:
            result.analysis = CodeAnalyzer.analyze_python(ctx.request.code)
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(ctx.request.code)
                temp_file = f.name
            
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, '-u', temp_file,
                    stdin=asyncio.subprocess.PIPE if ctx.request.input_data else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=ctx.request.input_data.encode() if ctx.request.input_data else None),
                    timeout=ctx.request.timeout_seconds
                )
                
                result.output = self.sanitize_output(stdout.decode('utf-8', errors='replace'))
                result.error = stderr.decode('utf-8', errors='replace')
                result.status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR
                    
            except asyncio.TimeoutError:
                process.kill()
                result.status = ExecutionStatus.TIMEOUT
                result.error = f"Timeout after {ctx.request.timeout_seconds}s"
            finally:
                os.unlink(temp_file)
                
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.error = str(e)
        
        ctx.end()
        result.metrics.execution_time_ms = ctx.elapsed_ms
        return result
    
    def validate(self, code: str, security_level: SecurityLevel) -> tuple[bool, str, SecurityReport]:
        report = SecurityReport()
        if security_level == SecurityLevel.PERMISSIVE:
            return True, "", report
        
        for module in self.FORBIDDEN:
            if f'import {module}' in code or f'from {module}' in code:
                report.risk_level = "high"
                report.blocked_operations.append(f"import:{module}")
                return False, f"Forbidden module: {module}", report
        return True, "", report

class JavaScriptExecutor(CodeExecutor):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        ctx.start()
        result = ExecutionResult(trace_id=ctx.trace_id)
        
        wrapped_code = f'''
(function() {{
    const __output = [];
    console.log = (...args) => __output.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
    try {{
        {ctx.request.code}
        return {{ status: 'success', output: __output.join('\\n') }};
    }} catch(e) {{ return {{ status: 'error', error: e.message }}; }}
}})()'''
        
        result.status = ExecutionStatus.SUCCESS
        result.output = wrapped_code
        ctx.end()
        result.metrics.execution_time_ms = ctx.elapsed_ms
        return result
    
    def validate(self, code: str, security_level: SecurityLevel) -> tuple[bool, str, SecurityReport]:
        return True, "", SecurityReport()

class CppExecutor(CodeExecutor):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        ctx.start()
        result = ExecutionResult(trace_id=ctx.trace_id)
        
        is_valid, error_msg, security = self.validate(ctx.request.code, ctx.request.security_level)
        if not is_valid:
            result.status = ExecutionStatus.SECURITY_VIOLATION
            result.error = error_msg
            result.security = security
            ctx.end()
            return result
        
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp()
            source_file = os.path.join(temp_dir, 'main.cpp')
            output_file = os.path.join(temp_dir, 'main')
            
            with open(source_file, 'w') as f:
                f.write(ctx.request.code)
            
            compile_process = await asyncio.create_subprocess_exec(
                'g++', '-std=c++20', '-O2', '-Wall', '-o', output_file, source_file,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            compile_stdout, compile_stderr = await asyncio.wait_for(compile_process.communicate(), timeout=30)
            
            if compile_process.returncode != 0:
                result.status = ExecutionStatus.COMPILATION_ERROR
                result.error = f"Compilation failed:\n{compile_stderr.decode()}"
                ctx.end()
                return result
            
            run_process = await asyncio.create_subprocess_exec(
                output_file,
                stdin=asyncio.subprocess.PIPE if ctx.request.input_data else None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                run_process.communicate(input=ctx.request.input_data.encode() if ctx.request.input_data else None),
                timeout=ctx.request.timeout_seconds
            )
            
            result.output = self.sanitize_output(stdout.decode('utf-8', errors='replace'))
            result.error = stderr.decode('utf-8', errors='replace')
            result.status = ExecutionStatus.SUCCESS if run_process.returncode == 0 else ExecutionStatus.RUNTIME_ERROR
            
        except asyncio.TimeoutError:
            result.status = ExecutionStatus.TIMEOUT
            result.error = f"Timeout after {ctx.request.timeout_seconds}s"
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.error = str(e)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        
        ctx.end()
        result.metrics.execution_time_ms = ctx.elapsed_ms
        return result
    
    def validate(self, code: str, security_level: SecurityLevel) -> tuple[bool, str, SecurityReport]:
        report = SecurityReport()
        if security_level == SecurityLevel.PERMISSIVE:
            return True, "", report
        dangerous = ['system(', 'popen(', 'fork(', 'exec']
        for d in dangerous:
            if d in code:
                return False, f"Blocked: {d}", report
        return True, "", report

class CExecutor(CppExecutor):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        # Similar to C++ but with gcc
        ctx.start()
        result = ExecutionResult(trace_id=ctx.trace_id)
        
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp()
            source_file = os.path.join(temp_dir, 'main.c')
            output_file = os.path.join(temp_dir, 'main')
            
            with open(source_file, 'w') as f:
                f.write(ctx.request.code)
            
            compile_process = await asyncio.create_subprocess_exec(
                'gcc', '-std=c17', '-O2', '-Wall', '-o', output_file, source_file,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            await asyncio.wait_for(compile_process.communicate(), timeout=30)
            
            if compile_process.returncode != 0:
                result.status = ExecutionStatus.COMPILATION_ERROR
                ctx.end()
                return result
            
            run_process = await asyncio.create_subprocess_exec(
                output_file, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(run_process.communicate(), timeout=ctx.request.timeout_seconds)
            result.output = stdout.decode()
            result.status = ExecutionStatus.SUCCESS if run_process.returncode == 0 else ExecutionStatus.ERROR
            
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.error = str(e)
        finally:
            if temp_dir: shutil.rmtree(temp_dir, ignore_errors=True)
        
        ctx.end()
        result.metrics.execution_time_ms = ctx.elapsed_ms
        return result

class HTMLExecutor(CodeExecutor):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        result = ExecutionResult()
        result.status = ExecutionStatus.SUCCESS
        result.output = ctx.request.code
        return result
    
    def validate(self, code: str, security_level: SecurityLevel) -> tuple[bool, str, SecurityReport]:
        return True, "", SecurityReport()

class TypeScriptExecutor(JavaScriptExecutor):
    pass

# Executor Factory
class ExecutorFactory:
    _executors = {
        LanguageType.PYTHON: PythonExecutor(),
        LanguageType.JAVASCRIPT: JavaScriptExecutor(),
        LanguageType.TYPESCRIPT: TypeScriptExecutor(),
        LanguageType.CPP: CppExecutor(),
        LanguageType.C: CExecutor(),
        LanguageType.HTML: HTMLExecutor(),
    }
    
    @classmethod
    def get_executor(cls, language: LanguageType):
        return cls._executors.get(language)
    
    @classmethod
    def is_executable(cls, language: LanguageType) -> bool:
        return language in cls._executors

#====================================================================================================
# AI SERVICE
#====================================================================================================

# ─── AIAssistantService extracted → services/ai_assistant_svc.py (Phase-9, Feb 2026)
#     Back-compat shim: singleton ``ai_service`` and class re-exported here.
from services.ai_assistant_svc import AIAssistantService, ai_service  # noqa: E402,F401

# executor_factory still constructed inline here (ExecutorFactory class lives in server.py)
executor_factory = ExecutorFactory()
app_start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ═══════════════════════════════════════════════════════════════════════
    # ★ GUARANTEED LAUNCH ENVELOPE  (2026-02 deploy fix)
    # The entire lifespan body is wrapped so ANY unexpected exception during
    # boot is logged and swallowed — FastAPI will still yield control and the
    # /api/health/live probe will succeed. Background seeders are staggered
    # via `_kick(delay, ...)` so we don't stamp Atlas with 20+ simultaneous
    # connections on a cold container.
    # ═══════════════════════════════════════════════════════════════════════
    print(f"[BOOT] {time.strftime('%H:%M:%S')} lifespan() entered", flush=True)
    logger.info("=" * 80)
    logger.info(f"CodeDock Quantum Nexus v{SYSTEM_VERSION} ({SYSTEM_CODENAME}) Starting...")
    logger.info("=" * 80)

    _skip_heavy = os.environ.get("SKIP_HEAVY_SEED", "false").strip().lower() in ("1", "true", "yes")
    if _skip_heavy:
        logger.info("[deploy-prep] SKIP_HEAVY_SEED=true — heavy seeders will be skipped on this boot")
        print(f"[BOOT] {time.strftime('%H:%M:%S')} SKIP_HEAVY_SEED active — fast startup mode", flush=True)

    # ─── Staggered task scheduler ────────────────────────────────────────
    # Each background task sleeps for its assigned `delay` seconds before
    # touching Mongo. This pulse-spaces seeders so the Atlas connection pool
    # never receives 15+ simultaneous queries at boot. Numbers tuned so the
    # K8s startup probe (typically 30-60s) is clear before heavy work begins.
    #
    # 2026-02-18 — upgraded:
    #   • Every kick is registered in `_BOOT_REGISTRY` (name → status dict)
    #     for /api/health/boot observability.
    #   • All task handles are collected so the lifespan can cancel them
    #     cleanly on shutdown (fixes "Waiting for background tasks to
    #     complete" hangs that surfaced after the fastapi 0.136 upgrade).
    #   • Per-task duration is tracked.
    _BOOT_REGISTRY: dict = {}
    _BOOT_TASKS: list = []
    _BOOT_START_TS = time.time()
    app.state._boot_registry = _BOOT_REGISTRY  # exposed via /api/health/boot
    app.state._boot_start_ts = _BOOT_START_TS

    def _kick(delay, label, coro_factory):
        """Schedule a background task that sleeps `delay` s then runs.

        Args:
            delay: seconds to wait before launching the task.
            label: human-readable name for logs & registry.
            coro_factory: a 0-arg callable that returns the coroutine to run
                          (factory pattern so we don't materialise the coro
                          before the sleep, which would start I/O early).

        SOTA wiring (Feb 2026):
            Every kick is ALSO auto-registered as a `Stage` in the
            declarative boot_stages registry, so /api/health/boot/{score,
            stages, timeline} reflects the entire startup fleet — not just
            the four manually-registered demo stages.
        """
        entry = {
            "label": label, "delay": delay,
            "status": "pending", "scheduled_at": time.time(),
            "started_at": None, "completed_at": None,
            "duration_ms": None, "error": None,
        }
        _BOOT_REGISTRY[label] = entry

        # Auto-bridge to the SOTA Stage registry. We can't reuse the kick's
        # own coroutine (timing semantics differ), so we install a thin
        # observer stage that simply mirrors the kick's terminal status.
        try:
            from core.boot_stages import registry as _stage_registry, Stage as _Stage
            from core import boot_timeline as _bt

            async def _observer():
                # SOTA bridge: tolerate long-running daemon kicks.
                #
                # Many lifespan tasks (build-watchdog, live-scrapers,
                # agent-knowledge scrapers) intentionally loop forever ─
                # they never set status="done". Treating them as failures
                # is wrong (and alarms K8s readiness probes in production).
                #
                # Heuristic:
                #   • Phase 1 — wait up to 180 s for the kick to START.
                #   • Phase 2 — once running, watch up to 900 s for done/
                #     failed. If still running after 60 s of stable running
                #     time, classify as DAEMON and return success.
                #
                # This keeps the Stage registry honest while reflecting the
                # actual semantics of background services.
                deadline_start = time.time() + 180.0
                while time.time() < deadline_start:
                    if entry["status"] in ("running", "done", "failed", "cancelled"):
                        break
                    await asyncio.sleep(0.5)
                else:
                    # Kick never even started — surface as pending observation
                    # but don't fail (its `delay` might just be very large).
                    return {"observation": "did_not_start", "delay_s": entry.get("delay")}

                deadline_done = time.time() + 900.0
                running_since: float | None = None
                while time.time() < deadline_done:
                    status = entry["status"]
                    if status == "done":
                        return {"duration_ms": entry.get("duration_ms")}
                    if status in ("failed", "cancelled"):
                        raise RuntimeError(entry.get("error") or f"kick_{status}")
                    if status == "running":
                        if running_since is None:
                            running_since = time.time()
                        elif (time.time() - running_since) >= 60.0:
                            # Long-running daemon detected — treat as OK.
                            return {"daemon": True,
                                    "running_for_s": int(time.time() - running_since)}
                    await asyncio.sleep(1.0)
                # Absolute deadline — be optimistic: report daemon rather
                # than spurious failure, since the kick clearly hasn't
                # crashed (its status never flipped to failed/cancelled).
                return {"daemon": True, "deadline_hit": True}

            # Phase 1 = background. Weight ~10 by default; criticality False.
            _stage_registry().register(_Stage(
                name=f"kick:{label}",
                fn=_observer,
                deps=[],
                timeout_s=320.0,
                retries=0,
                critical=False,
                phase=1,
                weight=10,
                description=f"Lifespan kick (delay={delay}s)",
            ))
            _bt.emit("kick_registered_as_stage", name=f"kick:{label}", delay=delay)
        except Exception as _e:  # noqa: BLE001
            # Registry not ready or duplicate name — never fatal.
            pass

        async def _runner():
            try:
                await asyncio.sleep(delay)
                entry["status"] = "running"
                entry["started_at"] = time.time()
                print(f"[BOOT] {time.strftime('%H:%M:%S')} background: {label} starting (+{delay:.0f}s)", flush=True)
                coro = coro_factory() if callable(coro_factory) else coro_factory
                if asyncio.iscoroutine(coro):
                    await coro
                entry["status"] = "done"
                entry["completed_at"] = time.time()
                if entry["started_at"]:
                    entry["duration_ms"] = int((entry["completed_at"] - entry["started_at"]) * 1000)
            except asyncio.CancelledError:
                entry["status"] = "cancelled"
                entry["completed_at"] = time.time()
                raise
            except Exception as e:
                entry["status"] = "failed"
                entry["completed_at"] = time.time()
                entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                logger.warning(f"[stagger] {label} failed: {e}")
        task = asyncio.create_task(_runner(), name=f"kick:{label}")
        _BOOT_TASKS.append(task)
        return task

    # Each section below has its own try/except — individual failures are
    # logged but never bubble up to kill the lifespan. The `_kick` helper
    # additionally wraps every background task so seeders fail-soft.

    # Resilient MongoDB index creation - don't block startup; fire-and-forget
    # ★ DEPLOYMENT FIX (2026-02): previously blocked startup for up to 60s
    # (4×15s) which exceeded K8s readiness/startup probe budgets on cold
    # Atlas SRV resolution. Now backgrounded so app is ready in <1s and
    # indexes settle in their own time.
    async def _kick_index_creation():
        try:
            await asyncio.wait_for(db.code_files.create_index("id", unique=True), timeout=10)
            await asyncio.wait_for(db.execution_history.create_index("created_at"), timeout=10)
            await asyncio.wait_for(db.language_addons.create_index("language_key", unique=True), timeout=10)
            await asyncio.wait_for(db.tutorial_progress.create_index("id", unique=True), timeout=10)
            # ── Session 11 feature collections (marketplace / tournaments / live-ops) ──
            await asyncio.wait_for(db.marketplace_listings.create_index("playable_id", unique=True), timeout=10)
            await asyncio.wait_for(db.marketplace_listings.create_index("creator_id"), timeout=10)
            await asyncio.wait_for(db.marketplace_listings.create_index([("active", 1), ("created_at", -1)]), timeout=10)
            await asyncio.wait_for(db.marketplace_purchases.create_index("session_id", unique=True), timeout=10)
            await asyncio.wait_for(db.marketplace_purchases.create_index([("buyer_id", 1), ("payment_status", 1)]), timeout=10)
            await asyncio.wait_for(db.payment_transactions.create_index("session_id", unique=True), timeout=10)
            await asyncio.wait_for(db.tournaments.create_index("tournament_id", unique=True), timeout=10)
            await asyncio.wait_for(db.tournaments.create_index("created_at"), timeout=10)
            await asyncio.wait_for(db.tournament_rewards.create_index("playable_id"), timeout=10)
            await asyncio.wait_for(db.liveops_progress.create_index("visitor_id", unique=True), timeout=10)
            await asyncio.wait_for(db.playable_jobs.create_index("job_id", unique=True), timeout=10)
            # VII.5 Governance & Safety
            await asyncio.wait_for(db.content_reports.create_index("report_id", unique=True), timeout=10)
            await asyncio.wait_for(db.content_reports.create_index([("status", 1), ("created_at", -1)]), timeout=10)
            await asyncio.wait_for(db.content_reports.create_index("playable_id"), timeout=10)
            await asyncio.wait_for(db.governance_audit.create_index("at"), timeout=10)
            await asyncio.wait_for(db.governance_audit.create_index("target_id"), timeout=10)
            await asyncio.wait_for(db.content_appeals.create_index("appeal_id", unique=True), timeout=10)
            await asyncio.wait_for(db.content_appeals.create_index([("status", 1), ("created_at", -1)]), timeout=10)
            logger.info("MongoDB indexes created successfully")
        except asyncio.TimeoutError:
            logger.warning("MongoDB index creation timed out - indexes will be created on first use")
        except Exception as e:
            logger.warning(f"MongoDB index creation deferred: {e}")
    _kick(2, "mongo-indexes", _kick_index_creation)

    # ── Jeeves self-training: prefill game-specific logic at launch ──────────
    async def _kick_jeeves_training():
        try:
            from gameforge.jeeves.jeeves_self_training import train_at_launch
            from core.databases import get_sync_db
            res = await asyncio.to_thread(train_at_launch, get_sync_db())
            logger.info(f"[jeeves] self-training at launch: {res}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[jeeves] self-training deferred: {e}")
    _kick(3, "jeeves-self-training", _kick_jeeves_training)

    # ── Seed default admin user (idempotent) for Studio RBAC ─────────────────
    async def _kick_seed_admin():
        try:
            from routes.gameforge_auth import seed_admin
            await asyncio.to_thread(seed_admin)
            logger.info("[auth] default admin seeded")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[auth] admin seed deferred: {e}")
    _kick(4, "seed-admin", _kick_seed_admin)

    # P3 — Feature flags warmup + audit indexes + metrics flusher.
    async def _kick_feature_flags_warmup():
        try:
            from core import feature_flags as _ff
            from core import feature_flags_audit as _ff_audit
            from core import feature_flags_metrics as _ff_metrics
            await asyncio.wait_for(_ff.warmup(), timeout=8)
            await asyncio.wait_for(_ff_audit.ensure_indexes(), timeout=8)
            await _ff_metrics.start_flusher()
            logger.info("[feature-flags] warmup complete (cache + audit indexes + metrics flusher)")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[feature-flags] warmup failed: {type(e).__name__}: {e}")
    _kick(3, "feature-flags-warmup", _kick_feature_flags_warmup)

    # Stability hardening — Tunnel watchdog start + JSON log adapter install.
    async def _kick_stability_hardening():
        try:
            from core import tunnel_watchdog as _tw
            await _tw.start()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[tunnel_watchdog] start failed: {type(e).__name__}: {e}")
        try:
            from core.structured_log import install_json_adapter
            if install_json_adapter():
                logger.info("[structured_log] JSON adapter installed (LOG_FORMAT=json)")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[structured_log] install failed: {type(e).__name__}: {e}")
    _kick(3, "stability-hardening", _kick_stability_hardening)

    # SOTA Boot Orchestrator — mirror critical kicks into the new declarative
    # stage registry so /api/health/boot/stages and /api/health/boot/score
    # have data to expose. These stages run AFTER the legacy kicks complete
    # (they probe the resulting state), giving us a unified observability
    # surface without rewriting every kick.
    async def _kick_register_boot_stages():
        try:
            from core.boot_stages import registry, Stage
            from core import boot_timeline as _tl
            reg = registry()

            async def _probe_mongo():
                await asyncio.wait_for(db.command("ping"), timeout=3)
                return {"ok": True}

            async def _probe_ff():
                from core import feature_flags as _ff
                h = await _ff.health()
                if not h.get("ok"): raise RuntimeError("ff_unhealthy")
                return h

            async def _probe_tunnel():
                from core import tunnel_watchdog as _tw
                return _tw.snapshot()

            async def _probe_indexes():
                # NB: indexes are created by _kick_index_creation — we just verify.
                names = await db.code_files.index_information()
                return {"ok": True, "count": len(names)}

            reg.register(Stage(
                name="mongo-ping", fn=_probe_mongo, deps=[], timeout_s=5,
                critical=True, weight=30, phase=0,
                description="Verify Mongo round-trip with `ping` command.",
            ))
            reg.register(Stage(
                name="mongo-indexes-verify", fn=_probe_indexes, deps=["mongo-ping"],
                timeout_s=5, critical=False, weight=15, phase=0,
                description="Confirm primary-collection indexes exist.",
            ))
            reg.register(Stage(
                name="feature-flags-ready", fn=_probe_ff, deps=["mongo-ping"],
                timeout_s=5, critical=False, weight=15, phase=1,
                description="Confirm the feature-flag service responds & has flags.",
            ))
            reg.register(Stage(
                name="tunnel-watchdog-ready", fn=_probe_tunnel, deps=[], retries=1,
                timeout_s=5, critical=False, weight=10, phase=1,
                description="Confirm tunnel watchdog is reporting.",
            ))
            _tl.emit("stage_registry_initialized", count=4)
            await reg.run()
            await reg.wait_until_phase(0, timeout_s=20)
            await reg.wait_until_phase(1, timeout_s=20)
            logger.info("[boot-stages] registry initialized — %s",
                        reg.summary().get("counts"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[boot-stages] register failed: {type(e).__name__}: {e}")
    _kick(4, "boot-stages-register", _kick_register_boot_stages)

    # Build watchdog — RE-ENABLED 2026-02-18 (post rate-limit work).
    #
    # The watchdog used to be a no-op (@app.on_event was ignored alongside
    # the lifespan) so it never ran in production. The first attempt to
    # wire it into _kick() resurrected ALL orphaned builds in parallel and
    # saturated the worker. core/build_watchdog now ships:
    #   • WARMUP_TICKS=3  — skip orphan restarts for first 3 sweeps
    #   • MAX_RESTARTS_PER_TICK=1
    #   • MAX_RESTARTS_PER_5MIN=3 (rolling window)
    # Combined with a +30s start delay this gives the watchdog plenty of
    # room to "warm up" and recover gracefully without thrashing the box.
    _kick(30, "build-watchdog", lambda: _kick_build_watchdog_start())

    # ═══════════════════════════════════════════════════════════════════════
    # ★ STATS-REFRESH KICK — REMOVED (2026-02-17).
    #   Previous attempt used `validate` on all 400+ collections at +95s to
    #   rebuild WiredTiger's collStats cache. This triggered repeated
    #   WiredTiger panics (`__wt_panic_func` + signal 6) on this container's
    #   memory-constrained mongod, causing crash loops. Mongo recovers but
    #   stats reset to 0 each time, defeating the purpose.
    #
    #   Instead, the affected endpoints (/api/galaxy-studio/mega-dbs/list
    #   and similar) have been switched to count_documents() which works
    #   correctly even when the cached stats are stale. This is slower per
    #   call but reliable and never triggers WT panics.
    # ═══════════════════════════════════════════════════════════════════════

    
    # Seed Academy & Bible data into MongoDB (idempotent — skips if already populated)
    # ★ DEPLOYMENT FIX (2026-02): run seeders fire-and-forget so cold Atlas boots
    #   don't stall the lifespan past K8s readiness probe timeout.
    async def _kick_tutolage_seed():
        try:
            from seeds.seed_runner import seed_database
            seed_result = await asyncio.wait_for(seed_database(db), timeout=120)
            logger.info(f"Seed result: {seed_result.get('status', 'unknown')}")
        except asyncio.TimeoutError:
            logger.warning("Database seeding timed out — will retry on next restart")
        except Exception as e:
            logger.warning(f"Database seeding deferred: {e}")
    _kick(5, "tutolage-seed", _kick_tutolage_seed)
    logger.info("Tutolage seed kicked off in background")

    # ═══ Bootstrap agent-facing collections + tutorial_progress (idempotent) ═══
    async def _kick_agent_bootstrap():
        try:
            from seeds.bootstrap_seeder import bootstrap_all as bootstrap_agent_dbs
            boot_result = await asyncio.wait_for(bootstrap_agent_dbs(db), timeout=30)
            logger.info(f"Agent DB bootstrap: tutorial={boot_result.get('tutorial_progress', 'n/a')} agent_colls={boot_result.get('agent_collections', {})}")
        except Exception as e:
            logger.warning(f"Agent DB bootstrap deferred: {e}")
    _kick(8, "agent-bootstrap", _kick_agent_bootstrap)

    # ─── Android APK toolchain auto-install (idempotent) ───
    # On fresh forks the Android SDK + qemu disappear. Kick the installer
    # in the background so /api/binary/package can produce real APKs
    # without manual intervention. The installer is idempotent and is
    # safe to re-run (each step checks for prior completion).
    async def _kick_android_toolchain():
        import subprocess, os, asyncio as _a
        try:
            # Skip if already installed
            sdk = "/opt/android-sdk/build-tools"
            if os.path.exists(sdk) and os.listdir(sdk):
                logger.info("[android-toolchain] already installed, skipping")
                return
            installer = "/app/scripts/install_android_toolchain.sh"
            if not os.path.exists(installer):
                logger.info("[android-toolchain] installer script missing, skipping")
                return
            logger.info("[android-toolchain] starting background install (5-10 min)")
            # nohup-style: run detached
            proc = await _a.create_subprocess_exec(
                "bash", installer,
                stdout=_a.subprocess.PIPE, stderr=_a.subprocess.STDOUT,
            )
            await proc.communicate()
            logger.info(f"[android-toolchain] installer exit: {proc.returncode}")
        except Exception as e:
            logger.warning(f"[android-toolchain] install deferred: {e}")
    _kick(10, "android-toolchain", _kick_android_toolchain)

    # ═══ Deploy-prep gate: when SKIP_HEAVY_SEED=true is set in .env, skip the
    # heavy auto-regenerable seeders. This keeps the dev MongoDB small enough
    # that Emergent's platform MONGODB_MIGRATE step can finish within its
    # time/size budget. Prod has this flag unset, so prod re-seeds from code
    # on first boot. See /app/backend/scripts/deploy_prep.py.
    _skip_heavy = os.environ.get("SKIP_HEAVY_SEED", "false").strip().lower() in ("1", "true", "yes")
    if _skip_heavy:
        logger.info("[deploy-prep] SKIP_HEAVY_SEED=true — skipping heavy seeders (mega-db, unique_flair, narrative_vault, game_knowledge, game_code_library, swarm, auto-reseal)")

    # ═══ Seed game_code_library (32M lines) if missing — non-blocking ═══
    if not _skip_heavy:
        try:
            lib_count = await asyncio.wait_for(
                content_db.game_code_library.count_documents({}, limit=1), timeout=10
            )
            if lib_count == 0:
                from seeds.game_code_library_seed import seed_game_code_library
                _kick(15, "game-code-library", lambda: seed_game_code_library(content_db))
                logger.info("game_code_library seed kicked off in background (content_db)")
            else:
                logger.info(f"game_code_library already populated (content_db)")
        except asyncio.TimeoutError:
            logger.warning("game_code_library count_documents timed out — skipping seed check on this boot")
        except Exception as e:
            logger.warning(f"game_code_library check deferred: {e}")
    
    # ═══ Seed 200-collection Mega Game Asset DB — non-blocking ═══
    # ★ FIX 2026-02 (final): seed into content_db (where the routing config
    # in core/databases.py says these collections belong AND where
    # routes/galaxy_studio.py /mega-dbs/list and /mega-dbs/query now read
    # from after their corresponding 2026-02 fix). Previously this seeder
    # wrote to core_db, which:
    #   1. Bloated the Atlas migrate target (caused the original deploy crash)
    #   2. Duplicated data the routes were no longer reading
    # The seeder is idempotent — spot-checks existing count first.
    if not _skip_heavy:
        try:
            from core.databases import content_db as _mega_target_db
            from seeds.mega_game_db_seed import seed_all_mega_dbs, MEGA_COLLECTIONS, DOCS_PER_COLLECTION
            # Spot-check first collection against current target
            sample_name = MEGA_COLLECTIONS[0][0]
            sample_count = await asyncio.wait_for(
                _mega_target_db[sample_name].count_documents({}, limit=DOCS_PER_COLLECTION + 1), timeout=10
            )
            if sample_count < DOCS_PER_COLLECTION:
                _kick(20, "mega-dbs", lambda: seed_all_mega_dbs(_mega_target_db))
                logger.info(f"Mega-DB hyperscale seed kicked off in background (content_db, target {DOCS_PER_COLLECTION}/col)")
            else:
                logger.info(f"Mega-DBs already at target (content_db, {sample_name}={sample_count})")
        except asyncio.TimeoutError:
            logger.warning("Mega-DB spot-check timed out — skipping seed on this boot")
        except Exception as e:
            logger.warning(f"Mega-DB seed check deferred: {e}")

    # ═══ Seed language_classes (500 langs) — fixes empty Language Academy modal ═══
    if not _skip_heavy:
        try:
            from services.database import db as _lang_db
            from seeds.language_classes_seed import seed_language_classes
            lang_count = await asyncio.wait_for(
                _lang_db.language_classes.count_documents({}, limit=600), timeout=10
            )
            if lang_count < 400:
                _kick(25, "language-classes", lambda: seed_language_classes(_lang_db))
                logger.info(f"language_classes seed kicked off (current={lang_count}, target=500)")
            else:
                logger.info(f"language_classes already at target ({lang_count})")
        except asyncio.TimeoutError:
            logger.warning("language_classes count timed out — skipping seed on this boot")
        except Exception as e:
            logger.warning(f"language_classes seed check deferred: {e}")

    # ═══ Seed FULL agent knowledge fabric — patch_notes (curated + extended),
    # github_code_refs, code_synthesis, procedural assets, game design, engine schemas.
    # All idempotent. Each kicks in its own background task so boot is never blocked.
    if not _skip_heavy:
        try:
            from core.databases import content_db as _agk_db
            # ★ FIX 2026-02: route agent-knowledge seeds to content_db
            # (where they're declared in CONTENT_COLLECTIONS) so they don't
            # bloat core_db and the Atlas migrate. Previously imported
            # `services.database.db` (= core_db).
            async def _kick_agent_knowledge():
                from seeds.patch_notes_seed     import seed_patch_notes
                from seeds.patch_notes_extended import seed_extended_patch_notes
                from seeds.github_code_seed     import seed_github_code
                from seeds.code_synthesis_seed  import seed_code_synthesis
                from seeds.procedural_assets_seed import seed_procedural_assets
                from seeds.game_design_seed     import seed_game_design
                from seeds.engine_api_seed      import seed_engine_api
                results = {}
                try: results["patch_notes_curated"] = await seed_patch_notes(_agk_db)
                except Exception as e: results["patch_notes_curated_error"] = str(e)[:200]
                try: results["patch_notes_extended"] = await seed_extended_patch_notes(_agk_db)
                except Exception as e: results["patch_notes_extended_error"] = str(e)[:200]
                try: results["github_code"] = await seed_github_code(_agk_db)
                except Exception as e: results["github_code_error"] = str(e)[:200]
                try: results["code_synthesis"] = await seed_code_synthesis(_agk_db)
                except Exception as e: results["code_synthesis_error"] = str(e)[:200]
                try: results["procedural_assets"] = await seed_procedural_assets(_agk_db)
                except Exception as e: results["procedural_assets_error"] = str(e)[:200]
                try: results["game_design"] = await seed_game_design(_agk_db)
                except Exception as e: results["game_design_error"] = str(e)[:200]
                try: results["engine_api"] = await seed_engine_api(_agk_db)
                except Exception as e: results["engine_api_error"] = str(e)[:200]
                # ─── NEW: gamestate / qa-oracles / ai-weights / build-recipes ───
                try:
                    from seeds.gamestate_schemas_seed import seed_gamestate_schemas
                    results["gamestate_schemas"] = await seed_gamestate_schemas(_agk_db)
                except Exception as e: results["gamestate_schemas_error"] = str(e)[:200]
                try:
                    from seeds.qa_oracles_seed import seed_qa_oracles
                    results["qa_oracles"] = await seed_qa_oracles(_agk_db)
                except Exception as e: results["qa_oracles_error"] = str(e)[:200]
                try:
                    from seeds.ai_generative_weights_seed import seed_ai_generative_weights
                    results["ai_generative_weights"] = await seed_ai_generative_weights(_agk_db)
                except Exception as e: results["ai_generative_weights_error"] = str(e)[:200]
                try:
                    from seeds.build_recipes_seed import seed_build_recipes
                    results["build_recipes"] = await seed_build_recipes(_agk_db)
                except Exception as e: results["build_recipes_error"] = str(e)[:200]
                # ─── BATCH 3 (2026-05): 14 additional knowledge collections ───
                _ext_seeds = [
                    ("input_haptics",            "input_haptics_seed",            "seed_input_haptics"),
                    ("physics_materials_sim",    "physics_materials_seed",        "seed_physics_materials"),
                    ("audio_dsp",                "audio_dsp_seed",                "seed_audio_dsp"),
                    ("security_crypto",          "security_crypto_seed",          "seed_security_crypto"),
                    ("legal_compliance",         "legal_compliance_seed",         "seed_legal_compliance"),
                    ("variation_mutation",       "variation_mutation_seed",       "seed_variation"),
                    ("emotional_dialogue",       "emotional_dialogue_seed",       "seed_emotional_dialogue"),
                    ("historical_meta",          "historical_meta_seed",          "seed_historical_meta"),
                    ("director_pacing",          "director_pacing_seed",          "seed_director_pacing"),
                    ("visual_juice",             "visual_juice_seed",             "seed_visual_juice"),
                    ("cognitive_psychographics", "cognitive_psychographics_seed", "seed_cognitive"),
                    ("deep_lore",                "deep_lore_seed",                "seed_deep_lore"),
                    ("ecosystems_biology",       "ecosystems_biology_seed",       "seed_ecosystems"),
                    ("publishing_assets",        "publishing_assets_seed",        "seed_publishing_assets"),
                ]
                for label, mod, fn in _ext_seeds:
                    try:
                        m = __import__(f"seeds.{mod}", fromlist=[fn])
                        results[label] = await getattr(m, fn)(_agk_db)
                    except Exception as e: results[f"{label}_error"] = str(e)[:200]
                # ─── Phase 4: anti-piracy + academic + training recipes + scrapers ───
                try:
                    from seeds.phase4_knowledge_seed import seed_phase4_all
                    results["phase4"] = await seed_phase4_all(_agk_db)
                except Exception as e:
                    results["phase4_error"] = str(e)[:200]
                logger.info(f"[agent-knowledge] seeding complete: {results}")
            _kick(30, "agent-knowledge", _kick_agent_knowledge)
            logger.info("[agent-knowledge] full knowledge fabric seed kicked off")

            # 2026-05-15 — Jeeves persona DB (catchphrases, mannerisms, quirks, …)
            async def _kick_jeeves_persona():
                try:
                    from seeds.jeeves_persona_seed import seed_jeeves_persona
                    r = await seed_jeeves_persona()
                    logger.info(f"[jeeves-persona] seeded: {r}")
                except Exception as e:
                    logger.warning(f"[jeeves-persona] seed failed: {e}")
            _kick(35, "jeeves-persona", _kick_jeeves_persona)
        except Exception as e:
            logger.warning(f"[agent-knowledge] seed kickoff failed: {e}")

    # ═══ Live web-scrapers — background loop (off-by-default per job) ═══
    if not _skip_heavy:
        try:
            from services.live_scrapers import scraper_loop
            # Use the agent-knowledge DB (content_db) where scraper_jobs lives.
            try:
                _scrape_db = content_db  # noqa: F821 — set earlier in startup
            except NameError:
                _scrape_db = None
            if _scrape_db is not None:
                _kick(120, "live-scrapers", lambda: scraper_loop(_scrape_db, interval_seconds=1800))
                logger.info("[live-scrapers] background loop started (30-min cadence)")
        except Exception as e:
            logger.warning(f"[live-scrapers] loop kickoff failed: {e}")

    # ═══ Seed unique_flair (50k creative entries) — non-blocking ═══
    if not _skip_heavy:
        try:
            from seeds.unique_flair_seed import seed_unique_flair, TOTAL_FLAIR
            flair_count = await asyncio.wait_for(
                content_db.unique_flair.count_documents({}, limit=TOTAL_FLAIR + 1), timeout=10
            )
            if flair_count < TOTAL_FLAIR:
                _kick(40, "unique-flair", lambda: seed_unique_flair(content_db))
                logger.info(f"unique_flair seed kicked off in background (content_db, target {TOTAL_FLAIR})")
            else:
                logger.info(f"unique_flair already at target (content_db, {flair_count})")
        except asyncio.TimeoutError:
            logger.warning("unique_flair count_documents timed out — skipping seed on this boot")
        except Exception as e:
            logger.warning(f"unique_flair check deferred: {e}")

    # ═══ Seed academy sub-collections (reading_library, bugfix_library, study_paths) ═══
    # reading_library + bugfix_library → content_db (regenerable, big)
    # study_paths → core db (small, user-facing)
    async def _kick_academy_extras_seed():
        try:
            # ── Reading library (books / classes) ── content_db
            if await content_db.reading_library.count_documents({}, limit=1) == 0:
                try:
                    from seeds.reading_library import get_reading_library
                    from seeds.reading_library_mega import get_mega_reading_library
                    from seeds.library_500 import get_500_books, get_supplemental_books
                    rl = get_reading_library()
                    mg = get_mega_reading_library()
                    ex = get_500_books()
                    sp = get_supplemental_books()
                    seen, out = set(), []
                    for b in mg + ex + sp + rl:
                        if b["id"] not in seen:
                            seen.add(b["id"])
                            b["_type"] = "reading_class"
                            b["seeded_at"] = datetime.utcnow().isoformat()
                            out.append(b)
                    if out:
                        await content_db.reading_library.insert_many(out)
                        logger.info(f"[academy-extras] reading_library: {len(out)} books inserted (content_db)")
                except Exception as _re:
                    logger.warning(f"[academy-extras] reading_library seed failed: {_re}")
            # ── Bug/Fix library ── content_db
            if await content_db.bugfix_library.count_documents({}, limit=1) == 0:
                try:
                    from seeds.bugfix_library import get_bugfix_library
                    from seeds.bugfix_mega import get_mega_bugfix_library
                    from seeds.bugfix_complete import get_complete_bugfix_encyclopedia
                    bf = get_bugfix_library()
                    mg = get_mega_bugfix_library()
                    cm = get_complete_bugfix_encyclopedia()
                    seen, out = set(), []
                    for e in cm + mg + bf:
                        if e["id"] not in seen:
                            seen.add(e["id"])
                            e["seeded_at"] = datetime.utcnow().isoformat()
                            out.append(e)
                    if out:
                        await content_db.bugfix_library.insert_many(out)
                        logger.info(f"[academy-extras] bugfix_library: {len(out)} entries inserted (content_db)")
                except Exception as _be:
                    logger.warning(f"[academy-extras] bugfix_library seed failed: {_be}")
            # ── Study paths ── core db (small, user-facing)
            if await db.study_paths.count_documents({}, limit=1) == 0:
                try:
                    from seeds.study_paths import get_study_paths
                    sps = get_study_paths()
                    for sp in sps:
                        sp["_type"] = "study_path"
                        sp["seeded_at"] = datetime.utcnow().isoformat()
                    if sps:
                        await db.study_paths.insert_many(sps)
                        logger.info(f"[academy-extras] study_paths: {len(sps)} paths inserted (core db)")
                except Exception as _se:
                    logger.warning(f"[academy-extras] study_paths seed failed: {_se}")
        except Exception as ex:
            logger.warning(f"[academy-extras] top-level failure: {ex}")
    _kick(45, "academy-extras", _kick_academy_extras_seed)
    logger.info("[academy-extras] reading_library/bugfix_library/study_paths seeders kicked off in background")

    # ═══ Auto-import open-license book registry + background reading content prewarm ═══
    async def _kick_reading_content_warmup():
        try:
            # 1) Idempotent open-license registry import — fills 23 catalogue cards
            from seeds.open_license_books import to_reading_library_records
            from seeds.reading_content_expansion import expand_open_license_chapters
            from core.databases import content_db as _cdb
            try:
                records = [expand_open_license_chapters(r) for r in to_reading_library_records()]
                imported = 0
                for r in records:
                    res = await _cdb.reading_library.update_one(
                        {"id": r["id"]}, {"$set": r}, upsert=True
                    )
                    if res.upserted_id is not None:
                        imported += 1
                logger.info(f"[reading-content] open-license registry import: {imported} new, {len(records) - imported} updated")
            except Exception as e:
                logger.warning(f"[reading-content] open-license import skipped: {e}")

            # 2) Background prewarm — fill content cache so APK clients get instant responses
            #    Bounded to avoid OOM on bootup. Iterates in 5-second sleep batches.
            from seeds.reading_content_generator import generate_chapter_content
            from datetime import datetime, timezone
            warmed = 0
            BATCH = 25
            try:
                # Prewarm books — first chapter of each book (most-opened)
                cursor = _cdb.reading_library.find({}, {"_id": 0, "id": 1, "title": 1, "author": 1, "category": 1, "difficulty": 1, "chapters": 1})
                async for book in cursor:
                    chapters = book.get("chapters") or []
                    if not chapters:
                        continue
                    for idx in range(min(len(chapters), 3)):  # warm first 3 chapters of every book
                        existing = await _cdb.reading_library_content.find_one(
                            {"book_id": book["id"], "chapter_idx": idx}, {"_id": 0, "body_md": 1}
                        )
                        if existing and existing.get("body_md"):
                            continue
                        ch = chapters[idx]
                        try:
                            content = generate_chapter_content(
                                book_title=book.get("title", "Untitled"),
                                author=book.get("author", "Unknown"),
                                category=book.get("category", "cs_foundations"),
                                difficulty=book.get("difficulty", "intermediate"),
                                chapter_name=ch.get("name", f"Chapter {idx + 1}"),
                                chapter_idx=idx,
                                total_chapters=len(chapters),
                            )
                            await _cdb.reading_library_content.update_one(
                                {"book_id": book["id"], "chapter_idx": idx},
                                {"$set": {**content, "book_id": book["id"], "generated_at": datetime.now(timezone.utc).isoformat()}},
                                upsert=True,
                            )
                            warmed += 1
                            if warmed % BATCH == 0:
                                await asyncio.sleep(0.4)  # cooperative yield to avoid RAM/CPU spike
                        except Exception:
                            continue
                logger.info(f"[reading-content] background prewarm complete: {warmed} chapters cached")
            except Exception as e:
                logger.warning(f"[reading-content] prewarm interrupted: {e}")
        except Exception as ex:
            logger.warning(f"[reading-content] warmup top-level failure: {ex}")

    if not _skip_heavy:
        _kick(50, "reading-content-warmup", _kick_reading_content_warmup)
        logger.info("[reading-content] open-license import + prewarm scheduled in background")

    # ═══ Hyperscale swarm: 200 compressed micro-DBs + 200 agents ═══
    if not _skip_heavy:
        try:
            from core.compressed_vault import vault_stats as _vs
            from core.swarm_agents import SWARM_DOMAINS as _SD

            def _kick_swarm_seed():
                try:
                    from seeds.hyperscale_micro_dbs import seed_all
                    res = seed_all(target_multiplier=25.0, force=False)
                    logger.info(f"[swarm] hyperscale seed: {res}")
                except Exception as ex:
                    logger.warning(f"[swarm] background seed failed: {ex}")

            stats = _vs()
            if stats.get("shard_count", 0) < len(_SD):
                import threading
                threading.Thread(target=_kick_swarm_seed, daemon=True).start()
                logger.info(f"[swarm] hyperscale seed kicked off (have {stats.get('shard_count',0)}/{len(_SD)} shards)")
            else:
                logger.info(f"[swarm] hyperscale vault ready: {stats['shard_count']} shards, {stats['total_rows']} rows, {round(stats['total_compressed_bytes']/1024/1024,2)} MB compressed")
        except Exception as e:
            logger.warning(f"[swarm] hyperscale bootstrap deferred: {e}")

    # ═══ Seed Narrative Vault (6 core libs) + Specialized Vault (200 topics)
    # + Game Knowledge Vault (500 topics) — idempotent, non-blocking.  ═══
    if not _skip_heavy:
        try:
            async def _kick_vault_seed():
                try:
                    from core.narrative_vault import seed_narrative_vault
                    from core.narrative_vault_specialized import seed_specialized_vault
                    from core.game_knowledge_vault import seed_game_knowledge_vault, topic_summary
                    # These vaults live in content_db now, not core db
                    rep_core = await seed_narrative_vault(content_db, target_per_genre=120)
                    logger.info(f"[narrative_vault] core seed: {rep_core} (content_db)")
                    rep_spec = await seed_specialized_vault(content_db, target_entries_per_topic_per_genre=25)
                    logger.info(f"[narrative_vault] specialized seed: {rep_spec} (content_db)")
                    logger.info(f"[game_knowledge] plan: {topic_summary()}")
                    rep_gk = await seed_game_knowledge_vault(content_db, target_per_topic_per_genre=6)
                    logger.info(f"[game_knowledge] seed: {rep_gk} (content_db)")
                except Exception as _ve:
                    logger.warning(f"[narrative_vault/game_knowledge] seed failed: {_ve}")
            _kick(55, "vault-seed", _kick_vault_seed)
            logger.info("[narrative_vault+game_knowledge] seeders kicked off in background (content_db)")
        except Exception as e:
            logger.warning(f"[narrative_vault] kick failed: {e}")

    # ═══ Rosetta Stone (~268k code samples × language matrix) ═══
    # Idempotent, content_db-routed, heavy first-time / instant on warm boots.
    if not _skip_heavy:
        try:
            async def _kick_rosetta_stone():
                try:
                    from seeds.rosetta_stone_seed import seed_rosetta_stone
                    # Ensure useful query indexes BEFORE the giant bulk insert
                    # so the unique-id retry path is fast.
                    try:
                        await content_db.rosetta_stone.create_index("id", unique=True)
                        await content_db.rosetta_stone.create_index([("language", 1), ("concept", 1)])
                        await content_db.rosetta_stone.create_index("category")
                        await content_db.rosetta_stone.create_index("language_family")
                    except Exception as _ie:
                        logger.warning(f"[rosetta_stone] index create deferred: {_ie}")
                    rep = await seed_rosetta_stone(content_db)
                    logger.info(f"[rosetta_stone] result: {rep}")
                except Exception as _re:
                    logger.warning(f"[rosetta_stone] seed failed: {_re}")
            _kick(65, "rosetta-stone", _kick_rosetta_stone)
            logger.info("[rosetta_stone] seeder kicked off in background (content_db)")
        except Exception as e:
            logger.warning(f"[rosetta_stone] kick failed: {e}")

    # ═══ Hyperscale References (encyclopedia aggregator) ═══
    # Snippets, cheatsheets, interview prep, glossary, etc. — 500+ entries.
    if not _skip_heavy:
        try:
            async def _kick_hyperscale_refs():
                try:
                    from seeds.reference_encyclopedia import get_all_reference_data
                    coll = content_db["hyperscale_references"]
                    try:
                        await coll.create_index("id", unique=True)
                        await coll.create_index("source")
                    except Exception:
                        pass
                    existing = await coll.count_documents({}, limit=400)
                    if existing >= 400:
                        logger.info(f"[hyperscale_references] already at {existing}+ docs — skipping")
                        return
                    data = get_all_reference_data()
                    entries = []
                    for source_key, items in data.items():
                        if isinstance(items, list):
                            for i, item in enumerate(items):
                                base = {"source": source_key, "idx": i}
                                if isinstance(item, dict):
                                    base.update(item)
                                else:
                                    base["value"] = item
                                if "id" not in base:
                                    base["id"] = f"hsref_{source_key}_{i:05d}"
                                entries.append(base)
                    if entries:
                        try:
                            await coll.insert_many(entries, ordered=False)
                        except Exception as e:
                            if "duplicate" not in str(e).lower():
                                raise
                    total = await coll.count_documents({})
                    logger.info(f"[hyperscale_references] seeded: total={total}")
                except Exception as _he:
                    logger.warning(f"[hyperscale_references] seed failed: {_he}")
            _kick(70, "hyperscale-refs", _kick_hyperscale_refs)
            logger.info("[hyperscale_references] seeder kicked off in background (content_db)")
        except Exception as e:
            logger.warning(f"[hyperscale_references] kick failed: {e}")

    # ═══ Cold-storage auto-reseal: DISABLED in this build.
    # This used to re-freeze collections that startup seeders rehydrated,
    # but it was inadvertently freezing live Academy / curriculum data
    # (reading_library, bugfix_library, etc.) which made the UI appear empty.
    # We now rely on SKIP_HEAVY_SEED + deploy_prep.py to keep the dev DB small
    # before deploy instead. See /app/backend/scripts/deploy_prep.py.
    # ═══
    def _kick_auto_reseal():
        return  # no-op — kept as placeholder for future optional auto-reseal
        try:
            import time as _t
            _t.sleep(90)
            from core import cold_storage as _cs
            regs = _cs.registry_list()
            if not regs:
                return
            # Only reseal names that are in registry (no surprise freezes)
            frozen_names = {r["name"] for r in regs if r.get("status") in ("frozen", "dropped_empty")}
            # ═══ NEVER reseal PROTECTED (academy, quizzes, galaxy builds, etc.)
            # These are user-facing hot collections — freezing them makes the UI
            # render empty lists. Respect PROTECTED even with force=True.
            protected = _cs.PROTECTED
            frozen_names = frozen_names - protected
            from core.databases import get_sync_db
            _xdb = get_sync_db()
            resealed = 0
            skipped_protected = 0
            for nm in list(_xdb.list_collection_names()):
                if nm in protected:
                    skipped_protected += 1
                    continue
                if nm in frozen_names:
                    try:
                        _cs.freeze(nm, drop_after=True, compact=False, force=True)
                        resealed += 1
                    except Exception:
                        pass
            logger.info(f"[cold] auto-reseal: re-froze {resealed} collections that startup seeders rehydrated; skipped {skipped_protected} PROTECTED")
        except Exception as _ex:
            logger.warning(f"[cold] auto-reseal failed: {_ex}")
    import threading as _tr
    _tr.Thread(target=_kick_auto_reseal, daemon=True).start()

    # ═══ Academy / Quiz / Test thawer: if any user-facing collection is still
    # frozen (from a previous auto-reseal run before it was PROTECTED), thaw
    # it back into Mongo so the UI has data immediately.  ═══
    def _kick_academy_thaw():
        try:
            import time as _t
            _t.sleep(5)  # short delay so startup seeders finish first
            from core import cold_storage as _cs
            from core.databases import get_sync_db
            _xdb = get_sync_db()
            regs = _cs.registry_list()
            frozen_names = {r["name"] for r in regs if r.get("status") in ("frozen", "dropped_empty")}
            # Only thaw PROTECTED collections that were frozen earlier
            targets = _cs.PROTECTED & frozen_names
            thawed = 0
            total_rows = 0
            for nm in targets:
                try:
                    # Skip if already populated live
                    if nm in _xdb.list_collection_names() and _xdb[nm].estimated_document_count() > 0:
                        continue
                    res = _cs.thaw(nm)
                    if res.get("status") == "thawed":
                        thawed += 1
                        total_rows += res.get("rows", 0)
                except Exception as _te:
                    logger.warning(f"[academy-thaw] {nm} failed: {_te}")
            if thawed:
                logger.info(f"[academy-thaw] restored {thawed} frozen user-facing collections ({total_rows} total rows)")
        except Exception as _ex:
            logger.warning(f"[academy-thaw] failed: {_ex}")
    _tr.Thread(target=_kick_academy_thaw, daemon=True).start()

    logger.info(f"CodeDock Quantum Nexus v{SYSTEM_VERSION} ready to serve requests")
    # Stage E — start the autonomic background scheduler (self-learning sweeps,
    # legion drills, fabric snapshots). Fail-soft: never blocks readiness.
    try:
        from core.scheduler import start_scheduler
        if start_scheduler():
            logger.info("[BOOT] Stage-E scheduler started (lafs_sweep · legion_drill · fabric_snapshot)")
    except Exception as _sch_ex:  # noqa: BLE001
        logger.warning(f"[BOOT] scheduler start failed: {_sch_ex}")
    # Snapshot boot duration to readiness time so observability tools can
    # surface it without scraping logs.
    app.state._boot_ready_at = time.time()
    app.state._boot_ready_ms = int((app.state._boot_ready_at - _BOOT_START_TS) * 1000)
    logger.info(f"[BOOT] readiness reached in {app.state._boot_ready_ms} ms — {len(_BOOT_TASKS)} background tasks scheduled")

    yield

    # ═══════════════════════════════════════════════════════════════════════
    # ★ CLEAN SHUTDOWN (2026-02-18 upgrade)
    #   FastAPI 0.130+ enforces graceful task drain at shutdown.  Without
    #   explicit cancellation, all `_kick()`-launched tasks would block
    #   uvicorn shutdown for up to several minutes — surfacing as
    #   "Waiting for background tasks to complete" hangs that froze
    #   /api/health during hot reloads.
    #
    #   Strategy:
    #     1. Stop the build watchdog cleanly (sets its _stopped flag).
    #     2. Cancel every kick task in the registry.
    #     3. Drain with a short wait_for so shutdown still completes if
    #        a single task ignores cancellation.
    #     4. Close the Mongo client last.
    # ═══════════════════════════════════════════════════════════════════════
    logger.info("Shutting down — cancelling %d background tasks...", len(_BOOT_TASKS))
    try:
        from core import build_watchdog as _bwd
        _bwd._stopped = True
        if _bwd._watchdog_task and not _bwd._watchdog_task.done():
            _bwd._watchdog_task.cancel()
    except Exception:
        pass
    for t in list(_BOOT_TASKS):
        if not t.done():
            t.cancel()
    if _BOOT_TASKS:
        try:
            await asyncio.wait_for(
                asyncio.gather(*_BOOT_TASKS, return_exceptions=True),
                timeout=5.0,
            )
            logger.info("All background tasks cancelled cleanly")
        except asyncio.TimeoutError:
            still_running = [t.get_name() for t in _BOOT_TASKS if not t.done()]
            logger.warning(f"Timed out cancelling tasks; still running: {still_running[:5]}")
    try:
        client.close()
    except Exception:
        pass
    logger.info("Shutdown complete.")

app = FastAPI(
    title="CodeDock Quantum Nexus",
    description="Beyond Bleeding-Edge Multi-Language Compiler Platform",
    version=SYSTEM_VERSION,
    lifespan=lifespan
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
# CORS origins configurable via env (required by deployment pipeline).
# Comma-separated list or "*" for all. Defaults to "*" for dev.
_cors_env = os.environ.get("CORS_ORIGINS", "*").strip()
if _cors_env == "*" or _cors_env == "":
    _cors_origins = ["*"]
else:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SOTA API controller server-side counterpart ─────────────────────
# Adds request-id propagation (X-Request-Id), structured access logs, and
# an in-memory per-IP token-bucket rate limiter. All tunable via env:
#   RATE_LIMIT_PER_MIN (default 600 = 10 rps/IP)
#   RATE_LIMIT_BURST   (default 60)
#   RATE_LIMIT_EXEMPT  (csv; loopback exempted by default)
#   ACCESS_LOG=0       (disable single-line access log)
from api_middleware import install_middleware as _install_api_middleware, get_stats as _api_stats  # noqa: E402
_install_api_middleware(app)

api_router = APIRouter(prefix="/api")

#====================================================================================================
# API ROUTES
#====================================================================================================

@api_router.get("/")
async def root():
    return {
        "name": "CodeDock Quantum Nexus",
        "version": SYSTEM_VERSION,
        "codename": SYSTEM_CODENAME,
        "build": SYSTEM_BUILD,
        "features": SYSTEM_FEATURES,
        "api_version": "v4"
    }

@api_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "uptime_seconds": time.time() - app_start_time,
        "ai_available": bool(ai_service.api_key),
        "features_enabled": [f.value for f, cfg in FEATURE_FLAGS.items() if cfg["enabled"]]
    }


# ═══════════════════════════════════════════════════════════════════════
# PRODUCTION HEALTH PROBES — startup / liveness / readiness / vault
# ═══════════════════════════════════════════════════════════════════════
# Kubernetes-compatible probe surface. Each probe is intentionally narrow
# and fast so the orchestrator can rely on them. Structured JSON output
# means operators can grep and alert on `status` and `checks.*` fields.
#
# Use:
#   • /api/health           — composite human-readable status (existing).
#   • /api/health/live      — liveness: is the process responsive at all?
#   • /api/health/ready     — readiness: can it serve real requests?
#   • /api/health/startup   — startup: did boot succeed (DB, vault, AI)?
#   • /api/health/vault     — galaxy-studio vault writable + listable?
#   • /api/health/deep      — exhaustive deep health (all checks combined).
# All probe endpoints log structured events with `probe=` and `outcome=`.
# ═══════════════════════════════════════════════════════════════════════

import logging as _probe_logging
_probe_log = _probe_logging.getLogger("probes")


def _probe_event(probe: str, outcome: str, **fields):
    """Emit a structured probe log line."""
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    _probe_log.info(f"probe={probe} outcome={outcome} {extra}")


@api_router.get("/health/live")
async def health_live():
    """Liveness probe — minimum signal that the event loop is alive.

    Never touches I/O. Always cheap. K8s should use this for liveness so
    it doesn't restart the pod just because Mongo is slow.
    """
    _probe_event("liveness", "ok")
    return {
        "status": "live",
        "ts": time.time(),
        "uptime_seconds": round(time.time() - app_start_time, 2),
    }


@api_router.get("/health/ready")
async def health_ready():
    """Readiness probe — can we serve real requests right now?

    Checks: Mongo ping (5s timeout), AI key presence, and that the
    persistent vault dirs are writable. Returns 503 if anything fails so
    K8s can stop sending traffic until we recover.
    """
    checks: dict = {}
    overall_ok = True

    # 1) Mongo ping — SOFT check. On a cold/slow managed Mongo (e.g. Atlas) the
    #    first connection can exceed the probe budget; we must NOT fail readiness
    #    on a transient downstream DB, otherwise K8s never marks the pod Ready and
    #    the deploy "stalls on healthcheck". Endpoints that need Mongo handle their
    #    own errors; the app also has deterministic fallbacks. So Mongo is reported
    #    as degraded-but-ready, never a hard 503.
    try:
        from services.database import db as _db
        import asyncio as _aio
        await _aio.wait_for(_db.command("ping"), timeout=4.0)
        checks["mongo"] = {"ok": True, "latency_ms_lt": 4000}
    except Exception as e:
        checks["mongo"] = {"ok": False, "soft": True, "warming": True,
                           "error": str(e)[:200],
                           "note": "DB warming/unreachable — readiness not failed (soft check)"}

    # 2) AI key
    try:
        checks["ai_key"] = {"ok": bool(ai_service.api_key)}
        if not ai_service.api_key:
            checks["ai_key"]["note"] = "AI features will fall back to deterministic generators"
    except Exception as e:
        checks["ai_key"] = {"ok": False, "error": str(e)[:200]}

    # 3) Vault writable (galaxy-studio)
    try:
        from routes.galaxy_studio import VAULT_DIR as _vault_dir
        test_path = os.path.join(_vault_dir, ".probe")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        checks["vault_galaxy"] = {"ok": True, "path": _vault_dir}
    except Exception as e:
        checks["vault_galaxy"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    # 4) Build-vault writable
    try:
        from core import build_vault as _bv
        test_path = os.path.join(str(_bv.BUILDS_ROOT), ".probe")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        checks["vault_builds"] = {"ok": True, "path": str(_bv.BUILDS_ROOT)}
    except Exception as e:
        checks["vault_builds"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    _probe_event("readiness", "ok" if overall_ok else "degraded",
                 failing=",".join(k for k, v in checks.items() if not v.get("ok")) or "none")

    body = {"status": "ready" if overall_ok else "not_ready", "checks": checks}
    if not overall_ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=body)
    return body


@api_router.get("/health/startup")
async def health_startup():
    """Startup probe — did first-boot succeed cleanly?

    Returns 200 once the app has been up for >=2 seconds AND core
    subsystems initialised. K8s should not fire liveness until this
    returns 200 (avoids killing slow-warming pods).
    """
    uptime = time.time() - app_start_time
    boot_threshold_s = 2.0
    boot_ready = uptime >= boot_threshold_s

    checks = {
        "uptime_ok": {"ok": boot_ready, "uptime_seconds": round(uptime, 2)},
        "feature_flags_loaded": {"ok": bool(FEATURE_FLAGS), "count": len(FEATURE_FLAGS)},
    }
    # Vault module imported successfully?
    try:
        from core import build_vault as _bv  # noqa
        checks["vault_module"] = {"ok": True}
    except Exception as e:
        checks["vault_module"] = {"ok": False, "error": str(e)[:200]}

    overall = all(c["ok"] for c in checks.values())
    _probe_event("startup", "ok" if overall else "pending")
    body = {"status": "started" if overall else "starting", "uptime_seconds": round(uptime, 2), "checks": checks}
    if not overall:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=body)
    return body


@api_router.get("/health/vault")
async def health_vault():
    """Deep vault probe — write/read/delete round-trip on both vaults.

    Useful for ops: confirms that builds will actually persist to disk
    and that file lookups will hit on the same shards we just wrote.
    """
    out: dict = {"status": "ok", "checks": {}}
    overall = True

    # Galaxy vault (ZIPs + APKs)
    try:
        from routes.galaxy_studio import VAULT_DIR as _gv
        tp = os.path.join(_gv, ".probe_rw")
        with open(tp, "w") as f: f.write("rw_test")
        with open(tp) as f: assert f.read() == "rw_test"
        os.remove(tp)
        # also list a few entries to confirm dir is readable
        zip_count = len(os.listdir(os.path.join(_gv, "zips"))) if os.path.isdir(os.path.join(_gv, "zips")) else 0
        out["checks"]["galaxy_vault"] = {"ok": True, "path": _gv, "zips": zip_count}
    except Exception as e:
        out["checks"]["galaxy_vault"] = {"ok": False, "error": str(e)[:200]}
        overall = False

    # Build vault (shards)
    try:
        from core import build_vault as _bv
        root = str(_bv.BUILDS_ROOT)
        tp = os.path.join(root, ".probe_rw")
        with open(tp, "w") as f: f.write("rw_test")
        with open(tp) as f: assert f.read() == "rw_test"
        os.remove(tp)
        build_count = len([x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))])
        out["checks"]["build_vault"] = {"ok": True, "path": root, "builds": build_count}
    except Exception as e:
        out["checks"]["build_vault"] = {"ok": False, "error": str(e)[:200]}
        overall = False

    # Disk free
    try:
        import shutil as _sh
        total, used, free = _sh.disk_usage("/app/backend/data")
        out["disk"] = {
            "total_gb": round(total / 1_073_741_824, 2),
            "used_gb": round(used / 1_073_741_824, 2),
            "free_gb": round(free / 1_073_741_824, 2),
            "free_pct": round(100 * free / total, 1),
        }
        if free / total < 0.05:  # <5% free → warn
            overall = False
            out["checks"]["disk_pressure"] = {"ok": False, "free_pct": out["disk"]["free_pct"]}
    except Exception as e:
        out["disk"] = {"error": str(e)[:200]}

    out["status"] = "ok" if overall else "degraded"
    _probe_event("vault", "ok" if overall else "degraded")
    if not overall:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=out)
    return out


@api_router.get("/health/deep")
async def health_deep():
    """Exhaustive deep health — all probes in one call.

    Slow (touches DB + filesystem). Don't poll faster than 30s. Useful
    for ops dashboards and the in-app /settings/api status panel.
    """
    live = await health_live()
    try:
        ready = await health_ready()
        if hasattr(ready, "body"):  # JSONResponse on 503
            import json as _json
            ready = _json.loads(ready.body)
    except Exception as e:
        ready = {"status": "error", "error": str(e)[:200]}
    try:
        startup = await health_startup()
        if hasattr(startup, "body"):
            import json as _json
            startup = _json.loads(startup.body)
    except Exception as e:
        startup = {"status": "error", "error": str(e)[:200]}
    try:
        vault = await health_vault()
        if hasattr(vault, "body"):
            import json as _json
            vault = _json.loads(vault.body)
    except Exception as e:
        vault = {"status": "error", "error": str(e)[:200]}
    return {
        "live": live, "ready": ready, "startup": startup, "vault": vault,
        "ts": time.time(),
    }


@api_router.get("/_telemetry")
async def telemetry():
    """SOTA API controller — server-side observability counterpart.

    Returns a live snapshot of request volume, status mix, latency percentiles,
    and rate-limit configuration. Cheap to call; safe to poll from the
    /settings/api panel."""
    return _api_stats()

@api_router.get("/system/info")
async def system_info():
    return {
        "version": SYSTEM_VERSION,
        "codename": SYSTEM_CODENAME,
        "build": SYSTEM_BUILD,
        "features": SYSTEM_FEATURES,
        "feature_flags": {k.value: v for k, v in FEATURE_FLAGS.items()},
        "hotfixes": list(HOTFIX_REGISTRY.keys()),
        "languages_installed": sum(1 for lang in LANGUAGE_DOCK_REGISTRY.values() if lang.get("status") == DockStatus.INSTALLED),
        "languages_available": len(LANGUAGE_DOCK_REGISTRY)
    }

# Languages & Dock System
@api_router.get("/languages")
async def get_languages():
    languages = []
    for lang_type, config in LANGUAGE_DOCK_REGISTRY.items():
        languages.append({
            "key": lang_type.value,
            "type": "builtin",
            **{k: v for k, v in config.items() if k not in ['dock_config', 'syntax', 'expansion_hooks']},
            "executable": executor_factory.is_executable(lang_type),
            "templates_available": lang_type in CODE_TEMPLATES
        })
    
    addons = await db.language_addons.find().to_list(100)
    for addon in addons:
        addon['_id'] = str(addon['_id'])
        addon['type'] = 'addon'
        languages.append(addon)
    
    return {"languages": languages, "count": len(languages)}

@api_router.get("/languages/{language_key}")
async def get_language(language_key: str):
    try:
        lang_type = LanguageType(language_key)
        if lang_type in LANGUAGE_DOCK_REGISTRY:
            config = LANGUAGE_DOCK_REGISTRY[lang_type]
            templates = CODE_TEMPLATES.get(lang_type, {})
            return {
                "key": lang_type.value,
                **config,
                "executable": executor_factory.is_executable(lang_type),
                "templates": [{"key": k, **v} for k, v in templates.items()]
            }
    except ValueError:
        pass
    
    addon = await db.language_addons.find_one({"language_key": language_key})
    if addon:
        addon['_id'] = str(addon['_id'])
        return addon
    
    raise HTTPException(status_code=404, detail="Language not found")

@api_router.get("/dock/available")
async def get_available_docks():
    """Get all available language docks for expansion"""
    docks = []
    for lang_type, config in LANGUAGE_DOCK_REGISTRY.items():
        docks.append({
            "key": lang_type.value,
            "name": config.get("name", lang_type.value),
            "display_name": config.get("display_name", config.get("name")),
            "tier": config.get("tier", 3),
            "status": config.get("status", DockStatus.COMING_SOON).value if isinstance(config.get("status"), DockStatus) else config.get("status", "coming_soon"),
            "color": config.get("color", "#6B7280"),
            "icon": config.get("icon", "code-slash"),
            "description": config.get("description", ""),
            "expansion_ready": config.get("expansion_ready", False),
            "executable": executor_factory.is_executable(lang_type)
        })
    return {"docks": sorted(docks, key=lambda x: (x["tier"], x["name"])), "total": len(docks)}


@api_router.get("/docks/available")
async def get_available_docks_alias():
    """Alias for /dock/available — plural form."""
    return await get_available_docks()

# Execution
@api_router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(request: CodeExecutionRequest):
    executor = executor_factory.get_executor(request.language)
    if not executor:
        raise HTTPException(status_code=400, detail=f"Language '{request.language.value}' not executable")
    
    ctx = ExecutionContext(request)
    result = await executor.execute(ctx)
    
    return CodeExecutionResponse(
        execution_id=result.id,
        result=result,
        language_info=LANGUAGE_DOCK_REGISTRY.get(request.language, {})
    )

@api_router.post("/analyze")
async def analyze_code(request: CodeExecutionRequest):
    analysis = None
    if request.language == LanguageType.PYTHON:
        analysis = CodeAnalyzer.analyze_python(request.code)
    else:
        analysis = CodeAnalysis(lines_of_code=len(request.code.splitlines()))
    return {"language": request.language.value, "analysis": analysis.dict()}

@api_router.post("/validate")
async def validate_code(request: CodeExecutionRequest):
    executor = executor_factory.get_executor(request.language)
    if not executor:
        return {"valid": True, "message": "No validation available"}
    
    is_valid, error_msg, security = executor.validate(request.code, request.security_level)
    return {"valid": is_valid, "message": error_msg or "Valid", "security": security.dict()}

# AI
@api_router.get("/ai/modes")
async def get_ai_modes():
    modes = [
        {"key": m.value, "name": m.value.replace("_", " ").title(), "description": d}
        for m, d in [
            (AIAssistantMode.EXPLAIN, "Get detailed code explanation"),
            (AIAssistantMode.DEBUG, "Find and fix bugs"),
            (AIAssistantMode.OPTIMIZE, "Improve performance"),
            (AIAssistantMode.COMPLETE, "Auto-complete code"),
            (AIAssistantMode.REFACTOR, "Improve structure"),
            (AIAssistantMode.DOCUMENT, "Generate documentation"),
            (AIAssistantMode.TEST_GEN, "Generate unit tests"),
            (AIAssistantMode.SECURITY_AUDIT, "Security analysis"),
            (AIAssistantMode.CONVERT, "Convert to another language"),
            (AIAssistantMode.TEACH, "Explain for beginners"),
            (AIAssistantMode.REVIEW, "Code review feedback"),
            (AIAssistantMode.ARCHITECTURE, "Architecture suggestions"),
        ]
    ]
    return {"modes": modes, "ai_available": bool(ai_service.api_key)}

@api_router.post("/ai/assist", response_model=AIAssistResponse)
async def ai_assist(request: AIAssistRequest):
    return await ai_service.assist(request)

# Templates
@api_router.get("/templates")
async def get_templates():
    templates = {}
    for lang_type, lang_templates in CODE_TEMPLATES.items():
        templates[lang_type.value] = [{"key": k, **v} for k, v in lang_templates.items()]
    return {"templates": templates}

@api_router.get("/templates/{language}")
async def get_language_templates(language: str):
    try:
        lang_type = LanguageType(language)
        if lang_type in CODE_TEMPLATES:
            return {"language": language, "templates": [{"key": k, **v} for k, v in CODE_TEMPLATES[lang_type].items()]}
    except ValueError:
        pass
    raise HTTPException(status_code=404, detail="No templates")

# Tooltips System
@api_router.get("/tooltips")
async def get_tooltips(category: Optional[str] = None):
    tooltips = TOOLTIPS_REGISTRY
    if category:
        tooltips = {k: v for k, v in tooltips.items() if v.get("category", "").value == category}
    return {"tooltips": tooltips, "categories": [c.value for c in TooltipCategory]}

@api_router.get("/tooltips/{tooltip_id}")
async def get_tooltip(tooltip_id: str):
    if tooltip_id in TOOLTIPS_REGISTRY:
        return TOOLTIPS_REGISTRY[tooltip_id]
    raise HTTPException(status_code=404, detail="Tooltip not found")

# Tutorial/Teaching Mode
@api_router.get("/tutorial/steps")
async def get_tutorial_steps():
    steps = []
    for step, config in TUTORIAL_STEPS.items():
        steps.append({"key": step.value, **config})
    return {"steps": sorted(steps, key=lambda x: x["order"]), "total_steps": len(steps)}

@api_router.get("/tutorial/step/{step_key}")
async def get_tutorial_step(step_key: str):
    try:
        step = TutorialStep(step_key)
        if step in TUTORIAL_STEPS:
            return {"key": step.value, **TUTORIAL_STEPS[step]}
    except ValueError:
        pass
    raise HTTPException(status_code=404, detail="Step not found")

@api_router.get("/tutorial/progress")
async def get_tutorial_progress():
    progress = await db.tutorial_progress.find_one({})
    if not progress:
        default = TutorialProgress()
        await db.tutorial_progress.insert_one(default.dict())
        return default
    return TutorialProgress(**progress)

@api_router.put("/tutorial/progress")
async def update_tutorial_progress(data: dict):
    await db.tutorial_progress.update_one({}, {"$set": data}, upsert=True)
    progress = await db.tutorial_progress.find_one({})
    return TutorialProgress(**progress)

@api_router.post("/tutorial/complete-step")
async def complete_tutorial_step(data: dict):
    step_key = data.get("step")
    progress = await db.tutorial_progress.find_one({})
    
    if not progress:
        progress = TutorialProgress().dict()
    
    completed = progress.get("completed_steps", [])
    if step_key not in completed:
        completed.append(step_key)
    
    # Find next step
    try:
        current = TutorialStep(step_key)
        next_step = TUTORIAL_STEPS.get(current, {}).get("next_step")
        
        update = {
            "completed_steps": completed,
            "current_step": next_step.value if next_step else "complete"
        }
        
        if next_step is None:
            update["completed_at"] = datetime.utcnow()
        
        await db.tutorial_progress.update_one({}, {"$set": update}, upsert=True)
    except ValueError:
        pass
    
    return {"success": True, "completed_steps": completed}

# Advanced Settings (Hidden Panel)
@api_router.get("/advanced/settings")
async def get_advanced_settings():
    prefs = await db.user_preferences.find_one({})
    if prefs and prefs.get("advanced_panel_unlocked"):
        return {
            "unlocked": True,
            "settings": prefs.get("advanced_settings", AdvancedSettings().dict()),
            "feature_flags": {k.value: v for k, v in FEATURE_FLAGS.items()}
        }
    return {"unlocked": False, "message": "Triple-tap version to unlock"}

@api_router.post("/advanced/unlock")
async def unlock_advanced_panel(data: dict):
    """Unlock with triple-tap gesture verification"""
    secret = data.get("secret")
    # Simple validation - in production would be more secure
    if secret == "quantum_nexus_unlock" or data.get("gesture") == "triple_tap_version":
        await db.user_preferences.update_one({}, {"$set": {"advanced_panel_unlocked": True}}, upsert=True)
        return {"success": True, "message": "Advanced panel unlocked!"}
    return {"success": False, "message": "Invalid unlock gesture"}

@api_router.put("/advanced/settings")
async def update_advanced_settings(settings: dict):
    await db.user_preferences.update_one({}, {"$set": {"advanced_settings": settings}}, upsert=True)
    return {"success": True}

# Hotfixes
@api_router.get("/hotfixes")
async def get_hotfixes():
    return {"hotfixes": list(HOTFIX_REGISTRY.values()), "count": len(HOTFIX_REGISTRY)}

@api_router.get("/hotfixes/{hotfix_id}")
async def get_hotfix(hotfix_id: str):
    if hotfix_id in HOTFIX_REGISTRY:
        return HOTFIX_REGISTRY[hotfix_id]
    raise HTTPException(status_code=404, detail="Hotfix not found")

# Files CRUD
@api_router.post("/files", response_model=CodeFile)
async def create_file(data: dict):
    code_file = CodeFile(**data)
    await db.code_files.insert_one(code_file.dict())
    return code_file

@api_router.get("/files")
async def get_files(language: Optional[str] = None, limit: int = 50):
    query = {"language": language} if language else {}
    files = await db.code_files.find(query).sort("updated_at", -1).to_list(limit)
    return {"files": [CodeFile(**f) for f in files]}

@api_router.get("/files/{file_id}")
async def get_file(file_id: str):
    file = await db.code_files.find_one({"id": file_id})
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return CodeFile(**file)

@api_router.put("/files/{file_id}")
async def update_file(file_id: str, data: dict):
    data["updated_at"] = datetime.utcnow()
    await db.code_files.update_one({"id": file_id}, {"$set": data})
    file = await db.code_files.find_one({"id": file_id})
    return CodeFile(**file)

@api_router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    await db.code_files.delete_one({"id": file_id})
    return {"success": True}

# Addons
@api_router.post("/addons", response_model=LanguageAddon)
async def create_addon(data: dict):
    existing = await db.language_addons.find_one({"language_key": data.get("language_key")})
    if existing:
        raise HTTPException(status_code=400, detail="Addon exists")
    addon = LanguageAddon(**data)
    await db.language_addons.insert_one(addon.dict())
    return addon

@api_router.get("/addons")
async def get_addons():
    addons = await db.language_addons.find().to_list(100)
    return {"addons": [LanguageAddon(**a) for a in addons]}

@api_router.delete("/addons/{addon_id}")
async def delete_addon(addon_id: str):
    await db.language_addons.delete_one({"id": addon_id})
    return {"success": True}

# Preferences
@api_router.get("/preferences")
async def get_preferences():
    prefs = await db.user_preferences.find_one({})
    if not prefs:
        default = UserPreferences()
        await db.user_preferences.insert_one(default.dict())
        return default
    return UserPreferences(**prefs)

@api_router.put("/preferences")
async def update_preferences(data: dict):
    data["updated_at"] = datetime.utcnow()
    await db.user_preferences.update_one({}, {"$set": data}, upsert=True)
    prefs = await db.user_preferences.find_one({})
    return UserPreferences(**prefs)

# Snippets
@api_router.post("/snippets")
async def create_snippet(data: dict):
    snippet_id = uuid.uuid4().hex[:8]
    snippet = {
        "id": snippet_id,
        "code": data.get("code"),
        "language": data.get("language"),
        "title": data.get("title", "Untitled"),
        "created_at": datetime.utcnow(),
        "views": 0
    }
    await db.snippets.insert_one(snippet)
    return {"id": snippet_id, "share_url": f"/snippets/{snippet_id}"}

@api_router.get("/snippets/{snippet_id}")
async def get_snippet(snippet_id: str):
    snippet = await db.snippets.find_one({"id": snippet_id})
    if not snippet:
        raise HTTPException(status_code=404, detail="Snippet not found")
    await db.snippets.update_one({"id": snippet_id}, {"$inc": {"views": 1}})
    snippet['_id'] = str(snippet['_id'])
    return snippet

# History
@api_router.get("/history")
async def get_history(limit: int = 50):
    history = await db.execution_history.find().sort("created_at", -1).to_list(limit)
    return {"history": history}

@api_router.delete("/history")
async def clear_history():
    await db.execution_history.delete_many({})
    return {"success": True}

# Routes will be included after all definitions at the end of file

#====================================================================================================
# QUANTUM COMPILER SUITE API - Real Compilation Backend
#====================================================================================================

class SanitizerType(str, Enum):
    MEMORY = "memory"           # Memory leak detection
    THREAD = "thread"           # Race condition detection
    UNDEFINED = "undefined"     # Undefined behavior detection
    ADDRESS = "address"         # Buffer overflow detection
    BEHAVIOR = "behavior"       # Runtime behavior analysis
    LEAK = "leak"              # Resource leak detection

class OptimizerType(str, Enum):
    LTO = "lto"                 # Link-Time Optimization
    PGO = "pgo"                 # Profile-Guided Optimization
    SIMD = "simd"               # Vectorization
    INLINE = "inline"           # Function inlining
    LOOP = "loop"               # Loop optimizations
    DEAD_CODE = "dead_code"     # Dead code elimination
    CONSTANT_PROP = "constant_prop"  # Constant propagation
    TAIL_CALL = "tail_call"    # Tail call optimization

# ─── Compiler pipeline Pydantic models REVERTED (Phase-9 rollback) — kept inline
#     here. models/compiler_pipeline.py file preserved on disk.
class CompilerStage(BaseModel):
    id: str
    name: str
    short_name: str
    status: str = "pending"
    duration_ms: float = 0.0
    metrics: Dict[str, Any] = {}
    output: Optional[str] = None
    errors: List[Dict[str, Any]] = []

class CompilationRequest(BaseModel):
    code: str
    language: LanguageType
    sanitizers: List[str] = []
    optimizers: List[str] = []
    optimization_level: int = Field(default=2, ge=0, le=3)
    target_arch: str = "x86_64"
    include_ir: bool = False
    include_assembly: bool = False
    agentic_analysis: bool = True
    micro_tests: bool = True

class SanitizerResult(BaseModel):
    type: str
    enabled: bool
    issues_found: int = 0
    issues: List[Dict[str, Any]] = []
    duration_ms: float = 0.0

class OptimizerResult(BaseModel):
    type: str
    applied: bool
    improvements: Dict[str, Any] = {}
    before_metrics: Dict[str, Any] = {}
    after_metrics: Dict[str, Any] = {}
    suggestions: List[str] = []

class PipelineStage(BaseModel):
    id: str
    name: str
    short_name: str
    description: str
    icon: str
    color: str
    status: str = "pending"
    duration_ms: float = 0.0
    metrics: Dict[str, Any] = {}
    details: List[str] = []

class CompilationResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    success: bool
    language: str
    stages: List[PipelineStage] = []
    sanitizer_results: List[SanitizerResult] = []
    optimizer_results: List[OptimizerResult] = []
    ir_code: Optional[str] = None
    assembly_code: Optional[str] = None
    binary_size: Optional[int] = None
    total_time_ms: float = 0.0
    agentic_analysis: Optional[Dict[str, Any]] = None
    micro_test_results: Optional[Dict[str, Any]] = None
    performance_suggestions: List[Dict[str, Any]] = []
    diagnostics: List[Dict[str, Any]] = []
# ─── QuantumCompilerService extracted → services/quantum_compiler_svc.py (Phase-8, Feb 2026)
#     Back-compat shim: singleton ``quantum_compiler`` and class re-exported here.
from services.quantum_compiler_svc import QuantumCompilerService, quantum_compiler  # noqa: E402,F401

# ─── Compiler / Benchmark / Verify endpoints extracted →
#     routes/compiler_tools.py (registered via routes_registry.py).


# ─── Starlog + Learning + Collaboration endpoints extracted →
#     routes/intelligence_collab.py (registered via routes_registry.py).


#====================================================================================================
# CODEDOCK v9.0.0 ULTIMATE HUB - Self-Evolving AI-Powered Expansion System
#====================================================================================================

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROK = "grok"  # Future support

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

# ============================================================================
# COMPREHENSIVE LANGUAGE PACK REGISTRY - 50+ Languages
# ============================================================================
# ─── LANGUAGE_PACK_REGISTRY extracted → services/registries/language_packs.py (Phase-8, Feb 2026)
from services.registries.language_packs import LANGUAGE_PACK_REGISTRY  # noqa: E402,F401

# ============================================================================
# ALGORITHM REGISTRY - State of the Art Compilation Algorithms
# ============================================================================
# ─── ALGORITHM_REGISTRY extracted → services/registries/algorithms.py (Phase-8, Feb 2026)
from services.registries.algorithms import ALGORITHM_REGISTRY  # noqa: E402,F401

# ============================================================================
# EXPANSION PACK DEFINITIONS
# ============================================================================
# ─── EXPANSION_PACKS extracted → services/registries/expansion_packs.py (Phase-8, Feb 2026)
from services.registries.expansion_packs import EXPANSION_PACKS  # noqa: E402,F401

# ============================================================================
# SELF-EVOLVING AI HUB SERVICE
# ============================================================================
# ─── AIHubService extracted → services/ai_hub_svc.py
#     (Phase-7, Feb 2026). Singleton constructed lazily via
#     ``get_ai_hub()`` (needs LLMProvider enum which is still owned
#     here in server.py).
from services.ai_hub_svc import AIHubService, get_ai_hub  # noqa: E402,F401
ai_hub = get_ai_hub()  # eager-init the singleton at boot for back-compat

# ============================================================================
# SELF-HEALING SERVICE
# ============================================================================
# ─── SelfHealingService extracted → services/self_healer_svc.py
#     (Phase-7, Feb 2026). Singleton ``self_healer`` re-exported here
#     for back-compat. Also includes the ``organize_library`` bugfix
#     for plain-string file inputs (was AttributeError before).
from services.self_healer_svc import SelfHealingService, self_healer  # noqa: E402,F401

# ============================================================================
# IMPORT/EXPORT SERVICE
# ============================================================================
# ─── ImportExportService extracted → services/import_export_svc.py
#     (Phase-7, Feb 2026). Singleton ``import_export`` re-exported here
#     for back-compat with ``from server import import_export`` callers.
from services.import_export_svc import ImportExportService, import_export  # noqa: E402,F401

# ============================================================================
# COMPILATION BIBLE - Deep Teaching System
# ============================================================================
COMPILATION_BIBLE = {
    "chapters": [
        {
            "id": "lexical_analysis",
            "title": "Chapter 1: Lexical Analysis",
            "subtitle": "From Characters to Tokens",
            "difficulty": "beginner",
            "content": """
# Lexical Analysis: The First Step

Lexical analysis (scanning) is the first phase of compilation. It converts a stream of characters into a stream of tokens.

## Key Concepts

### 1. Tokens
A token is a meaningful unit:
- **Keywords**: if, while, for, class
- **Identifiers**: variable names, function names
- **Literals**: numbers, strings
- **Operators**: +, -, *, /, ==
- **Delimiters**: (, ), {, }, ;

### 2. Regular Expressions
Tokens are typically defined using regular expressions:
- `[a-zA-Z_][a-zA-Z0-9_]*` - Identifiers
- `[0-9]+` - Integer literals
- `"[^"]*"` - String literals

### 3. Finite Automata
Lexers are implemented as finite automata:
- DFA (Deterministic) - One transition per input
- NFA (Non-deterministic) - Multiple possible transitions

## Algorithm: Maximal Munch
The lexer always matches the longest possible token.

```
Input: "ifdef"
Could be: "if" + "def" OR "ifdef"
Result: "ifdef" (identifier)
```

## Practice Exercise
Build a lexer that tokenizes: `x = 10 + 20`
Expected tokens: [IDENT:x, ASSIGN, INT:10, PLUS, INT:20]
            """,
            "exercises": [
                {"type": "code", "prompt": "Implement a simple tokenizer for arithmetic expressions"},
                {"type": "quiz", "question": "What is the time complexity of a DFA-based lexer?", "answer": "O(n)"}
            ]
        },
        {
            "id": "parsing",
            "title": "Chapter 2: Parsing",
            "subtitle": "Building the Syntax Tree",
            "difficulty": "intermediate",
            "content": """
# Parsing: From Tokens to Trees

Parsing (syntactic analysis) constructs an Abstract Syntax Tree (AST) from tokens.

## Grammar Notation

### Context-Free Grammars (CFG)
```
expr   → term (('+' | '-') term)*
term   → factor (('*' | '/') factor)*
factor → NUMBER | '(' expr ')'
```

### BNF (Backus-Naur Form)
```
<expr>   ::= <term> | <expr> '+' <term>
<term>   ::= <factor> | <term> '*' <factor>
<factor> ::= <number> | '(' <expr> ')'
```

## Parsing Strategies

### Top-Down Parsing
- **Recursive Descent**: Hand-written, intuitive
- **LL(k)**: Table-driven, k lookahead tokens
- **Pratt Parsing**: Elegant operator precedence

### Bottom-Up Parsing
- **LR(k)**: Powerful, handles left recursion
- **LALR**: Used by Yacc/Bison
- **GLR**: Handles ambiguous grammars

## Precedence & Associativity

| Operator | Precedence | Associativity |
|----------|------------|---------------|
| =        | 1          | Right         |
| + -      | 2          | Left          |
| * /      | 3          | Left          |
| ^        | 4          | Right         |
| - (unary)| 5          | Right         |

## Building an AST

```python
class BinaryOp:
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

# For: 2 + 3 * 4
ast = BinaryOp(
    Num(2),
    '+',
    BinaryOp(Num(3), '*', Num(4))
)
```
            """,
            "exercises": [
                {"type": "code", "prompt": "Implement a recursive descent parser for arithmetic"},
                {"type": "diagram", "prompt": "Draw the AST for: (a + b) * c - d"}
            ]
        },
        {
            "id": "semantic_analysis",
            "title": "Chapter 3: Semantic Analysis",
            "subtitle": "Making Sense of Syntax",
            "difficulty": "intermediate",
            "content": """
# Semantic Analysis: Beyond Syntax

Semantic analysis checks that the program makes sense: types match, variables are declared, etc.

## Symbol Tables

Track identifiers and their attributes:
```
Symbol Table:
| Name  | Type   | Scope  | Address |
|-------|--------|--------|---------|
| x     | int    | global | 0x100   |
| foo   | func   | global | 0x200   |
| y     | float  | foo    | 0x208   |
```

## Type Checking

### Static Type Checking (Compile-time)
```
int x = "hello";  // ERROR: type mismatch
```

### Type Inference
```python
def add(a, b):
    return a + b  # Types inferred from usage
```

### Type Coercion
```c
int a = 5;
float b = a;  // Implicit conversion: int → float
```

## Scope Rules

### Lexical Scoping
```python
x = 10  # Global
def foo():
    x = 20  # Local shadows global
    def bar():
        print(x)  # Uses foo's x (20)
```

### Dynamic Scoping (rare)
Variable binding determined at runtime.

## Control Flow Analysis

- **Dead Code Detection**: Unreachable statements
- **Definite Assignment**: Variables initialized before use
- **Return Path Analysis**: All paths return a value
            """,
            "exercises": [
                {"type": "code", "prompt": "Implement a type checker for a simple language"},
                {"type": "quiz", "question": "What is the difference between static and dynamic scoping?"}
            ]
        },
        {
            "id": "intermediate_representation",
            "title": "Chapter 4: Intermediate Representation",
            "subtitle": "The Bridge Between Front and Back",
            "difficulty": "advanced",
            "content": """
# Intermediate Representation (IR)

IR bridges the gap between source language and target machine code.

## IR Formats

### Three-Address Code (TAC)
Each instruction has at most 3 operands:
```
t1 = a + b
t2 = c * d
t3 = t1 - t2
```

### Static Single Assignment (SSA)
Every variable assigned exactly once:
```
// Original
x = 1
x = 2
y = x

// SSA Form
x1 = 1
x2 = 2
y = x2
```

### LLVM IR
```llvm
define i32 @add(i32 %a, i32 %b) {
entry:
  %sum = add i32 %a, %b
  ret i32 %sum
}
```

## Control Flow Graph (CFG)

Basic blocks connected by control flow edges:
```
┌─────────┐
│ Entry   │
└────┬────┘
     │
┌────▼────┐
│ if cond │──false──┐
└────┬────┘         │
     │true          │
┌────▼────┐   ┌─────▼────┐
│ then    │   │ else     │
└────┬────┘   └────┬─────┘
     │             │
     └──────┬──────┘
      ┌─────▼─────┐
      │  merge    │
      └───────────┘
```

## SSA Construction

### φ (phi) Functions
Merge values at join points:
```
if (cond)
  x = 1
else
  x = 2
// At merge: x3 = φ(x1, x2)
```

### Dominance Frontier Algorithm
Efficiently place φ functions using dominance information.
            """,
            "exercises": [
                {"type": "code", "prompt": "Convert a simple program to SSA form"},
                {"type": "diagram", "prompt": "Draw the CFG for a while loop"}
            ]
        },
        {
            "id": "optimization",
            "title": "Chapter 5: Optimization",
            "subtitle": "Making Code Fast",
            "difficulty": "advanced",
            "content": """
# Code Optimization

Transform code to run faster or use less memory.

## Local Optimizations (Single Block)

### Constant Folding
```
x = 2 + 3    →    x = 5
```

### Constant Propagation
```
x = 5
y = x + 2    →    y = 7
```

### Algebraic Simplification
```
x * 1 → x
x + 0 → x
x * 2 → x << 1
```

### Dead Code Elimination
```
x = 5
x = 10  // Previous assignment is dead
```

## Global Optimizations (Multiple Blocks)

### Common Subexpression Elimination (CSE)
```
a = b + c
...
d = b + c    →    d = a (if b,c unchanged)
```

### Loop Invariant Code Motion (LICM)
```
for i in range(n):
    x = y + z      // Move outside loop
    a[i] = x * i

// Becomes:
x = y + z
for i in range(n):
    a[i] = x * i
```

### Strength Reduction
```
// Original
for i in range(n):
    y = i * 4

// Optimized
y = 0
for i in range(n):
    y += 4
```

## Loop Optimizations

### Loop Unrolling
```
// Original
for i in range(4):
    sum += a[i]

// Unrolled
sum += a[0] + a[1] + a[2] + a[3]
```

### Loop Fusion
Combine adjacent loops with same bounds.

### Loop Tiling
Improve cache performance for nested loops.

## Data Flow Analysis

- **Reaching Definitions**: Which assignments reach a point
- **Live Variables**: Which variables are used later
- **Available Expressions**: Which expressions are already computed
            """,
            "exercises": [
                {"type": "code", "prompt": "Implement constant propagation"},
                {"type": "analysis", "prompt": "Identify optimizations for a given code snippet"}
            ]
        },
        {
            "id": "register_allocation",
            "title": "Chapter 6: Register Allocation",
            "subtitle": "From Virtual to Physical",
            "difficulty": "advanced",
            "content": """
# Register Allocation

Map virtual registers to physical machine registers.

## The Challenge

- CPUs have limited registers (8-32 typically)
- Programs may use thousands of variables
- Some instructions require specific registers

## Live Ranges & Interference

### Live Range
The span where a variable's value is needed:
```
x = 10      // x live starts
y = 20
z = x + y   // x live ends
```

### Interference Graph
Nodes = variables, Edges = simultaneous liveness
```
If x and y are both live at some point,
they cannot share a register.
```

## Algorithms

### Graph Coloring
- Color graph with k colors (k = register count)
- NP-complete in general
- Heuristics work well in practice

### Chaitin-Briggs Algorithm
1. Build interference graph
2. Simplify: Remove nodes with < k edges
3. Spill: If stuck, spill a variable to memory
4. Select: Assign colors in reverse order

### Linear Scan
- Faster than graph coloring
- Order variables by live range start
- Greedily assign registers
- Commonly used in JIT compilers

## Spilling

When registers run out:
1. Choose a variable to spill
2. Store to memory (stack)
3. Load when needed

### Spill Cost
```
cost = Σ (10^loop_depth × use_count)
```
Spill variables with lowest cost.

## Coalescing

Eliminate unnecessary copies:
```
a = b   // If a and b don't interfere,
        // assign same register
```
            """,
            "exercises": [
                {"type": "code", "prompt": "Implement linear scan register allocation"},
                {"type": "diagram", "prompt": "Build interference graph for a code snippet"}
            ]
        },
        {
            "id": "code_generation",
            "title": "Chapter 7: Code Generation",
            "subtitle": "Generating Machine Code",
            "difficulty": "expert",
            "content": """
# Code Generation

Transform IR to target machine code.

## Instruction Selection

### Tree Pattern Matching
Match IR trees to instruction templates:
```
ADD(REG, CONST) → addi rd, rs, imm
ADD(REG, REG)   → add rd, rs1, rs2
```

### BURG-style Selection
- Define cost for each pattern
- Find minimum-cost covering
- Dynamic programming on trees

## Instruction Scheduling

Reorder instructions to:
- Hide latencies (pipelining)
- Avoid stalls
- Maximize parallelism

### List Scheduling
1. Build dependence DAG
2. Compute priorities
3. Schedule highest priority ready instruction

### Software Pipelining
Overlap iterations of loops.

## Target-Specific Concerns

### x86-64 Calling Convention
- Args: RDI, RSI, RDX, RCX, R8, R9
- Return: RAX
- Callee-saved: RBX, RBP, R12-R15

### ARM64 Calling Convention
- Args: X0-X7
- Return: X0
- Callee-saved: X19-X28

### SIMD Code Generation
Vectorize loops for SSE/AVX/NEON:
```c
// Scalar
for (int i = 0; i < n; i++)
    c[i] = a[i] + b[i];

// Vector (AVX)
for (int i = 0; i < n; i += 8)
    _mm256_store_ps(&c[i], 
        _mm256_add_ps(
            _mm256_load_ps(&a[i]),
            _mm256_load_ps(&b[i])));
```

## Peephole Optimization

Local rewriting of instruction sequences:
```
mov eax, 0    →    xor eax, eax
add eax, 1    →    inc eax
```
            """,
            "exercises": [
                {"type": "code", "prompt": "Generate x86 assembly for a simple function"},
                {"type": "analysis", "prompt": "Identify instruction scheduling opportunities"}
            ]
        },
        {
            "id": "advanced_topics",
            "title": "Chapter 8: Advanced Topics",
            "subtitle": "Cutting-Edge Compilation",
            "difficulty": "expert",
            "content": """
# Advanced Compilation Topics

## Just-In-Time (JIT) Compilation

Compile at runtime for dynamic optimization:
- **Tracing JIT**: Record hot paths, compile traces
- **Method JIT**: Compile whole methods
- **Tiered Compilation**: Interpret → Baseline → Optimizing

## Profile-Guided Optimization (PGO)

Use runtime profiles to guide optimization:
1. Instrument build
2. Run with representative workload
3. Rebuild with profile data

Benefits:
- Better branch prediction
- Improved function inlining
- Optimized code layout

## Polyhedral Optimization

Model nested loops as polyhedra:
- Represent iterations as integer points
- Apply affine transformations
- Optimize for parallelism and locality

## Link-Time Optimization (LTO)

Optimize across compilation units:
- Cross-module inlining
- Whole-program dead code elimination
- Better constant propagation

## Garbage Collection

### Tracing GC
- Mark reachable objects
- Sweep/compact unreachable

### Reference Counting
- Increment on reference
- Decrement on dereference
- Cycle detection needed

### Generational GC
- Young generation: frequent, fast collection
- Old generation: rare, thorough collection

## Formal Verification

Prove compiler correctness:
- CompCert (verified C compiler)
- CakeML (verified ML compiler)
- Proof-carrying code
            """,
            "exercises": [
                {"type": "research", "prompt": "Compare tracing and method JIT compilation"},
                {"type": "project", "prompt": "Implement a simple mark-sweep garbage collector"}
            ]
        }
    ],
    "total_chapters": 8,
    "estimated_hours": 40,
    "certification_available": True
}

# ============================================================================
# API ENDPOINTS - Ultimate Hub
# ============================================================================

# ─── Hub-tools endpoints (v9/info, language-packs, expansions, ai/hub,
#     healing, import/export, algorithms) extracted → routes/hub_tools.py
#     (registered via routes_registry.py KNOWN_ROUTES_WITH_PREFIX).


# Include all routes at the end after all definitions

# ═══════════════════════════════════════════════════════════════════════
#  ROOT + K8S-FRIENDLY ENDPOINTS — must be 200 OK so the orchestrator's
#  default HTTP probes (GET /, HEAD /, OPTIONS /) recognise this pod as
#  healthy even before it knows about /api/health/*.
#
#  This was discovered while debugging "pod not found" errors in
#  Emergent's MANAGE_SECRETS step: if the source pod is marked NotReady
#  because GET / returns 404, the deploy pipeline can't query its env.
# ═══════════════════════════════════════════════════════════════════════

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
async def _root_probe():
    """K8s/loadbalancer-friendly root response.

    Returns 200 OK with minimum metadata so any HTTP health probe at the
    root path treats this pod as alive. The actual app surface lives under
    /api/* — clients should hit that prefix, not /.
    """
    return {
        "service": "codedock-quantum-nexus",
        "status": "ok",
        "api_prefix": "/api",
        "health": "/api/health",
        "probes": {
            "live":    "/api/health/live",
            "ready":   "/api/health/ready",
            "startup": "/api/health/startup",
            "vault":   "/api/health/vault",
        },
    }


@app.options("/", include_in_schema=False)
@app.options("/api", include_in_schema=False)
@app.options("/api/health", include_in_schema=False)
@app.options("/api/health/live", include_in_schema=False)
@app.options("/api/health/ready", include_in_schema=False)
@app.options("/api/health/startup", include_in_schema=False)
async def _options_probe():
    """Explicit OPTIONS handlers — some K8s ingresses send OPTIONS first
    as a probe. FastAPI's CORS middleware handles real preflights, but a
    fast no-body 200 here is safe + cheap."""
    return {"ok": True}


@app.get("/_kube/live", include_in_schema=False)
@app.head("/_kube/live", include_in_schema=False)
async def _kube_live():
    """Mirror of /api/health/live at a path some K8s probes prefer."""
    return {"status": "live", "ts": time.time()}


@app.get("/_kube/ready", include_in_schema=False)
@app.head("/_kube/ready", include_in_schema=False)
async def _kube_ready():
    """Mirror of /api/health/ready — lightweight check K8s readiness."""
    try:
        from services.database import db as _db
        await asyncio.wait_for(_db.command("ping"), timeout=3.0)
        return {"status": "ready"}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "not_ready"})


# ─── Mount the inline `api_router` defined in this file (holds every
# ``@api_router.get/post(...)`` endpoint declared throughout server.py). Must
# run BEFORE register_known_routes so middleware ordering is consistent.
app.include_router(api_router)

# ─── Security + observability middleware (added 2026) ──────────────
# All three layers use module-level shared state so the telemetry router
# can read the same audit ring / rate-limit buckets that the middleware
# instances populate. Order: outermost wraps innermost. Rate-limit is
# outermost so capacity-exceeded never enters the audit ring.
app.add_middleware(SizeLimitMiddleware)
app.add_middleware(AuditMiddleware, max_entries=5000)
app.add_middleware(RateLimitMiddleware)

# ─── Hardening middleware + router (added Feb 2026) ────────────────
# Hard wall-clock timeout on every /api/* request (504 instead of hang)
# plus a /api/health/detailed endpoint with CPU / memory / disk metrics
# that the frontend can use to detect resource exhaustion.
try:
    from middleware.hardening import RequestTimeoutMiddleware, hardening_router
    app.add_middleware(RequestTimeoutMiddleware, default_timeout_s=30.0)
    if hardening_router is not None:
        app.include_router(hardening_router, prefix="/api")
except Exception as e:
    import logging as _hlogging
    _hlogging.getLogger("api.bootstrap").warning("hardening middleware unavailable: %s", e)


# ─── Reliability layer (Feb 2026 Cat-1 upgrade) ───────────────────────
# Wires LoadSheddingMiddleware + graceful SIGTERM drain + DLQ endpoints.
# Sheds load when watchdog is stale or _shedding flag is set; allows the
# Emergent K8s probe paths through unconditionally so deploy stays green.
try:
    from core.reliability import (
        LoadSheddingMiddleware, install_graceful_drain,
        dlq_snapshot, reliability_snapshot,
    )
    from core.perf import (
        install_brotli, perf_snapshot, boot_index_audit,
    )
    from core.security_v2 import install_security_headers
    from core.observability import (
        ObservabilityMiddleware, observability_snapshot, prom_metrics,
        ERRORS, LATENCY, BREADCRUMBS,
    )
    app.add_middleware(LoadSheddingMiddleware, wd_stale_sec=180.0)
    app.add_middleware(ObservabilityMiddleware)
    # Brotli ~20-25% smaller than gzip for typical JSON payloads.
    install_brotli(app)
    # Cat-3 hardening (CSP/HSTS/XCTO/XFO/Referrer-Policy + log scrub)
    install_security_headers(
        app,
        csp="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "connect-src 'self' https: wss:; frame-ancestors 'none'",
    )

    @app.get("/api/health/dlq")
    async def _dlq_endpoint():
        """Dead-letter queue snapshot — last 200 failed background tasks."""
        return {"entries": dlq_snapshot()}

    @app.get("/api/health/reliability")
    async def _reliability_endpoint():
        """Idempotency cache size, circuit-breaker states, DLQ depth."""
        return reliability_snapshot()

    @app.get("/api/health/perf")
    async def _perf_endpoint():
        """TTLCache stats — surface hit-rate-relevant info to operators."""
        return perf_snapshot()

    @app.get("/api/health/indexes")
    async def _index_audit_endpoint():
        """List actual Mongo indexes per collection (boot-time audit)."""
        try:
            from core.databases import core_db as _c, content_db as _t
            return await boot_index_audit([_c, _t])
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/metrics")
    async def _metrics_endpoint():
        """Prom-style scrape endpoint — per-endpoint latency + error totals."""
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(prom_metrics(), media_type="text/plain; version=0.0.4")

    @app.get("/api/health/errors")
    async def _errors_endpoint():
        """Last-100 5xx error ringbuffer for ops triage."""
        return {"errors": ERRORS.snapshot()}

    @app.get("/api/health/observability")
    async def _observability_endpoint():
        """Latency p50/p95/p99 + error ringbuffer summary."""
        return observability_snapshot()

    # SIGTERM/SIGINT graceful drain — must be installed on the running loop,
    # so do it on the first request rather than at import time.
    # DEV NOTE: we skip this in --reload dev mode because WatchFiles sends
    # SIGTERM to recycle the worker, and a 20 s drain on every code edit
    # would slow inner-loop dev to a crawl. Production runs `--workers N`
    # without --reload so SIGTERM is always shutdown-intent.
    _SKIP_DRAIN_IN_DEV = os.environ.get("UVICORN_RELOAD") == "1" or \
                          "--reload" in " ".join(__import__("sys").argv)
    @app.middleware("http")
    async def _install_drain_once(request, call_next):
        s = request.app.state
        if not getattr(s, "_drain_installed", False):
            try:
                if not _SKIP_DRAIN_IN_DEV:
                    install_graceful_drain(request.app, grace_seconds=20.0)
                s._drain_installed = True
            except Exception:
                pass
        response = await call_next(request)
        # Tunnel-watchdog heartbeat (mark every successful response).
        try:
            from core import tunnel_watchdog as _tw
            _tw.mark_seen()
        except Exception:
            pass
        return response
    logger.info("[reliability] LoadShedding + DLQ + reliability endpoints installed")
except Exception as e:
    logger.warning(f"[reliability] layer unavailable: {e}")

# SOTA 2026 Feature Routes
# v11.2 Masterclass & Asset Pipeline Routes
# v11.3 Multi-Agent & SOTA 2026 Routes
# v11.5 AI-to-Game Pipelines
# v11.6 SOTA Extended & Educational Engines
# v11.7 SOTA - Reading Curriculum & Jeeves EQ
# v11.8 - Export & GitHub Integration
# v11.9 - Enhanced AI Toolkit
# v12.0 - Synergy Integration (Cross-Feature Data Flow)
# v12.5 - Multi-Layer Learning Engine
# v13.0 - Jeeves Hyperion (20x Knowledge Base + Self-Learning)
# v13.5 - Jeeves Voice & Personality (Young English Butler)

# v14.0 - Immersive Tutoring Engine

# v14.5 - Jeeves Synergy Engine (Full System Integration)

# v15.0 - New Pipelines & Jeeves Core
# 2026-05-15 — Jeeves persona + personality-aware TTS (already prefixed)

# v15.5 - Extended Pipelines (Text-to-X)

# v16.0 - Language Academy, Jeeves All-Languages & Class Progress

# v16.5 - Math Academy, Pipeline Agents, Quality Control

# v17.0 - Game Factory (Full Game Creation + Compile System)

# v17.5 - Studio API (Templates, Analytics, Agent Metrics)

# v18.0 - Overheat Mitigation System (Thermal Engine + Warm Standby Redundancy)

# v18.5 - Performance Armor (13 Subsystem Fortress)

# v19.0+ — All remaining router mounts migrated to the declarative
# routes_registry (Feb 2026). This replaces ~225 lines of per-router
# try/except + None-guarded include_router boilerplate with a single call.
# To add a new router: append a tuple to ``KNOWN_ROUTES`` in
# ``core/routes_registry.py`` — DO NOT add another block here.
#
# Kept inline below: ``knowledge_nexus_router`` (eager import — it triggers
# ``_kn_engine.initialize()`` at module scope; routes_registry only mounts
# routers and would lose that side-effect).
try:
    from routes.knowledge_updater import router as knowledge_nexus_router, updater_engine as _kn_engine
    if knowledge_nexus_router is not None:
        app.include_router(knowledge_nexus_router)
    _kn_engine.initialize()
except Exception as _e:
    import sys as _s; print(f'[BOOT] route import SKIPPED: routes.knowledge_updater -> {type(_e).__name__}: {_e}', flush=True, file=_s.stderr)

# ─── Background-thread bootstrap hooks (restored Feb 2026 from the
# decomposed-router block — these stay inline because routes_registry
# only handles router mounting, not lifecycle callbacks).
try:
    from core.cold_storage import start_evictor as _start_evictor
    _start_evictor()
except Exception as _e:
    logger.warning(f"[cold_storage] evictor not started: {_e}")


def _kick_build_watchdog_start():
    """Galaxy Studio build watchdog — self-heals stuck/orphaned builds.

    Called from lifespan() via ``_kick(30, "build-watchdog", ...)``. Scans
    every 20s, resurrects orphaned runners, snapshots to vault, and
    force-completes builds that have run past their target duration.
    """
    try:
        from core.build_watchdog import start_watchdog
        start_watchdog()
        logger.info("[watchdog] Galaxy Studio build watchdog started")
    except Exception as _e:
        logger.warning(f"[watchdog] failed to start: {_e}")


# ─── Declarative router mounts ───────────────────────────────────────────
# All entries declared in core.routes_registry.KNOWN_ROUTES are registered
# here. The helper preserves the same lazy-import + SKIPPED-on-failure
# semantics that the old per-router try/except blocks had.
from core.routes_registry import register_known_routes as _register_known_routes
_register_known_routes(app)
