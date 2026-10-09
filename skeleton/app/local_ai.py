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
from skeleton.app.local_ai_transcript import load_transcript, save_transcript


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


def inspect_local_model(backend: NativeRuntimeLocalModel) -> dict[str, object]:
    """Report actual offline model limits and identity without executing a prompt.

    This is technical capability inspection, NOT a trained-quality or general
    intelligence certificate.
    """
    if not isinstance(backend, NativeRuntimeLocalModel):
        raise OfflineAIError("native transformer model required")
    backend.assert_identity()
    runtime = backend.runtime
    return {
        "schema_version": 1,
        "model_id": backend.model_id,
        "model_digest": backend.model_digest,
        "tokenizer_digest": backend.tokenizer_digest,
        "runtime_digest": backend.runtime_digest,
        "max_context_tokens": runtime.limits.max_context,
        "max_output_tokens": runtime.limits.max_new_tokens,
        "model_bytes": runtime.model_bytes,
        "provider_credentials_required": False,
        "network_required": False,
        "model_quality_certified": False,
    }


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

    def export_transcript(self, path: str | Path) -> str:
        """User-requested offline snapshot; not the durable assistant authority."""
        self.backend.assert_identity()
        return save_transcript(
            path, model_digest=self.backend.model_digest,
            tokenizer_digest=self.backend.tokenizer_digest, history=self.history,
        )

    def import_transcript(self, path: str | Path) -> int:
        """Restore only fully verified turns bound to this exact native model."""
        self.backend.assert_identity()
        restored = load_transcript(
            path, model_digest=self.backend.model_digest,
            tokenizer_digest=self.backend.tokenizer_digest,
        )
        self.history = restored  # commit only after all checks pass
        return len(restored) // 2

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
        self.train_button = ttk.Button(toolbar, text="Train small local model…", command=self.train_model)
        self.train_button.pack(side="left", padx=4)
        self.improve_button = ttk.Button(toolbar, text="Improve model…", command=self.improve_model)
        self.improve_button.pack(side="left", padx=4)
        self.clear_button = ttk.Button(toolbar, text="New conversation", command=self.clear)
        self.clear_button.pack(side="left", padx=8)
        self.open_history_button = ttk.Button(toolbar, text="Open chat…", command=self.open_history)
        self.open_history_button.pack(side="left", padx=4)
        self.save_history_button = ttk.Button(toolbar, text="Save chat…", command=self.save_history)
        self.save_history_button.pack(side="left", padx=4)
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
        self.train_button.configure(state="disabled" if self.active else "normal")
        self.improve_button.configure(
            state="normal" if self.session is not None and not self.active else "disabled"
        )
        self.send_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.clear_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.cancel_button.configure(state="normal" if self.active else "disabled")
        self.open_history_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.save_history_button.configure(state="normal" if self.session is not None and not self.active else "disabled")

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

    def train_model(self) -> None:
        """Bootstrap one genuine, tiny CPU checkpoint from user-chosen text.

        This is an educational/experimental local transformer, not
        production-trained LLM weights. Never train on startup without consent.
        """
        if self.active:
            return
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Experimental CPU model training",
            "Train a small transformer only on the local text you choose? "
            "The output is experimental and not comparable to a trained "
            "foundation language model. No data is uploaded.",
            parent=self.window,
        ):
            return
        source = self.filedialog.askopenfilename(
            parent=self.window, title="Choose UTF-8 local training text",
            filetypes=[("UTF-8 text", "*.txt"), ("All files", "*.*")],
        )
        if not source:
            return
        destination = self.filedialog.asksaveasfilename(
            parent=self.window, title="Save new experimental native checkpoint",
            defaultextension=".json", filetypes=[("Native checkpoint", "*.json")],
        )
        if not destination:
            return
        self.active = True
        self.status.set("Training a bounded native CPU transformer locally…")
        self._refresh()

        def work() -> None:
            try:
                from skeleton.app.local_ai_training import train_local_text

                receipt = train_local_text(source, destination)
                session = OfflineAISession(load_native_checkpoint(destination))
                self.events.put(("trained", (session, receipt)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(
            target=work, daemon=True, name="skeleton-native-cpu-training",
        ).start()

    def improve_model(self) -> None:
        """Consent-bound learning never modifies the loaded checkpoint itself."""
        if self.active or self.session is None:
            return
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Evaluate experimental model improvement",
            "Continue CPU training this model on your chosen text, "
            "evaluate it on a separate held-out text file, and save "
            "a NEW checkpoint only if held-out perplexity improves? "
            "The current model is kept unchanged. No data is uploaded.",
            parent=self.window,
        ):
            return
        parent_path = self.filedialog.askopenfilename(
            parent=self.window, title="Choose current native checkpoint",
            filetypes=[("Native checkpoint", "*.json"), ("All files", "*.*")],
        )
        if not parent_path:
            return
        training_path = self.filedialog.askopenfilename(
            parent=self.window, title="Choose incremental training text",
            filetypes=[("UTF-8 text", "*.txt"), ("All files", "*.*")],
        )
        if not training_path:
            return
        heldout_path = self.filedialog.askopenfilename(
            parent=self.window, title="Choose separate held-out evaluation text",
            filetypes=[("UTF-8 text", "*.txt"), ("All files", "*.*")],
        )
        if not heldout_path:
            return
        destination = self.filedialog.asksaveasfilename(
            parent=self.window, title="Save evaluated checkpoint to NEW file",
            defaultextension=".json", filetypes=[("Native checkpoint", "*.json")],
        )
        if not destination:
            return
        session = self.session
        self.active = True
        self.status.set("Training locally and checking held-out model quality…")
        self._refresh()

        def work() -> None:
            try:
                from skeleton.app.local_ai_improvement import improve_local_model

                parent = load_native_checkpoint(parent_path)
                if parent.model_digest != session.model_digest:
                    raise OfflineAIError(
                        "selected checkpoint does not match the active local model"
                    )
                receipt = improve_local_model(
                    parent_path, training_path, heldout_path, destination,
                )
                improved = OfflineAISession(load_native_checkpoint(destination))
                self.events.put(("improved", (improved, receipt)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(
            target=work, daemon=True, name="skeleton-evaluated-local-learning",
        ).start()

    def clear(self) -> None:
        if self.active or self.session is None:
            return
        self.session.clear()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.status.set("Conversation reset in memory.")

    def open_history(self) -> None:
        """Import is explicit and never modifies the session on bad input."""
        if self.active or self.session is None:
            return
        selected = self.filedialog.askopenfilename(
            parent=self.window, title="Open an offline Skeleton chat",
            filetypes=[("Skeleton chat", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            turns = self.session.import_transcript(selected)
        except (ValueError, OSError) as exc:
            self.status.set("Chat not opened: " + str(exc))
            return
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        for role, text in self.session.history:
            self._append("You" if role == "user" else "Skeleton · Local", text)
        self.status.set(f"Restored {turns} complete offline turns for this model.")

    def save_history(self) -> None:
        """The chosen file is readable local plaintext; no background upload."""
        if self.active or self.session is None:
            return
        selected = self.filedialog.asksaveasfilename(
            parent=self.window, title="Save offline chat as plaintext JSON",
            defaultextension=".json", filetypes=[("Skeleton chat", "*.json")],
        )
        if not selected:
            return
        try:
            digest = self.session.export_transcript(selected)
        except (ValueError, OSError) as exc:
            self.status.set("Chat not saved: " + str(exc))
            return
        self.status.set("Saved local chat · SHA-256 " + digest[:16] + "… · file is plaintext.")

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
                if kind == "improved":
                    self.session, receipt = value  # type: ignore[misc]
                    # Different weight identity means old turns are not silently
                    # assigned to the newly evaluated model.
                    self.clear()
                    self.status.set(
                        "Local candidate accepted by held-out perplexity · "
                        + f"{receipt.baseline_perplexity:.2f} → "
                        + f"{receipt.accepted_perplexity:.2f}"
                        + " · keep parent checkpoint for rollback"
                    )
                elif kind == "trained":
                    self.session, receipt = value  # type: ignore[misc]
                    self.clear()
                    self.status.set(
                        "Experimental CPU checkpoint ready · "
                        + str(receipt.training_steps) + " SGD steps · "
                        + f"corpus perplexity {receipt.initial_perplexity:.2f} → "
                        + f"{receipt.final_perplexity:.2f} · not quality certified"
                    )
                elif kind == "loaded":
                    self.session = value  # type: ignore[assignment]
                    self.clear()
                    info = inspect_local_model(self.session.backend)
                    self.status.set(
                        "Native model loaded · context "
                        + str(info["max_context_tokens"])
                        + " tokens · weights "
                        + str(info["model_bytes"])
                        + " bytes · " + self.session.model_digest[:12] + "…"
                    )
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
    session = OfflineAISession(NativeRuntimeLocalModel(runtime))
    answer = asyncio.run(session.ask("hello", max_output_tokens=2))
    # The Windows bundled binary must also round-trip a verified, private
    # conversation snapshot without importing optional hosted services.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="skeleton-native-smoke-") as folder:
        transcript = Path(folder) / "chat.json"
        session.export_transcript(transcript)
        restored = OfflineAISession(NativeRuntimeLocalModel(runtime))
        turns = restored.import_transcript(transcript)
        snapshot_ok = turns == 1 and restored.history == session.history
    return (
        bool(answer.text)
        and answer.model_digest == runtime.model_digest
        and len(answer.execution_receipt_digest) == 64
        and len(session.history) == 2
        and snapshot_ok
    )
