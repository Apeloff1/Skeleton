"""Expressive TTS shaping for engine-owned speech synthesis.\n\nThe backend owns presentation concerns only: tone presets, voice/speed choices,\ncadence shaping, chunking, and the product-facing response shape. Provider\ncredentials, provider transport, governance/admission, and speech execution\nbelong to the Skeleton engine process through EngineClient.\n\nThis keeps the historical immersive storyteller behavior while enforcing the\nStage-5 process boundary: backend may describe the desired speech operation but\ncannot instantiate or authenticate a model provider locally.\n"""
from __future__ import annotations
import base64
import math
import re
import uuid
from typing import Dict, List, Optional

from core.engine_client import EngineClient, EngineClientError

TTS_LIMIT = 4096
MAX_NARRATION_TEXT_CHARS = 1_000_000
MAX_NARRATION_CHUNKS = 4096
MAX_ENGINE_AUDIO_BYTES = 48 * 1024 * 1024

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
    if emotional_state is None or emotional_state == "":
        return DEFAULT_TONE
    if not isinstance(emotional_state, str):
        raise ValueError("emotional state must be a string")
    return EMOTION_TONE.get(emotional_state.strip().lower(), DEFAULT_TONE)


def resolve_tone(tone: Optional[str]) -> Dict:
    if tone is not None and not isinstance(tone, str):
        raise ValueError("TTS tone must be a string")
    t = (tone or DEFAULT_TONE).strip().lower()
    preset = TONE_PRESETS.get(t)
    if not preset:
        preset = TONE_PRESETS[DEFAULT_TONE]
        t = DEFAULT_TONE
    return {"id": t, **preset}


def shape_cadence(text: str, tone: Optional[str] = None) -> str:
    """Rewrite a script with bounded, linear-time cadence shaping."""
    if not isinstance(text, str):
        raise ValueError("TTS text must be a string")
    preset = resolve_tone(tone)
    pauses = preset["pauses"]
    use_ellipses = preset["ellipses"]
    if not text:
        return ""

    # Bound caller-controlled input *before* stripping. Calling strip() on a
    # million-character hostile string allocates and scans the whole value
    # despite the TTS_LIMIT contract.
    s = text[:TTS_LIMIT].strip()
    if not s:
        return ""

    translation = str.maketrans({ch: " " for ch in "#*_`~>"})
    s = s.translate(translation)
    s = " ".join(s.split())
    s = s.replace(" - ", " — ")

    if pauses in ("medium", "rich"):
        # One-pass connective detection: each character is visited once,
        # with a fixed 16-word vocabulary. Avoid repeated casefold() and
        # whole-string insertion on every occurrence (quadratic on "a and "
        # repeated thousands of times).
        emitted: list[str] = []
        index = 0
        length = len(s)
        folded_words = tuple((word, word.casefold()) for word in _BREATH_WORDS)
        while index < length:
            if s[index] == " " and index > 0 and s[index - 1].isalpha():
                matched = False
                for word, folded_word in folded_words:
                    end = index + 1 + len(word)
                    if (
                        end < length
                        and s[end] == " "
                        and s[index + 1:end].casefold() == folded_word
                    ):
                        emitted.append(", ")
                        index += 1  # consume the original space exactly once
                        matched = True
                        break
                if matched:
                    continue
            emitted.append(s[index])
            index += 1
        s = "".join(emitted)

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
    if type(shape) is not bool:
        raise ValueError("TTS shaping flag must be boolean")
    if not isinstance(text, str):
        raise ValueError("TTS text must be a string")
    preset = resolve_tone(tone)
    if voice_override is not None and (
        not isinstance(voice_override, str)
        or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", voice_override) is None
    ):
        raise ValueError("TTS voice must be a normalized identifier")
    voice = voice_override or preset["voice"]
    if isinstance(speed_override, bool):
        raise ValueError("TTS speed must be a finite numeric value")
    try:
        speed = float(speed_override) if speed_override is not None else float(preset["speed"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("TTS speed must be a finite numeric value") from exc
    if not math.isfinite(speed):
        raise ValueError("TTS speed must be finite")
    # Preserve historical in-range clamping for otherwise valid numeric rates.
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
    if not isinstance(response, dict):
        raise EngineClientError("engine speech response is not an object")
    audio = response.get("audio")
    if not isinstance(audio, (bytes, bytearray)) or not audio:
        raise EngineClientError("engine speech response is missing audio")
    if len(audio) > MAX_ENGINE_AUDIO_BYTES:
        raise EngineClientError("engine speech response exceeds the media budget")
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
    """Yield a complete narration in bounded, ordered chunks.

    Prefer sentence ends and then whitespace, but always split unusually long
    sentences or words. Never pass an oversized chunk to engine-owned TTS.
    The scan walks the input once without making an unbounded split list.
    """
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 1 <= max_chars <= TTS_LIMIT:
        raise ValueError(f"max_chars must be an integer in [1, {TTS_LIMIT}]")
    if not isinstance(text, str):
        raise TypeError("narration text must be a string")
    if len(text) > MAX_NARRATION_TEXT_CHARS:
        raise ValueError("narration text exceeds the maximum text budget")
    if not text or not text.strip():
        return []

    out: List[str] = []
    current = ""

    def append_sentence(sentence: str) -> None:
        nonlocal current
        pos = 0
        length = len(sentence)
        while pos < length:
            while pos < length and sentence[pos].isspace():
                pos += 1
            if pos >= length:
                break
            stop = min(length, pos + max_chars)
            if stop < length:
                # A natural word break is preferable; an unbroken word still
                # advances by max_chars rather than producing an oversized row.
                boundary = sentence.rfind(" ", pos + 1, stop + 1)
                if boundary > pos:
                    stop = boundary
            piece = sentence[pos:stop].strip()
            pos = stop
            if not piece:
                continue
            if current and len(current) + len(piece) + 1 > max_chars:
                if len(out) >= MAX_NARRATION_CHUNKS:
                    raise ValueError("narration exceeds the maximum chunk count")
                out.append(current)
                current = ""
            current = f"{current} {piece}" if current else piece

    start = 0
    for match in re.finditer(r"(?<=[.!?…])\s+", text):
        append_sentence(text[start:match.start()])
        start = match.end()
    append_sentence(text[start:])
    if current:
        if len(out) >= MAX_NARRATION_CHUNKS:
            raise ValueError("narration exceeds the maximum chunk count")
        out.append(current)
    return out


def tones_catalog() -> List[Dict]:
    return [
        {"id": tid, "label": p["label"], "voice": p["voice"], "speed": p["speed"]}
        for tid, p in TONE_PRESETS.items()
    ]
