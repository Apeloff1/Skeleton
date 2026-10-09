"""Docker-free, provider-free desktop conversation over the canonical native model.

This is an app-shell adapter, not a new AI runtime, transcript authority,
model trainer, or provider. Only a locally selected, integrity-checked native
checkpoint can be executed. No checkpoint or demo response is bundled.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
import threading
from typing import Any

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
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

    def __init__(self, backend: NativeRuntimeLocalModel) -> None:
        if not isinstance(backend, NativeRuntimeLocalModel):
            raise OfflineAIError("canonical native model backend required")
        backend.assert_identity()
        self.backend = backend
        self.engine = LocalInferenceEngine(backend, cache_size=0)
        self.history: tuple[tuple[str, str], ...] = ()

    def clear(self) -> None:
        self.history = ()

    @property
    def model_digest(self) -> str:
        return self.backend.model_digest

    def _request(self, prompt: str, max_output_tokens: int) -> tuple[LocalInferenceRequest, tuple[tuple[str, str], ...]]:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_USER_CHARS:
            raise OfflineAIError("message must contain 1-4096 characters")
        runtime = self.backend.runtime
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= runtime.limits.max_new_tokens
        ):
            raise OfflineAIError("output-token budget exceeds the loaded model limit")
        # Leave enough context for the answer. Drop oldest full turns, never
        # truncate a message mid-token or corrupt role framing.
        available = runtime.limits.max_context - max_output_tokens
        if available < 1:
            raise OfflineAIError("checkpoint has insufficient context for this output budget")
        history = self.history
        while True:
            request = LocalInferenceRequest(
                prompt=prompt.strip(),
                history=history,
                max_output_tokens=max_output_tokens,
            )
            observed = len(runtime.tokenizer.encode_ids(request.rendered_input))
            if observed <= available:
                return request, history
            if not history:
                raise OfflineAIError("message exceeds native model context; shorten it or reduce the output budget")
            history = history[2:]

    async def ask(self, prompt: str, *, max_output_tokens: int = 32) -> OfflineAnswer:
        request, retained_history = self._request(prompt, max_output_tokens)
        result: LocalInferenceResult = await self.engine.generate(request)
        if (
            not isinstance(result.text, str)
            or not result.text.strip()
            or result.tool_calls
            or not result.execution_receipt_digest
            or result.model_digest != self.backend.model_digest
        ):
            raise OfflineAIError("native model did not return a bound, text-only answer")
        # Only commit a complete, verified local inference result.
        self.history = (
            retained_history
            + (("user", request.prompt), ("assistant", result.text))
        )[-MAX_HISTORY_MESSAGES:]
        return OfflineAnswer(
            text=result.text,
            model_digest=result.model_digest,
            execution_receipt_digest=result.execution_receipt_digest,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )


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
        self.closed = False
        self.worker_loop: asyncio.AbstractEventLoop | None = None
        self.worker_task: asyncio.Task[OfflineAnswer] | None = None
        self.worker_lock = threading.Lock()

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
        self.load_button = ttk.Button(toolbar, text="Load checkpoint…", command=self.choose_model)
        self.load_button.pack(side="left")
        self.clear_button = ttk.Button(toolbar, text="New conversation", command=self.clear)
        self.clear_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(toolbar, text="Cancel generation", command=self.cancel)
        self.cancel_button.pack(side="left")
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
        self.send_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.clear_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.cancel_button.configure(state="normal" if self.active else "disabled")

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", speaker + "\n" + text + "\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def choose_model(self) -> None:
        if self.active:
            return
        selected = self.filedialog.askopenfilename(
            parent=self.window,
            title="Select a Skeleton native model checkpoint",
            filetypes=[("JSON checkpoint", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        self.active = True
        self.status.set("Validating the checkpoint and native model weights…")
        self._refresh()

        def work() -> None:
            try:
                session = OfflineAISession(load_native_checkpoint(selected))
                self.events.put(("loaded", session))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, name="skeleton-local-model-load", daemon=True).start()

    def clear(self) -> None:
        if self.active or self.session is None:
            return
        self.session.clear()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.status.set("Conversation reset in memory.")

    def send(self) -> None:
        if self.active or self.session is None:
            return
        prompt = self.composer.get("1.0", "end-1c").strip()
        if not prompt:
            return
        self.composer.delete("1.0", "end")
        self._append("You", prompt)
        self.active = True
        self.status.set("Generating locally…")
        self._refresh()
        session = self.session

        def work() -> None:
            async def generate() -> OfflineAnswer:
                task = asyncio.create_task(session.ask(prompt, max_output_tokens=min(32, session.backend.runtime.limits.max_new_tokens, max(1, session.backend.runtime.limits.max_context // 4))))
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
                if kind == "loaded":
                    self.session = value  # type: ignore[assignment]
                    self.clear()
                    self.status.set("Native model loaded: " + self.session.model_digest[:16] + "…")
                elif kind == "answer":
                    answer = value
                    self._append("Skeleton · Local", answer.text)  # type: ignore[attr-defined]
                    self.status.set(
                        "Completed · " + str(answer.input_tokens) + " input / " + str(answer.output_tokens) + " output tokens · receipt " + answer.execution_receipt_digest[:12]  # type: ignore[attr-defined]
                    )
                else:
                    self._append("Local runtime", "Request rejected: " + str(value))
                    self.status.set("Local model unavailable or request rejected.")
                self._refresh()
        except Empty:
            pass
        self.window.after(100, self._drain)

    def close(self) -> None:
        self.cancel()
        self.closed = True
        self.window.destroy()


def open_offline_ai(parent: Any) -> OfflineAIWindow:
    return OfflineAIWindow(parent)
