"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          TEXT-TO-ANIMATION PIPELINE v15.5 - AI-POWERED MOTION                ║
║                                                                              ║
║  Generate animation data with LLM integration:                               ║
║  • AI-designed skeleton/armature definitions                                 ║
║  • Intelligent keyframe animation sequences                                  ║
║  • Smart blend trees and state machines                                      ║
║  • AI-generated procedural animation rules                                   ║
║  • Optimized IK/FK chain configurations                                      ║
║  • Motion capture style data generation                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from core.http_errors import internal_http_error
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Literal, Tuple
from datetime import datetime
from enum import Enum
import uuid
import random
import math
import re

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/animation-pipeline", tags=["Text-to-Animation Pipeline v15.5"])

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class AnimationType(str, Enum):
    IDLE = "idle"
    LOCOMOTION = "locomotion"
    COMBAT = "combat"
    INTERACTION = "interaction"
    EMOTE = "emote"
    CINEMATIC = "cinematic"
    PROCEDURAL = "procedural"

class RigType(str, Enum):
    HUMANOID = "humanoid"
    QUADRUPED = "quadruped"
    BIPED = "biped"
    SERPENTINE = "serpentine"
    AVIAN = "avian"
    INSECTOID = "insectoid"
    CUSTOM = "custom"

class BlendMode(str, Enum):
    OVERRIDE = "override"
    ADDITIVE = "additive"
    MULTIPLY = "multiply"
    BLEND = "blend"

class InterpolationType(str, Enum):
    LINEAR = "linear"
    BEZIER = "bezier"
    STEP = "step"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"

# Standard skeleton definitions
SKELETON_TEMPLATES = {
    RigType.HUMANOID: {
        "bones": [
            {"name": "root", "parent": None, "position": [0, 0, 0]},
            {"name": "hips", "parent": "root", "position": [0, 1.0, 0]},
            {"name": "spine", "parent": "hips", "position": [0, 0.2, 0]},
            {"name": "spine1", "parent": "spine", "position": [0, 0.15, 0]},
            {"name": "spine2", "parent": "spine1", "position": [0, 0.15, 0]},
            {"name": "neck", "parent": "spine2", "position": [0, 0.1, 0]},
            {"name": "head", "parent": "neck", "position": [0, 0.15, 0]},
            # Left arm
            {"name": "shoulder_l", "parent": "spine2", "position": [-0.15, 0.05, 0]},
            {"name": "upper_arm_l", "parent": "shoulder_l", "position": [-0.1, 0, 0]},
            {"name": "forearm_l", "parent": "upper_arm_l", "position": [-0.25, 0, 0]},
            {"name": "hand_l", "parent": "forearm_l", "position": [-0.25, 0, 0]},
            # Right arm
            {"name": "shoulder_r", "parent": "spine2", "position": [0.15, 0.05, 0]},
            {"name": "upper_arm_r", "parent": "shoulder_r", "position": [0.1, 0, 0]},
            {"name": "forearm_r", "parent": "upper_arm_r", "position": [0.25, 0, 0]},
            {"name": "hand_r", "parent": "forearm_r", "position": [0.25, 0, 0]},
            # Left leg
            {"name": "thigh_l", "parent": "hips", "position": [-0.1, -0.05, 0]},
            {"name": "calf_l", "parent": "thigh_l", "position": [0, -0.45, 0]},
            {"name": "foot_l", "parent": "calf_l", "position": [0, -0.45, 0.05]},
            {"name": "toe_l", "parent": "foot_l", "position": [0, -0.05, 0.1]},
            # Right leg
            {"name": "thigh_r", "parent": "hips", "position": [0.1, -0.05, 0]},
            {"name": "calf_r", "parent": "thigh_r", "position": [0, -0.45, 0]},
            {"name": "foot_r", "parent": "calf_r", "position": [0, -0.45, 0.05]},
            {"name": "toe_r", "parent": "foot_r", "position": [0, -0.05, 0.1]},
        ],
        "ik_chains": [
            {"name": "arm_ik_l", "start": "upper_arm_l", "end": "hand_l", "pole": "elbow_l"},
            {"name": "arm_ik_r", "start": "upper_arm_r", "end": "hand_r", "pole": "elbow_r"},
            {"name": "leg_ik_l", "start": "thigh_l", "end": "foot_l", "pole": "knee_l"},
            {"name": "leg_ik_r", "start": "thigh_r", "end": "foot_r", "pole": "knee_r"}
        ],
        "bone_count": 24
    },
    RigType.QUADRUPED: {
        "bones": [
            {"name": "root", "parent": None, "position": [0, 0, 0]},
            {"name": "hips", "parent": "root", "position": [0, 0.8, -0.5]},
            {"name": "spine", "parent": "hips", "position": [0, 0.05, 0.3]},
            {"name": "spine1", "parent": "spine", "position": [0, 0.05, 0.3]},
            {"name": "chest", "parent": "spine1", "position": [0, 0.1, 0.3]},
            {"name": "neck", "parent": "chest", "position": [0, 0.15, 0.2]},
            {"name": "head", "parent": "neck", "position": [0, 0.1, 0.2]},
            {"name": "tail", "parent": "hips", "position": [0, -0.1, -0.3]},
            # Front legs
            {"name": "front_leg_l", "parent": "chest", "position": [-0.15, -0.1, 0.1]},
            {"name": "front_foreleg_l", "parent": "front_leg_l", "position": [0, -0.3, 0]},
            {"name": "front_paw_l", "parent": "front_foreleg_l", "position": [0, -0.25, 0]},
            {"name": "front_leg_r", "parent": "chest", "position": [0.15, -0.1, 0.1]},
            {"name": "front_foreleg_r", "parent": "front_leg_r", "position": [0, -0.3, 0]},
            {"name": "front_paw_r", "parent": "front_foreleg_r", "position": [0, -0.25, 0]},
            # Back legs
            {"name": "back_leg_l", "parent": "hips", "position": [-0.15, -0.1, -0.1]},
            {"name": "back_foreleg_l", "parent": "back_leg_l", "position": [0, -0.3, 0]},
            {"name": "back_paw_l", "parent": "back_foreleg_l", "position": [0, -0.25, 0]},
            {"name": "back_leg_r", "parent": "hips", "position": [0.15, -0.1, -0.1]},
            {"name": "back_foreleg_r", "parent": "back_leg_r", "position": [0, -0.3, 0]},
            {"name": "back_paw_r", "parent": "back_foreleg_r", "position": [0, -0.25, 0]},
        ],
        "ik_chains": [
            {"name": "front_leg_ik_l", "start": "front_leg_l", "end": "front_paw_l"},
            {"name": "front_leg_ik_r", "start": "front_leg_r", "end": "front_paw_r"},
            {"name": "back_leg_ik_l", "start": "back_leg_l", "end": "back_paw_l"},
            {"name": "back_leg_ik_r", "start": "back_leg_r", "end": "back_paw_r"}
        ],
        "bone_count": 20
    }
}

