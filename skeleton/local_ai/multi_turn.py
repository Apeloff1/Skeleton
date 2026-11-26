"""Local multi-turn desk. No model is called and none is bound."""

from __future__ import annotations

import os
from pathlib import Path

from skeleton.local_ai.docx_ops import create_doc
from skeleton.local_ai.ffmpeg_ops import MediaRejected, plan_media
from skeleton.local_ai.memory_book import MemoryBook, MemoryRejected
from skeleton.local_ai.office_pack import (
    OfficeRejected,
    build_pdf,
    build_pptx,
    build_xlsx,
)

_MAX_TURNS = 24
_MAX_TURN_CHARS = 4000
_VERBS = {"remember", "replace", "forget", "ask", "pdf", "docx", "deck", "xlsx", "media"}
_NO_MATCH = "No note on this desk matches. No model is bound."
_TOOL_ERRORS = (MemoryRejected, OfficeRejected, MediaRejected)


class TurnRejected(ValueError):
    """The run or a turn verb is not a desk command."""


class TurnRecord:
    def __init__(
        self,
        *,
        verb: str,
        status: str,
        answer: str,
        path: str = "",
        executed: bool | None = None,
        shell: bool | None = None,
    ) -> None:
        self.verb = verb
        self.status = status
        self.answer = answer
        self.path = path
        self.executed = executed
        self.shell = shell

    @property
    def model_called(self) -> bool:
        return False

    def __getitem__(self, key: str):
        if key == "model_called":
            return False
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


class DeskRun:
    def __init__(self, turns: list[TurnRecord], memory_count: int) -> None:
        self.turns = turns
        self.memory_count = memory_count

    @property
    def model_called(self) -> bool:
        return False

    def __getitem__(self, key: str):
        if key == "model_called":
            return False
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


class MultiTurnDesk:
    """Remember notes and write office files under ``root``. Never calls a model."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory = MemoryBook(self.root / "memory.md")

    def run(self, messages) -> DeskRun:
        if not isinstance(messages, (list, tuple)) or len(messages) == 0:
            raise TurnRejected("empty run")
        if len(messages) > _MAX_TURNS:
            raise TurnRejected("max 24 turns")
        turns: list[TurnRecord] = []
        for message in messages:
            if not isinstance(message, str):
                raise TurnRejected("turn must be text")
            if len(message) > _MAX_TURN_CHARS:
                raise TurnRejected("turn exceeds 4000 characters")
            verb, payload = _split(message)
            if verb not in _VERBS:
                raise TurnRejected("unknown verb")
            try:
                turns.append(self._apply(verb, payload))
            except _TOOL_ERRORS as exc:
                turns.append(TurnRecord(verb=verb, status="refused", answer=str(exc)))
        return DeskRun(turns, memory_count=len(self.memory.facts()))

    def _apply(self, verb: str, payload: str) -> TurnRecord:
        if verb == "remember":
            self.memory.remember(payload)
            return TurnRecord(verb=verb, status="ok", answer=payload.strip())
        if verb == "replace":
            if "|" not in payload:
                raise MemoryRejected("replace requires old | new")
            old, new = payload.split("|", 1)
            self.memory.replace(old, new)
            return TurnRecord(verb=verb, status="ok", answer=new.strip())
        if verb == "forget":
            self.memory.forget(payload)
            return TurnRecord(verb=verb, status="ok", answer=payload.strip())
        if verb == "ask":
            hits = self.memory.search(payload)
            if not hits:
                answer = _NO_MATCH
            elif len(hits) == 1:
                answer = hits[0]
            else:
                answer = "\n".join(hits)
            return TurnRecord(verb=verb, status="ok", answer=answer)
        if verb == "pdf":
            path = self._write("notes.pdf", build_pdf(_pieces(payload)))
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path))
        if verb == "docx":
            path = self._write("notes.docx", create_doc(_pieces(payload)))
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path))
        if verb == "deck":
            path = self._write("notes.pptx", build_pptx(_pieces(payload)))
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path))
        if verb == "xlsx":
            rows = [[piece] for piece in _pieces(payload)]
            path = self._write("notes.xlsx", build_xlsx(rows))
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path))
        result = plan_media(payload, root=self.root)
        return TurnRecord(
            verb=verb,
            status="ok",
            answer=result.verb,
            executed=bool(result.executed),
            shell=False,
        )

    def _write(self, name: str, payload: bytes) -> Path:
        destination = self.root / name
        temporary = destination.with_name(f".{name}.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise OfficeRejected("document could not be saved") from exc
        return destination


def _split(message: str) -> tuple[str, str]:
    text = message.strip()
    verb, separator, payload = text.partition(" ")
    if not separator:
        return verb.casefold(), ""
    return verb.casefold(), payload.strip()


def _pieces(payload: str) -> list[str]:
    if not payload.strip():
        raise OfficeRejected("missing pieces")
    parts = [part.strip() for part in payload.split("|")]
    if any(part == "" for part in parts):
        raise OfficeRejected("empty piece")
    return parts
