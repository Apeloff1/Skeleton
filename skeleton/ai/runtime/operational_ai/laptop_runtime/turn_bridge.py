"""One source-bound native turn verified against its durable SQLite commit.

This is the existing native supervisor path, not an alternate provider,
model backend, or replay database. The installed model and active principal
must remain unchanged before generation and before publishing any answer.
"""
from __future__ import annotations

from .identity import ActiveModel
from .result_protocol import verify_turn_receipt
from .contracts import identifier, utf8, nonnegative, number, refuse
from .once_guard import OnceGuard


class TurnBridge:
    def __init__(self, supervisor, guard=None):
        self.worker = supervisor
        self.guard = guard if guard is not None else OnceGuard()
        self.identity = ActiveModel.from_supervisor(supervisor)

    def _assert_current(self) -> None:
        """Fail closed if the checked model, tokenizer or principal changed."""
        try:
            active = ActiveModel.from_supervisor(self.worker)
        except Exception as exc:
            from .contracts import ContractViolation
            raise ContractViolation("native supervisor source identity unavailable") from exc
        if active != self.identity:
            refuse("native principal epoch changed after turn bridge binding")

    def _committed(self, session: str, request: str, question: str,
                   *, seed: int, temperature: float) -> dict:
        """Never trust model output without a read-only SQLite replay proof."""
        saved = self.worker.spine.replay(
            session, request, question, seed=seed, temperature=temperature
        )
        if saved is None:
            refuse("native output lacks authoritative SQLite commit")
        result = verify_turn_receipt(
            saved,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
        )
        if result["replayed"] is not True:
            refuse("SQLite replay must be explicitly marked committed")
        return result

    def turn(self, session_id, request_id, prompt, *, seed=0, temperature=0.8):
        """Bound one real turn, then independently prove its durable receipt."""
        session_id = identifier(session_id)
        request_id = identifier(request_id)
        question = utf8(prompt, maximum=self.worker.spine.limits.input_bytes)
        seed = nonnegative(seed, maximum=2**32 - 1)
        temperature = number(temperature, minimum=0.000000001, maximum=2)
        self._assert_current()
        with self.guard.hold(self.identity.tenant, session_id, request_id):
            # Guard against model swaps between preflight and the native lock.
            self._assert_current()
            result = self.worker.turn(
                session_id, request_id, question,
                seed=seed, temperature=temperature,
            )
            verified = verify_turn_receipt(
                result,
                model_sha256=self.identity.model_sha256,
                tokenizer_sha256=self.identity.tokenizer_sha256,
            )
            committed = self._committed(
                session_id, request_id, question,
                seed=seed, temperature=temperature,
            )
            for field in (
                "text", "output_sha256", "model_sha256", "tokenizer_sha256",
                "prompt_tokens", "generated_tokens",
            ):
                if verified[field] != committed[field]:
                    refuse("native result differs from durable committed replay")
            # An otherwise valid receipt is unsafe to disclose after an epoch
            # transition, even if the SQLite transaction already succeeded.
            self._assert_current()
            return verified
