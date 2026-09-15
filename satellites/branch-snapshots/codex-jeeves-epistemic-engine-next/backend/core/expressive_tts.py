"""
╔══════════════════════════════════════════════════════════════════════════╗
║  EXPRESSIVE TTS ENGINE — "innlevelse" / immersive storyteller delivery    ║
║                                                                            ║
║  The Emergent LLM key only exposes `tts-1` / `tts-1-hd` (the steerable     ║
║  `gpt-4o-mini-tts` `instructions` param is NOT available through the       ║
║  proxy). tts-1-hd, however, honours PUNCTUATION & PACING in the input      ║
║  text — commas, periods, ellipses, em-dashes and line breaks all change    ║
║  the delivered rhythm.                                                      ║
║                                                                            ║
║  So we get augmented tone control two ways:                                ║
║    1. TONE PRESETS  → pick the voice + speaking-rate that fits the mood.    ║
║    2. CADENCE SHAPING → rewrite the script with storyteller punctuation     ║
║       (dramatic em-dash beats, suspense ellipses, breath pauses) so the     ║
║       HD model performs it with real rhythm & emotional lift.               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import re
from typing import Dict, List, Optional

TTS_LIMIT = 4096

# ── TONE PRESETS ────────────────────────────────────────────────────────────
# voice    : a valid tts-1-hd voice (alloy/ash/coral/echo/fable/nova/onyx/sage/shimmer)
# speed    : 0.25–4.0 — measured (<1) reads more cinematic; >1 reads more energetic
# pauses   : cadence richness — "light" | "gentle" | "medium" | "rich"
# ellipses : add suspense beats at clause boundaries
# label    : human description for the UI
TONE_PRESETS: Dict[str, Dict] = {
    "butler":      {"voice": "fable",   "speed": 0.94, "pauses": "rich",   "ellipses": False, "label": "Jeeves — warm, immersive butler"},
    "storyteller": {"voice": "fable",   "speed": 0.92, "pauses": "rich",   "ellipses": True,  "label": "Cinematic storyteller"},
    "warm":        {"voice": "nova",    "speed": 0.96, "pauses": "gentle", "ellipses": False, "label": "Warm & friendly"},
    "dramatic":    {"voice": "onyx",    "speed": 0.88, "pauses": "rich",   "ellipses": True,  "label": "Dramatic & deep"},
    "witty":       {"voice": "fable",   "speed": 1.05, "pauses": "light",  "ellipses": False, "label": "Witty & quick"},
    "solemn":      {"voice": "onyx",    "speed": 0.85, "pauses": "rich",   "ellipses": False, "label": "Solemn & grave"},
    "excited":     {"voice": "shimmer", "speed": 1.12, "pauses": "light",  "ellipses": False, "label": "Excited & upbeat"},
    "gentle":      {"voice": "coral",   "speed": 0.90, "pauses": "gentle", "ellipses": False, "label": "Gentle & reassuring"},
    "calm":        {"voice": "sage",    "speed": 0.90, "pauses": "gentle", "ellipses": False, "label": "Calm & measured"},
    "suspense":    {"voice": "onyx",    "speed": 0.86, "pauses": "rich",   "ellipses": True,  "label": "Suspenseful"},
    "triumphant":  {"voice": "fable",   "speed": 1.00, "pauses": "medium", "ellipses": False, "label": "Triumphant"},
    "narrator":    {"voice": "sage",    "speed": 0.93, "pauses": "rich",   "ellipses": True,  "label": "Epic lore narrator"},
}
DEFAULT_TONE = "butler"

# Emotion (from agent context) → best-fit tone, so delivery adapts to the user.
EMOTION_TONE = {
    "frustrated": "gentle",
    "confused":   "calm",
    "overwhelmed": "gentle",
    "tired":      "calm",
    "confident":  "triumphant",
    "excited":    "excited",
    "happy":      "warm",
    "neutral":    "butler",
}

# Words that open a clause — a gentle breath pause *before* them adds rhythm.
_BREATH_WORDS = (
    "but", "and yet", "however", "meanwhile", "suddenly", "finally",
    "at last", "of course", "indeed", "naturally", "in truth", "now then",
    "you see", "after all", "for", "because", "so", "then", "yet",
)
_PAUSE_AFTER_INTRO = (
    "now", "well", "ah", "so", "right then", "right", "listen", "behold",
    "once upon a time", "long ago", "in the beginning", "picture this",
)


def emotion_to_tone(emotional_state: Optional[str]) -> str:
    if not emotional_state:
        return DEFAULT_TONE
    return EMOTION_TONE.get(emotional_state.strip().lower(), DEFAULT_TONE)


def resolve_tone(tone: Optional[str]) -> Dict:
    t = (tone or DEFAULT_TONE).strip().lower()
    preset = TONE_PRESETS.get(t)
    if not preset:
        preset = TONE_PRESETS[DEFAULT_TONE]
        t = DEFAULT_TONE
    return {"id": t, **preset}


def shape_cadence(text: str, tone: Optional[str] = None) -> str:
    """Rewrite a script with storyteller punctuation so tts-1-hd performs it
    with rhythm, breath and emotional lift. Meaning is never changed — only
    pacing marks (commas, em-dashes, ellipses) are added."""
    preset = resolve_tone(tone)
    pauses = preset["pauses"]
    use_ellipses = preset["ellipses"]
    if not text:
        return ""

    s = text.strip()
    # Normalise whitespace and stray markdown that would be read aloud.
    s = re.sub(r"[#*_`~>]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # 1) Hyphen spans → em-dash dramatic beats.  "word - word" → "word — word"
    s = re.sub(r"\s+-\s+", " — ", s)

    if pauses in ("medium", "rich"):
        # 2) Gentle breath comma *before* clause-opening connective words
        #    (only when not already preceded by punctuation).
        for w in _BREATH_WORDS:
            s = re.sub(rf"(?<=[a-zA-Z])\s+({re.escape(w)})\b",
                       lambda m: f", {m.group(1)}", s, flags=re.IGNORECASE)
        # 3) Pause after a short scene-setting opener: "Now then the door..."
        for w in _PAUSE_AFTER_INTRO:
            s = re.sub(rf"^({re.escape(w)})\s+(?=[a-zA-Z])",
                       lambda m: f"{m.group(1)}, ", s, flags=re.IGNORECASE)

    if pauses == "rich":
        # 4) Break very long run-on sentences so the model can breathe — insert
        #    a comma at a natural midpoint conjunction if the sentence is long.
        def _breathe(sentence: str) -> str:
            if len(sentence) < 140:
                return sentence
            # add a comma before a mid conjunction if none nearby
            return re.sub(r"\s+(and|but|which|where|while)\s+",
                          r", \1 ", sentence, count=1)
        s = " ".join(_breathe(p) for p in re.split(r"(?<=[.!?])\s+", s))

    if use_ellipses:
        # 5) Suspense beat: turn a comma after a strong lead-in into an ellipsis
        #    once per script, for a held dramatic pause.
        s = re.sub(r"\b(and then|until|but then|slowly|at last|finally),",
                   r"\1…", s, count=1, flags=re.IGNORECASE)

    # Tidy duplicate punctuation and spacing artefacts.
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\s+—\s+", " — ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Guarantee terminal punctuation for a clean final cadence.
    if s and s[-1] not in ".!?…":
        s += "."

    # Respect the hard TTS input limit — trim at a sentence boundary.
    if len(s) > TTS_LIMIT:
        cut = s[:TTS_LIMIT]
        m = re.search(r"[.!?…][^.!?…]*$", cut)
        s = cut[: m.start() + 1] if m else cut
    return s


async def generate_expressive_tts(
    text: str,
    tone: Optional[str] = None,
    voice_override: Optional[str] = None,
    speed_override: Optional[float] = None,
    shape: bool = True,
) -> Dict:
    """Generate immersive HD audio. Returns {audio_base64, voice, speed, tone,
    spoken_text}. Always uses tts-1-hd (top scale). Raises on failure so the
    caller can present a graceful fallback."""
    preset = resolve_tone(tone)
    voice = voice_override or preset["voice"]
    speed = float(speed_override) if speed_override is not None else float(preset["speed"])
    speed = max(0.25, min(4.0, speed))

    spoken = shape_cadence(text, preset["id"]) if shape else (text or "").strip()[:TTS_LIMIT]
    if not spoken:
        raise ValueError("No text to speak")

    from emergentintegrations.llm.openai import OpenAITextToSpeech
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    tts = OpenAITextToSpeech(api_key=api_key)
    audio_b64 = await tts.generate_speech_base64(
        text=spoken, model="tts-1-hd", voice=voice, speed=speed,
    )
    return {
        "audio_base64": audio_b64,
        "format": "mp3",
        "model": "tts-1-hd",
        "voice": voice,
        "speed": round(speed, 3),
        "tone": preset["id"],
        "tone_label": preset["label"],
        "spoken_text": spoken,
    }


def chunk_for_narration(text: str, max_chars: int = 700) -> List[str]:
    """Split long narration into sentence-bounded chunks for smooth, fast-first
    playback (architect win: streaming-friendly narration)."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    out: List[str] = []
    cur = ""
    for sent in sentences:
        if len(cur) + len(sent) + 1 > max_chars and cur:
            out.append(cur.strip())
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur.strip())
    return out


def tones_catalog() -> List[Dict]:
    return [
        {"id": tid, "label": p["label"], "voice": p["voice"], "speed": p["speed"]}
        for tid, p in TONE_PRESETS.items()
    ]