# Animation preset templates
ANIMATION_TEMPLATES = {
    AnimationType.IDLE: {
        "humanoid": {
            "breathing": {
                "duration": 4.0,
                "looping": True,
                "keyframes": [
                    {"time": 0.0, "bones": {"spine": {"rotation": [0, 0, 0]}}},
                    {"time": 2.0, "bones": {"spine": {"rotation": [2, 0, 0]}}},
                    {"time": 4.0, "bones": {"spine": {"rotation": [0, 0, 0]}}}
                ]
            },
            "weight_shift": {
                "duration": 6.0,
                "looping": True,
                "keyframes": [
                    {"time": 0.0, "bones": {"hips": {"position": [0, 0, 0]}}},
                    {"time": 3.0, "bones": {"hips": {"position": [0.02, 0, 0]}}},
                    {"time": 6.0, "bones": {"hips": {"position": [0, 0, 0]}}}
                ]
            }
        }
    },
    AnimationType.LOCOMOTION: {
        "humanoid": {
            "walk": {
                "duration": 1.0,
                "looping": True,
                "root_motion": True,
                "speed": 1.4
            },
            "run": {
                "duration": 0.6,
                "looping": True,
                "root_motion": True,
                "speed": 5.0
            },
            "sprint": {
                "duration": 0.4,
                "looping": True,
                "root_motion": True,
                "speed": 8.0
            }
        }
    },
    AnimationType.COMBAT: {
        "humanoid": {
            "light_attack": {
                "duration": 0.5,
                "looping": False,
                "damage_window": [0.2, 0.35],
                "recovery": 0.15
            },
            "heavy_attack": {
                "duration": 1.0,
                "looping": False,
                "damage_window": [0.4, 0.6],
                "recovery": 0.4
            },
            "block": {
                "duration": 0.2,
                "looping": False,
                "hold_pose": True
            },
            "dodge": {
                "duration": 0.6,
                "looping": False,
                "root_motion": True,
                "i_frames": [0.1, 0.4]
            }
        }
    }
}

# ============================================================================
# FRAME-TIMING CONTRACT (anticipation / active-contact / recovery)
# ============================================================================
# One timing source for animation, VFX and audio. Every contact event carries an
# integer ``hit_frame``: a 0-based frame index from clip start at the clip's
# authored fps. VFX cues and audio hooks key off that exact field name, so there
# are no separate timing tables. See docs/animation/ANIMATION_STATE_MACHINE_SPEC.md.

TIMING_CONTRACT_VERSION = "anim.timing.v1"
DEFAULT_FPS = 30
MIN_ANIMATION_DURATION_SECONDS = 0.1   # 3 frames at 30 fps: one per combat phase
MAX_ANIMATION_DURATION_SECONDS = 120.0
MAX_TRANSITION_BLEND_SECONDS = 2.0

# Readability budgets, in frames at DEFAULT_FPS. Scaled linearly for other fps.
# Below the anticipation minimum a telegraph is unreadable at gameplay speed;
# above the recovery maximum the move feels sluggish and uncancellable.
COMBAT_TIMING_BUDGETS: Dict[str, Dict[str, int]] = {
    "light": {
        "anticipation_min": 4, "anticipation_max": 12,
        "active_min": 2, "active_max": 8,
        "recovery_min": 4, "recovery_max": 15,
    },
    "heavy": {
        "anticipation_min": 10, "anticipation_max": 24,
        "active_min": 3, "active_max": 10,
        "recovery_min": 8, "recovery_max": 30,
    },
}

# Default cross-fade (seconds) by transition family. Locomotion<->locomotion
# blends soft; anything entering a reactive/combat state must snap.
BLEND_TIME_DEFAULTS: Dict[str, float] = {
    "locomotion": 0.25,
    "any_state": 0.1,
    "exit_to_default": 0.2,
}

COMBAT_MOVE_WEIGHT_CLASS = {"light_attack": "light", "heavy_attack": "heavy"}

# States that loop by default; everything else is a one-shot clip.
LOOPING_STATES = {"idle", "walk", "jog", "run", "sprint", "strafe", "crouch", "fall", "swim", "block"}
# Terminal states have no outgoing transitions and ignore any-state transitions.
TERMINAL_STATES = {"death", "dead"}
# Exit conditions for one-shot states when the machine is auto-generated.
ONE_SHOT_EXIT_CONDITIONS = {"jump": "grounded", "fall": "grounded"}
EXIT_TIME_CONDITION = "anim_complete"

_CONDITION_NON_PARAMS = {"and", "or", "not", "true", "false", EXIT_TIME_CONDITION}
_CONDITION_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_COMPARATOR = r"(<=|>=|==|!=|<|>)"


def _scaled_budget(weight_class: str, fps: int) -> Dict[str, int]:
    """Readability budget for ``weight_class`` expressed in frames at ``fps``."""
    base = COMBAT_TIMING_BUDGETS.get(weight_class, COMBAT_TIMING_BUDGETS["light"])
    scale = fps / DEFAULT_FPS
    return {key: max(1, int(round(value * scale))) for key, value in base.items()}


def compute_combat_phases(move: str, duration: float, fps: int = DEFAULT_FPS) -> Dict[str, Any]:
    """Derive frame-exact anticipation/active/recovery phases for a combat move.

    Phases come from the move template's ``damage_window`` (normalised to the
    template duration) so generated clips, events and the presets endpoint all
    agree. ``end_frame`` is exclusive. ``hit_frame`` is the first active frame.
    """
    template = ANIMATION_TEMPLATES[AnimationType.COMBAT]["humanoid"][move]
    template_duration = template["duration"]
    window_start, window_end = template["damage_window"]
    total_frames = max(3, int(round(duration * fps)))

    contact = int(round(window_start / template_duration * total_frames))
    active_end = int(round(window_end / template_duration * total_frames))
    # Every phase keeps at least one frame.
    contact = min(max(contact, 1), total_frames - 2)
    active_end = min(max(active_end, contact + 1), total_frames - 1)

    return {
        "contract": TIMING_CONTRACT_VERSION,
        "move": move,
        "weight_class": COMBAT_MOVE_WEIGHT_CLASS.get(move, "light"),
        "fps": fps,
        "total_frames": total_frames,
        "hit_frame": contact,
        "phases": {
            "anticipation": {"start_frame": 0, "end_frame": contact, "frames": contact},
            "active": {"start_frame": contact, "end_frame": active_end, "frames": active_end - contact},
            "recovery": {"start_frame": active_end, "end_frame": total_frames, "frames": total_frames - active_end},
        },
    }


