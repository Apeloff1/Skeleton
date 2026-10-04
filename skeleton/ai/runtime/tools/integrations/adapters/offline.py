"""Local, deterministic offline provider so Skeleton runs with no services.

``OfflineProvider`` never opens a socket.  It answers from a small ordered
set of *skills* (pure functions over the request) and, failing those, from an
extractive summary of the conversation.  Output is deterministic for a given
request, which also makes it the reference provider for tests.

Applications may plug in a local generator (for example a llama.cpp or ONNX
binding) via ``generator``; it is called in a worker thread and its failure
degrades back to the built-in skills rather than failing the request.
"""

from __future__ import annotations

import ast
import asyncio
import json
import operator
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Iterable, Sequence

from .provider import BaseProvider, CallContext, HealthStatus, ProviderInfo
from .types import (
    ChatRequest,
    ChatResponse,
    ChunkKind,
    FinishReason,
    ProviderCapability,
    Role,
    StreamChunk,
    ToolCall,
    ToolSpec,
    Usage,
)

__all__ = [
    "OfflineProvider",
    "OfflineSkill",
    "estimate_tokens",
    "extractive_summary",
    "safe_arithmetic",
    "DEFAULT_SKILLS",
]

_WORD = re.compile(r"[A-Za-z0-9_']+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have i if in into is it its of on or so that the their "
    "then there these this to was were will with you your we our they them can could should would".split()
)


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token, min 1 per word)."""

    if not text:
        return 0
    words = len(_WORD.findall(text))
    return max(words, (len(text) + 3) // 4)


def extractive_summary(text: str, max_sentences: int = 3) -> str:
    """Pick the highest-scoring sentences by content-word frequency, in order."""

    sentences = [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    freq = Counter(w.lower() for w in _WORD.findall(text) if w.lower() not in _STOPWORDS)
    if not freq:
        return " ".join(sentences[:max_sentences])
    top = max(freq.values())
    scored = []
    for idx, sentence in enumerate(sentences):
        words = [w.lower() for w in _WORD.findall(sentence) if w.lower() not in _STOPWORDS]
        score = sum(freq[w] / top for w in words) / (len(words) ** 0.5 if words else 1.0)
        scored.append((score, -idx, idx))
    keep = sorted(idx for _s, _n, idx in sorted(scored, reverse=True)[:max_sentences])
    return " ".join(sentences[i] for i in keep)


_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNOPS: dict[type, Callable[[Any], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_arithmetic(expression: str, *, max_power: int = 64, max_len: int = 200) -> float | int:
    """Evaluate a pure arithmetic expression without ``eval``.

    Only numeric literals, + - * / // % ** and parentheses are accepted.
    Exponents are bounded to stop CPU/memory blowups.
    """

    if len(expression) > max_len:
        raise ValueError("expression too long")
    tree = ast.parse(expression, mode="eval")

    def walk(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                raise ValueError("booleans are not numbers here")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > max_power or abs(left) > 10**6):
                raise ValueError("exponent out of range")
            return _BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
            return _UNOPS[type(node.op)](walk(node.operand))
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    return walk(tree)


@dataclass(frozen=True)
class OfflineSkill:
    """A named, pure responder: returns text or ``None`` to pass."""

    name: str
    respond: Callable[[ChatRequest], str | None]


_ARITH = re.compile(r"^[\s\d().+\-*/%]+$")
_ARITH_PROMPT = re.compile(
    r"(?:what\s+is|what's|calculate|compute|evaluate)\s+([\d\s().+\-*/%]+?)\s*\??$", re.IGNORECASE
)


def _skill_arithmetic(request: ChatRequest) -> str | None:
    text = request.last_user_text.strip()
    match = _ARITH_PROMPT.search(text)
    expr = match.group(1) if match else (text if _ARITH.match(text) and any(c.isdigit() for c in text) else None)
    if not expr or not any(op in expr for op in "+-*/%"):
        return None
    try:
        value = safe_arithmetic(expr.strip())
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{expr.strip()} = {value}"


_GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|yo)\b[\s!.,]*$", re.IGNORECASE)


def _skill_greeting(request: ChatRequest) -> str | None:
    if _GREETING.match(request.last_user_text):
        return "Hello. I'm Skeleton's offline assistant; no external model is reachable right now."
    return None


_SUMMARIZE = re.compile(r"^\s*(summari[sz]e|tl;?dr|give me a summary)[:\s]*", re.IGNORECASE)


def _skill_summarize(request: ChatRequest) -> str | None:
    text = request.last_user_text
    match = _SUMMARIZE.match(text)
    if not match:
        return None
    body = text[match.end():].strip()
    if not body:
        prior = [m.content for m in request.messages[:-1] if m.role in (Role.USER, Role.ASSISTANT)]
        body = " ".join(prior)
    if not body:
        return "There is nothing to summarize yet."
    return extractive_summary(body, max_sentences=3)


_STATUS = re.compile(r"\b(are you (online|offline)|which (model|provider)|who are you)\b", re.IGNORECASE)


def _skill_status(request: ChatRequest) -> str | None:
    if _STATUS.search(request.last_user_text):
        return (
            "I am the offline fallback provider. External model providers are unavailable or disabled, "
            "so answers come from deterministic local skills."
        )
    return None


DEFAULT_SKILLS: tuple[OfflineSkill, ...] = (
    OfflineSkill("greeting", _skill_greeting),
    OfflineSkill("status", _skill_status),
    OfflineSkill("arithmetic", _skill_arithmetic),
    OfflineSkill("summarize", _skill_summarize),
)

_TOOL_INVOKE = re.compile(r"(?:^|\s)(?:/|call\s+|use\s+)([A-Za-z0-9_.\-]+)\s*(\{.*\})?\s*$", re.DOTALL)


class OfflineProvider(BaseProvider):
    """Deterministic, dependency-free local provider."""

    DEFAULT_NAME = "offline"

    def __init__(
        self,
        name: str = DEFAULT_NAME,
        *,
        skills: Sequence[OfflineSkill] = DEFAULT_SKILLS,
        generator: Callable[[str], str] | None = None,
        priority: int = 1000,
        chunk_words: int = 1,
    ) -> None:
        super().__init__(
            ProviderInfo(
                name=name,
                capabilities=frozenset(
                    {
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.TOOLS,
                        ProviderCapability.JSON_MODE,
                        ProviderCapability.OFFLINE,
                    }
                ),
                models=("offline-skills",),
                priority=priority,
                local=True,
                tags=frozenset({"offline", "deterministic"}),
            )
        )
        if chunk_words < 1:
            raise ValueError("chunk_words must be >= 1")
        self._skills = tuple(skills)
        self._generator = generator
        self._chunk_words = chunk_words
        self.calls = 0

    # -- answering ---------------------------------------------------------
    def _tool_call(self, request: ChatRequest) -> ToolCall | None:
        if not request.tools:
            return None
        if request.messages[-1].role is Role.TOOL:
            return None
        match = _TOOL_INVOKE.search(request.last_user_text.strip())
        if not match:
            return None
        name = match.group(1)
        spec = _find_tool(request.tools, name)
        if spec is None:
            return None
        raw = match.group(2)
        try:
            arguments = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return None
        if not isinstance(arguments, dict):
            return None
        call_id = f"offline-{request.fingerprint()[:12]}"
        return ToolCall(id=call_id, name=spec.name, arguments=arguments)

    def _skill_answer(self, request: ChatRequest) -> tuple[str, str]:
        last = request.messages[-1]
        if last.role is Role.TOOL:
            return f"Tool {last.name or last.tool_call_id} returned: {last.content}", "tool_echo"
        for skill in self._skills:
            try:
                answer = skill.respond(request)
            except Exception:  # noqa: BLE001 - a broken skill must not fail offline mode
                continue
            if answer:
                return answer, skill.name
        text = request.last_user_text.strip()
        if not text:
            return "I'm running offline and received no user message.", "empty"
        summary = extractive_summary(text, max_sentences=2)
        return (
            "I'm running offline without an external model, so I can't fully answer that. "
            f"Here is what I understood: {summary}",
            "fallback",
        )

    async def _generate(self, request: ChatRequest, ctx: CallContext) -> tuple[str, str]:
        if self._generator is not None:
            prompt = "\n".join(f"{m.role.value}: {m.content}" for m in request.messages)
            try:
                remaining = ctx.deadline.cap(None)
                text = await asyncio.wait_for(asyncio.to_thread(self._generator, prompt), timeout=remaining)
                if isinstance(text, str) and text.strip():
                    return text, "generator"
            except Exception:  # noqa: BLE001 - degrade to deterministic skills
                pass
        return self._skill_answer(request)

    def _finalize_text(self, request: ChatRequest, text: str, skill: str) -> tuple[str, bool]:
        """Apply json_mode, stop sequences and max_tokens; report truncation."""

        if request.json_mode:
            return json.dumps({"answer": text, "source": "offline", "skill": skill}, sort_keys=True), False
        for stop in request.stop:
            if stop and stop in text:
                text = text.split(stop, 1)[0]
        if request.max_tokens is not None:
            words = text.split()
            if len(words) > request.max_tokens:
                return " ".join(words[: request.max_tokens]), True
        return text, False

    async def _complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        ctx.check()
        self.calls += 1
        model = self.resolve_model(request)
        prompt_tokens = sum(estimate_tokens(m.content) for m in request.messages)
        call = self._tool_call(request)
        if call is not None:
            return ChatResponse(
                text="",
                provider=self.name,
                model=model,
                finish_reason=FinishReason.TOOL_CALLS,
                tool_calls=(call,),
                usage=Usage(prompt_tokens, 0),
                attempts=ctx.attempt,
                metadata={"skill": "tool_router"},
            )
        text, skill = await self._generate(request, ctx)
        final, truncated = self._finalize_text(request, text, skill)
        return ChatResponse(
            text=final,
            provider=self.name,
            model=model,
            finish_reason=FinishReason.LENGTH if truncated else FinishReason.STOP,
            usage=Usage(prompt_tokens, estimate_tokens(final)),
            attempts=ctx.attempt,
            metadata={"skill": skill},
        )

    async def _stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]:
        response = await self._complete(request, ctx)
        index = 0
        for piece in _split_words(response.text, self._chunk_words):
            ctx.token.check()
            yield StreamChunk.text_delta(index, piece, provider=self.name, model=response.model)
            index += 1
            await asyncio.sleep(0)
        for call in response.tool_calls:
            yield StreamChunk(ChunkKind.TOOL_CALL, index, tool_call=call, provider=self.name)
            index += 1
        yield StreamChunk(ChunkKind.USAGE, index, usage=response.usage, provider=self.name)
        index += 1
        yield StreamChunk.finish(index, response.finish_reason, provider=self.name, model=response.model)

    async def health(self) -> HealthStatus:
        return HealthStatus(True, "offline provider is always available")


def _find_tool(tools: Iterable[ToolSpec], name: str) -> ToolSpec | None:
    for spec in tools:
        if spec.name == name:
            return spec
    return None


def _split_words(text: str, per_chunk: int) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"\S+\s*", text)
    leading = text[: len(text) - len(text.lstrip())]
    pieces = ["".join(tokens[i : i + per_chunk]) for i in range(0, len(tokens), per_chunk)]
    if leading and pieces:
        pieces[0] = leading + pieces[0]
    return pieces
