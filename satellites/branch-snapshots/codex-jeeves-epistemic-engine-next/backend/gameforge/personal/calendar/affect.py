from __future__ import annotations
"""
Daily simulated affective state from weather, temperature, noise.
Biases Jeeves toward empathetic, positive responses — never punitive.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from gameforge.personal.calendar.weather_decade import WeatherDay


@dataclass
class DailyAffect:
    day: str
    energy: float  # 0..1
    calm: float  # 0..1
    sociability: float  # 0..1
    focus: float  # 0..1
    valence: float  # -1..1 soft mood lean
    drivers: List[str]
    jeeves_guidance: str

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_daily_affect(weather: WeatherDay) -> DailyAffect:
    drivers: List[str] = []
    energy = 0.55
    calm = 0.55
    sociability = 0.55
    focus = 0.55
    valence = 0.1

    t = weather.temp_c
    if 16 <= t <= 24:
        energy += 0.1
        valence += 0.1
        drivers.append("comfortable_temperature")
    elif t < 0:
        energy -= 0.1
        calm += 0.05
        drivers.append("cold_day")
    elif t > 28:
        energy -= 0.08
        focus -= 0.1
        drivers.append("hot_day")

    if weather.condition == "clear":
        valence += 0.12
        sociability += 0.08
        drivers.append("clear_skies")
    elif weather.condition in ("rain", "storm"):
        calm += 0.05
        sociability -= 0.08
        focus += 0.05
        drivers.append("wet_weather_inward")
    elif weather.condition == "snow":
        valence += 0.05
        energy -= 0.05
        drivers.append("snow_day")
    elif weather.condition == "fog":
        focus -= 0.08
        drivers.append("fog_low_visibility")

    n = weather.noise_db
    if n > 70:
        calm -= 0.15
        focus -= 0.12
        valence -= 0.05
        drivers.append("high_noise")
    elif n < 45:
        calm += 0.1
        focus += 0.08
        drivers.append("quiet_environment")

    if weather.precip_mm > 8:
        drivers.append("heavy_precip")
        energy -= 0.05

    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    energy, calm, sociability, focus = map(clamp01, (energy, calm, sociability, focus))
    valence = max(-1.0, min(1.0, valence))

    guidance = _jeeves_guidance(energy, calm, focus, valence, drivers)
    return DailyAffect(
        day=weather.day,
        energy=round(energy, 2),
        calm=round(calm, 2),
        sociability=round(sociability, 2),
        focus=round(focus, 2),
        valence=round(valence, 2),
        drivers=drivers,
        jeeves_guidance=guidance,
    )


def _jeeves_guidance(energy, calm, focus, valence, drivers: List[str]) -> str:
    bits = []
    if "high_noise" in drivers:
        bits.append("Acknowledge sensory load; keep suggestions simple and kind.")
    if energy < 0.4:
        bits.append("Prefer lighter tasks and recovery-friendly framing.")
    if focus < 0.4:
        bits.append("Offer one clear next step, not a long list.")
    if calm < 0.4:
        bits.append("Lead with warmth and steadiness; avoid urgency.")
    if valence >= 0.15:
        bits.append("Match the brighter weather mood with gentle encouragement.")
    if "clear_skies" in drivers and energy >= 0.5:
        bits.append("Good day for outdoor micro-breaks or a short walk prompt.")
    if not bits:
        bits.append("Stay empathetic, concrete, and positively reinforcing.")
    bits.append("Always positive and non-judgmental.")
    return " ".join(bits)
