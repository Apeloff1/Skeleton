"""
╔══════════════════════════════════════════════════════════════════════════════╗
║    TEXT-TO-HARDWARE & OPTIMIZATION PIPELINE v15.5 - AI PERFORMANCE           ║
║                                                                              ║
║  Generate hardware optimization with LLM integration:                        ║
║  • AI platform-specific optimizations                                        ║
║  • Intelligent performance profiling                                         ║
║  • Smart memory management                                                   ║
║  • AI GPU optimization                                                       ║
║  • Adaptive cross-platform support                                           ║
║  • Intelligent scalability systems                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
import uuid

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/hardware-optimization", tags=["Text-to-Hardware & Optimization v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class Platform(str, Enum):
    PC = "pc"
    PS5 = "ps5"
    XBOX_SERIES = "xbox_series"
    NINTENDO_SWITCH = "nintendo_switch"
    MOBILE_IOS = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    VR = "vr"
    CLOUD = "cloud"


class QualityTier(str, Enum):
    ULTRA_LOW = "ultra_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ULTRA = "ultra"
    EXTREME = "extreme"


class OptimizationType(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    BATTERY = "battery"


class GraphicsAPI(str, Enum):
    DIRECTX12 = "directx12"
    VULKAN = "vulkan"
    METAL = "metal"
    OPENGL = "opengl"
    WEBGPU = "webgpu"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class PlatformOptimizationRequest(BaseModel):
    platform: Platform
    target_fps: int = Field(60, ge=30, le=240)
    target_resolution: str = "1080p"
    quality_tier: QualityTier = QualityTier.HIGH


class PerformanceProfileRequest(BaseModel):
    profile_name: str
    target_platforms: List[Platform] = [Platform.PC]
    metrics: List[str] = ["fps", "frame_time", "memory", "gpu_utilization"]
    sampling_rate_hz: int = Field(60, ge=1, le=1000)


class MemoryBudgetRequest(BaseModel):
    total_budget_mb: int = Field(4096, ge=512, le=32768)
    streaming_enabled: bool = True
    pool_allocation: bool = True
    garbage_collection: Literal["manual", "incremental", "generational"] = "incremental"


class GPUOptimizationRequest(BaseModel):
    graphics_api: GraphicsAPI = GraphicsAPI.VULKAN
    ray_tracing: bool = False
    mesh_shaders: bool = False
    variable_rate_shading: bool = True
    async_compute: bool = True


class ScalabilityRequest(BaseModel):
    min_spec: QualityTier = QualityTier.LOW
    max_spec: QualityTier = QualityTier.ULTRA
    auto_detect: bool = True
    dynamic_scaling: bool = True
    target_frame_time_ms: float = Field(16.67, ge=4.0, le=33.33)


# ============================================================================
# HARDWARE OPTIMIZATION GENERATOR
# ============================================================================

class HardwareOptimizationGenerator:
    """Advanced hardware optimization generation engine."""

    @staticmethod
    def generate_platform_optimization(request: PlatformOptimizationRequest) -> Dict[str, Any]:
        """Generate platform-specific optimization profile."""
        platform_specs = {
            Platform.PC: {
                "api": "dx12_vulkan",
                "max_resolution": "8k",
                "ray_tracing": True,
                "variable_specs": True
            },
            Platform.PS5: {
                "api": "gnm",
                "max_resolution": "4k",
                "ray_tracing": True,
                "ssd_streaming": True
            },
            Platform.XBOX_SERIES: {
                "api": "dx12",
                "max_resolution": "4k",
                "ray_tracing": True,
                "quick_resume": True
            },
            Platform.NINTENDO_SWITCH: {
                "api": "nvn",
                "max_resolution": "1080p_docked",
                "ray_tracing": False,
                "portable_mode": True
            },
            Platform.MOBILE_IOS: {
                "api": "metal",
                "max_resolution": "1440p",
                "ray_tracing": True,
                "thermal_throttling": True
            },
            Platform.MOBILE_ANDROID: {
                "api": "vulkan",
                "max_resolution": "1440p",
                "ray_tracing": False,
                "fragmentation": True
            },
            Platform.VR: {
                "api": "vulkan_openxr",
                "target_fps": 90,
                "stereo_rendering": True,
                "foveated_rendering": True
            }
        }
        
        specs = platform_specs.get(request.platform, platform_specs[Platform.PC])
        
        quality_settings = {
            QualityTier.ULTRA_LOW: {"shadow": "off", "aa": "none", "textures": "low", "effects": "minimal"},
            QualityTier.LOW: {"shadow": "low", "aa": "fxaa", "textures": "low", "effects": "low"},
            QualityTier.MEDIUM: {"shadow": "medium", "aa": "smaa", "textures": "medium", "effects": "medium"},
            QualityTier.HIGH: {"shadow": "high", "aa": "taa", "textures": "high", "effects": "high"},
            QualityTier.ULTRA: {"shadow": "ultra", "aa": "taa", "textures": "ultra", "effects": "ultra"},
            QualityTier.EXTREME: {"shadow": "rt", "aa": "dlss", "textures": "ultra", "effects": "cinematic"}
        }
        
        return {
            "id": str(uuid.uuid4()),
            "platform": request.platform.value,
            "specs": specs,
            "targets": {
                "fps": request.target_fps,
                "resolution": request.target_resolution,
                "frame_time_ms": 1000 / request.target_fps
            },
            "quality": quality_settings[request.quality_tier],
            "optimizations": {
                "occlusion_culling": True,
                "lod_system": True,
                "texture_streaming": True,
                "shader_warmup": True,
                "instancing": True
            },
            "platform_specific": specs
        }

    @staticmethod
    def generate_performance_profile(request: PerformanceProfileRequest) -> Dict[str, Any]:
        """Generate performance profiling configuration."""
        metric_configs = {
            "fps": {"unit": "frames/s", "warning": 30, "critical": 20},
            "frame_time": {"unit": "ms", "warning": 33.33, "critical": 50},
            "memory": {"unit": "MB", "warning": 0.8, "critical": 0.95},
            "gpu_utilization": {"unit": "%", "warning": 95, "critical": 99},
            "cpu_utilization": {"unit": "%", "warning": 90, "critical": 98},
            "draw_calls": {"unit": "count", "warning": 5000, "critical": 10000},
            "triangles": {"unit": "count", "warning": 5000000, "critical": 10000000}
        }
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.profile_name,
            "platforms": [p.value for p in request.target_platforms],
            "sampling": {
                "rate_hz": request.sampling_rate_hz,
                "buffer_seconds": 60,
                "averaging_window": 1.0
            },
            "metrics": {
                metric: metric_configs.get(metric, {"unit": "unknown"})
                for metric in request.metrics
            },
            "capture": {
                "gpu_trace": True,
                "cpu_trace": True,
                "memory_snapshot": True,
                "frame_capture": True
            },
            "analysis": {
                "bottleneck_detection": True,
                "regression_tracking": True,
                "trend_analysis": True
            },
            "output": {
                "formats": ["json", "csv", "html"],
                "visualization": True,
                "alerts": True
            }
        }

    @staticmethod
    def generate_memory_budget(request: MemoryBudgetRequest) -> Dict[str, Any]:
        """Generate memory budget allocation."""
        total = request.total_budget_mb
        
        return {
            "id": str(uuid.uuid4()),
            "total_budget_mb": total,
            "allocation": {
                "textures": int(total * 0.4),
                "meshes": int(total * 0.2),
                "audio": int(total * 0.1),
                "scripts": int(total * 0.05),
                "physics": int(total * 0.05),
                "ai": int(total * 0.05),
                "ui": int(total * 0.05),
                "system": int(total * 0.1)
            },
            "streaming": {
                "enabled": request.streaming_enabled,
                "preload_distance": 100,
                "unload_distance": 200,
                "priority_system": True
            },
            "pooling": {
                "enabled": request.pool_allocation,
                "object_pools": ["projectiles", "particles", "effects", "enemies"],
                "defragmentation": "periodic"
            },
            "gc": {
                "strategy": request.garbage_collection,
                "budget_ms": 2.0,
                "incremental_steps": 4
            },
            "monitoring": {
                "warnings": True,
                "leak_detection": True,
                "fragmentation_tracking": True
            }
        }

    @staticmethod
    def generate_gpu_optimization(request: GPUOptimizationRequest) -> Dict[str, Any]:
        """Generate GPU optimization configuration."""
        api_features = {
            GraphicsAPI.DIRECTX12: {
                "bindless": True,
                "mesh_shaders": request.mesh_shaders,
                "raytracing": request.ray_tracing,
                "work_graphs": True
            },
            GraphicsAPI.VULKAN: {
                "bindless": True,
                "mesh_shaders": request.mesh_shaders,
                "raytracing": request.ray_tracing,
                "descriptor_indexing": True
            },
            GraphicsAPI.METAL: {
                "bindless": True,
                "mesh_shaders": request.mesh_shaders,
                "raytracing": request.ray_tracing,
                "tile_based": True
            }
        }
        
        features = api_features.get(request.graphics_api, api_features[GraphicsAPI.VULKAN])
        
        return {
            "id": str(uuid.uuid4()),
            "api": request.graphics_api.value,
            "features": features,
            "rendering": {
                "variable_rate_shading": request.variable_rate_shading,
                "async_compute": request.async_compute,
                "indirect_rendering": True,
                "gpu_culling": True
            },
            "ray_tracing": {
                "enabled": request.ray_tracing,
                "shadows": request.ray_tracing,
                "reflections": request.ray_tracing,
                "gi": request.ray_tracing,
                "denoising": request.ray_tracing
            },
            "batching": {
                "static_batching": True,
                "dynamic_batching": True,
                "gpu_instancing": True,
                "srp_batcher": True
            },
            "pipeline_state": {
                "pso_caching": True,
                "shader_warmup": True,
                "async_compilation": True
            }
        }

    @staticmethod
    def generate_scalability_system(request: ScalabilityRequest) -> Dict[str, Any]:
        """Generate scalability system."""
        quality_tiers = list(QualityTier)
        min_idx = quality_tiers.index(request.min_spec)
        max_idx = quality_tiers.index(request.max_spec)
        available_tiers = quality_tiers[min_idx:max_idx + 1]
        
        return {
            "id": str(uuid.uuid4()),
            "range": {
                "min": request.min_spec.value,
                "max": request.max_spec.value,
                "available_tiers": [t.value for t in available_tiers]
            },
            "auto_detect": {
                "enabled": request.auto_detect,
                "benchmark_on_start": True,
                "hardware_detection": True,
                "adaptive_initial": True
            },
            "dynamic_scaling": {
                "enabled": request.dynamic_scaling,
                "target_frame_time_ms": request.target_frame_time_ms,
                "headroom_ms": 2.0,
                "adjustment_speed": 0.1
            },
            "scalable_features": [
                {"name": "resolution_scale", "range": [0.5, 1.0], "impact": "high"},
                {"name": "shadow_quality", "range": [0, 4], "impact": "high"},
                {"name": "draw_distance", "range": [0.5, 1.0], "impact": "medium"},
                {"name": "foliage_density", "range": [0.25, 1.0], "impact": "medium"},
                {"name": "particle_count", "range": [0.25, 1.0], "impact": "low"},
                {"name": "post_processing", "range": [0, 3], "impact": "low"}
            ],
            "presets": {
                tier.value: {"resolution_scale": 0.5 + (i / len(available_tiers)) * 0.5}
                for i, tier in enumerate(available_tiers)
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Hardware & Optimization Pipeline."""
    return {
        "pipeline": "Text-to-Hardware & Optimization Pipeline v15.5",
        "description": "Generate hardware optimization systems from natural language",
        "capabilities": [
            "Platform-specific optimizations",
            "Performance profiling",
            "Memory budget management",
            "GPU optimization",
            "Scalability systems"
        ],
        "platforms": [p.value for p in Platform],
        "quality_tiers": [q.value for q in QualityTier],
        "graphics_apis": [g.value for g in GraphicsAPI]
    }


