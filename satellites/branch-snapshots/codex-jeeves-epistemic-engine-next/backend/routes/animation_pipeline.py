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
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Tuple
from datetime import datetime
from enum import Enum
import uuid
import random
import math

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
# REQUEST/RESPONSE MODELS
# ============================================================================

class RigGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description of the character")
    rig_type: Optional[RigType] = None
    include_face_rig: bool = False
    include_fingers: bool = True
    custom_bones: List[str] = []

class AnimationGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description of the animation")
    animation_type: Optional[AnimationType] = None
    rig_type: RigType = RigType.HUMANOID
    duration: Optional[float] = None
    looping: bool = False
    include_root_motion: bool = False

class BlendTreeRequest(BaseModel):
    animations: List[str]
    blend_parameter: str = "speed"
    blend_type: Literal["1d", "2d", "direct"] = "1d"

class StateMachineRequest(BaseModel):
    states: List[str]
    default_state: str
    transitions: List[Dict[str, Any]] = []

class ProceduralAnimationRequest(BaseModel):
    animation_type: str
    parameters: Dict[str, float] = {}
    constraints: List[str] = []

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
        style_hints: List[str]
    ) -> Dict[str, Any]:
        """Generate keyframe animation data."""
        template = ANIMATION_TEMPLATES.get(anim_type, {}).get(rig_type.value, {})
        
        animation = {
            "id": str(uuid.uuid4()),
            "type": anim_type.value,
            "rig_type": rig_type.value,
            "duration": duration,
            "looping": looping,
            "fps": 30,
            "keyframes": [],
            "curves": {},
            "events": [],
            "metadata": {
                "style": style_hints,
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
        # Generate keyframes based on animation type
        if anim_type == AnimationType.IDLE:
            animation["keyframes"] = AnimationGenerator._generate_idle_keyframes(duration)
        elif anim_type == AnimationType.LOCOMOTION:
            animation["keyframes"] = AnimationGenerator._generate_locomotion_keyframes(duration, style_hints)
            animation["root_motion"] = True
        elif anim_type == AnimationType.COMBAT:
            animation["keyframes"] = AnimationGenerator._generate_combat_keyframes(duration, style_hints)
            animation["events"].append({"time": duration * 0.5, "type": "damage_start"})
            animation["events"].append({"time": duration * 0.7, "type": "damage_end"})
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
    def _generate_idle_keyframes(duration: float) -> List[Dict[str, Any]]:
        """Generate idle animation keyframes."""
        keyframes = []
        num_frames = int(duration * 30)  # 30 fps
        
        for i in range(num_frames + 1):
            time = (i / num_frames) * duration
            breath_cycle = math.sin(time * math.pi * 2 / duration)
            
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
    def _generate_locomotion_keyframes(duration: float, style: List[str]) -> List[Dict[str, Any]]:
        """Generate locomotion animation keyframes."""
        keyframes = []
        num_frames = int(duration * 30)
        
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
            spine_twist = math.sin(cycle * math.pi * 2) * 5
            
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
                "root_position": [0, abs(math.sin(cycle * math.pi * 4)) * 0.02, cycle * 1.4 * speed_multiplier]
            })
        
        return keyframes
    
    @staticmethod
    def _generate_combat_keyframes(duration: float, style: List[str]) -> List[Dict[str, Any]]:
        """Generate combat animation keyframes."""
        keyframes = []
        
        is_powerful = "powerful" in style
        
        # Wind-up phase (0-30%)
        keyframes.append({
            "time": 0,
            "transforms": {
                "spine": {"rotation": [0, -30 if is_powerful else -20, 0]},
                "upper_arm_r": {"rotation": [-60 if is_powerful else -45, 0, -30]},
                "forearm_r": {"rotation": [-90, 0, 0]}
            }
        })
        
        # Peak wind-up (30%)
        keyframes.append({
            "time": duration * 0.3,
            "transforms": {
                "spine": {"rotation": [0, -45 if is_powerful else -30, 0]},
                "upper_arm_r": {"rotation": [-90 if is_powerful else -60, 0, -45]},
                "forearm_r": {"rotation": [-120, 0, 0]}
            }
        })
        
        # Strike (50%)
        keyframes.append({
            "time": duration * 0.5,
            "transforms": {
                "spine": {"rotation": [0, 30 if is_powerful else 20, 0]},
                "upper_arm_r": {"rotation": [30, 0, 30]},
                "forearm_r": {"rotation": [-30, 0, 0]}
            }
        })
        
        # Follow-through (70%)
        keyframes.append({
            "time": duration * 0.7,
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
            for i, anim in enumerate(animations[:4]):
                pos = positions[i] if i < len(positions) else (0, 0)
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
        """Generate an animation state machine."""
        state_machine = {
            "id": str(uuid.uuid4()),
            "default_state": default,
            "states": {},
            "any_state_transitions": [],
            "parameters": []
        }
        
        # Create states
        for state in states:
            state_machine["states"][state] = {
                "name": state,
                "animation": state,
                "transitions": [],
                "speed": 1.0,
                "loop": state in ["idle", "walk", "run"]
            }
        
        # Add transitions
        for trans in transitions:
            from_state = trans.get("from", "any")
            to_state = trans.get("to")
            condition = trans.get("condition", "")
            duration = trans.get("duration", 0.25)
            
            transition_obj = {
                "to": to_state,
                "duration": duration,
                "condition": condition,
                "interruption": "current_then_next"
            }
            
            if from_state == "any":
                state_machine["any_state_transitions"].append(transition_obj)
            elif from_state in state_machine["states"]:
                state_machine["states"][from_state]["transitions"].append(transition_obj)
        
        # Auto-generate common transitions if none provided
        if not transitions:
            common_transitions = [
                {"from": "idle", "to": "walk", "condition": "speed > 0.1"},
                {"from": "walk", "to": "idle", "condition": "speed < 0.1"},
                {"from": "walk", "to": "run", "condition": "speed > 0.5"},
                {"from": "run", "to": "walk", "condition": "speed < 0.5"},
                {"from": "any", "to": "jump", "condition": "jump_trigger"},
                {"from": "any", "to": "attack", "condition": "attack_trigger"}
            ]
            for trans in common_transitions:
                if trans["from"] in state_machine["states"] or trans["from"] == "any":
                    if trans["to"] in state_machine["states"]:
                        if trans["from"] == "any":
                            state_machine["any_state_transitions"].append({
                                "to": trans["to"],
                                "condition": trans["condition"],
                                "duration": 0.1
                            })
                        else:
                            state_machine["states"][trans["from"]]["transitions"].append({
                                "to": trans["to"],
                                "condition": trans["condition"],
                                "duration": 0.25
                            })
        
        # Extract parameters from conditions
        for state in state_machine["states"].values():
            for trans in state["transitions"]:
                if "speed" in trans["condition"]:
                    state_machine["parameters"].append({"name": "speed", "type": "float", "default": 0})
                if "trigger" in trans["condition"]:
                    param = trans["condition"].replace("_trigger", "").replace(" ", "")
                    state_machine["parameters"].append({"name": f"{param}_trigger", "type": "trigger"})
        
        state_machine["parameters"] = list({p["name"]: p for p in state_machine["parameters"]}.values())
        
        return state_machine
    
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
        "jeeves_integration": True
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/animation/generate")
async def generate_animation(request: AnimationGenerationRequest):
    """Generate keyframe animation from description"""
    try:
        parsed = AnimationGenerator.parse_description(request.description)
        anim_type = request.animation_type or parsed["animation_type"] or AnimationType.IDLE
        duration = request.duration or 1.0
        
        animation = AnimationGenerator.generate_keyframe_animation(
            anim_type,
            request.rig_type,
            duration,
            request.looping,
            parsed["style_hints"]
        )
        
        if request.include_root_motion:
            animation["root_motion"] = True
        
        return {
            "success": True,
            "animation": animation,
            "parsed_description": parsed
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_animation_sequence(
            character_type=request.character_type,
            animation_name=request.animation_name,
            style=request.style
        )
        
        if result["success"]:
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
            # Fallback to template-based generation
            fallback_request = AnimationGenerationRequest(
                description=f"{request.character_type} {request.animation_name}",
                animation_type=AnimationType.LOCOMOTION
            )
            return {
                "success": True,
                "animation": AnimationGenerator.generate_animation(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI animation generation failed: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"AI VFX generation failed: {str(e)}")
