"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CODEDOCK AI MUSIC PIPELINE v11.0.0                         ║
║                                                                               ║
║  Text-to-Game-Music Generation System                                         ║
║  - AI-powered music composition                                               ║
║  - Game soundtrack generation                                                 ║
║  - Sound effects creation                                                     ║
║  - Adaptive/procedural music                                                  ║
║  - Multiple genres and moods                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import uuid
import os

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter(prefix="/music", tags=["AI Music Pipeline"])

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ============================================================================
# REQUEST MODELS
# ============================================================================

class MusicGenerationRequest(BaseModel):
    description: str = Field(..., min_length=5, description="Music description")
    genre: Literal[
        "8bit", "chiptune", "orchestral", "ambient", "electronic", 
        "rock", "jazz", "synthwave", "lofi", "epic", "horror",
        "peaceful", "action", "puzzle", "adventure", "retro"
    ] = "orchestral"
    mood: Literal[
        "happy", "sad", "tense", "peaceful", "epic", "mysterious",
        "energetic", "calm", "dark", "uplifting", "nostalgic", "heroic"
    ] = "epic"
    duration: Literal["short", "medium", "long"] = "medium"  # 15s, 30s, 60s+
    loopable: bool = True
    tempo: Optional[int] = Field(None, ge=40, le=200, description="BPM")
    game_context: Optional[str] = Field(None, description="Game scene/context")

class SoundEffectRequest(BaseModel):
    description: str = Field(..., min_length=3)
    category: Literal[
        "ui", "combat", "environment", "character", "item",
        "ambient", "explosion", "magic", "mechanical", "nature"
    ] = "ui"
    duration: Literal["instant", "short", "medium"] = "short"  # <0.5s, 0.5-2s, 2-5s

class AdaptiveMusicRequest(BaseModel):
    game_state: str = Field(..., description="Current game state")
    intensity: float = Field(0.5, ge=0.0, le=1.0, description="Action intensity 0-1")
    base_theme: Optional[str] = Field(None, description="Base musical theme")
    transitions: bool = True

class MusicTheoryRequest(BaseModel):
    description: str
    output_format: Literal["midi_data", "sheet_music", "chord_progression", "melody_notes"] = "chord_progression"

# ============================================================================
# AI HELPER
# ============================================================================

async def call_music_ai(prompt: str, system_prompt: str) -> str:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"music-{uuid.uuid4().hex[:8]}",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        response = await chat.send_message(UserMessage(text=prompt))
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

# ============================================================================
# MUSIC PIPELINE ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_music_info():
    """Get Music Pipeline capabilities"""
    return {
        "name": "CodeDock AI Music Pipeline",
        "version": "11.0.0",
        "description": "AI-powered game music and sound generation",
        "capabilities": [
            "Text-to-music generation",
            "Game soundtrack composition",
            "Sound effect creation",
            "Adaptive/procedural music",
            "Loop-ready tracks",
            "Mood-based generation",
            "Music theory assistance"
        ],
        "genres": [
            "8bit", "chiptune", "orchestral", "ambient", "electronic",
            "rock", "jazz", "synthwave", "lofi", "epic", "horror",
            "peaceful", "action", "puzzle", "adventure", "retro"
        ],
        "moods": [
            "happy", "sad", "tense", "peaceful", "epic", "mysterious",
            "energetic", "calm", "dark", "uplifting", "nostalgic", "heroic"
        ],
        "output_formats": [
            "composition_spec",  # Detailed musical specification
            "midi_description",  # MIDI-compatible data
            "chord_progression",
            "melody_notation",
            "production_notes"
        ],
        "integrations": ["Suno", "Stable Audio", "Mubert", "AIVA"],
        "features": {
            "loopable_tracks": True,
            "adaptive_music": True,
            "sound_effects": True,
            "stem_separation": True,
            "tempo_control": True
        }
    }

