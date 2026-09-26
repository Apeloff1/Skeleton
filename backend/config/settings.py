"""
Configuration settings for CodeDock Quantum Nexus
All environment-specific settings should be loaded here
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

# =============================================================================
# System Version & Build Info
# =============================================================================
SYSTEM_VERSION = "10.0.0"
SYSTEM_CODENAME = "CS Bible Edition"
SYSTEM_BUILD = "2026.02.22-PRODUCTION"
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
    "grok_enhanced_prompts",
    "cs_bible_15_year_curriculum",
    "multiplayer_collaboration",
    "quantum_compiler_suite",
    "ultimate_hub"
]

# =============================================================================
# Database Configuration
# =============================================================================
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'codedock')

# MongoDB Pool Settings (Production-optimized with resilient timeouts)
MONGO_POOL_CONFIG = {
    "maxPoolSize": 100,
    "minPoolSize": 10,
    "maxIdleTimeMS": 45000,
    "serverSelectionTimeoutMS": 30000,
    "connectTimeoutMS": 20000,
    "socketTimeoutMS": 60000,
    "retryWrites": True,
    "retryReads": True
}

# =============================================================================
# API Configuration
# =============================================================================
API_PREFIX = "/api"
API_VERSION = "v10"

# CORS Settings. Wildcard origins and credentialed requests are incompatible
# in browsers, so credentials are enabled only for an explicit origin list.
_cors_env = os.environ.get("CORS_ORIGINS", "*").strip()
CORS_ORIGINS = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env not in {"", "*"}
    else ["*"]
)
CORS_ALLOW_CREDENTIALS = CORS_ORIGINS != ["*"]
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]

# =============================================================================
# Execution Limits
# =============================================================================
DEFAULT_EXECUTION_TIMEOUT = 10  # seconds
MAX_EXECUTION_TIMEOUT = 60  # seconds
DEFAULT_MEMORY_LIMIT_MB = 256
MAX_MEMORY_LIMIT_MB = 1024

# =============================================================================
# AI Configuration
# =============================================================================
# Provider credentials are owned exclusively by skeleton/provider_runtime.py.
EMERGENT_LLM_KEY = ""  # retired compatibility sentinel; never loads secrets
DEFAULT_AI_MODEL = "gpt-4o"
AI_TIMEOUT = 30  # seconds

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# =============================================================================
# Feature Flags
# =============================================================================
FEATURE_FLAGS = {
    "teaching_mode": True,
    "advanced_panel": True,
    "ai_suggestions": True,
    "custom_languages": True,
    "expansion_dock": True,
    "experimental": False,
    "streaming_output": False,
    "collaborative": True,
    "cloud_sync": False
}