@router.post("/platform/generate")
async def generate_platform_optimization(request: PlatformOptimizationRequest):
    """Generate platform optimization profile."""
    return {
        "success": True,
        "platform_optimization": HardwareOptimizationGenerator.generate_platform_optimization(request)
    }


@router.post("/profiling/generate")
async def generate_performance_profile(request: PerformanceProfileRequest):
    """Generate performance profile."""
    return {
        "success": True,
        "performance_profile": HardwareOptimizationGenerator.generate_performance_profile(request)
    }


@router.post("/memory/generate")
async def generate_memory_budget(request: MemoryBudgetRequest):
    """Generate memory budget."""
    return {
        "success": True,
        "memory_budget": HardwareOptimizationGenerator.generate_memory_budget(request)
    }


@router.post("/gpu/generate")
async def generate_gpu_optimization(request: GPUOptimizationRequest):
    """Generate GPU optimization."""
    return {
        "success": True,
        "gpu_optimization": HardwareOptimizationGenerator.generate_gpu_optimization(request)
    }


@router.post("/scalability/generate")
async def generate_scalability_system(request: ScalabilityRequest):
    """Generate scalability system."""
    return {
        "success": True,
        "scalability_system": HardwareOptimizationGenerator.generate_scalability_system(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIOptimizationRequest(BaseModel):
    """Request for AI-powered optimization profile"""
    target_platform: str = Field(..., description="PC, PS5, Xbox, Mobile, etc.")
    target_fps: int = Field(default=60, description="Target frame rate")


@router.post("/ai/optimization/profile")
async def ai_generate_optimization_profile(request: AIOptimizationRequest):
    """
    Generate hardware optimization recommendations using AI (GPT-4o).
    Creates platform-specific performance profiles.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_optimization_profile(
            target_platform=request.target_platform,
            target_fps=request.target_fps
        )
        
        if result["success"]:
            return {
                "success": True,
                "optimization_profile": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "optimization_profile": {
                    "platform": request.target_platform,
                    "target_fps": request.target_fps,
                    "template": "basic_optimization"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI optimization profile generation failed: {str(e)}")
