"""Docker-free, provider-free desktop conversations over local model runtimes.

The app shell is neither a model owner nor a production conversation authority.
Operator-controlled file backups are portable data, not verified execution
evidence. Real native or GGUF model weights must be supplied locally.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
import threading
from typing import Any

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
from skeleton.ai.runtime.inference.local import LocalInferenceRequest, LocalInferenceResult, LocalInferenceEngine
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.offline_history import backup_history, restore_history
from skeleton.app.offline_workspace import DurableOfflineSession
from skeleton.app.offline_library import OfflineDocumentLibrary


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


class _PortableOfflineHistory:
    """Opt-in portable transcript copies without taking conversation authority."""

    history: tuple[tuple[str, str], ...]

    @property
    def model_digest(self) -> str:
        raise NotImplementedError

    def save_history_backup(self, path: str | Path) -> str:
        return backup_history(path, self.model_digest, self.history)

    def restore_history_backup(self, path: str | Path) -> int:
        if self.history:
            raise OfflineAIError("start a new conversation before restoring a backup")
        recovered = restore_history(path, self.model_digest)
        self.history = recovered
        return len(recovered) // 2


class OfflineAISession(_PortableOfflineHistory):
    """Ephemeral canonical-native conversation with opt-in portable backups.

    This shell creates no production durable terminal/chat authority. Restored
    history is untrusted context and never a replay or verification receipt.
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
    def max_interactive_tokens(self) -> int:
        runtime = self.backend.runtime
        return max(1, min(32, runtime.limits.max_new_tokens, runtime.limits.max_context // 4))

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




class OfflineGGUFSession(_PortableOfflineHistory):
    """Desktop/headless chat over the already-governed offline llama.cpp owner.

    A manifest pins both a local executable and the operator-supplied GGUF by
    SHA-256. Every inference revalidates artifact hashes; no hosted provider,
    model download, or implicit cloud fallback is constructed. Transcript
    history is volatile, and only complete model results enter the next turn.
    """

    def __init__(self, manifest_path: str | Path) -> None:
        deployment = LocalModelDeployment.load(manifest_path)
        self.deployment = deployment
        self.backend = LlamaCppModel(
            deployment.llama_cpp_config(rehash_artifacts_each_run=True)
        )
        self.engine = LocalInferenceEngine(self.backend, cache_size=0)
        self.history: tuple[tuple[str, str], ...] = ()

    @property
    def model_digest(self) -> str:
        return self.backend.model_digest

    @property
    def max_interactive_tokens(self) -> int:
        return min(32, max(1, (self.deployment.context_size or 2048) // 4))

    def clear(self) -> None:
        self.history = ()

    def _request(
        self, prompt: str, max_output_tokens: int
    ) -> tuple[LocalInferenceRequest, tuple[tuple[str, str], ...]]:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_USER_CHARS:
            raise OfflineAIError("message must contain 1-4096 characters")
        context = self.deployment.context_size
        limit = min(8192, context // 2) if context is not None else 8192
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= limit
        ):
            raise OfflineAIError("output-token budget exceeds the local GGUF deployment limit")

        # Bounded history prevents unbounded transcript growth in the desktop
        # process. The llama.cpp runtime remains the token/context authority.
        history = self.history
        while history and (
            sum(len(text) for _, text in history) + len(prompt) > 16_384
            or len(history) > MAX_HISTORY_MESSAGES - 2
        ):
            history = history[2:]
        return LocalInferenceRequest(
            prompt=prompt.strip(),
            history=history,
            max_output_tokens=max_output_tokens,
        ), history

    async def ask(self, prompt: str, *, max_output_tokens: int = 32) -> OfflineAnswer:
        request, retained = self._request(prompt, max_output_tokens)
        result = await self.engine.generate(request)
        if (
            not isinstance(result.text, str)
            or not result.text.strip()
            or result.tool_calls
            or not result.execution_receipt_digest
            or result.model_digest != self.model_digest
            or result.finish_reason not in {"completed", "length"}
        ):
            raise OfflineAIError("local GGUF model did not return a bound, text-only answer")
        self.history = (
            retained + (("user", request.prompt), ("assistant", result.text))
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
        from tkinter import filedialog, messagebox, scrolledtext, ttk

        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.window = tk.Toplevel(parent)
        self.window.title("Skeleton · Local AI")
        self.window.geometry("850x660")
        self.window.minsize(600, 440)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.session: OfflineAISession | OfflineGGUFSession | DurableOfflineSession | None = None
        self.library: OfflineDocumentLibrary | None = None
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
            text="Select a native checkpoint or a digest-pinned local GGUF deployment. No model is bundled or downloaded; answer quality depends on local weights.",
            wraplength=790,
        ).pack(anchor="w", pady=(4, 10))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x")
        self.load_button = ttk.Button(toolbar, text="Load checkpoint…", command=self.choose_model)
        self.load_button.pack(side="left")
        self.deployment_button = ttk.Button(toolbar, text="Load GGUF deployment…", command=self.choose_deployment)
        self.deployment_button.pack(side="left", padx=8)
        self.clear_button = ttk.Button(toolbar, text="New conversation", command=self.clear)
        self.clear_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(toolbar, text="Cancel generation", command=self.cancel)
        self.cancel_button.pack(side="left")
        backup_toolbar = ttk.Frame(frame)
        backup_toolbar.pack(fill="x", pady=(7, 0))
        self.save_history_button = ttk.Button(
            backup_toolbar, text="Back up conversation…", command=self.save_backup
        )
        self.save_history_button.pack(side="left")
        self.restore_history_button = ttk.Button(
            backup_toolbar, text="Restore conversation…", command=self.restore_backup
        )
        self.restore_history_button.pack(side="left", padx=8)
        self.workspace_button = ttk.Button(
            backup_toolbar, text="Attach local workspace…", command=self.attach_workspace
        )
        self.workspace_button.pack(side="left", padx=8)
        library_toolbar = ttk.Frame(frame)
        library_toolbar.pack(fill="x", pady=(7, 0))
        self.attach_library_button = ttk.Button(
            library_toolbar, text="Open local library…", command=self.attach_library
        )
        self.attach_library_button.pack(side="left")
        self.index_library_button = ttk.Button(
            library_toolbar, text="Index text folder…", command=self.index_library
        )
        self.index_library_button.pack(side="left", padx=8)
        self.search_library_button = ttk.Button(
            library_toolbar, text="Search local library", command=self.search_library
        )
        self.search_library_button.pack(side="left")
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
        self.deployment_button.configure(state="disabled" if self.active else "normal")
        self.save_history_button.configure(
            state="normal" if self.session is not None and not self.active else "disabled"
        )
        self.restore_history_button.configure(
            state="normal" if self.session is not None and not self.active else "disabled"
        )
        self.workspace_button.configure(
            state="normal"
            if (self.session is not None and not self.active
                and not isinstance(self.session, DurableOfflineSession))
            else "disabled"
        )
        self.attach_library_button.configure(state="disabled" if self.active else "normal")
        self.index_library_button.configure(
            state="normal" if self.library is not None and not self.active else "disabled"
        )
        self.search_library_button.configure(
            state="normal" if self.library is not None and not self.active else "disabled"
        )
        self.send_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.clear_button.configure(state="normal" if self.session is not None and not self.active else "disabled")
        self.cancel_button.configure(state="normal" if self.active else "disabled")

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", speaker + "\n" + text + "\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _redraw_history(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        if self.session is not None:
            for role, content in self.session.history:
                self._append("You" if role == "user" else "Skeleton · Local", content)

    def save_backup(self) -> None:
        if self.session is None or self.active:
            return
        destination = self.filedialog.asksaveasfilename(
            parent=self.window,
            title="Back up local conversation (unencrypted plaintext)",
            defaultextension=".json",
            filetypes=[("JSON backup", "*.json")],
        )
        if not destination:
            return
        try:
            checksum = self.session.save_history_backup(destination)
        except (ValueError, OSError) as exc:
            self.status.set("Backup rejected: " + str(exc))
        else:
            self.status.set("Local transcript backup saved · checksum " + checksum[:12])

    def restore_backup(self) -> None:
        if self.session is None or self.active:
            return
        source = self.filedialog.askopenfilename(
            parent=self.window,
            title="Restore model-matched offline transcript",
            filetypes=[("JSON backup", "*.json"), ("All files", "*.*")],
        )
        if not source:
            return
        try:
            turns = self.session.restore_history_backup(source)
        except (ValueError, OSError) as exc:
            self.status.set("Restore rejected: " + str(exc))
        else:
            self._redraw_history()
            self.status.set("Restored " + str(turns) + " local turns as untrusted context")

    def attach_workspace(self) -> None:
        """Attach a user-selected SQLite workspace; never silently overwrite turns."""
        if self.active or self.session is None or isinstance(self.session, DurableOfflineSession):
            return
        if self.session.history:
            self.status.set("Start a new empty conversation before attaching durable workspace.")
            return
        selected = self.filedialog.asksaveasfilename(
            parent=self.window,
            title="Create or open an unencrypted local SQLite workspace",
            defaultextension=".sqlite",
            filetypes=[("SQLite workspace", "*.sqlite"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
        if not selected:
            return
        try:
            self.session = DurableOfflineSession(self.session, selected)
        except (ValueError, RuntimeError, OSError) as exc:
            self.status.set("Workspace rejected: " + str(exc))
            return
        self._redraw_history()
        self.status.set(
            "Offline SQLite workspace active: " + str(len(self.session.history) // 2)
            + " restored turns (unencrypted local state)"
        )
        self._refresh()

    def attach_library(self) -> None:
        if self.active:
            return
        selected = self.filedialog.asksaveasfilename(
            parent=self.window,
            title="Select or create an offline document index",
            defaultextension=".sqlite",
            filetypes=[("SQLite library", "*.sqlite"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
        if not selected:
            return
        try:
            replacement = OfflineDocumentLibrary(selected)
        except (ValueError, RuntimeError, OSError) as exc:
            self.status.set("Local library rejected: " + str(exc))
            return
        previous = self.library
        self.library = replacement
        if previous is not None:
            previous.close()
        self.status.set(
            "Offline document library opened · " + str(replacement.count())
            + " indexed files"
        )
        self._refresh()

    def index_library(self) -> None:
        if self.active or self.library is None:
            return
        selected = self.filedialog.askdirectory(
            parent=self.window,
            title="Select a local UTF-8 text folder to index (no network)",
        )
        if not selected:
            return
        self.active = True
        self.status.set("Indexing selected local text files; no provider calls…")
        self._refresh()
        library = self.library

        def work() -> None:
            try:
                self.events.put(("indexed", library.index_directory(selected)))
            except Exception as exc:
                self.events.put(("library_error", str(exc)))

        threading.Thread(target=work, name="skeleton-offline-indexer", daemon=True).start()

    def search_library(self) -> None:
        if self.active or self.library is None:
            return
        query = self.composer.get("1.0", "end-1c").strip()
        if not query:
            self.status.set("Enter a search phrase in the message field.")
            return
        self.active = True
        self.status.set("Searching on-device FTS5 library without model inference…")
        self._refresh()
        library = self.library

        def work() -> None:
            try:
                self.events.put(("library_hits", library.search(query)))
            except Exception as exc:
                self.events.put(("library_error", str(exc)))

        threading.Thread(target=work, name="skeleton-offline-library-search", daemon=True).start()

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

    def choose_deployment(self) -> None:
        if self.active:
            return
        selected = self.filedialog.askopenfilename(
            parent=self.window,
            title="Select a local GGUF deployment manifest",
            filetypes=[("JSON deployment manifest", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        self.active = True
        self.status.set("Verifying the local executable and GGUF SHA-256 identities…")
        self._refresh()

        def work() -> None:
            try:
                self.events.put(("loaded", OfflineGGUFSession(selected)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, name="skeleton-gguf-manifest-load", daemon=True).start()

    def clear(self) -> None:
        if self.active or self.session is None:
            return
        if isinstance(self.session, DurableOfflineSession):
            if not self.messagebox.askyesno(
                "Clear saved offline conversation?",
                "This clears the current SQLite workspace conversation and cannot be undone. "
                "Portable backups are unaffected.",
                parent=self.window,
            ):
                return
        try:
            self.session.clear()
        except (ValueError, RuntimeError, OSError) as exc:
            self.status.set("Clear rejected: " + str(exc))
            return
        self._redraw_history()
        self.status.set("Conversation cleared; portable backups are unchanged.")

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
                task = asyncio.create_task(session.ask(prompt, max_output_tokens=session.max_interactive_tokens))
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
                    previous = self.session
                    if isinstance(previous, DurableOfflineSession):
                        previous.close()
                    self.session = value  # type: ignore[assignment]
                    self._redraw_history()
                    self.status.set("Offline model loaded: " + self.session.model_digest[:16] + "…")
                elif kind == "indexed":
                    summary = value
                    self.status.set(
                        "Indexed " + str(summary["indexed_files"]) + " local files · "
                        + str(summary["updated_files"]) + " updated · "
                        + str(summary["removed_files"]) + " removed"
                    )
                elif kind == "library_hits":
                    matches = value
                    if matches:
                        lines = [
                            hit.relative_path + " · sha256 "
                            + hit.document_sha256[:16] + "\n" + hit.excerpt
                            for hit in matches
                        ]
                        self._append("Local library · not an AI response", "\n\n".join(lines))
                    self.status.set(
                        str(len(matches)) + " local source matches (not generated by a model)"
                    )
                elif kind == "library_error":
                    self.status.set("Offline library rejected: " + str(value))
                elif kind == "answer":
                    answer = value
                    self._append("Skeleton · Local", answer.text)  # type: ignore[attr-defined]
                    self.status.set(
                        "Completed · " + str(answer.input_tokens) + " input / " + str(answer.output_tokens) + " output tokens · receipt " + answer.execution_receipt_digest[:12]  # type: ignore[attr-defined]
                    )
                else:
                    # A failed invocation did not commit a turn. Discard its
                    # provisional visible user message as well.
                    self._redraw_history()
                    self.status.set("Local runtime rejected the request: " + str(value))
                self._refresh()
        except Empty:
            pass
        self.window.after(100, self._drain)

    def close(self) -> None:
        self.cancel()
        self.closed = True
        if isinstance(self.session, DurableOfflineSession):
            self.session.close()
        if self.library is not None:
            self.library.close()
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
    return (
        bool(answer.text)
        and answer.model_digest == runtime.model_digest
        and len(answer.execution_receipt_digest) == 64
        and len(session.history) == 2
    )
