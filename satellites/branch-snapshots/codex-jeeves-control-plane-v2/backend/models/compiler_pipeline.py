"""
models/compiler_pipeline.py — Pydantic models for compiler pipeline.

Extracted from server.py (Feb 2026 Phase-9). Pure-shape data classes,
no runtime logic. server.py keeps back-compat shims so existing imports
(`from server import CompilationRequest, OptimizerResult, ...`) continue
to work.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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




__all__ = [
    "CompilerStage", "CompilationRequest", "SanitizerResult",
    "OptimizerResult", "PipelineStage", "CompilationResponse",
]
