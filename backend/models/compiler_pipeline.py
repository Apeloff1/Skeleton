"""
models/compiler_pipeline.py — Pydantic models for compiler pipeline.

Extracted from server.py (Feb 2026 Phase-9). Pure-shape data classes,
no runtime logic. server.py keeps back-compat shims so existing imports
(`from server import CompilationRequest, OptimizerResult, ...`) continue
to work.
"""
from __future__ import annotations

import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from models.enums import LanguageType


class CompilerStage(BaseModel):
    id: str
    name: str
    short_name: str
    status: str = "pending"
    duration_ms: float = 0.0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[str] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)

class CompilationRequest(BaseModel):
    code: str
    language: LanguageType
    sanitizers: List[str] = Field(default_factory=list, max_length=50)
    optimizers: List[str] = Field(default_factory=list, max_length=50)
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
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = 0.0

class OptimizerResult(BaseModel):
    type: str
    applied: bool
    improvements: Dict[str, Any] = Field(default_factory=dict)
    before_metrics: Dict[str, Any] = Field(default_factory=dict)
    after_metrics: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[str] = Field(default_factory=list)

class PipelineStage(BaseModel):
    id: str
    name: str
    short_name: str
    description: str
    icon: str
    color: str
    status: str = "pending"
    duration_ms: float = 0.0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    details: List[str] = Field(default_factory=list)

class CompilationResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    success: bool
    language: str
    stages: List[PipelineStage] = Field(default_factory=list)
    sanitizer_results: List[SanitizerResult] = Field(default_factory=list)
    optimizer_results: List[OptimizerResult] = Field(default_factory=list)
    ir_code: Optional[str] = None
    assembly_code: Optional[str] = None
    binary_size: Optional[int] = None
    total_time_ms: float = 0.0
    agentic_analysis: Optional[Dict[str, Any]] = None
    micro_test_results: Optional[Dict[str, Any]] = None
    performance_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)




__all__ = [
    "CompilerStage", "CompilationRequest", "SanitizerResult",
    "OptimizerResult", "PipelineStage", "CompilationResponse",
]
