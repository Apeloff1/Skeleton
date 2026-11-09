"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         TEXT-TO-VFX & MATERIALS PIPELINE v15.5 - AI VISUAL EFFECTS           ║
║                                                                              ║
║  Generate visual effects and materials with LLM integration:                 ║
║  • AI-powered particle systems (fire, smoke, magic, weather)                 ║
║  • Intelligent shader graphs & material definitions                          ║
║  • Smart post-processing effects                                             ║
║  • AI lighting setups                                                        ║
║  • Adaptive screen-space effects                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Tuple
from enum import Enum
import uuid
import random
import math

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/vfx-materials", tags=["Text-to-VFX & Materials v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class ParticleType(str, Enum):
    FIRE = "fire"
    SMOKE = "smoke"
    SPARKS = "sparks"
    MAGIC = "magic"
    RAIN = "rain"
    SNOW = "snow"
    DUST = "dust"
    EXPLOSION = "explosion"
    BLOOD = "blood"
    LEAVES = "leaves"
    BUBBLES = "bubbles"
    LIGHTNING = "lightning"


class MaterialType(str, Enum):
    PBR_STANDARD = "pbr_standard"
    PBR_METALLIC = "pbr_metallic"
    UNLIT = "unlit"
    TOON = "toon"
    SUBSURFACE = "subsurface"
    GLASS = "glass"
    WATER = "water"
    HOLOGRAM = "hologram"
    EMISSION = "emission"
    TERRAIN = "terrain"


class PostProcessEffect(str, Enum):
    BLOOM = "bloom"
    DOF = "depth_of_field"
    MOTION_BLUR = "motion_blur"
    VIGNETTE = "vignette"
    COLOR_GRADING = "color_grading"
    CHROMATIC_ABERRATION = "chromatic_aberration"
    FILM_GRAIN = "film_grain"
    AMBIENT_OCCLUSION = "ambient_occlusion"
    SCREEN_SPACE_REFLECTIONS = "screen_space_reflections"
    VOLUMETRIC_LIGHTING = "volumetric_lighting"


class BlendMode(str, Enum):
    OPAQUE = "opaque"
    TRANSPARENT = "transparent"
    ADDITIVE = "additive"
    MULTIPLY = "multiply"
    ALPHA_BLEND = "alpha_blend"
    PREMULTIPLIED = "premultiplied"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class ParticleSystemRequest(BaseModel):
    effect_type: ParticleType
    description: Optional[str] = None
    intensity: float = Field(1.0, ge=0.1, le=10.0)
    duration: float = Field(2.0, ge=0.1, le=60.0)
    looping: bool = True
    world_space: bool = True
    color_over_lifetime: bool = True


class MaterialRequest(BaseModel):
    material_type: MaterialType
    description: Optional[str] = None
    base_color: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    metallic: float = Field(0.0, ge=0.0, le=1.0)
    roughness: float = Field(0.5, ge=0.0, le=1.0)
    normal_strength: float = Field(1.0, ge=0.0, le=2.0)
    emission_enabled: bool = False
    emission_color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    emission_intensity: float = 1.0


class ShaderGraphRequest(BaseModel):
    name: str
    shader_type: Literal["vertex", "fragment", "compute", "full"] = "full"
    features: List[str] = []
    target_platform: Literal["universal", "mobile", "desktop", "vr"] = "universal"


class PostProcessRequest(BaseModel):
    effects: List[PostProcessEffect]
    profile_name: str = "default"
    hdr_enabled: bool = True
    anti_aliasing: Literal["none", "fxaa", "smaa", "taa", "msaa"] = "taa"


class LightingSetupRequest(BaseModel):
    environment: Literal["outdoor_day", "outdoor_night", "indoor", "studio", "dramatic", "horror"]
    time_of_day: Optional[float] = None  # 0-24 hours
    weather: Optional[Literal["clear", "cloudy", "rain", "fog", "storm"]] = "clear"
    ambient_intensity: float = Field(1.0, ge=0.0, le=5.0)


# ============================================================================
# VFX GENERATORS
# ============================================================================

