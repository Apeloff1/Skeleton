"""
models/code_runtime.py — Pydantic models for code execution & AI assist.

Extracted from server.py (Feb 2026 Phase-9). Pure-shape data classes,
no runtime logic. server.py keeps back-compat shims so existing imports
(`from server import ExecutionMetrics, CodeFile, AIAssistRequest, ...`)
continue to work.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Phase-9 (Feb 2026): CodeComplexity + AIAssistantMode enums still live
# in server.py. Pydantic v1 needs them resolved at class-body time. We
# import lazily via a try/except so this module is also importable
# standalone for tests / docs generation.
try:
    from server import (
        CodeComplexity, AIAssistantMode, LanguageType,
        ExecutionStatus, SecurityLevel, TutorialStep,
    )
except ImportError:
    # Defensive fallback when this module is parsed before server.py
    # has defined the enums (e.g. tools-only imports). The real values
    # are re-bound the next time server.py loads.
    from enum import Enum
    class CodeComplexity(str, Enum):
        TRIVIAL = "trivial"
    class AIAssistantMode(str, Enum):
        EXPLAIN = "explain"
    class LanguageType(str, Enum):
        PYTHON = "python"
    class ExecutionStatus(str, Enum):
        PENDING = "pending"
    class SecurityLevel(str, Enum):
        SAFE = "safe"
    class TutorialStep(str, Enum):
        WELCOME = "welcome"


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



__all__ = [
    "ExecutionMetrics", "SecurityReport", "CodeAnalysis", "ExecutionResult",
    "CodeExecutionRequest", "CodeExecutionResponse",
    "AIAssistRequest", "AIAssistResponse",
    "CodeFile", "UserPreferences", "LanguageAddon",
    "TutorialProgress", "AdvancedSettings",
]
