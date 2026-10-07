"""Local Whisper speech-recognition interoperability.

Model downloads are never implicit. Supply a preloaded model, or explicitly set
allow_model_download=True before asking this adapter to load one.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Mapping

from .optional import OptionalDependencyError, load_optional
from .registry import source


@dataclass(frozen=True, slots=True)
class WhisperTranscription:
    text: str
    language: str | None
    segments: tuple[Mapping[str, object], ...]
    model_name: str
    task: str


class WhisperAdapter:
    def __init__(
        self,
        *,
        model: object | None = None,
        model_name: str = "turbo",
        allow_model_download: bool = False,
        download_root: str | None = None,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be non-empty")
        self.model_name = model_name.strip()
        self.allow_model_download = bool(allow_model_download)
        self.download_root = download_root
        self._importer = importer
        self._model = model

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self):
        if self._model is not None:
            return self._model
        if not self.allow_model_download:
            raise OptionalDependencyError(
                "Whisper model is not preloaded; implicit model download is disabled"
            )
        module = load_optional(source("whisper"), "whisper", importer=self._importer)
        available = getattr(module, "available_models", None)
        if callable(available):
            known = set(available())
            if self.model_name not in known:
                raise ValueError(f"unknown Whisper model: {self.model_name}")
        kwargs = {}
        if self.download_root is not None:
            kwargs["download_root"] = self.download_root
        self._model = module.load_model(self.model_name, **kwargs)
        return self._model

    def transcribe(
        self,
        audio: object,
        *,
        language: str | None = None,
        task: str = "transcribe",
        word_timestamps: bool = False,
        temperature: float = 0.0,
    ) -> WhisperTranscription:
        if task not in {"transcribe", "translate"}:
            raise ValueError("task must be transcribe or translate")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise TypeError("temperature must be numeric")
        if not 0.0 <= float(temperature) <= 1.0:
            raise ValueError("temperature must be in [0, 1]")
        if language is not None and (
            not isinstance(language, str) or not language.strip()
        ):
            raise ValueError("language must be non-empty when supplied")

        model = self.load()
        result = model.transcribe(
            audio,
            language=None if language is None else language.strip(),
            task=task,
            word_timestamps=bool(word_timestamps),
            temperature=float(temperature),
        )
        if not isinstance(result, Mapping):
            raise TypeError("Whisper transcription result must be a mapping")
        text = result.get("text")
        if not isinstance(text, str):
            raise TypeError("Whisper transcription result is missing text")
        detected = result.get("language")
        if detected is not None and not isinstance(detected, str):
            raise TypeError("Whisper language must be text")
        raw_segments = result.get("segments", ())
        if not isinstance(raw_segments, (list, tuple)):
            raise TypeError("Whisper segments must be a sequence")
        segments: list[Mapping[str, object]] = []
        for item in raw_segments:
            if not isinstance(item, Mapping):
                raise TypeError("Whisper segment must be a mapping")
            segments.append(dict(item))
        return WhisperTranscription(
            text=text,
            language=detected,
            segments=tuple(segments),
            model_name=self.model_name,
            task=task,
        )


__all__ = ["WhisperAdapter", "WhisperTranscription"]
