"""Expressive TTS shaping for engine-owned speech synthesis.\n\nThe backend owns presentation concerns only: tone presets, voice/speed choices,\ncadence shaping, chunking, and the product-facing response shape. Provider\ncredentials, provider transport, governance/admission, and speech execution\nbelong to the Skeleton engine process through EngineClient.\n\nThis keeps the historical immersive storyteller behavior while enforcing the\nStage-5 process boundary: backend may describe the desired speech operation but\ncannot instantiate or authenticate a model provider locally.\n"""
from __future__ import annotations
import base64
import re
import uuid
from typing import Dict, List, Optional

from core.engine_client import EngineClient, EngineClientError

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
    """Rewrite a script with bounded, linear-time cadence shaping."""
    preset = resolve_tone(tone)
    pauses = preset["pauses"]
    use_ellipses = preset["ellipses"]
    if not text:
        return ""

    # Bound caller-controlled text before any shaping work. TTS accepts at most
    # TTS_LIMIT characters anyway, so processing more only creates DoS surface.
    s = text.strip()[:TTS_LIMIT]
    if not s:
        return ""

    translation = str.maketrans({ch: " " for ch in "#*_`~>"})
    s = s.translate(translation)
    s = " ".join(s.split())
    s = s.replace(" - ", " — ")

    if pauses in ("medium", "rich"):
        # Input is whitespace-normalized, so connective matching can use
        # bounded case-insensitive substring scans instead of backtracking regex.
        for word in _BREATH_WORDS:
            needle = f" {word.casefold()} "
            cursor = 0
            while True:
                folded = s.casefold()
                index = folded.find(needle, cursor)
                if index < 0:
                    break
                if index > 0 and s[index - 1].isalpha():
                    s = s[:index] + ", " + s[index + 1:]
                    cursor = index + len(word) + 2
                else:
                    cursor = index + len(needle)

        folded = s.casefold()
        for word in _PAUSE_AFTER_INTRO:
            prefix = word.casefold() + " "
            if folded.startswith(prefix):
                s = s[:len(word)] + ", " + s[len(word) + 1:]
                break

    if pauses == "rich":
        def _breathe(sentence: str) -> str:
            if len(sentence) < 140:
                return sentence
            folded = sentence.casefold()
            candidates = []
            for word in ("and", "but", "which", "where", "while"):
                index = folded.find(f" {word} ")
                if index >= 0:
                    candidates.append(index)
            if not candidates:
                return sentence
            index = min(candidates)
            return sentence[:index] + ", " + sentence[index + 1:]

        sentences: list[str] = []
        current: list[str] = []
        for character in s:
            current.append(character)
            if character in ".!?":
                sentence = "".join(current).strip()
                if sentence:
                    sentences.append(sentence)
                current = []
        tail = "".join(current).strip()
        if tail:
            sentences.append(tail)
        s = " ".join(_breathe(sentence) for sentence in sentences)

    if use_ellipses:
        folded = s.casefold()
        for phrase in ("and then", "until", "but then", "slowly", "at last", "finally"):
            needle = phrase + ","
            index = folded.find(needle)
            if index >= 0:
                comma = index + len(phrase)
                s = s[:comma] + "…" + s[comma + 1:]
                break

    s = s.replace(" ,", ",").replace(", ,", ",")
    s = " ".join(s.split()).strip()

    if s and s[-1] not in ".!?…":
        s += "."

    if len(s) > TTS_LIMIT:
        cut = s[:TTS_LIMIT]
        last_terminal = max(cut.rfind(mark) for mark in ".!?…")
        s = cut[: last_terminal + 1] if last_terminal >= 0 else cut
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

    client = EngineClient.from_env()
    if client is None:
        raise EngineClientError("canonical engine is not configured")
    operation_id = str(uuid.uuid4())
    response = await client.synthesize_speech(
        actor_id="expressive-tts",
        tenant_id="default",
        operation_id=operation_id,
        text=spoken,
        voice=voice,
        speed=speed,
        response_format="mp3",
        trace_id="expressive-tts:" + operation_id,
    )
    audio = response.get("audio")
    if not isinstance(audio, (bytes, bytearray)) or not audio:
        raise EngineClientError("engine speech response is missing audio")
    audio_b64 = base64.b64encode(bytes(audio)).decode("ascii")
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
