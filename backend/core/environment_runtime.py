"""Deterministic environment/weather runtime mined from Newmove2.

Preserves preset-driven weather, smooth transitions, bounded natural variation,
and gameplay-facing visibility/wind/temperature state without browser timers or
rendering concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True, slots=True)
class WeatherPreset:
    cloud_cover: float
    rain: float
    wind_speed: float
    temperature: float
    humidity: float
    visibility: float
    pressure: float
    fog: float = 0.0
    lightning: float = 0.0
    snow: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.cloud_cover, self.rain, self.humidity / 100, self.visibility, self.fog, self.lightning, self.snow):
            if not 0 <= value <= 1:
                raise ValueError("normalized weather values must be between 0 and 1")
        if self.wind_speed < 0:
            raise ValueError("wind speed cannot be negative")


DEFAULT_WEATHER: dict[str, WeatherPreset] = {
    "sunny": WeatherPreset(0.1, 0.0, 5, 25, 40, 1.0, 1020),
    "cloudy": WeatherPreset(0.6, 0.0, 10, 20, 60, 0.9, 1010, fog=0.1),
    "rain": WeatherPreset(0.95, 0.6, 20, 14, 90, 0.5, 995, fog=0.3, lightning=0.1),
    "storm": WeatherPreset(1.0, 0.9, 50, 10, 95, 0.2, 975, fog=0.5, lightning=0.4),
    "foggy": WeatherPreset(0.4, 0.0, 3, 12, 95, 0.2, 1008, fog=0.9),
    "snow": WeatherPreset(0.9, 0.0, 15, -5, 80, 0.4, 1010, fog=0.2, snow=0.7),
}


class EnvironmentRuntime:
    def __init__(self, presets: dict[str, WeatherPreset] | None = None, *, weather: str = "sunny") -> None:
        self.presets = dict(presets or DEFAULT_WEATHER)
        if weather not in self.presets:
            raise ValueError("unknown initial weather")
        self.current_weather = weather
        self.target_weather = weather
        self.progress = 1.0
        self._from = self.presets[weather]
        self.state = self.presets[weather]

    @staticmethod
    def _ease(t: float) -> float:
        return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2

    @staticmethod
    def _mix(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def set_weather(self, weather: str, *, instant: bool = False) -> None:
        if weather not in self.presets:
            raise ValueError(f"unknown weather: {weather}")
        if instant:
            self.current_weather = weather
            self.target_weather = weather
            self._from = self.presets[weather]
            self.state = self.presets[weather]
            self.progress = 1.0
            return
        self._from = self.state
        self.target_weather = weather
        self.progress = 0.0

    def step(self, dt: float, *, transition_seconds: float = 30.0, seed: int | None = None) -> WeatherPreset:
        if dt <= 0 or transition_seconds <= 0:
            raise ValueError("dt and transition_seconds must be positive")
        target = self.presets[self.target_weather]
        if self.progress < 1:
            self.progress = min(1.0, self.progress + dt / transition_seconds)
            t = self._ease(self.progress)
            base = WeatherPreset(
                cloud_cover=self._mix(self._from.cloud_cover, target.cloud_cover, t),
                rain=self._mix(self._from.rain, target.rain, t),
                wind_speed=self._mix(self._from.wind_speed, target.wind_speed, t),
                temperature=self._mix(self._from.temperature, target.temperature, t),
                humidity=self._mix(self._from.humidity, target.humidity, t),
                visibility=self._mix(self._from.visibility, target.visibility, t),
                pressure=self._mix(self._from.pressure, target.pressure, t),
                fog=self._mix(self._from.fog, target.fog, t),
                lightning=self._mix(self._from.lightning, target.lightning, t),
                snow=self._mix(self._from.snow, target.snow, t),
            )
            if self.progress == 1:
                self.current_weather = self.target_weather
        else:
            base = target

        rng = random.Random(seed)
        gust = (rng.random() - 0.5) * min(2.0, dt * 0.1)
        temp = (rng.random() - 0.5) * min(0.4, dt * 0.02)
        self.state = WeatherPreset(
            cloud_cover=max(0.0, min(1.0, base.cloud_cover)),
            rain=max(0.0, min(1.0, base.rain)),
            wind_speed=max(0.0, base.wind_speed + gust),
            temperature=base.temperature + temp,
            humidity=max(0.0, min(100.0, base.humidity)),
            visibility=max(0.0, min(1.0, base.visibility)),
            pressure=base.pressure,
            fog=max(0.0, min(1.0, base.fog)),
            lightning=max(0.0, min(1.0, base.lightning)),
            snow=max(0.0, min(1.0, base.snow)),
        )
        return self.state

    def contexts(self) -> tuple[str, ...]:
        contexts = [self.current_weather]
        if self.state.rain > 0.2:
            contexts.append("rainy")
        if self.state.wind_speed >= 35 or self.state.lightning >= 0.25:
            contexts.append("stormy")
        if self.state.fog >= 0.5:
            contexts.append("foggy")
        return tuple(dict.fromkeys(contexts))