def validate_combat_timing(
    anticipation_frames: int,
    active_frames: int,
    recovery_frames: int,
    hit_frames: List[int],
    fps: int = DEFAULT_FPS,
    weight_class: str = "light",
    total_frames: Optional[int] = None,
) -> Dict[str, Any]:
    """Validate authored combat timing against the contract and readability budgets.

    ``errors`` are contract violations (the clip cannot be synced to VFX/audio).
    ``warnings`` are readability-budget breaches; ``readable`` is False if any.
    """
    errors: List[str] = []
    warnings: List[str] = []
    phases = {"anticipation": anticipation_frames, "active": active_frames, "recovery": recovery_frames}

    for name, frames in phases.items():
        if frames < 1:
            errors.append(f"{name} phase must have at least 1 frame (got {frames})")

    phase_total = anticipation_frames + active_frames + recovery_frames
    if total_frames is not None and total_frames != phase_total:
        errors.append(f"phases sum to {phase_total} frames but total_frames is {total_frames}")

    active_start = anticipation_frames
    active_end = anticipation_frames + active_frames
    if not hit_frames:
        errors.append("at least one hit_frame is required for a combat clip")
    if len(set(hit_frames)) != len(hit_frames):
        errors.append("hit_frames must be unique")
    if hit_frames != sorted(hit_frames):
        errors.append("hit_frames must be in ascending order")
    for hit in hit_frames:
        if not active_start <= hit < active_end:
            errors.append(
                f"hit_frame {hit} is outside the active window [{active_start}, {active_end})"
            )

    budget = _scaled_budget(weight_class, fps)
    for name, frames in phases.items():
        lo, hi = budget[f"{name}_min"], budget[f"{name}_max"]
        if frames < lo:
            warnings.append(f"{name} is {frames} frames; {weight_class} budget minimum is {lo} at {fps} fps")
        elif frames > hi:
            warnings.append(f"{name} is {frames} frames; {weight_class} budget maximum is {hi} at {fps} fps")

    return {
        "contract": TIMING_CONTRACT_VERSION,
        "valid": not errors,
        "readable": not errors and not warnings,
        "errors": errors,
        "warnings": warnings,
        "budget": budget,
        "fps": fps,
        "weight_class": weight_class,
        "total_frames": phase_total,
        "active_window": [active_start, active_end],
    }


def _extract_condition_parameters(condition: str) -> List[Dict[str, Any]]:
    """Infer animator parameters referenced by a transition condition.

    ``*_trigger`` -> trigger, identifiers used in a comparison -> float,
    bare identifiers -> bool. ``anim_complete`` is exit time, not a parameter.
    """
    params: List[Dict[str, Any]] = []
    for name in dict.fromkeys(_CONDITION_IDENT.findall(condition or "")):
        if name.lower() in _CONDITION_NON_PARAMS:
            continue
        if name.endswith("_trigger"):
            params.append({"name": name, "type": "trigger"})
        elif re.search(rf"\b{name}\b\s*{_COMPARATOR}", condition) or re.search(
            rf"{_COMPARATOR}\s*\b{name}\b", condition
        ):
            params.append({"name": name, "type": "float", "default": 0})
        else:
            params.append({"name": name, "type": "bool", "default": False})
    return params


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class RigGenerationRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=10000, description="Natural language description of the character")
    rig_type: Optional[RigType] = None
    include_face_rig: bool = False
    include_fingers: bool = True
    custom_bones: List[str] = Field(default_factory=list, max_length=200)

class AnimationGenerationRequest(BaseModel):
    description: str = Field(..., max_length=10000, description="Natural language description of the animation")
    animation_type: Optional[AnimationType] = None
    rig_type: RigType = RigType.HUMANOID
    duration: Optional[float] = Field(
        None,
        ge=MIN_ANIMATION_DURATION_SECONDS,
        le=MAX_ANIMATION_DURATION_SECONDS,
        description="Clip length in seconds (>= 3 frames at 30 fps)",
    )
    looping: bool = False
    include_root_motion: bool = False
    reduced_motion: bool = Field(
        False,
        description="Attenuate cosmetic motion (root bob, sway). Never changes gameplay timing or hit_frame.",
    )

class BlendTreeRequest(BaseModel):
    animations: List[str] = Field(..., min_length=1, max_length=100)
    blend_parameter: str = Field("speed", max_length=100)
    blend_type: Literal["1d", "2d", "direct"] = "1d"

class StateMachineRequest(BaseModel):
    states: List[str] = Field(..., min_length=1, max_length=100)
    default_state: str = Field(..., min_length=1, max_length=100)
    transitions: List[Dict[str, Any]] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _validate_graph(self) -> "StateMachineRequest":
        """Reject graphs that would silently drop transitions or start nowhere."""
        if len(set(self.states)) != len(self.states):
            raise ValueError("state names must be unique")
        if any(not state or len(state) > 100 for state in self.states):
            raise ValueError("state names must be 1-100 characters")
        if self.default_state not in self.states:
            raise ValueError(f"default_state '{self.default_state}' is not one of the declared states")
        known = set(self.states)
        for index, trans in enumerate(self.transitions):
            to_state = trans.get("to")
            from_state = trans.get("from", "any")
            if to_state not in known:
                raise ValueError(f"transitions[{index}].to '{to_state}' is not a declared state")
            if from_state != "any" and from_state not in known:
                raise ValueError(f"transitions[{index}].from '{from_state}' is not a declared state or 'any'")
            if from_state in TERMINAL_STATES:
                raise ValueError(f"transitions[{index}] leaves terminal state '{from_state}'")
            condition = trans.get("condition", "")
            if not isinstance(condition, str) or len(condition) > 500:
                raise ValueError(f"transitions[{index}].condition must be a string of at most 500 characters")
            duration = trans.get("duration", 0.25)
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                raise ValueError(f"transitions[{index}].duration must be a number of seconds")
            if not 0 <= duration <= MAX_TRANSITION_BLEND_SECONDS:
                raise ValueError(
                    f"transitions[{index}].duration must be between 0 and {MAX_TRANSITION_BLEND_SECONDS} seconds"
                )
            priority = trans.get("priority", 0)
            if isinstance(priority, bool) or not isinstance(priority, int) or not -1000 <= priority <= 1000:
                raise ValueError(f"transitions[{index}].priority must be an integer between -1000 and 1000")
        return self

class TimingValidationRequest(BaseModel):
    """Authored combat timing to check against the hit-frame contract."""
    fps: int = Field(DEFAULT_FPS, ge=12, le=240)
    weight_class: Literal["light", "heavy"] = "light"
    anticipation_frames: int = Field(..., ge=0, le=10000)
    active_frames: int = Field(..., ge=0, le=10000)
    recovery_frames: int = Field(..., ge=0, le=10000)
    hit_frames: List[int] = Field(default_factory=list, max_length=64)
    total_frames: Optional[int] = Field(None, ge=1, le=30000)