@router.post("/generate")
async def generate_music(request: MusicGenerationRequest):
    """Generate game music from text description"""
    request_id = str(uuid.uuid4())
    
    tempo_map = {
        "8bit": 140, "chiptune": 150, "orchestral": 90, "ambient": 60,
        "electronic": 128, "rock": 120, "jazz": 100, "synthwave": 110,
        "lofi": 75, "epic": 100, "horror": 70, "peaceful": 65,
        "action": 140, "puzzle": 85, "adventure": 110, "retro": 130
    }
    
    duration_map = {"short": "15-20 seconds", "medium": "30-45 seconds", "long": "60-90 seconds"}
    tempo = request.tempo or tempo_map.get(request.genre, 100)
    
    system_prompt = """You are a world-class video game music composer with expertise in all genres.
You've composed for AAA games and indie hits alike.
You understand music theory deeply and can translate descriptions into detailed musical specifications.
Your compositions are memorable, appropriate for games, and technically sound."""

    prompt = f"""Compose game music based on this description:

**Description:** {request.description}
**Genre:** {request.genre}
**Mood:** {request.mood}
**Duration:** {duration_map[request.duration]}
**Tempo:** {tempo} BPM
**Loopable:** {"Yes - ensure seamless loop" if request.loopable else "No"}
{f'**Game Context:** {request.game_context}' if request.game_context else ''}

**Create a complete musical specification including:**

1. **Overview**
   - Title suggestion
   - One-line description
   - Key and time signature
   - Tempo and feel

2. **Structure** (for {duration_map[request.duration]})
   - Intro (if applicable)
   - Main sections (A, B, etc.)
   - Loop point (if loopable)
   - Transitions

3. **Instrumentation**
   - Lead instruments
   - Rhythm section
   - Bass
   - Percussion
   - Atmosphere/pads
   - Special effects

4. **Chord Progression**
   - Main progression with Roman numerals and actual chords
   - Secondary progressions
   - Any modulations

5. **Melody**
   - Main melodic theme (describe the contour and notes)
   - Counter-melodies
   - Motifs to repeat

6. **Rhythm Patterns**
   - Drum pattern description
   - Bass rhythm
   - Rhythmic hooks

7. **Production Notes**
   - Mix suggestions
   - Effects (reverb, delay, etc.)
   - Dynamic range
   - Reference tracks (similar existing songs)

8. **Implementation Code** (for game engines)
   - Pseudo-code for adaptive playback
   - Loop markers
   - Stem suggestions for dynamic mixing"""

    try:
        result = await call_music_ai(prompt, system_prompt)
        
        return {
            "id": request_id,
            "status": "success",
            "composition": result,
            "parameters": {
                "genre": request.genre,
                "mood": request.mood,
                "tempo": tempo,
                "duration": request.duration,
                "loopable": request.loopable,
                "game_context": request.game_context
            },
            "export_ready": {
                "suno_prompt": f"{request.genre} {request.mood} game music, {tempo}BPM, {request.description}",
                "mubert_tags": [request.genre, request.mood, "game", "loop" if request.loopable else "linear"],
                "stable_audio_prompt": f"{request.mood} {request.genre} video game soundtrack, {tempo} bpm, {'loopable' if request.loopable else 'cinematic'}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sound-effect")
async def generate_sound_effect(request: SoundEffectRequest):
    """Generate sound effect specification"""
    request_id = str(uuid.uuid4())
    
    duration_map = {"instant": "0.1-0.5 seconds", "short": "0.5-2 seconds", "medium": "2-5 seconds"}
    
    prompt = f"""Design a game sound effect:

**Description:** {request.description}
**Category:** {request.category}
**Duration:** {duration_map[request.duration]}

**Create a detailed sound design specification:**

1. **Sound Overview**
   - One-line description
   - Emotional/functional purpose
   - When it triggers in-game

2. **Sound Layers**
   - Primary sound (main element)
   - Secondary sounds (supporting)
   - Sub-bass/rumble (if applicable)
   - High-end sparkle/air

3. **ADSR Envelope**
   - Attack time
   - Decay time
   - Sustain level
   - Release time

4. **Synthesis/Source**
   - Base waveform or sample type
   - Pitch envelope
   - Filter settings
   - Modulation

5. **Processing Chain**
   - EQ suggestions
   - Compression
   - Reverb/delay
   - Special effects (distortion, chorus, etc.)

6. **Variations**
   - Random pitch range
   - Random timing variations
   - Alternative versions

7. **Integration Notes**
   - Volume level (relative to music)
   - Spatialization (2D/3D)
   - Priority level
   - Polyphony limit"""

    try:
        result = await call_music_ai(prompt, "You are a professional game audio designer.")
        
        return {
            "id": request_id,
            "status": "success",
            "sound_design": result,
            "parameters": {
                "category": request.category,
                "duration": request.duration,
                "description": request.description
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/adaptive-music")
async def generate_adaptive_music(request: AdaptiveMusicRequest):
    """Generate adaptive/procedural music system"""
    request_id = str(uuid.uuid4())
    
    prompt = f"""Design an adaptive music system for this game state:

**Current State:** {request.game_state}
**Intensity Level:** {request.intensity * 100:.0f}%
{f'**Base Theme:** {request.base_theme}' if request.base_theme else ''}
**Smooth Transitions:** {"Yes" if request.transitions else "No"}

**Create an adaptive music specification:**

1. **Layer System**
   - Base layer (always playing)
   - Intensity layers (added as intensity increases)
   - Stinger triggers (one-shots for events)

2. **Intensity Mapping**
   - 0-25%: Ambient/exploration layers
   - 25-50%: Light tension layers
   - 50-75%: Action/combat layers
   - 75-100%: Full intensity/boss layers

3. **Transitions**
   - Crossfade durations
   - Musical transition points (beat-synced)
   - Stinger overlays

4. **Implementation**
   ```
   // Pseudo-code for adaptive system
   function updateMusic(intensity) {{
       // Layer control logic
   }}
   ```

5. **Stem List**
   - Drums (with intensity variations)
   - Bass (with intensity variations)
   - Melody/lead
   - Harmony/pads
   - Percussion accents
   - Tension elements

6. **Game State Mappings**
   - Menu → Ambient base
   - Exploration → Base + light melody
   - Combat → Full layers
   - Victory → Triumphant stinger
   - Defeat → Somber transition"""

    try:
        result = await call_music_ai(prompt, "You are an expert in adaptive game audio systems like FMOD and Wwise.")
        
        return {
            "id": request_id,
            "status": "success",
            "adaptive_system": result,
            "current_config": {
                "game_state": request.game_state,
                "intensity": request.intensity,
                "recommended_layers": [
                    "base" if request.intensity > 0 else None,
                    "rhythm" if request.intensity > 0.25 else None,
                    "melody" if request.intensity > 0.5 else None,
                    "full" if request.intensity > 0.75 else None
                ]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/music-theory")
async def music_theory_assist(request: MusicTheoryRequest):
    """Get music theory assistance"""
    request_id = str(uuid.uuid4())
    
    format_instructions = {
        "midi_data": "Provide note data in MIDI-compatible format (note, velocity, duration)",
        "sheet_music": "Provide standard music notation description",
        "chord_progression": "Provide chord symbols and Roman numeral analysis",
        "melody_notes": "Provide melody as note names with octave and rhythm"
    }
    
    prompt = f"""Music theory request:

**Description:** {request.description}
**Output Format:** {request.output_format}

{format_instructions[request.output_format]}

Provide comprehensive musical data that can be used for:
- Implementation in code
- Input to DAW software
- Reference for musicians
- Educational purposes"""

    try:
        result = await call_music_ai(prompt, "You are a music theory expert and composer.")
        
        return {
            "id": request_id,
            "status": "success",
            "output_format": request.output_format,
            "music_data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/presets")
async def get_music_presets():
    """Get pre-configured music presets for common game scenarios"""
    return {
        "presets": [
            {
                "id": "menu_theme",
                "name": "Main Menu",
                "genre": "orchestral",
                "mood": "epic",
                "tempo": 90,
                "loopable": True,
                "description": "Majestic, inviting main menu music"
            },
            {
                "id": "exploration",
                "name": "Exploration",
                "genre": "ambient",
                "mood": "mysterious",
                "tempo": 70,
                "loopable": True,
                "description": "Atmospheric exploration music"
            },
            {
                "id": "combat",
                "name": "Combat",
                "genre": "action",
                "mood": "energetic",
                "tempo": 140,
                "loopable": True,
                "description": "Intense battle music"
            },
            {
                "id": "boss_battle",
                "name": "Boss Battle",
                "genre": "epic",
                "mood": "tense",
                "tempo": 120,
                "loopable": True,
                "description": "Epic boss encounter music"
            },
            {
                "id": "victory",
                "name": "Victory",
                "genre": "orchestral",
                "mood": "uplifting",
                "tempo": 110,
                "loopable": False,
                "description": "Triumphant victory fanfare"
            },
            {
                "id": "puzzle",
                "name": "Puzzle",
                "genre": "lofi",
                "mood": "calm",
                "tempo": 80,
                "loopable": True,
                "description": "Thoughtful puzzle-solving music"
            },
            {
                "id": "retro_platformer",
                "name": "Retro Platformer",
                "genre": "chiptune",
                "mood": "happy",
                "tempo": 150,
                "loopable": True,
                "description": "Upbeat 8-bit platformer music"
            },
            {
                "id": "horror",
                "name": "Horror",
                "genre": "horror",
                "mood": "dark",
                "tempo": 60,
                "loopable": True,
                "description": "Creepy atmospheric horror music"
            }
        ]
    }
