"""Local multi-turn desk.

Direct verbs still run one tool each. ``commit`` asks the local desk model to
turn an utterance into a short program. No remote model is called, and no GGUF
runtime is bound.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from skeleton.local_ai.desk_journal import DeskJournal, JournalRejected
from skeleton.local_ai.desk_model import DeskModel, ModelRejected, NO_EVIDENCE, Step
from skeleton.local_ai.docx_ops import create_doc
from skeleton.local_ai.ffmpeg_ops import MediaRejected, plan_media
from skeleton.local_ai.memory_book import MemoryBook, MemoryRejected, screen_fact
from skeleton.local_ai.office_pack import (
    MAX_PAGES,
    MAX_PARAGRAPHS,
    MAX_ROWS,
    MAX_SLIDES,
    OfficeRejected,
    build_docx,
    build_pdf,
    build_pptx,
    build_xlsx,
    read_docx,
    read_pdf,
    read_pptx,
    read_xlsx,
)

_MAX_TURNS = 24
_MAX_TURN_CHARS = 4000
_MAX_JOURNAL = 256
_MAX_HASH_BYTES = 8 * 1024 * 1024
_VERBS = {
    "remember",
    "replace",
    "forget",
    "ask",
    "reason",
    "pdf",
    "docx",
    "deck",
    "xlsx",
    "media",
    "append",
    "recall",
    "hash",
    "commit",
    "teach",
    "judge",
}
_NO_MATCH = "No note on this desk matches. No model is bound."
_TOOL_ERRORS = (MemoryRejected, OfficeRejected, MediaRejected, ModelRejected, JournalRejected)
_FILE_VERBS = {"pdf": "notes.pdf", "docx": "notes.docx", "deck": "notes.pptx", "xlsx": "notes.xlsx"}
_APPEND = {
    "pdf": ("notes.pdf", read_pdf, build_pdf, MAX_PAGES),
    "page": ("notes.pdf", read_pdf, build_pdf, MAX_PAGES),
    "docx": ("notes.docx", read_docx, build_docx, MAX_PARAGRAPHS),
    "paragraph": ("notes.docx", read_docx, build_docx, MAX_PARAGRAPHS),
    "deck": ("notes.pptx", read_pptx, build_pptx, MAX_SLIDES),
    "slide": ("notes.pptx", read_pptx, build_pptx, MAX_SLIDES),
    "xlsx": ("notes.xlsx", read_xlsx, build_xlsx, MAX_ROWS),
    "row": ("notes.xlsx", read_xlsx, build_xlsx, MAX_ROWS),
}
_PATH_FORBIDDEN = re.compile(r"[;|&$`<>\n\r]")


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
        verified: bool | None = None,
        local_model_used: bool = False,
        steps: tuple[TurnRecord, ...] = (),
    ) -> None:
        self.verb = verb
        self.status = status
        self.answer = answer
        self.path = path
        self.executed = executed
        self.shell = shell
        self.verified = verified
        self.local_model_used = local_model_used
        self.steps = steps

    @property
    def model_called(self) -> bool:
        return False

    @property
    def remote_called(self) -> bool:
        return False

    def __getitem__(self, key: str):
        if key == "model_called":
            return False
        if key == "remote_called":
            return False
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


class DeskRun:
    def __init__(self, turns: list[TurnRecord], memory_count: int) -> None:
        self.turns = turns
        self.memory_count = memory_count
        self.local_model_bound = True

    @property
    def model_called(self) -> bool:
        return False

    @property
    def remote_called(self) -> bool:
        return False

    def __getitem__(self, key: str):
        if key in {"model_called", "remote_called"}:
            return False
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


class MultiTurnDesk:
    """Remember notes, rank them locally, and write office files under ``root``."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory = MemoryBook(self.root / "memory.md")
        self.model = DeskModel(self.root / "desk_model.json")
        self.journal = DeskJournal(self.root / "journal.jsonl", max_entries=_MAX_JOURNAL)
        self._last_fact = ""
        self._last_answer = ""

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
                record = self._apply(verb, payload)
            except _TOOL_ERRORS as exc:
                record = TurnRecord(verb=verb, status="refused", answer=str(exc))
            self._note(record)
            self.journal.append(record.verb, record.status, record.answer)
            turns.append(record)
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
        if verb == "reason":
            found = self.model.answer(payload, self.memory.facts())
            return TurnRecord(
                verb=verb,
                status="ok",
                answer=found.text,
                local_model_used=True,
            )
        if verb == "pdf":
            pieces = _pieces(payload)
            path = self._write_checked("notes.pdf", build_pdf(pieces), pieces, read_pdf)
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path), verified=True)
        if verb == "docx":
            pieces = _pieces(payload)
            path = self._write_checked("notes.docx", create_doc(pieces), pieces, read_docx)
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path), verified=True)
        if verb == "deck":
            pieces = _pieces(payload)
            path = self._write_checked("notes.pptx", build_pptx(pieces), pieces, read_pptx)
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path), verified=True)
        if verb == "xlsx":
            rows = [[piece] for piece in _pieces(payload)]
            path = self._write_checked("notes.xlsx", build_xlsx(rows), rows, read_xlsx)
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path), verified=True)
        if verb == "append":
            name, payload_bytes, expected, reader = self._compose_append(payload)
            path = self._write_checked(name, payload_bytes, expected, reader)
            return TurnRecord(verb=verb, status="ok", answer=path.name, path=str(path), verified=True)
        if verb == "media":
            result = plan_media(payload, root=self.root)
            return TurnRecord(
                verb=verb,
                status="ok",
                answer=result.verb,
                executed=bool(result.executed),
                shell=False,
            )
        if verb == "hash":
            digest = _hash_file(_desk_file(self.root, payload))
            return TurnRecord(verb=verb, status="ok", answer=digest)
        if verb == "recall":
            return self._recall(payload)
        if verb == "teach":
            text, separator, label = payload.partition("=>")
            if not separator:
                raise ModelRejected("teach requires example => label")
            self.model.teach(text, label)
            return TurnRecord(
                verb=verb,
                status="ok",
                answer=f"taught {label.strip().casefold()}",
                local_model_used=True,
            )
        if verb == "judge":
            return self._judge(payload)
        if verb == "commit":
            return self._commit(payload)
        raise TurnRejected("unknown verb")

    def _judge(self, payload: str) -> TurnRecord:
        parts = payload.split()
        if not parts or parts[0].casefold() not in {"good", "bad"}:
            raise ModelRejected("judge needs good or bad")
        good = parts[0].casefold() == "good"
        label = parts[1] if len(parts) > 1 else None
        if not good and label is None:
            raise ModelRejected("judge bad needs a label")
        if len(parts) > 2:
            raise ModelRejected("judge needs good or bad")
        target = self.model.judge(good, label)
        return TurnRecord(verb="judge", status="ok", answer=f"judged {parts[0].casefold()} {target}", local_model_used=True)

    def _commit(self, payload: str) -> TurnRecord:
        program = self.model.plan(payload)
        if not program.confident:
            return TurnRecord(verb="commit", status="refused", answer=program.reason, local_model_used=True)
        blocked = self._preflight(program.steps)
        if blocked:
            return TurnRecord(verb="commit", status="refused", answer=blocked, local_model_used=True)
        snapshot = self.memory.facts()
        saved_fact = self._last_fact
        saved_answer = self._last_answer
        backups: dict[Path, bytes | None] = {}
        steps: list[TurnRecord] = []
        try:
            for step in program.steps:
                self._backup(step, backups)
                record = self._apply(step.verb, self._resolve(step))
                steps.append(record)
                self._note(record)
        except _TOOL_ERRORS as exc:
            self._restore(snapshot, backups)
            self._last_fact = saved_fact
            self._last_answer = saved_answer
            return TurnRecord(verb="commit", status="refused", answer=str(exc), local_model_used=True)
        answer = " -> ".join(f"{step.verb}: {step.answer}" for step in steps)
        verified = True if any(step.verified for step in steps) else None
        return TurnRecord(
            verb="commit",
            status="ok",
            answer=answer,
            local_model_used=True,
            steps=tuple(steps),
            verified=verified,
        )

    def _preflight(self, steps: tuple[Step, ...]) -> str | None:
        last_fact = self._last_fact
        last_answer = self._last_answer
        known = {fact.casefold() for fact in self.memory.facts()}
        pending: set[str] = set()
        try:
            for step in steps:
                if step.resolve == "fact" and not last_fact:
                    return "nothing to resolve"
                if step.resolve == "answer" and not last_answer:
                    return "nothing to resolve"
                self._screen(step, known, pending)
                if step.verb in {"remember", "replace"}:
                    last_fact = "pending"
                    if step.verb == "remember" and not step.resolve:
                        known.add(screen_fact(step.payload).casefold())
                    elif step.verb == "replace" and not step.resolve and "|" in step.payload:
                        old, new = step.payload.split("|", 1)
                        known.discard(screen_fact(old).casefold())
                        known.add(screen_fact(new).casefold())
                if step.verb in {"ask", "reason"}:
                    last_answer = "pending"
                if step.verb in _FILE_VERBS:
                    pending.add(_FILE_VERBS[step.verb])
                elif step.verb == "append":
                    kind = step.payload.split(" ", 1)[0].casefold()
                    spec = _APPEND.get(kind)
                    if spec is not None:
                        pending.add(spec[0])
        except _TOOL_ERRORS as exc:
            return str(exc)
        return None

    def _screen(self, step: Step, known: set[str], pending: set[str]) -> None:
        if step.verb == "remember" and not step.resolve:
            screen_fact(step.payload)
            return
        if step.verb == "forget" and not step.resolve:
            cleaned = screen_fact(step.payload)
            if cleaned.casefold() not in known:
                raise MemoryRejected("no matching fact")
            return
        if step.verb == "replace" and not step.resolve:
            if "|" not in step.payload:
                raise MemoryRejected("replace requires old | new")
            old, new = step.payload.split("|", 1)
            old_clean = screen_fact(old)
            screen_fact(new)
            if old_clean.casefold() not in known:
                raise MemoryRejected("no matching fact")
            return
        if step.verb in {"pdf", "docx", "deck", "xlsx"}:
            _pieces("placeholder" if step.resolve else step.payload)
            return
        if step.verb == "append":
            payload = step.payload
            if step.resolve:
                kind, _, _rest = payload.partition(" ")
                payload = f"{kind} placeholder"
            self._compose_append(payload, write=False)
            return
        if step.verb == "hash":
            argument = step.payload.strip()
            if argument not in pending:
                _desk_file(self.root, argument)
            elif argument.startswith(("-", "/", "\\")) or ".." in Path(argument).parts:
                raise MediaRejected("path escapes root")
            return
        if step.verb == "recall":
            self._recall(step.payload)
            return
        if step.verb == "media":
            plan_media(step.payload, root=self.root)
            return
        if step.verb in {"ask", "reason"} and not step.payload.strip():
            raise ModelRejected("missing question")

    def _resolve(self, step: Step) -> str:
        if not step.resolve:
            return step.payload
        value = self._last_fact if step.resolve == "fact" else self._last_answer
        if not value:
            raise ModelRejected("nothing to resolve")
        if step.verb == "append":
            kind, _, rest = step.payload.partition(" ")
            if rest.casefold() in {"that", "it", "this", "the last note", "the last answer"}:
                return f"{kind} {value}"
        if step.payload.casefold() in {"that", "it", "this", "the last note", "the last answer"}:
            return value
        return step.payload

    def _backup(self, step: Step, backups: dict[Path, bytes | None]) -> None:
        names: list[str] = []
        if step.verb in _FILE_VERBS:
            names.append(_FILE_VERBS[step.verb])
        elif step.verb == "append":
            kind = step.payload.split(" ", 1)[0].casefold()
            spec = _APPEND.get(kind)
            if spec is not None:
                names.append(spec[0])
        for name in names:
            path = self.root / name
            if path in backups:
                continue
            if path.is_symlink():
                raise OfficeRejected("document path is a symlink")
            backups[path] = path.read_bytes() if path.is_file() else None

    def _restore(self, snapshot: list[str], backups: dict[Path, bytes | None]) -> None:
        self.memory.replace_all(snapshot)
        for path, payload in backups.items():
            if payload is None:
                path.unlink(missing_ok=True)
                continue
            path.write_bytes(payload)

    def _compose_append(self, payload: str, *, write: bool = True):
        kind, _, rest = payload.partition(" ")
        spec = _APPEND.get(kind.casefold())
        if spec is None or not rest.strip():
            raise OfficeRejected("append target is missing")
        name, reader, builder, limit = spec
        path = self.root / name
        if path.is_symlink():
            raise OfficeRejected("document path is a symlink")
        existing = reader(path.read_bytes()) if path.is_file() else []
        pieces = _pieces(rest)
        if kind.casefold() in {"xlsx", "row"}:
            combined = [*existing, *([piece] for piece in pieces)]
        else:
            combined = [*existing, *pieces]
        if len(combined) > limit:
            raise OfficeRejected(f"{name} exceeds {limit}")
        if not write:
            return None
        return name, builder(combined), combined, reader

    def _recall(self, payload: str) -> TurnRecord:
        key = payload.strip().casefold()
        self.journal.verify()
        rows = self.journal.entries()
        if key == "check":
            return TurnRecord(verb="recall", status="ok", answer="chain ok")
        if key == "last":
            if not rows:
                raise JournalRejected("no such turn")
            return TurnRecord(verb="recall", status="ok", answer=str(rows[-1]["answer"]))
        if key.isdigit():
            number = int(key)
            for row in rows:
                if row["i"] == number:
                    return TurnRecord(verb="recall", status="ok", answer=str(row["answer"]))
            raise JournalRejected("no such turn")
        raise JournalRejected("recall needs a turn number, last, or check")

    def _note(self, record: TurnRecord) -> None:
        if record.status != "ok":
            return
        if record.verb == "forget" and record.answer.casefold() == self._last_fact.casefold():
            self._last_fact = ""
            return
        if record.verb in {"remember", "replace"} and record.answer:
            self._last_fact = record.answer
        elif record.verb in {"ask", "reason"}:
            self._last_answer = record.answer
        elif record.verb == "commit":
            for step in record.steps:
                self._note(step)

    def _write(self, name: str, payload: bytes) -> Path:
        destination = self.root / name
        if destination.is_symlink():
            raise OfficeRejected("document path is a symlink")
        temporary = destination.with_name(f".{name}.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise OfficeRejected("document could not be saved") from exc
        return destination

    def _write_checked(self, name: str, payload: bytes, expected: object, reader) -> Path:
        path = self._write(name, payload)
        if reader(path.read_bytes()) != expected:
            raise OfficeRejected("document did not round-trip")
        return path


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


def _desk_file(root: Path, argument: str) -> Path:
    if not isinstance(argument, str) or not argument.strip():
        raise MediaRejected("file is not on the desk")
    if argument.startswith(("-", "/", "\\")) or ".." in Path(argument).parts:
        raise MediaRejected("path escapes root")
    if _PATH_FORBIDDEN.search(argument):
        raise MediaRejected("path escapes root")
    root_resolved = root.resolve()
    current = root
    for part in Path(argument).parts:
        if part in {"", ".", ".."}:
            raise MediaRejected("path escapes root")
        current = current / part
        if current.is_symlink():
            raise MediaRejected("path escapes root")
    if not current.is_file():
        raise MediaRejected("file is not on the desk")
    resolved = current.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise MediaRejected("path escapes root") from exc
    if current.stat().st_size > _MAX_HASH_BYTES:
        raise MediaRejected("file exceeds 8 MiB")
    return current


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["DeskRun", "MultiTurnDesk", "TurnRecord", "TurnRejected", "NO_EVIDENCE"]
