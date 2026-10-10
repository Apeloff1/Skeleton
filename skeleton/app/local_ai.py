"""Docker-free, provider-free desktop conversation over the canonical native model.

This is an app-shell adapter, not a new AI runtime, transcript authority,
model trainer, or provider. Only a locally selected, integrity-checked native
checkpoint can be executed. No checkpoint or demo response is bundled.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from queue import Empty, Queue
import secrets
import threading
from typing import Any

from skeleton.ai.model_runtime.offline_chat import (
    OfflineChatStore, _digest_request, _identifier,
    load_private_bundle, save_private_bundle,
)
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
from skeleton.ai.runtime.inference.local import LocalInferenceRequest, LocalInferenceResult, LocalInferenceEngine
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel


MAX_USER_CHARS = 4096
MAX_HISTORY_MESSAGES = 16


class OfflineAIError(ValueError):
    """The offline application cannot safely execute the requested action."""


def load_native_checkpoint(source: str | Path) -> NativeRuntimeLocalModel:
    """Load exactly one native checkpoint, without fetching or training weights."""
    loaded = load_local_model_artifact(source)
    if not isinstance(loaded.model, NativeRuntimeLocalModel):
        raise OfflineAIError("checkpoint must contain a native transformer, not a reference/demo model")
    loaded.model.assert_identity()
    return loaded.model


def load_gguf_deployment(source: str | Path) -> LlamaCppModel:
    """Admit a preinstalled local GGUF and llama.cpp executable by SHA-256."""
    deployment = LocalModelDeployment.load(source)
    return LlamaCppModel(deployment.llama_cpp_config(
        rehash_artifacts_each_run=True,
    ))


LocalDesktopModel = NativeRuntimeLocalModel | LlamaCppModel


def _model_tokenizer_digest(backend: LocalDesktopModel) -> str:
    if isinstance(backend, NativeRuntimeLocalModel):
        return backend.tokenizer_digest
    if isinstance(backend, LlamaCppModel):
        # GGUF embeds its vocabulary; exact model bytes bind that tokenizer.
        return sha256(b"skeleton.ai.gguf-tokenizer.v1:" +
                      bytes.fromhex(backend.model_digest)).hexdigest()
    raise OfflineAIError("unsupported desktop model backend")


@dataclass(frozen=True)
class OfflineAnswer:
    text: str
    model_digest: str
    execution_receipt_digest: str
    input_tokens: int
    output_tokens: int


class OfflineAISession:
    """Ephemeral conversation; all model work uses the canonical inference plane.

    The desktop shell intentionally does not fabricate persistence or a
    system-completion verdict. For durable production chat use the governed
    assistant/workspace and terminal-turn authority instead.
    """

    def __init__(self, backend: LocalDesktopModel) -> None:
        if not isinstance(backend, (NativeRuntimeLocalModel, LlamaCppModel)):
            raise OfflineAIError("canonical offline model backend required")
        if isinstance(backend, NativeRuntimeLocalModel):
            backend.assert_identity()
        else:
            backend._assert_artifacts_stable()
        self.backend = backend
        self.engine = LocalInferenceEngine(backend, cache_size=0)
        self.history: tuple[tuple[str, str], ...] = ()
        self.instructions: str = ""

    def clear(self) -> None:
        self.history = ()

    @property
    def model_digest(self) -> str:
        return self.backend.model_digest

    @property
    def tokenizer_digest(self) -> str:
        return _model_tokenizer_digest(self.backend)

    @property
    def preferred_output_tokens(self) -> int:
        if isinstance(self.backend, NativeRuntimeLocalModel):
            runtime = self.backend.runtime
            return min(32, runtime.limits.max_new_tokens,
                       max(1, runtime.limits.max_context // 4))
        return min(32, max(1, (self.backend.config.context_size or 4096) // 4))

    def _request(self, prompt: str, max_output_tokens: int) -> tuple[LocalInferenceRequest, tuple[tuple[str, str], ...]]:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_USER_CHARS:
            raise OfflineAIError("message must contain 1-4096 characters")
        runtime = self.backend.runtime if isinstance(
            self.backend, NativeRuntimeLocalModel
        ) else None
        context_limit = (
            runtime.limits.max_context if runtime is not None
            else self.backend.config.context_size or 4096
        )
        output_limit = runtime.limits.max_new_tokens if runtime is not None else 8192
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= output_limit
        ):
            raise OfflineAIError("output-token budget exceeds the loaded model limit")
        # Native has exact token counts; GGUF uses conservative UTF-8 bytes
        # and delegates final token/context validation to llama.cpp.
        available = context_limit - max_output_tokens
        if available < 1:
            raise OfflineAIError("checkpoint has insufficient context for this output budget")
        history = self.history
        while True:
            request = LocalInferenceRequest(
                prompt=prompt.strip(),
                instructions=self.instructions,
                history=history,
                max_output_tokens=max_output_tokens,
            )
            observed = (
                len(runtime.tokenizer.encode_ids(request.rendered_input))
                if runtime is not None
                else len(request.rendered_input.encode("utf-8")) + 16
            )
            if observed <= available:
                return request, history
            if not history:
                raise OfflineAIError("message exceeds native model context; shorten it or reduce the output budget")
            history = history[2:]

    async def ask(self, prompt: str, *, max_output_tokens: int = 32,
                  grounding_context: str | None = None) -> OfflineAnswer:
        # The evidence goes only into the untrusted *user* prompt passed to
        # the local model, never instructions/system authority or durable user
        # message. The archived transcript retains the actual user question.
        if grounding_context is not None:
            if (not isinstance(grounding_context, str)
                    or not grounding_context.strip()
                    or len(grounding_context.encode("utf-8")) > 4_096):
                raise OfflineAIError("invalid bounded source context")
            inference_prompt = prompt.strip() + "\n\n" + grounding_context
        else:
            inference_prompt = prompt
        request, retained_history = self._request(
            inference_prompt, max_output_tokens
        )
        result: LocalInferenceResult = await self.engine.generate(request)
        if (
            not isinstance(result.text, str)
            or not result.text.strip()
            or result.tool_calls
            or result.finish_reason in {"cancelled", "deadline"}
            or result.model_digest != self.backend.model_digest
        ):
            raise OfflineAIError(
                "local model did not return a completed, bound text-only answer"
            )
        receipt_digest = result.execution_receipt_digest
        if isinstance(self.backend, LlamaCppModel) and not receipt_digest:
            # llama.cpp returns a concrete request-bound process response ID
            # rather than the native transformer receipt. Derive a local
            # response digest from its admitted binary/model identity, full
            # request, and exact output. This is NOT remote attestation.
            prefix = ("local:llama:" + self.backend.runtime_digest + ":"
                      + self.backend.model_digest + ":")
            if not isinstance(result.response_id, str) or not result.response_id.startswith(prefix):
                raise OfflineAIError("GGUF subprocess response lacks bound identity")
            receipt_digest = sha256(json.dumps({
                "schema": "skeleton.offline-gguf-receipt.v1",
                "response_id": result.response_id,
                "request_digest": request.digest,
                "model": result.model_digest,
                "runtime": self.backend.runtime_digest,
                "output_sha256": sha256(result.text.encode("utf-8")).hexdigest(),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            raise OfflineAIError("offline inference has no bound execution receipt")
        # Only commit a complete, verified local inference result.
        self.history = (
            retained_history
            + (("user", prompt.strip()), ("assistant", result.text))
        )[-MAX_HISTORY_MESSAGES:]
        return OfflineAnswer(
            text=result.text,
            model_digest=result.model_digest,
            execution_receipt_digest=receipt_digest,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )


class DurableOfflineAISession(OfflineAISession):
    """Durable desktop adapter; the existing canonical inference backend stays owner.

    LocalInferenceEngine still executes/cancels each turn. The native
    OfflineChatStore alone owns the transcript, version CAS, and durable
    receipts. The app shell can never silently substitute a different model.
    """

    def __init__(self, backend: LocalDesktopModel, *,
                 database: str | Path, session_id: str | None = None) -> None:
        super().__init__(backend)
        self.store = OfflineChatStore(database)
        self._busy_lock = threading.Lock()
        self._busy = False
        try:
            if session_id is None:
                existing = self.store.list_sessions(
                    backend.model_digest, self.tokenizer_digest, limit=1
                )
                session_id = existing[0][0] if existing else self.store.create(
                    backend.model_digest, self.tokenizer_digest
                )
            self.session_id = session_id
            self._restore()
        except BaseException:
            self.store.close()
            raise

    def _restore(self) -> None:
        record = self.store.load(
            self.session_id, self.backend.model_digest, self.tokenizer_digest
        )
        messages = record.transcript.messages
        has_instruction = bool(messages and messages[0].role == "system")
        dialogue = messages[1:] if has_instruction else messages
        # Preserve an imported system instruction verbatim, but reject any
        # later instructions or mismatched dialogue turns.
        if len(dialogue) % 2 or any(
            message.role != ("user" if index % 2 == 0 else "assistant")
            or not message.content.strip()
            for index, message in enumerate(dialogue)
        ):
            raise OfflineAIError("desktop conversation contains invalid dialogue history")
        self.instructions = messages[0].content if has_instruction else ""
        self.history = tuple((m.role, m.content) for m in dialogue)

    def create_conversation(self) -> str:
        if self._busy:
            raise OfflineAIError("cannot switch conversation during generation")
        self.session_id = self.store.create(
            self.backend.model_digest, self.tokenizer_digest
        )
        self.history = ()
        self.instructions = ""
        return self.session_id

    def resume(self, session_id: str) -> None:
        if self._busy:
            raise OfflineAIError("cannot resume conversation during generation")
        previous = self.session_id
        history = self.history
        instructions = self.instructions
        self.session_id = session_id
        try:
            self._restore()
        except BaseException:
            self.session_id = previous
            self.history = history
            self.instructions = instructions
            raise

    def list_conversations(self) -> tuple[tuple[str, int], ...]:
        return self.store.list_sessions(
            self.backend.model_digest, self.tokenizer_digest
        )

    def export_conversation(self, session_id: str) -> bytes:
        return self.store.export_bundle(
            session_id, self.backend.model_digest, self.tokenizer_digest
        )

    def import_conversation(self, payload: bytes) -> str:
        if self._busy:
            raise OfflineAIError("cannot import during model generation")
        session_id = self.store.import_bundle(
            payload, self.backend.model_digest, self.tokenizer_digest
        )
        self.resume(session_id)
        return session_id

    def fork_conversation(self, session_id: str, *,
                          after_turn: int | None = None) -> str:
        if self._busy:
            raise OfflineAIError("cannot fork during model generation")
        forked_id = self.store.fork(
            session_id, self.backend.model_digest, self.tokenizer_digest,
            after_turn=after_turn,
        )
        self.resume(forked_id)
        return forked_id

    def delete_conversation(self, session_id: str) -> None:
        if self._busy:
            raise OfflineAIError("cannot delete conversation during generation")
        self.store.delete(
            session_id, self.backend.model_digest, self.tokenizer_digest
        )
        if session_id == self.session_id:
            self.create_conversation()

    async def ask(self, prompt: str, *, max_output_tokens: int = 32,
                  request_id: str | None = None,
                  evidence_manifest: dict[str, Any] | None = None) -> OfflineAnswer:
        rid = (_identifier("request id", request_id)
               if request_id is not None else secrets.token_urlsafe(18))
        with self._busy_lock:
            if self._busy:
                raise OfflineAIError("a local generation is already running")
            self._busy = True
        previous_history = self.history
        try:
            # Recheck durable authority immediately before inference so a
            # concurrent process cannot silently rewrite the prior context.
            saved = self.store.load(
                self.session_id, self.backend.model_digest, self.tokenizer_digest
            )
            stored_messages = saved.transcript.messages
            stored_has_system = bool(stored_messages and stored_messages[0].role == "system")
            persisted_instruction = stored_messages[0].content if stored_has_system else ""
            persisted_history = tuple(
                (m.role, m.content) for m in
                (stored_messages[1:] if stored_has_system else stored_messages)
            )
            if persisted_history != previous_history or persisted_instruction != self.instructions:
                raise OfflineAIError("conversation changed on disk; reload before retry")
            self.store.ensure_can_append(saved)
            config = GenerationConfig(max_new_tokens=max_output_tokens)
            request_digest = _digest_request(prompt.strip(), config)
            grounding_context = None
            if evidence_manifest is not None:
                from skeleton.app.offline_grounding import (
                    grounded_request_digest, validate_evidence,
                )
                request_digest = grounded_request_digest(request_digest)
                validate_evidence(
                    evidence_manifest, prompt.strip(), request_digest,
                    self.backend.model_digest, self.tokenizer_digest,
                )
                grounding_context = evidence_manifest["context"]
            # super().ask() deliberately shrinks inference context. The
            # persisted transcript MUST instead extend the complete prior
            # SQLite history, not the model's shortened context window.
            answer = await super().ask(
                prompt, max_output_tokens=max_output_tokens,
                grounding_context=grounding_context,
            )
            transcript = saved.transcript.append("user", prompt.strip()).append(
                "assistant", answer.text
            )
            transcript.validate_turn_order()
            # The desktop adapter records generated text identity separately
            # from the canonical inference execution receipt shown to users.
            text_digest = sha256(answer.text.encode("utf-8")).hexdigest()
            # GenerationConfig matches the actual local request's seed and
            # bounded output budget; random IDs avoid accidental replay.
            self.store.commit(
                session=saved,
                request_id=rid,
                request_digest=request_digest,
                transcript=transcript,
                text=answer.text,
                output_digest=text_digest,
                prompt_tokens=answer.input_tokens,
                generated_tokens=answer.output_tokens,
                evidence_manifest=evidence_manifest,
            )
            # Keep the full durable state available to the desktop while the
            # inference adapter independently limits prompt context per turn.
            self.history = tuple((item.role, item.content) for item in
                                 transcript.messages if item.role in {"user", "assistant"})
            return answer
        except BaseException:
            # Discard uncommitted in-memory content even when inference itself
            # succeeded but SQLite CAS/disk storage failed.
            self.history = previous_history
            raise
        finally:
            with self._busy_lock:
                self._busy = False

    def close(self) -> None:
        if self._busy:
            raise OfflineAIError("cannot close active local generation")
        self.store.close()


def private_desktop_database(model_digest: str) -> Path:
    """Per-model owner-only local data directory, no network or cloud paths."""
    if (not isinstance(model_digest, str) or len(model_digest) != 64
            or any(c not in "0123456789abcdef" for c in model_digest)):
        raise OfflineAIError("invalid model identity for local conversation store")
    root = Path.home() / ".skeleton"
    folder = root / "offline-ai"
    for directory in (root, folder):
        if directory.is_symlink():
            raise OfflineAIError("offline data directory must not be a symlink")
        directory.mkdir(exist_ok=True, mode=0o700)
        if directory.is_symlink():
            raise OfflineAIError("offline data directory must not be a symlink")
    return folder / (model_digest + ".sqlite3")


class OfflineAIWindow:
    """Tk window hosted by the existing Windows desktop launcher."""

    def __init__(self, parent: Any) -> None:
        import tkinter as tk
        from tkinter import filedialog, scrolledtext, ttk

        self.tk = tk
        self.filedialog = filedialog
        self.window = tk.Toplevel(parent)
        self.window.title("Skeleton · Local AI")
        self.window.geometry("850x660")
        self.window.minsize(600, 440)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.session: OfflineAISession | None = None
        self.events: Queue[tuple[str, object]] = Queue()
        self.active = False
        self.loading_model = False
        self.closed = False
        self.worker_loop: asyncio.AbstractEventLoop | None = None
        self.worker_task: asyncio.Task[OfflineAnswer] | None = None
        self.worker_lock = threading.Lock()
        self.pending_prompt: str | None = None

        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Local AI · no Docker / no hosted provider", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Runs an explicitly selected native checkpoint offline. No trained model is supplied; quality depends on your checkpoint.",
            wraplength=790,
        ).pack(anchor="w", pady=(4, 10))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x")
        self.load_button = ttk.Button(toolbar, text="Load native checkpoint…",
                                      command=self.choose_model)
        self.load_button.pack(side="left")
        self.load_gguf_button = ttk.Button(
            toolbar, text="Load local GGUF…",
            command=lambda: self.choose_model("gguf")
        )
        self.load_gguf_button.pack(side="left", padx=5)
        self.clear_button = ttk.Button(toolbar, text="New conversation", command=self.clear)
        self.clear_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(toolbar, text="Cancel generation", command=self.cancel)
        self.cancel_button.pack(side="left")
        sessions = ttk.Frame(frame)
        sessions.pack(fill="x", pady=(8, 0))
        ttk.Label(sessions, text="Saved conversation").pack(side="left")
        self.session_choices: dict[str, str] = {}
        self.session_picker = ttk.Combobox(sessions, state="readonly", width=33)
        self.session_picker.pack(side="left", padx=6)
        self.resume_button = ttk.Button(
            sessions, text="Resume", command=self.resume_selected
        )
        self.resume_button.pack(side="left")
        self.delete_button = ttk.Button(
            sessions, text="Delete", command=self.delete_selected
        )
        self.delete_button.pack(side="left", padx=6)
        self.fork_button = ttk.Button(
            sessions, text="Fork", command=self.fork_selected
        )
        self.fork_button.pack(side="left", padx=3)
        self.export_button = ttk.Button(
            sessions, text="Export…", command=self.export_selected
        )
        self.export_button.pack(side="left", padx=3)
        self.import_button = ttk.Button(
            sessions, text="Import…", command=self.import_selected
        )
        self.import_button.pack(side="left", padx=3)
        self.status = tk.StringVar(value="Choose a local native model checkpoint to begin.")
        ttk.Label(frame, textvariable=self.status, wraplength=790).pack(anchor="w", pady=8)
        self.transcript = scrolledtext.ScrolledText(frame, state="disabled", wrap="word", height=18, font=("Segoe UI", 10))
        self.transcript.pack(fill="both", expand=True)
        ttk.Label(frame, text="Message").pack(anchor="w", pady=(10, 0))
        self.composer = tk.Text(frame, height=4, wrap="word", font=("Segoe UI", 10))
        self.composer.pack(fill="x")
        self.send_button = ttk.Button(frame, text="Send to local model", command=self.send)
        self.send_button.pack(anchor="e", pady=(8, 0))
        self._refresh()
        self.window.after(100, self._drain)

    def _refresh(self) -> None:
        self.load_button.configure(state="disabled" if self.active else "normal")
        self.load_gguf_button.configure(state="disabled" if self.active else "normal")
        self.send_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.clear_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.cancel_button.configure(state="normal" if self.active else "disabled")
        can_switch = isinstance(self.session, DurableOfflineAISession) and not self.active
        self.resume_button.configure(state="normal" if can_switch else "disabled")
        self.delete_button.configure(state="normal" if can_switch else "disabled")
        self.fork_button.configure(state="normal" if can_switch else "disabled")
        self.export_button.configure(state="normal" if can_switch else "disabled")
        self.import_button.configure(state="normal" if can_switch else "disabled")

    def _update_sessions(self) -> None:
        if not isinstance(self.session, DurableOfflineAISession):
            return
        choices = {}
        selected = ""
        for sid, revision in self.session.list_conversations():
            label = f"{sid[:18]}…  ·  {revision} turns"
            choices[label] = sid
            if sid == self.session.session_id:
                selected = label
        self.session_choices = choices
        self.session_picker.configure(values=tuple(choices))
        self.session_picker.set(selected)

    def _display_history(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        if self.session is not None:
            for role, content in self.session.history:
                self._append("You" if role == "user" else "Skeleton · Local", content)

    def resume_selected(self) -> None:
        if self.active or not isinstance(self.session, DurableOfflineAISession):
            return
        sid = self.session_choices.get(self.session_picker.get())
        if sid is None:
            return
        try:
            self.session.resume(sid)
            self._display_history()
            self._update_sessions()
            self.status.set("Restored saved conversation: " + sid[:18] + "…")
        except Exception as exc:
            self.status.set("Cannot restore conversation: " + str(exc))
        self._refresh()

    def fork_selected(self) -> None:
        if self.active or not isinstance(self.session, DurableOfflineAISession):
            return
        sid = self.session_choices.get(self.session_picker.get())
        if sid is None:
            return
        try:
            forked = self.session.fork_conversation(sid)
            self._display_history()
            self._update_sessions()
            self.status.set("Forked saved conversation: " + forked[:18] + "…")
        except Exception as exc:
            self.status.set("Cannot fork conversation: " + str(exc))
        self._refresh()

    def delete_selected(self) -> None:
        if self.active or not isinstance(self.session, DurableOfflineAISession):
            return
        sid = self.session_choices.get(self.session_picker.get())
        if sid is None:
            return
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Delete saved conversation?",
            "Permanently delete this local conversation and its saved receipts?",
            parent=self.window,
        ):
            return
        try:
            self.session.delete_conversation(sid)
            self._display_history()
            self._update_sessions()
            self.status.set("Local conversation deleted.")
        except Exception as exc:
            self.status.set("Cannot delete conversation: " + str(exc))
        self._refresh()

    def export_selected(self) -> None:
        if self.active or not isinstance(self.session, DurableOfflineAISession):
            return
        sid = self.session_choices.get(self.session_picker.get())
        if sid is None:
            return
        selected = self.filedialog.asksaveasfilename(
            parent=self.window, title="Export private offline chat",
            defaultextension=".json",
            filetypes=[("Conversation backup", "*.json")],
        )
        if not selected:
            return
        try:
            save_private_bundle(selected, self.session.export_conversation(sid))
            self.status.set("Conversation and retry receipts exported.")
        except Exception as exc:
            self.status.set("Conversation export failed: " + str(exc))

    def import_selected(self) -> None:
        if self.active or not isinstance(self.session, DurableOfflineAISession):
            return
        selected = self.filedialog.askopenfilename(
            parent=self.window, title="Import private offline chat",
            filetypes=[("Conversation backup", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            sid = self.session.import_conversation(load_private_bundle(selected))
            self._display_history()
            self._update_sessions()
            self.status.set("Imported conversation: " + sid[:18] + "…")
        except Exception as exc:
            self.status.set("Conversation import failed: " + str(exc))
        self._refresh()

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", speaker + "\n" + text + "\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def choose_model(self, kind: str = "native") -> None:
        if self.active:
            return
        is_gguf = kind == "gguf"
        selected = self.filedialog.askopenfilename(
            parent=self.window,
            title=("Select digest-pinned local GGUF deployment manifest"
                   if is_gguf else "Select a Skeleton native model checkpoint"),
            filetypes=[("JSON manifest/checkpoint", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        self.active = True
        self.loading_model = True
        self.status.set("Validating offline GGUF executable/model…" if is_gguf
                        else "Validating the native model checkpoint…")
        self._refresh()

        def work() -> None:
            try:
                backend = (load_gguf_deployment(selected)
                           if is_gguf else load_native_checkpoint(selected))
                session = DurableOfflineAISession(
                    backend, database=private_desktop_database(backend.model_digest)
                )
                if self.closed:
                    session.close()
                    return
                self.events.put(("loaded", session))
            except Exception as exc:
                if not self.closed:
                    self.events.put(("error", str(exc)))

        threading.Thread(target=work, name="skeleton-local-model-load", daemon=True).start()

    def clear(self) -> None:
        if self.active or self.session is None:
            return
        if isinstance(self.session, DurableOfflineAISession):
            try:
                self.session.create_conversation()
                self._display_history()
                self._update_sessions()
                self.status.set("New persistent conversation created.")
            except Exception as exc:
                self.status.set("Unable to create local conversation: " + str(exc))
        else:
            self.session.clear()
            self._display_history()
            self.status.set("Conversation reset in memory.")

    def send(self) -> None:
        if self.active or self.session is None:
            return
        prompt = self.composer.get("1.0", "end-1c").strip()
        if not prompt:
            return
        # A submitted prompt is only shown as an accepted conversation turn
        # *after* native execution AND durable SQLite commit succeed.
        self.composer.delete("1.0", "end")
        self.pending_prompt = prompt
        self.active = True
        self.status.set("Generating locally…")
        self._refresh()
        session = self.session

        def work() -> None:
            if self.closed:
                return
            async def generate() -> OfflineAnswer:
                if self.closed:
                    raise asyncio.CancelledError()
                task = asyncio.create_task(session.ask(
                    prompt, max_output_tokens=session.preferred_output_tokens
                ))
                with self.worker_lock:
                    self.worker_loop = asyncio.get_running_loop()
                    self.worker_task = task
                return await task

            try:
                answer = asyncio.run(generate())
                self.events.put(("answer", answer))
            except asyncio.CancelledError:
                self.events.put(("error", "Generation cancelled; no conversation state committed."))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                with self.worker_lock:
                    self.worker_loop = None
                    self.worker_task = None
                if self.closed and isinstance(session, DurableOfflineAISession):
                    # GUI lifetime may end during a long subprocess inference.
                    # Always close the model-specific SQLite authority once
                    # the worker really finished and cancellation settled.
                    try:
                        session.close()
                    except Exception:
                        pass

        threading.Thread(target=work, name="skeleton-native-inference", daemon=True).start()

    def cancel(self) -> None:
        with self.worker_lock:
            loop, task = self.worker_loop, self.worker_task
            if loop is not None and task is not None and not task.done():
                loop.call_soon_threadsafe(task.cancel)
                self.status.set("Cancellation requested…")

    def _drain(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                self.active = False
                if self.loading_model:
                    self.loading_model = False
                if kind == "loaded":
                    if isinstance(self.session, DurableOfflineAISession):
                        self.session.close()
                    self.session = value  # type: ignore[assignment]
                    self._display_history()
                    self._update_sessions()
                    kind = ("GGUF / llama.cpp" if isinstance(self.session.backend, LlamaCppModel)
                            else "Native transformer")
                    self.status.set(
                        kind + " loaded offline: "
                        + self.session.model_digest[:16] + "… · saved locally"
                    )
                elif kind == "answer":
                    answer = value
                    self.pending_prompt = None
                    self._display_history()
                    self._update_sessions()
                    self.status.set(
                        "Completed · " + str(answer.input_tokens) + " input / " + str(answer.output_tokens) + " output tokens · receipt " + answer.execution_receipt_digest[:12]  # type: ignore[attr-defined]
                    )
                else:
                    # An inference or persistence failure did not commit the
                    # turn. Restore the unsaved prompt to the composer instead
                    # of presenting it as durable conversational history.
                    if self.pending_prompt:
                        previous_draft = self.composer.get("1.0", "end-1c")
                        self.composer.delete("1.0", "end")
                        self.composer.insert(
                            "1.0", self.pending_prompt +
                            ("\n" + previous_draft if previous_draft.strip() else "")
                        )
                        self.pending_prompt = None
                    self.status.set("Local turn not committed: " + str(value))
                self._refresh()
        except Empty:
            pass
        self.window.after(100, self._drain)

    def close(self) -> None:
        if self.closed:
            return
        self.cancel()
        self.closed = True
        # A checkpoint loader can finish before the closed window drains
        # its event queue. Release these orphan session handles explicitly.
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "loaded" and isinstance(value, DurableOfflineAISession):
                    value.close()
        except Empty:
            pass
        if (isinstance(self.session, DurableOfflineAISession)
                and (not self.active or self.loading_model)):
            # The old session is not being used during checkpoint loading;
            # release it even if an unrelated model-load thread is active.
            self.session.close()
        self.window.destroy()


def open_offline_ai(parent: Any) -> OfflineAIWindow:
    return OfflineAIWindow(parent)


def run_offline_ai() -> int:
    """Start the local-only AI desktop surface on any Tk-capable host."""
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    window = open_offline_ai(root)

    def finish() -> None:
        window.close()
        root.destroy()

    window.window.protocol("WM_DELETE_WINDOW", finish)
    root.mainloop()
    return 0


def smoke_offline_gguf_deployment(manifest_path: str | Path) -> bool:
    """Execute an actual operator-provided GGUF model and verify durable resume.

    Unlike the tiny synthetic native smoke, this command runs the admitted
    llama.cpp executable against real supplied model weights. It never
    downloads an artifact or contacts a remote model provider.
    """
    from tempfile import TemporaryDirectory

    model = load_gguf_deployment(manifest_path)
    with TemporaryDirectory(prefix="skeleton-gguf-smoke-") as root:
        database = Path(root) / "gguf.sqlite3"
        chat = DurableOfflineAISession(model, database=database)
        sid = chat.session_id
        try:
            answer = asyncio.run(chat.ask(
                "Reply with a short greeting.", max_output_tokens=chat.preferred_output_tokens
            ))
            history = chat.history
            if (
                not answer.text.strip()
                or len(answer.execution_receipt_digest) != 64
                or answer.model_digest != model.model_digest
                or chat.list_conversations() != ((sid, 1),)
            ):
                return False
        finally:
            chat.close()
        recovered = DurableOfflineAISession(
            model, database=database, session_id=sid
        )
        try:
            return (
                recovered.history == history
                and recovered.tokenizer_digest == _model_tokenizer_digest(model)
            )
        finally:
            recovered.close()


def smoke_offline_native_inference() -> bool:
    """Exercise the native inference graph in an isolated tiny fixture.

    Used solely to confirm frozen app bundle integrity. This untrained model
    is never offered to users or represented as a usable AI checkpoint.
    """
    from skeleton.ai.model_runtime import NativeLLMRuntime
    from skeleton.cortex.transformer import TinyTransformer

    runtime = NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=48, seed=41, n_heads=2, n_layers=2, d_ff=16,
    ))
    from tempfile import TemporaryDirectory

    session = OfflineAISession(NativeRuntimeLocalModel(runtime))
    answer = asyncio.run(session.ask("hello", max_output_tokens=2))
    if not (
        bool(answer.text)
        and answer.model_digest == runtime.model_digest
        and len(answer.execution_receipt_digest) == 64
        and len(session.history) == 2
    ):
        return False
    # Release packaging must prove the same native backend survives a
    # complete in-process window/store teardown and fresh SQLite reopen.
    with TemporaryDirectory(prefix="skeleton-offline-smoke-") as directory:
        path = Path(directory) / "local.sqlite3"
        durable = DurableOfflineAISession(
            NativeRuntimeLocalModel(runtime), database=path
        )
        sid = durable.session_id
        completed = asyncio.run(durable.ask("hello", max_output_tokens=2))
        expected_history = durable.history
        durable.close()
        restored = DurableOfflineAISession(
            NativeRuntimeLocalModel(runtime), database=path, session_id=sid
        )
        try:
            return (
                bool(completed.text)
                and completed.model_digest == runtime.model_digest
                and restored.history == expected_history
                and restored.list_conversations() == ((sid, 1),)
            )
        finally:
            restored.close()