class VFXGenerator:
    """Advanced VFX and Materials generation engine."""

    @staticmethod
    def generate_particle_system(request: ParticleSystemRequest) -> Dict[str, Any]:
        """Generate a complete particle system definition."""
        
        # Base configurations for each particle type
        particle_configs = {
            ParticleType.FIRE: {
                "emission_rate": 50 * request.intensity,
                "lifetime": (0.5, 1.5),
                "start_size": (0.3, 0.8),
                "end_size": (0.1, 0.3),
                "start_color": (1.0, 0.6, 0.1, 1.0),
                "end_color": (0.8, 0.2, 0.0, 0.0),
                "velocity": (0, 3, 0),
                "velocity_variance": (0.5, 1, 0.5),
                "gravity": -0.5,
                "texture": "fire_particle",
                "blend_mode": BlendMode.ADDITIVE.value,
                "sub_emitters": ["sparks", "smoke"]
            },
            ParticleType.SMOKE: {
                "emission_rate": 20 * request.intensity,
                "lifetime": (2.0, 4.0),
                "start_size": (0.5, 1.0),
                "end_size": (2.0, 4.0),
                "start_color": (0.3, 0.3, 0.3, 0.8),
                "end_color": (0.5, 0.5, 0.5, 0.0),
                "velocity": (0, 1, 0),
                "velocity_variance": (0.3, 0.5, 0.3),
                "gravity": -0.1,
                "texture": "smoke_particle",
                "blend_mode": BlendMode.ALPHA_BLEND.value,
                "noise": {"enabled": True, "strength": 0.5, "frequency": 1.0}
            },
            ParticleType.MAGIC: {
                "emission_rate": 100 * request.intensity,
                "lifetime": (0.8, 1.5),
                "start_size": (0.1, 0.3),
                "end_size": (0.0, 0.1),
                "start_color": (0.5, 0.8, 1.0, 1.0),
                "end_color": (0.8, 0.5, 1.0, 0.0),
                "velocity": (0, 0, 0),
                "velocity_variance": (2, 2, 2),
                "gravity": 0,
                "texture": "magic_particle",
                "blend_mode": BlendMode.ADDITIVE.value,
                "orbit": {"enabled": True, "radius": 1.0, "speed": 2.0}
            },
            ParticleType.RAIN: {
                "emission_rate": 500 * request.intensity,
                "lifetime": (1.0, 2.0),
                "start_size": (0.02, 0.05),
                "end_size": (0.02, 0.05),
                "start_color": (0.7, 0.8, 0.9, 0.6),
                "end_color": (0.7, 0.8, 0.9, 0.3),
                "velocity": (0, -15, 0),
                "velocity_variance": (0.5, 2, 0.5),
                "gravity": 0,
                "texture": "rain_drop",
                "blend_mode": BlendMode.ALPHA_BLEND.value,
                "collision": {"enabled": True, "bounce": 0.0, "spawn_splash": True}
            },
            ParticleType.EXPLOSION: {
                "emission_rate": 0,  # Burst
                "burst": {"count": int(200 * request.intensity), "time": 0},
                "lifetime": (0.5, 1.5),
                "start_size": (1.0, 2.0),
                "end_size": (3.0, 5.0),
                "start_color": (1.0, 0.8, 0.3, 1.0),
                "end_color": (0.3, 0.1, 0.0, 0.0),
                "velocity": (0, 0, 0),
                "velocity_variance": (10, 10, 10),
                "gravity": -2,
                "texture": "explosion_particle",
                "blend_mode": BlendMode.ADDITIVE.value,
                "sub_emitters": ["debris", "smoke", "sparks"]
            }
        }

        config = particle_configs.get(request.effect_type, particle_configs[ParticleType.MAGIC])

        return {
            "id": str(uuid.uuid4()),
            "type": "particle_system",
            "effect_type": request.effect_type.value,
            "main": {
                "duration": request.duration,
                "looping": request.looping,
                "start_delay": 0,
                "start_lifetime": config["lifetime"],
                "start_speed": 1.0,
                "start_size": config["start_size"],
                "start_rotation": (0, 360),
                "simulation_space": "world" if request.world_space else "local",
                "max_particles": 1000,
                "play_on_awake": True
            },
            "emission": {
                "rate_over_time": config["emission_rate"],
                "rate_over_distance": 0,
                "bursts": [config.get("burst")] if "burst" in config else []
            },
            "shape": {
                "type": "cone",
                "angle": 25,
                "radius": 0.5,
                "emit_from": "base"
            },
            "velocity_over_lifetime": {
                "linear": config["velocity"],
                "orbital": config.get("orbit", {}).get("speed", 0)
            },
            "color_over_lifetime": {
                "enabled": request.color_over_lifetime,
                "gradient": [
                    {"time": 0.0, "color": config["start_color"]},
                    {"time": 1.0, "color": config["end_color"]}
                ]
            },
            "size_over_lifetime": {
                "enabled": True,
                "curve": "ease_out",
                "start": config["start_size"][1],
                "end": config["end_size"][1]
            },
            "renderer": {
                "render_mode": "billboard",
                "material": config["texture"],
                "blend_mode": config["blend_mode"],
                "sort_mode": "by_distance",
                "cast_shadows": False,
                "receive_shadows": False
            },
            "sub_emitters": config.get("sub_emitters", []),
            "collision": config.get("collision", {"enabled": False}),
            "noise": config.get("noise", {"enabled": False})
        }

    @staticmethod
    def generate_material(request: MaterialRequest) -> Dict[str, Any]:
        """Generate a PBR material definition."""
        
        material_presets = {
            MaterialType.PBR_STANDARD: {
                "shader": "Universal/Lit",
                "surface_type": "opaque",
                "workflow": "metallic"
            },
            MaterialType.GLASS: {
                "shader": "Universal/Lit",
                "surface_type": "transparent",
                "workflow": "specular",
                "ior": 1.5,
                "refraction": True
            },
            MaterialType.WATER: {
                "shader": "Universal/Water",
                "surface_type": "transparent",
                "tessellation": True,
                "displacement": True,
                "caustics": True
            },
            MaterialType.TOON: {
                "shader": "Universal/Toon",
                "surface_type": "opaque",
                "cel_shading_steps": 3,
                "outline": True
            },
            MaterialType.HOLOGRAM: {
                "shader": "Universal/Hologram",
                "surface_type": "transparent",
                "scanlines": True,
                "glitch": True,
                "fresnel": True
            },
            MaterialType.SUBSURFACE: {
                "shader": "Universal/Lit",
                "surface_type": "opaque",
                "subsurface_scattering": True,
                "translucency": 0.5
            }
        }

        preset = material_presets.get(request.material_type, material_presets[MaterialType.PBR_STANDARD])

        material = {
            "id": str(uuid.uuid4()),
            "type": "material",
            "name": f"Mat_{request.material_type.value}_{str(uuid.uuid4())[:6]}",
            "shader": preset["shader"],
            "render_queue": 2000 if preset["surface_type"] == "opaque" else 3000,
            "properties": {
                "base_color": {
                    "type": "color",
                    "value": request.base_color,
                    "texture": None
                },
                "metallic": {
                    "type": "float",
                    "value": request.metallic,
                    "texture": None
                },
                "roughness": {
                    "type": "float",
                    "value": request.roughness,
                    "texture": None
                },
                "normal": {
                    "type": "normal_map",
                    "strength": request.normal_strength,
                    "texture": None
                },
                "ambient_occlusion": {
                    "type": "float",
                    "value": 1.0,
                    "texture": None
                },
                "height": {
                    "type": "float",
                    "value": 0.0,
                    "texture": None,
                    "parallax_enabled": False
                }
            },
            "emission": {
                "enabled": request.emission_enabled,
                "color": request.emission_color,
                "intensity": request.emission_intensity,
                "texture": None
            },
            "surface": preset["surface_type"],
            "blend_mode": "alpha" if preset["surface_type"] == "transparent" else "opaque",
            "cull_mode": "back",
            "alpha_clip": False,
            "receive_shadows": True,
            "keywords": [],
            "custom_properties": {k: v for k, v in preset.items() if k not in ["shader", "surface_type", "workflow"]}
        }

        return material

    @staticmethod
    def generate_shader_graph(request: ShaderGraphRequest) -> Dict[str, Any]:
        """Generate a shader graph definition."""
        
        nodes = []
        connections = []
        
        # Master node
        nodes.append({
            "id": "master",
            "type": "PBRMasterNode",
            "position": (800, 300),
            "inputs": ["Albedo", "Normal", "Metallic", "Smoothness", "Emission", "Alpha"]
        })

        # Base texture sample
        nodes.append({
            "id": "base_texture",
            "type": "SampleTexture2D",
            "position": (200, 200),
            "inputs": ["UV", "Texture"],
            "outputs": ["RGBA", "R", "G", "B", "A"]
        })
        connections.append({"from": "base_texture.RGBA", "to": "master.Albedo"})

        # Normal map
        nodes.append({
            "id": "normal_texture",
            "type": "SampleTexture2D",
            "position": (200, 400),
            "inputs": ["UV", "Texture"],
            "outputs": ["RGBA"]
        })
        nodes.append({
            "id": "normal_unpack",
            "type": "NormalUnpack",
            "position": (400, 400),
            "inputs": ["In"],
            "outputs": ["Out"]
        })
        connections.append({"from": "normal_texture.RGBA", "to": "normal_unpack.In"})
        connections.append({"from": "normal_unpack.Out", "to": "master.Normal"})

        # Feature nodes based on request
        if "fresnel" in request.features:
            nodes.append({
                "id": "fresnel",
                "type": "FresnelEffect",
                "position": (400, 600),
                "inputs": ["Normal", "ViewDir", "Power"],
                "outputs": ["Out"],
                "properties": {"power": 3.0}
            })

        if "dissolve" in request.features:
            nodes.append({
                "id": "noise",
                "type": "SimpleNoise",
                "position": (200, 700),
                "inputs": ["UV", "Scale"],
                "outputs": ["Out"]
            })
            nodes.append({
                "id": "dissolve_step",
                "type": "Step",
                "position": (400, 700),
                "inputs": ["Edge", "In"],
                "outputs": ["Out"]
            })

        if "triplanar" in request.features:
            nodes.append({
                "id": "triplanar",
                "type": "TriplanarMapping",
                "position": (100, 200),
                "inputs": ["Texture", "Position", "Normal", "Blend"],
                "outputs": ["RGBA"]
            })

        return {
            "id": str(uuid.uuid4()),
            "type": "shader_graph",
            "name": request.name,
            "shader_type": request.shader_type,
            "target_platform": request.target_platform,
            "graph": {
                "nodes": nodes,
                "connections": connections,
                "properties": [
                    {"name": "_BaseMap", "type": "Texture2D", "default": "white"},
                    {"name": "_NormalMap", "type": "Texture2D", "default": "bump"},
                    {"name": "_Metallic", "type": "Float", "default": 0.0, "range": (0, 1)},
                    {"name": "_Smoothness", "type": "Float", "default": 0.5, "range": (0, 1)},
                    {"name": "_EmissionColor", "type": "Color", "default": (0, 0, 0, 1)}
                ],
                "keywords": request.features
            },
            "preview": "sphere",
            "code_template": VFXGenerator._generate_shader_code(request)
        }

    @staticmethod
    def _generate_shader_code(request: ShaderGraphRequest) -> str:
        """Generate HLSL/GLSL shader code template."""
        return f'''
// Auto-generated shader: {request.name}
// Target: {request.target_platform}

Shader "Custom/{request.name}"
{{
    Properties
    {{
        _BaseMap ("Base Map", 2D) = "white" {{}}
        _BaseColor ("Base Color", Color) = (1,1,1,1)
        _NormalMap ("Normal Map", 2D) = "bump" {{}}
        _Metallic ("Metallic", Range(0,1)) = 0.0
        _Smoothness ("Smoothness", Range(0,1)) = 0.5
        [HDR] _EmissionColor ("Emission", Color) = (0,0,0,1)
    }}
    
    SubShader
    {{
        Tags {{ "RenderType"="Opaque" "Queue"="Geometry" }}
        
        Pass
        {{
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            
            struct Attributes
            {{
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                float3 normalOS : NORMAL;
                float4 tangentOS : TANGENT;
            }};
            
            struct Varyings
            {{
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionWS : TEXCOORD2;
            }};
            
            Varyings vert(Attributes IN)
            {{
                Varyings OUT;
                OUT.positionCS = TransformObjectToHClip(IN.positionOS.xyz);
                OUT.uv = IN.uv;
                OUT.normalWS = TransformObjectToWorldNormal(IN.normalOS);
                OUT.positionWS = TransformObjectToWorld(IN.positionOS.xyz);
                return OUT;
            }}
            
            half4 frag(Varyings IN) : SV_Target
            {{
                half4 baseMap = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, IN.uv);
                half4 color = baseMap * _BaseColor;
                return color;
            }}
            ENDHLSL
        }}
    }}
}}
'''

    @staticmethod
    def generate_post_process_profile(request: PostProcessRequest) -> Dict[str, Any]:
        """Generate a post-processing profile."""
        
        effect_configs = {
            PostProcessEffect.BLOOM: {
                "threshold": 0.9,
                "intensity": 1.0,
                "scatter": 0.7,
                "tint": (1.0, 1.0, 1.0),
                "high_quality": True,
                "dirt_texture": None,
                "dirt_intensity": 0.0
            },
            PostProcessEffect.DOF: {
                "mode": "bokeh",
                "focus_distance": 10.0,
                "aperture": 5.6,
                "focal_length": 50,
                "blade_count": 5,
                "blade_curvature": 1.0,
                "blade_rotation": 0
            },
            PostProcessEffect.MOTION_BLUR: {
                "mode": "camera",
                "quality": "medium",
                "intensity": 0.5,
                "clamp": 0.05
            },
            PostProcessEffect.COLOR_GRADING: {
                "mode": "high_definition_range",
                "lookup_texture": None,
                "temperature": 0,
                "tint": 0,
                "saturation": 0,
                "contrast": 0,
                "lift": (1, 1, 1, 0),
                "gamma": (1, 1, 1, 0),
                "gain": (1, 1, 1, 0),
                "tone_mapping": "aces"
            },
            PostProcessEffect.VIGNETTE: {
                "color": (0, 0, 0),
                "intensity": 0.3,
                "smoothness": 0.5,
                "rounded": True
            },
            PostProcessEffect.AMBIENT_OCCLUSION: {
                "mode": "scalable_ambient_obscurance",
                "intensity": 1.0,
                "radius": 0.3,
                "quality": "high",
                "full_resolution": True
            },
            PostProcessEffect.VOLUMETRIC_LIGHTING: {
                "enabled": True,
                "intensity": 1.0,
                "quality": "high",
                "max_distance": 100,
                "denoising": True
            }
        }

        effects = []
        for effect in request.effects:
            if effect in effect_configs:
                effects.append({
                    "type": effect.value,
                    "enabled": True,
                    "settings": effect_configs[effect]
                })

        return {
            "id": str(uuid.uuid4()),
            "type": "post_process_profile",
            "name": request.profile_name,
            "hdr": request.hdr_enabled,
            "anti_aliasing": {
                "mode": request.anti_aliasing,
                "quality": "high"
            },
            "effects": effects,
            "global_settings": {
                "exposure_mode": "auto",
                "exposure_compensation": 0,
                "adaptation_speed": 1.0
            }
        }

    @staticmethod
    def generate_lighting_setup(request: LightingSetupRequest) -> Dict[str, Any]:
        """Generate a complete lighting setup."""
        
        presets = {
            "outdoor_day": {
                "sun": {"color": (1.0, 0.96, 0.9), "intensity": 1.5, "angle": (50, 30)},
                "ambient": {"sky_color": (0.5, 0.7, 1.0), "ground_color": (0.3, 0.25, 0.2)},
                "skybox": "procedural_sky",
                "fog": {"enabled": False}
            },
            "outdoor_night": {
                "sun": {"color": (0.4, 0.45, 0.6), "intensity": 0.1, "angle": (-30, 45)},
                "moon": {"color": (0.8, 0.85, 1.0), "intensity": 0.3},
                "ambient": {"sky_color": (0.05, 0.05, 0.1), "ground_color": (0.02, 0.02, 0.03)},
                "skybox": "night_sky",
                "stars": True
            },
            "indoor": {
                "sun": None,
                "ambient": {"color": (0.15, 0.15, 0.15), "intensity": 0.5},
                "point_lights": [
                    {"position": (0, 3, 0), "color": (1.0, 0.95, 0.9), "intensity": 1.0, "range": 10}
                ],
                "gi": {"enabled": True, "bounces": 2}
            },
            "dramatic": {
                "sun": {"color": (1.0, 0.7, 0.4), "intensity": 2.0, "angle": (15, 60)},
                "ambient": {"sky_color": (0.1, 0.1, 0.15), "ground_color": (0.05, 0.03, 0.02)},
                "volumetric": True,
                "god_rays": True
            },
            "horror": {
                "sun": None,
                "ambient": {"color": (0.02, 0.02, 0.03), "intensity": 0.1},
                "fog": {"enabled": True, "density": 0.1, "color": (0.1, 0.1, 0.12)},
                "point_lights": [],
                "flickering": True
            }
        }

        preset = presets.get(request.environment, presets["outdoor_day"])

        # Apply time of day if specified
        if request.time_of_day is not None and preset.get("sun"):
            hour = request.time_of_day
            sun_angle = (90 - abs(hour - 12) * 7.5, (hour - 6) * 15)
            intensity_factor = max(0, 1 - abs(hour - 12) / 12)
            preset["sun"]["angle"] = sun_angle
            preset["sun"]["intensity"] *= intensity_factor

        # Apply weather
        weather_modifiers = {
            "cloudy": {"ambient_mult": 0.7, "sun_mult": 0.5, "fog": {"enabled": True, "density": 0.02}},
            "rain": {"ambient_mult": 0.5, "sun_mult": 0.3, "fog": {"enabled": True, "density": 0.05}},
            "fog": {"ambient_mult": 0.6, "sun_mult": 0.2, "fog": {"enabled": True, "density": 0.15}},
            "storm": {"ambient_mult": 0.3, "sun_mult": 0.1, "fog": {"enabled": True, "density": 0.08}, "lightning": True}
        }

        if request.weather and request.weather != "clear":
            mods = weather_modifiers.get(request.weather, {})
            if preset.get("sun"):
                preset["sun"]["intensity"] *= mods.get("sun_mult", 1)
            preset["fog"] = mods.get("fog", preset.get("fog", {"enabled": False}))

        return {
            "id": str(uuid.uuid4()),
            "type": "lighting_setup",
            "environment": request.environment,
            "time_of_day": request.time_of_day,
            "weather": request.weather,
            "directional_lights": [preset.get("sun")] if preset.get("sun") else [],
            "ambient_lighting": {
                **preset.get("ambient", {}),
                "intensity": request.ambient_intensity
            },
            "skybox": preset.get("skybox", "default"),
            "fog": preset.get("fog", {"enabled": False}),
            "reflection_probes": [
                {"position": (0, 2, 0), "type": "baked", "resolution": 256}
            ],
            "light_probes": {
                "enabled": True,
                "density": "medium"
            },
            "global_illumination": preset.get("gi", {"enabled": False}),
            "special_effects": {
                "volumetric": preset.get("volumetric", False),
                "god_rays": preset.get("god_rays", False),
                "stars": preset.get("stars", False),
                "lightning": preset.get("lightning", False),
                "flickering": preset.get("flickering", False)
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the VFX & Materials Pipeline."""
    return {
        "pipeline": "Text-to-VFX & Materials Pipeline v15.5",
        "description": "Generate visual effects and materials from natural language",
        "capabilities": [
            "Particle systems (fire, smoke, magic, weather)",
            "PBR material generation",
            "Shader graph creation",
            "Post-processing profiles",
            "Lighting setups"
        ],
        "particle_types": [p.value for p in ParticleType],
        "material_types": [m.value for m in MaterialType],
        "post_process_effects": [e.value for e in PostProcessEffect]
    }


@router.post("/particles/generate")
async def generate_particles(request: ParticleSystemRequest):
    """Generate a particle system."""
    return {
        "success": True,
        "particle_system": VFXGenerator.generate_particle_system(request)
    }


@router.post("/material/generate")
async def generate_material(request: MaterialRequest):
    """Generate a PBR material."""
    return {
        "success": True,
        "material": VFXGenerator.generate_material(request)
    }


@router.post("/shader/generate")
async def generate_shader(request: ShaderGraphRequest):
    """Generate a shader graph."""
    return {
        "success": True,
        "shader": VFXGenerator.generate_shader_graph(request)
    }


@router.post("/post-process/generate")
async def generate_post_process(request: PostProcessRequest):
    """Generate a post-processing profile."""
    return {
        "success": True,
        "profile": VFXGenerator.generate_post_process_profile(request)
    }


@router.post("/lighting/generate")
async def generate_lighting(request: LightingSetupRequest):
    """Generate a lighting setup."""
    return {
        "success": True,
        "lighting": VFXGenerator.generate_lighting_setup(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIVFXSystemRequest(BaseModel):
    """Request for AI-powered VFX system generation"""
    effect_type: str = Field(..., description="explosion, fire, magic, water, etc.")
    visual_style: str = Field(default="realistic", description="realistic, stylized, pixel, cartoon")


class AIMaterialRequest(BaseModel):
    """Request for AI-powered material generation"""
    material_type: str = Field(..., description="metal, wood, fabric, skin, etc.")
    properties: List[str] = Field(default=["diffuse", "normal"], description="Material properties to include")


@router.post("/ai/vfx/generate")
async def ai_generate_vfx_system(request: AIVFXSystemRequest):
    """
    Generate VFX particle systems using AI (GPT-4o).
    Creates visually stunning, performant particle effects.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_vfx_system(
            effect_type=request.effect_type,
            visual_style=request.visual_style
        )
        
        if result["success"]:
            return {
                "success": True,
                "vfx_system": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            fallback_request = ParticleSystemRequest(
                effect_type=ParticleType.FIRE if "fire" in request.effect_type.lower() else ParticleType.MAGIC
            )
            return {
                "success": True,
                "vfx_system": VFXGenerator.generate_particle_system(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI VFX generation failed: {str(e)}")


@router.post("/ai/material/generate")
async def ai_generate_material(request: AIMaterialRequest):
    """
    Generate material/shader definitions using AI.
    Creates PBR-ready materials with all necessary properties.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = """You are an expert technical artist specializing in game materials.
Create detailed, production-ready material definitions with proper PBR values.
Always respond with valid JSON."""
        
        properties_str = ', '.join(request.properties)
        user_prompt = f"""Create a {request.material_type} material with properties: {properties_str}

Generate JSON with:
{{
    "material_name": "...",
    "type": "{request.material_type}",
    "shader_model": "PBR_Standard",
    "properties": {{
        "base_color": "#...",
        "metallic": 0.0,
        "roughness": 0.5,
        "normal_strength": 1.0,
        "ao_strength": 1.0
    }},
    "textures": [{{"slot": "diffuse", "resolution": "2048", "format": "BC7"}}],
    "shader_code": "HLSL snippet for custom effects"
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt)
        
        if result["success"]:
            return {
                "success": True,
                "material": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            fallback_request = MaterialRequest(material_type=MaterialType.METAL)
            return {
                "success": True,
                "material": VFXGenerator.generate_material(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI material generation failed: {str(e)}")