class ProceduralAnimationRequest(BaseModel):
    animation_type: str = Field(..., min_length=1, max_length=100)
    parameters: Dict[str, float] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list, max_length=100)

# ============================================================================
# ANIMATION GENERATOR ENGINE
# ============================================================================

class AnimationGenerator:
    """
    Comprehensive animation and rigging generator.
    """

    @staticmethod
    def parse_description(description: str) -> Dict[str, Any]:
        """Parse natural language to detect animation parameters."""
        desc_lower = description.lower()

        parsed = {
            "rig_type": None,
            "animation_type": None,
            "motion_keywords": [],
            "speed_hints": [],
            "style_hints": []
        }

        # Detect rig type
        rig_keywords = {
            RigType.HUMANOID: ["human", "person", "humanoid", "character", "player"],
            RigType.QUADRUPED: ["dog", "cat", "wolf", "horse", "quadruped", "animal", "beast"],
            RigType.AVIAN: ["bird", "flying", "wings", "avian"],
            RigType.SERPENTINE: ["snake", "serpent", "worm", "tentacle"],
            RigType.INSECTOID: ["insect", "spider", "bug", "beetle"]
        }

        for rig_type, keywords in rig_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                parsed["rig_type"] = rig_type
                break

        # Detect animation type
        anim_keywords = {
            AnimationType.IDLE: ["idle", "standing", "waiting", "breathing", "rest"],
            AnimationType.LOCOMOTION: ["walk", "run", "sprint", "jog", "move", "locomotion"],
            AnimationType.COMBAT: ["attack", "fight", "swing", "punch", "kick", "block", "dodge"],
            AnimationType.INTERACTION: ["pick up", "grab", "use", "interact", "open", "push", "pull"],
            AnimationType.EMOTE: ["wave", "dance", "celebrate", "taunt", "emote", "gesture"],
            AnimationType.CINEMATIC: ["cutscene", "cinematic", "dramatic", "scripted"]
        }

        for anim_type, keywords in anim_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                parsed["animation_type"] = anim_type
                parsed["motion_keywords"].extend([kw for kw in keywords if kw in desc_lower])

        # Speed hints
        if any(w in desc_lower for w in ["fast", "quick", "rapid", "swift"]):
            parsed["speed_hints"].append("fast")
        if any(w in desc_lower for w in ["slow", "careful", "cautious", "gentle"]):
            parsed["speed_hints"].append("slow")

        # Style hints
        if any(w in desc_lower for w in ["aggressive", "powerful", "strong"]):
            parsed["style_hints"].append("powerful")
        if any(w in desc_lower for w in ["graceful", "smooth", "fluid"]):
            parsed["style_hints"].append("graceful")
        if any(w in desc_lower for w in ["robotic", "mechanical", "stiff"]):
            parsed["style_hints"].append("mechanical")

        return parsed

    @staticmethod
    def generate_skeleton(rig_type: RigType, include_fingers: bool = True, include_face: bool = False) -> Dict[str, Any]:
        """Generate skeleton/armature definition."""
        template = SKELETON_TEMPLATES.get(rig_type, SKELETON_TEMPLATES[RigType.HUMANOID])

        skeleton = {
            "id": str(uuid.uuid4()),
            "type": rig_type.value,
            "bones": template["bones"].copy(),
            "ik_chains": template["ik_chains"].copy(),
            "constraints": [],
            "metadata": {
                "bone_count": template["bone_count"],
                "has_fingers": include_fingers,
                "has_face_rig": include_face
            }
        }

        # Add finger bones if requested
        if include_fingers and rig_type in [RigType.HUMANOID, RigType.BIPED]:
            finger_names = ["thumb", "index", "middle", "ring", "pinky"]
            for side in ["l", "r"]:
                for finger in finger_names:
                    for i in range(3):
                        parent = f"hand_{side}" if i == 0 else f"{finger}_{i}_{side}"
                        skeleton["bones"].append({
                            "name": f"{finger}_{i+1}_{side}",
                            "parent": parent,
                            "position": [0.02 if side == "r" else -0.02, 0, 0.01 * (i + 1)]
                        })
            skeleton["metadata"]["bone_count"] += 30

        # Add face rig if requested
        if include_face:
            face_bones = [
                {"name": "jaw", "parent": "head", "position": [0, -0.05, 0.05]},
                {"name": "eye_l", "parent": "head", "position": [-0.03, 0.02, 0.08]},
                {"name": "eye_r", "parent": "head", "position": [0.03, 0.02, 0.08]},
                {"name": "brow_l", "parent": "head", "position": [-0.03, 0.05, 0.08]},
                {"name": "brow_r", "parent": "head", "position": [0.03, 0.05, 0.08]},
                {"name": "cheek_l", "parent": "head", "position": [-0.04, -0.01, 0.06]},
                {"name": "cheek_r", "parent": "head", "position": [0.04, -0.01, 0.06]},
                {"name": "lip_upper", "parent": "head", "position": [0, -0.03, 0.09]},
                {"name": "lip_lower", "parent": "jaw", "position": [0, 0.01, 0.04]}
            ]
            skeleton["bones"].extend(face_bones)
            skeleton["metadata"]["bone_count"] += len(face_bones)

        # Add constraints
        skeleton["constraints"] = [
            {"type": "limit_rotation", "bone": "head", "limits": {"x": [-60, 60], "y": [-80, 80], "z": [-30, 30]}},
            {"type": "limit_rotation", "bone": "spine", "limits": {"x": [-30, 60], "y": [-45, 45], "z": [-30, 30]}}
        ]

        return skeleton

    @staticmethod
    def generate_keyframe_animation(
        anim_type: AnimationType,
        rig_type: RigType,
        duration: float,
        looping: bool,
        style_hints: List[str],
        reduced_motion: bool = False
    ) -> Dict[str, Any]:
        """Generate keyframe animation data."""
        template = ANIMATION_TEMPLATES.get(anim_type, {}).get(rig_type.value, {})

        animation = {
            "id": str(uuid.uuid4()),
            "type": anim_type.value,
            "rig_type": rig_type.value,
            "duration": duration,
            "looping": looping,
            "fps": DEFAULT_FPS,
            "keyframes": [],
            "curves": {},
            "events": [],
            "metadata": {
                "style": style_hints,
                "generated_at": datetime.utcnow().isoformat()
            }
        }

        # Cosmetic motion scale; gameplay timing is never affected by reduced motion.
        motion_scale = 0.5 if reduced_motion else 1.0
        animation["accessibility"] = {
            "reduced_motion": reduced_motion,
            "cosmetic_motion_scale": motion_scale,
            "root_bob_enabled": not reduced_motion,
            "timing_preserved": True,
        }

        # Generate keyframes based on animation type
        if anim_type == AnimationType.IDLE:
            animation["keyframes"] = AnimationGenerator._generate_idle_keyframes(duration, motion_scale)
        elif anim_type == AnimationType.LOCOMOTION:
            animation["keyframes"] = AnimationGenerator._generate_locomotion_keyframes(
                duration, style_hints, reduced_motion
            )
            animation["root_motion"] = True
        elif anim_type == AnimationType.COMBAT:
            move = "heavy_attack" if "powerful" in style_hints else "light_attack"
            timing = compute_combat_phases(move, duration, animation["fps"])
            phases = timing["phases"]
            timing["readability"] = validate_combat_timing(
                phases["anticipation"]["frames"],
                phases["active"]["frames"],
                phases["recovery"]["frames"],
                [timing["hit_frame"]],
                fps=timing["fps"],
                weight_class=timing["weight_class"],
                total_frames=timing["total_frames"],
            )
            animation["timing"] = timing
            animation["keyframes"] = AnimationGenerator._generate_combat_keyframes(duration, style_hints, timing)
            animation["events"] = AnimationGenerator._build_combat_events(timing)
        else:
            animation["keyframes"] = AnimationGenerator._generate_generic_keyframes(duration)

        # Generate interpolation curves
        animation["curves"] = {
            "default": InterpolationType.BEZIER.value,
            "spine": InterpolationType.EASE_IN_OUT.value,
            "hands": InterpolationType.LINEAR.value
        }

        return animation

    @staticmethod
    def _generate_idle_keyframes(duration: float, motion_scale: float = 1.0) -> List[Dict[str, Any]]:
        """Generate idle animation keyframes."""
        keyframes = []
        num_frames = max(1, int(duration * DEFAULT_FPS))

        for i in range(num_frames + 1):
            time = (i / num_frames) * duration
            breath_cycle = math.sin(time * math.pi * 2 / duration) * motion_scale

            keyframes.append({
                "time": round(time, 3),
                "transforms": {
                    "spine": {"rotation": [breath_cycle * 2, 0, 0]},
                    "spine1": {"rotation": [breath_cycle * 1.5, 0, 0]},
                    "shoulder_l": {"rotation": [0, 0, breath_cycle * 0.5]},
                    "shoulder_r": {"rotation": [0, 0, -breath_cycle * 0.5]}
                }
            })

        return keyframes

    @staticmethod
    def _generate_locomotion_keyframes(
        duration: float, style: List[str], reduced_motion: bool = False
    ) -> List[Dict[str, Any]]:
        """Generate locomotion animation keyframes.

        Reduced motion removes vertical root bob and halves spine twist; stride
        timing and root travel are unchanged so foot contacts stay in sync.
        """
        keyframes = []
        num_frames = max(1, int(duration * DEFAULT_FPS))
        bob_scale = 0.0 if reduced_motion else 1.0
        twist_scale = 0.5 if reduced_motion else 1.0

        speed_multiplier = 1.5 if "fast" in style else 0.7 if "slow" in style else 1.0

        for i in range(num_frames + 1):
            time = (i / num_frames) * duration
            cycle = time / duration

            # Leg cycle (opposite phase)
            leg_angle_l = math.sin(cycle * math.pi * 2) * 30
            leg_angle_r = math.sin(cycle * math.pi * 2 + math.pi) * 30

            # Arm swing (opposite to legs)
            arm_angle_l = math.sin(cycle * math.pi * 2 + math.pi) * 20
            arm_angle_r = math.sin(cycle * math.pi * 2) * 20

            # Spine twist
            spine_twist = math.sin(cycle * math.pi * 2) * 5 * twist_scale

            keyframes.append({
                "time": round(time, 3),
                "transforms": {
                    "thigh_l": {"rotation": [leg_angle_l * speed_multiplier, 0, 0]},
                    "thigh_r": {"rotation": [leg_angle_r * speed_multiplier, 0, 0]},
                    "calf_l": {"rotation": [max(0, -leg_angle_l) * 0.5, 0, 0]},
                    "calf_r": {"rotation": [max(0, -leg_angle_r) * 0.5, 0, 0]},
                    "upper_arm_l": {"rotation": [arm_angle_l, 0, 0]},
                    "upper_arm_r": {"rotation": [arm_angle_r, 0, 0]},
                    "spine": {"rotation": [0, spine_twist, 0]}
                },
                "root_position": [
                    0,
                    abs(math.sin(cycle * math.pi * 4)) * 0.02 * bob_scale,
                    cycle * 1.4 * speed_multiplier,
                ]
            })

        return keyframes

    @staticmethod
    def _generate_combat_keyframes(
        duration: float, style: List[str], timing: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate combat animation keyframes.

        With ``timing`` (from ``compute_combat_phases``) the poses are placed on
        frame boundaries: the wind-up peaks and holds before contact, the strike
        pose lands exactly on ``hit_frame`` and follow-through ends the active
        window, so VFX/audio keyed to ``hit_frame`` hit the strike pose.
        """
        keyframes = []

        is_powerful = "powerful" in style
        peak_time, strike_time, follow_time = duration * 0.3, duration * 0.5, duration * 0.7
        if timing:
            fps = timing["fps"]
            anticipation = timing["phases"]["anticipation"]["frames"]
            hit = timing["hit_frame"]
            peak_frame = max(1, hit - max(1, anticipation // 3)) if anticipation > 1 else 0
            peak_time = round(peak_frame / fps, 4)
            strike_time = round(hit / fps, 4)
            follow_time = round(timing["phases"]["active"]["end_frame"] / fps, 4)

        # Wind-up phase (0-30%)
        keyframes.append({
            "time": 0,
            "transforms": {
                "spine": {"rotation": [0, -30 if is_powerful else -20, 0]},
                "upper_arm_r": {"rotation": [-60 if is_powerful else -45, 0, -30]},
                "forearm_r": {"rotation": [-90, 0, 0]}
            }
        })

        # Peak wind-up (hold before contact)
        keyframes.append({
            "time": peak_time,
            "transforms": {
                "spine": {"rotation": [0, -45 if is_powerful else -30, 0]},
                "upper_arm_r": {"rotation": [-90 if is_powerful else -60, 0, -45]},
                "forearm_r": {"rotation": [-120, 0, 0]}
            }
        })

        # Strike (contact / hit_frame)
        keyframes.append({
            "time": strike_time,
            "transforms": {
                "spine": {"rotation": [0, 30 if is_powerful else 20, 0]},
                "upper_arm_r": {"rotation": [30, 0, 30]},
                "forearm_r": {"rotation": [-30, 0, 0]}
            }
        })

        # Follow-through (end of active window)
        keyframes.append({
            "time": follow_time,
            "transforms": {
                "spine": {"rotation": [0, 45 if is_powerful else 30, 0]},
                "upper_arm_r": {"rotation": [45, 0, 45]},
                "forearm_r": {"rotation": [0, 0, 0]}
            }
        })

        # Recovery (100%)
        keyframes.append({
            "time": duration,
            "transforms": {
                "spine": {"rotation": [0, 0, 0]},
                "upper_arm_r": {"rotation": [0, 0, 0]},
                "forearm_r": {"rotation": [0, 0, 0]}
            }
        })

        return keyframes

    @staticmethod
    def _build_combat_events(timing: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Frame-stamped combat events. ``contact`` carries the canonical ``hit_frame``.

        ``damage_start``/``damage_end`` are kept for existing consumers and are
        derived from the same phases, so there is a single timing source.
        """
        fps = timing["fps"]
        phases = timing["phases"]
        hit = timing["hit_frame"]
        active_end = phases["active"]["end_frame"]

        def _event(event_type: str, frame: int, **extra: Any) -> Dict[str, Any]:
            return {"type": event_type, "frame": frame, "time": round(frame / fps, 4), **extra}

        return [
            _event("anticipation_start", 0),
            _event(
                "contact",
                hit,
                hit_frame=hit,
                weight_class=timing["weight_class"],
                cue_hooks=["vfx", "audio"],
            ),
            _event("damage_start", hit),
            _event("damage_end", active_end),
            _event("recovery_start", active_end),
        ]

    @staticmethod
    def _build_animation(request: "AnimationGenerationRequest") -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build an animation from a request; returns ``(animation, parsed_description)``."""
        parsed = AnimationGenerator.parse_description(request.description)
        anim_type = request.animation_type or parsed["animation_type"] or AnimationType.IDLE
        duration = request.duration
        if duration is None and anim_type == AnimationType.COMBAT:
            # Default combat clips to the move's authored length so timing lands in budget.
            move = "heavy_attack" if "powerful" in parsed["style_hints"] else "light_attack"
            duration = ANIMATION_TEMPLATES[AnimationType.COMBAT]["humanoid"][move]["duration"]
        duration = duration or 1.0

        animation = AnimationGenerator.generate_keyframe_animation(
            anim_type,
            request.rig_type,
            duration,
            request.looping,
            parsed["style_hints"],
            request.reduced_motion,
        )
        if request.include_root_motion:
            animation["root_motion"] = True
        return animation, parsed

    @staticmethod
    def generate_animation(request: "AnimationGenerationRequest") -> Dict[str, Any]:
        """Template-based animation for a request (used by the AI fallback path)."""
        animation, _ = AnimationGenerator._build_animation(request)
        return animation

    @staticmethod
    def _generate_generic_keyframes(duration: float) -> List[Dict[str, Any]]:
        """Generate generic animation keyframes."""
        return [
            {"time": 0, "transforms": {}},
            {"time": duration * 0.5, "transforms": {}},
            {"time": duration, "transforms": {}}
        ]

    @staticmethod
    def generate_blend_tree(animations: List[str], blend_param: str, blend_type: str) -> Dict[str, Any]:
        """Generate a blend tree configuration."""
        blend_tree = {
            "id": str(uuid.uuid4()),
            "type": blend_type,
            "parameter": blend_param,
            "nodes": [],
            "thresholds": []
        }

        if blend_type == "1d":
            # Linear blend (e.g., walk to run based on speed)
            for i, anim in enumerate(animations):
                threshold = i / (len(animations) - 1) if len(animations) > 1 else 0
                blend_tree["nodes"].append({
                    "animation": anim,
                    "threshold": threshold,
                    "speed_multiplier": 1.0
                })
                blend_tree["thresholds"].append(threshold)

        elif blend_type == "2d":
            # 2D blend (e.g., strafe based on x/y direction)
            blend_tree["parameter_y"] = f"{blend_param}_y"
            positions = [
                (0, 1),   # Forward
                (1, 0),   # Right
                (0, -1),  # Backward
                (-1, 0),  # Left
            ]
            count = len(animations)
            for i, anim in enumerate(animations):
                if count <= len(positions):
                    pos = positions[i]
                else:
                    # More than four clips: spread evenly on the unit circle,
                    # clockwise from forward, instead of silently dropping them.
                    angle = 2 * math.pi * i / count
                    pos = (round(math.sin(angle), 4) + 0.0, round(math.cos(angle), 4) + 0.0)
                blend_tree["nodes"].append({
                    "animation": anim,
                    "position": pos
                })

        elif blend_type == "direct":
            # Direct blend (manual weights)
            for anim in animations:
                blend_tree["nodes"].append({
                    "animation": anim,
                    "weight_parameter": f"weight_{anim}"
                })

        return blend_tree

    @staticmethod
    def generate_state_machine(states: List[str], default: str, transitions: List[Dict]) -> Dict[str, Any]:
        """Generate an animation state machine.

        User transitions are kept as authored. When none are given, canonical
        locomotion (with hysteresis), combat/reactive any-state transitions and
        exits for one-shot states are generated so no state is a dead end.
        Every machine carries a ``validation`` block (unreachable/dead-end states).
        """
        state_machine = {
            "id": str(uuid.uuid4()),
            "default_state": default,
            "states": {},
            "any_state_transitions": [],
            "parameters": [],
            "validation": {}
        }
        terminal_present = sorted(state for state in states if state in TERMINAL_STATES)

        # Create states
        for state in states:
            state_machine["states"][state] = {
                "name": state,
                "animation": state,
                "transitions": [],
                "speed": 1.0,
                "loop": state in LOOPING_STATES,
                "terminal": state in TERMINAL_STATES
            }

        def _any_state(to_state: str, condition: str, duration: float, priority: int) -> Dict[str, Any]:
            return {
                "to": to_state,
                "duration": duration,
                "condition": condition,
                "interruption": "current_then_next",
                "priority": priority,
                "can_transition_to_self": False,
                "excluded_source_states": terminal_present
            }

        def _state_transition(to_state: str, condition: str, duration: float) -> Dict[str, Any]:
            transition_obj = {
                "to": to_state,
                "duration": duration,
                "condition": condition,
                "interruption": "current_then_next"
            }
            if condition == EXIT_TIME_CONDITION:
                transition_obj["has_exit_time"] = True
                transition_obj["exit_time"] = 1.0
            return transition_obj

        # Add transitions
        for trans in transitions:
            from_state = trans.get("from", "any")
            to_state = trans.get("to")
            condition = trans.get("condition", "")
            duration = trans.get("duration", 0.25)

            if from_state == "any":
                state_machine["any_state_transitions"].append(
                    _any_state(to_state, condition, duration, int(trans.get("priority", 0)))
                )
            elif from_state in state_machine["states"]:
                state_machine["states"][from_state]["transitions"].append(
                    _state_transition(to_state, condition, duration)
                )

        # Auto-generate common transitions if none provided
        if not transitions:
            # Locomotion thresholds use hysteresis (enter > exit) so a speed
            # hovering on a boundary cannot flicker between clips.
            common_transitions = [
                {"from": "idle", "to": "walk", "condition": "speed > 0.1"},
                {"from": "walk", "to": "idle", "condition": "speed < 0.05"},
                {"from": "walk", "to": "run", "condition": "speed > 0.5"},
                {"from": "run", "to": "walk", "condition": "speed < 0.45"},
                {"from": "run", "to": "sprint", "condition": "speed > 0.85"},
                {"from": "sprint", "to": "run", "condition": "speed < 0.8"},
                {"from": "jump", "to": "fall", "condition": EXIT_TIME_CONDITION},
                {"from": "fall", "to": "land", "condition": "grounded"},
                {"from": "land", "to": default, "condition": EXIT_TIME_CONDITION},
            ]
            # Higher priority wins when several any-state conditions fire together.
            any_state_transitions = [
                {"to": "death", "condition": "health <= 0", "priority": 100},
                {"to": "hit_react", "condition": "hit_trigger", "priority": 80},
                {"to": "dodge", "condition": "dodge_trigger", "priority": 60},
                {"to": "jump", "condition": "jump_trigger", "priority": 40},
                {"to": "attack", "condition": "attack_trigger", "priority": 20},
            ]
            for trans in common_transitions:
                if trans["from"] in state_machine["states"] and trans["to"] in state_machine["states"]:
                    if trans["from"] != trans["to"]:
                        state_machine["states"][trans["from"]]["transitions"].append(
                            _state_transition(trans["to"], trans["condition"], BLEND_TIME_DEFAULTS["locomotion"])
                        )
            for trans in any_state_transitions:
                if trans["to"] in state_machine["states"]:
                    state_machine["any_state_transitions"].append(
                        _any_state(trans["to"], trans["condition"], BLEND_TIME_DEFAULTS["any_state"], trans["priority"])
                    )
            # Exits for one-shot states that would otherwise freeze on their last frame.
            for name, state in state_machine["states"].items():
                if state["loop"] or state["terminal"] or state["transitions"] or name == default:
                    continue
                condition = ONE_SHOT_EXIT_CONDITIONS.get(name, EXIT_TIME_CONDITION)
                state["transitions"].append(
                    _state_transition(default, condition, BLEND_TIME_DEFAULTS["exit_to_default"])
                )

        state_machine["any_state_transitions"].sort(key=lambda t: -t.get("priority", 0))

        # Extract parameters from conditions (state and any-state transitions)
        all_transitions = [t for st in state_machine["states"].values() for t in st["transitions"]]
        all_transitions += state_machine["any_state_transitions"]
        parameters: Dict[str, Dict[str, Any]] = {}
        for trans in all_transitions:
            for param in _extract_condition_parameters(trans["condition"]):
                parameters.setdefault(param["name"], param)
        state_machine["parameters"] = list(parameters.values())

        state_machine["validation"] = AnimationGenerator.validate_state_machine(state_machine)

        return state_machine

    @staticmethod
    def validate_state_machine(state_machine: Dict[str, Any]) -> Dict[str, Any]:
        """Report unreachable states and dead ends (non-looping, non-terminal, no exit)."""
        states = state_machine["states"]
        any_targets = [t["to"] for t in state_machine["any_state_transitions"]]
        reachable = {state_machine["default_state"]}
        frontier = [state_machine["default_state"]]
        while frontier:
            current = frontier.pop()
            targets = [t["to"] for t in states[current]["transitions"]]
            if not states[current]["terminal"]:
                targets += any_targets
            for target in targets:
                if target in states and target not in reachable:
                    reachable.add(target)
                    frontier.append(target)

        unreachable = [name for name in states if name not in reachable]
        dead_ends = [
            name for name, st in states.items()
            if not st["loop"] and not st["terminal"] and not st["transitions"]
        ]
        terminal_with_exits = [name for name, st in states.items() if st["terminal"] and st["transitions"]]
        return {
            "valid": not unreachable and not dead_ends and not terminal_with_exits,
            "unreachable_states": unreachable,
            "dead_end_states": dead_ends,
            "terminal_states": [name for name, st in states.items() if st["terminal"]],
            "terminal_states_with_exits": terminal_with_exits
        }

    @staticmethod
    def generate_procedural_animation(anim_type: str, params: Dict[str, float]) -> Dict[str, Any]:
        """Generate procedural animation rules."""
        procedural = {
            "id": str(uuid.uuid4()),
            "type": anim_type,
            "parameters": params,
            "rules": [],
            "update_frequency": "every_frame"
        }

        if anim_type == "look_at":
            procedural["rules"] = [
                {"bone": "head", "type": "aim", "target": "look_target", "weight": params.get("head_weight", 0.6)},
                {"bone": "neck", "type": "aim", "target": "look_target", "weight": params.get("neck_weight", 0.3)},
                {"bone": "spine2", "type": "aim", "target": "look_target", "weight": params.get("spine_weight", 0.1)}
            ]

        elif anim_type == "foot_ik":
            procedural["rules"] = [
                {"chain": "leg_ik_l", "type": "ground_conform", "ray_offset": 0.1},
                {"chain": "leg_ik_r", "type": "ground_conform", "ray_offset": 0.1},
                {"bone": "hips", "type": "height_adjust", "based_on": ["foot_l", "foot_r"]}
            ]

        elif anim_type == "ragdoll_blend":
            procedural["rules"] = [
                {"type": "physics_blend", "weight": params.get("ragdoll_weight", 0)},
                {"type": "recovery_blend", "duration": params.get("recovery_time", 1.0)}
            ]

        elif anim_type == "breathing":
            procedural["rules"] = [
                {"bone": "spine", "type": "sine_rotation", "axis": "x", "amplitude": 2, "frequency": 0.25},
                {"bone": "spine1", "type": "sine_rotation", "axis": "x", "amplitude": 1.5, "frequency": 0.25, "phase": 0.1}
            ]

        return procedural

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_pipeline_overview():
    """Get overview of the Text-to-Animation Pipeline"""
    return {
        "pipeline": "Text-to-Animation Pipeline v15.0",
        "description": "Generate animation data and rigging specs from natural language",
        "capabilities": [
            "Skeleton/armature generation",
            "Keyframe animation sequences",
            "Blend tree configuration",
            "State machine generation",
            "Procedural animation rules",
            "IK/FK chain setup",
            "Face rig support"
        ],
        "rig_types": [r.value for r in RigType],
        "animation_types": [a.value for a in AnimationType],
        "interpolation_types": [i.value for i in InterpolationType],
        "co_coding_enabled": True,
        "jeeves_integration": True,
        "timing_contract": TIMING_CONTRACT_VERSION
    }

@router.post("/rig/generate")
async def generate_rig(request: RigGenerationRequest):
    """Generate skeleton/armature from description"""
    try:
        parsed = AnimationGenerator.parse_description(request.description)
        rig_type = request.rig_type or parsed["rig_type"] or RigType.HUMANOID

        skeleton = AnimationGenerator.generate_skeleton(
            rig_type,
            request.include_fingers,
            request.include_face_rig
        )

        # Add custom bones
        for bone_name in request.custom_bones:
            skeleton["bones"].append({
                "name": bone_name,
                "parent": "root",
                "position": [0, 0, 0],
                "custom": True
            })
            skeleton["metadata"]["bone_count"] += 1

        return {
            "success": True,
            "skeleton": skeleton,
            "parsed_description": parsed
        }

    except Exception as e:
        raise internal_http_error("Animation request failed", e) from None

@router.post("/animation/generate")
async def generate_animation(request: AnimationGenerationRequest):
    """Generate keyframe animation from description"""
    try:
        animation, parsed = AnimationGenerator._build_animation(request)

        return {
            "success": True,
            "animation": animation,
            "parsed_description": parsed
        }

    except Exception as e:
        raise internal_http_error("Animation request failed", e) from None

@router.post("/blend-tree/generate")
async def generate_blend_tree(request: BlendTreeRequest):
    """Generate blend tree configuration"""
    blend_tree = AnimationGenerator.generate_blend_tree(
        request.animations,
        request.blend_parameter,
        request.blend_type
    )

    return {
        "success": True,
        "blend_tree": blend_tree
    }

@router.post("/state-machine/generate")
async def generate_state_machine(request: StateMachineRequest):
    """Generate animation state machine"""
    state_machine = AnimationGenerator.generate_state_machine(
        request.states,
        request.default_state,
        request.transitions
    )

    return {
        "success": True,
        "state_machine": state_machine
    }

@router.post("/procedural/generate")
async def generate_procedural(request: ProceduralAnimationRequest):
    """Generate procedural animation rules"""
    procedural = AnimationGenerator.generate_procedural_animation(
        request.animation_type,
        request.parameters
    )

    return {
        "success": True,
        "procedural_animation": procedural
    }

@router.get("/timing/budgets")
async def get_timing_budgets():
    """Frame-timing contract and readability budgets (frames at the default fps)."""
    return {
        "contract": TIMING_CONTRACT_VERSION,
        "default_fps": DEFAULT_FPS,
        "hit_frame": "0-based integer frame index from clip start at the clip's authored fps",
        "combat_budgets": COMBAT_TIMING_BUDGETS,
        "blend_time_defaults": BLEND_TIME_DEFAULTS,
        "max_transition_blend_seconds": MAX_TRANSITION_BLEND_SECONDS,
        "presets": {
            move: compute_combat_phases(move, template["duration"])
            for move, template in ANIMATION_TEMPLATES[AnimationType.COMBAT]["humanoid"].items()
            if move in COMBAT_MOVE_WEIGHT_CLASS
        }
    }

@router.post("/timing/validate")
async def validate_timing(request: TimingValidationRequest):
    """Validate authored combat timing against the hit-frame contract and budgets."""
    return validate_combat_timing(
        request.anticipation_frames,
        request.active_frames,
        request.recovery_frames,
        request.hit_frames,
        fps=request.fps,
        weight_class=request.weight_class,
        total_frames=request.total_frames,
    )

@router.get("/skeletons")
async def get_skeleton_templates():
    """Get all skeleton templates"""
    return {
        "templates": {
            rig_type.value: {
                "bone_count": template["bone_count"],
                "ik_chains": len(template["ik_chains"])
            }
            for rig_type, template in SKELETON_TEMPLATES.items()
        }
    }

@router.get("/presets/{animation_type}")
async def get_animation_presets(animation_type: str):
    """Get animation presets for a type"""
    try:
        anim_type = AnimationType(animation_type)
        return {
            "success": True,
            "presets": ANIMATION_TEMPLATES.get(anim_type, {})
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown animation type: {animation_type}")



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIAnimationRequest(BaseModel):
    """Request for AI-powered animation generation"""
    character_type: str = Field(..., description="humanoid, quadruped, creature, etc.")
    animation_name: str = Field(..., description="walk, run, attack, idle, etc.")
    style: str = Field(default="realistic", description="realistic, stylized, cartoon")


class AIVFXRequest(BaseModel):
    """Request for AI-powered VFX generation"""
    effect_type: str = Field(..., description="explosion, fire, magic, etc.")
    visual_style: str = Field(default="realistic", description="realistic, stylized, pixel")


@router.post("/ai/animation/generate")
async def ai_generate_animation(request: AIAnimationRequest):
    """
    Generate animation keyframes and timing using AI (GPT-4o).
    Creates smooth, expressive animations with proper timing.
    """
    try:
        fallback_reason = None
        try:
            llm_service = get_game_llm_service()
            result = await llm_service.generate_animation_sequence(
                character_type=request.character_type,
                animation_name=request.animation_name,
                style=request.style
            )
        except Exception as llm_error:  # LLM outage must degrade to templates, not 500
            result = {"success": False}
            fallback_reason = type(llm_error).__name__

        if isinstance(result, dict) and result.get("success"):
            return {
                "success": True,
                "animation": result["response"],
                "ai_generated": True,
                "model": "gpt-4o",
                "generation_metadata": {
                    "character_type": request.character_type,
                    "animation_name": request.animation_name,
                    "style": request.style
                }
            }
        else:
            # Fallback to template-based generation; infer the clip family from
            # the requested name (e.g. "attack" -> combat) instead of forcing locomotion.
            inferred = AnimationGenerator.parse_description(request.animation_name)["animation_type"]
            fallback_request = AnimationGenerationRequest(
                description=f"{request.character_type} {request.animation_name} {request.style}"[:10000],
                animation_type=inferred or AnimationType.LOCOMOTION
            )
            return {
                "success": True,
                "animation": AnimationGenerator.generate_animation(fallback_request),
                "ai_generated": False,
                "fallback_reason": fallback_reason or "llm_unavailable"
            }

    except Exception as e:
        raise internal_http_error("AI animation generation failed", e) from None


@router.post("/ai/vfx/generate")
async def ai_generate_vfx(request: AIVFXRequest):
    """
    Generate VFX particle system configurations using AI.
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
            return {
                "success": True,
                "vfx_system": {
                    "effect_type": request.effect_type,
                    "template": "basic_particle_system"
                },
                "ai_generated": False
            }

    except Exception as e:
        raise internal_http_error("AI VFX generation failed", e) from None
