"""
services/ai_assistant_svc.py — GROK-enhanced AI Assistant service.

Extracted from server.py (Feb 2026 Phase-9). Self-contained except for
``AIAssistantMode`` enum (still in server.py) and ``AIAssistRequest`` /
``AIAssistResponse`` Pydantic models (now in models/code_runtime.py).

Model execution is delegated to the canonical Skeleton engine through the
backend engine-text compatibility adapter. This legacy service owns neither
provider credentials nor provider transport.
"""
from __future__ import annotations

import hashlib
import logging
import re

from fastapi import HTTPException

from core.engine_client import EngineClient, EngineClientError
from core.engine_chat import EngineChat, EngineTextError, UserMessage
from core.engine_text import execute_engine_text
from skeleton.context.instruction_policy import InstructionPolicy


def _ai_modes():
    """Lazy access to server.AIAssistantMode enum."""
    from server import AIAssistantMode  # noqa: PLC0415

    return AIAssistantMode


# Pydantic request/response shapes
from models.code_runtime import AIAssistRequest, AIAssistResponse  # noqa: E402


AIAssistantMode = _ai_modes()  # eager-resolve at module-load time (server.py already loaded)
logger = logging.getLogger("CodeDock.AIAssistant")


class AIAssistantService:
    """Legacy code-assistance surface backed by the canonical engine."""

    def __init__(
        self,
        *,
        registry: object | None = None,
        runtime: object | None = None,
        engine_executor=None,
    ) -> None:
        if registry is not None or runtime is not None:
            raise ValueError(
                "local model runtime injection is disabled; use the canonical engine"
            )
        self._engine_executor = engine_executor or execute_engine_text
        self.model = "engine-routed"

    @property
    def api_key(self) -> str:
        """Legacy health compatibility without exposing credential material."""
        return "configured" if self.available else ""

    @property
    def available(self) -> bool:
        try:
            return EngineClient.from_env() is not None
        except EngineClientError:
            return False

    def provider_status(self) -> dict:
        """Return non-secret engine ownership metadata."""
        available = self.available
        return {
            "active": "skeleton-engine" if available else None,
            "available": available,
            "providers": [
                {
                    "id": "skeleton-engine",
                    "available": available,
                    "ownership": "engine-process",
                }
            ],
        }

    async def assist(self, request: AIAssistRequest) -> AIAssistResponse:
        prompts = {
            AIAssistantMode.EXPLAIN: """You are an elite code explanation expert. Your task is to:
1. Provide a clear, comprehensive explanation of what this code does
2. Break down complex logic step-by-step
3. Explain the purpose of each function/class/variable
4. Note any design patterns or idioms used
5. Format your response with clear sections and bullet points
Be thorough but accessible - explain like teaching a smart colleague.""",
            AIAssistantMode.DEBUG: """You are a senior debugging specialist. Your task is to:
1. Carefully analyze the code for bugs, errors, and potential issues
2. Identify both syntax errors and logical bugs
3. Point out edge cases that may cause failures
4. Provide specific line-by-line fixes with explanations
5. Suggest preventive measures for similar bugs
Format: List each issue with [BUG], [WARNING], or [SUGGESTION] prefixes.""",
            AIAssistantMode.OPTIMIZE: """You are a performance optimization expert. Your task is to:
1. Analyze time complexity and identify bottlenecks
2. Check for memory inefficiencies
3. Suggest algorithmic improvements
4. Recommend language-specific optimizations
5. Provide before/after comparisons with expected improvements
Focus on practical, measurable improvements.""",
            AIAssistantMode.COMPLETE: """You are a code completion assistant. Your task is to:
1. Analyze the partial code and understand the intent
2. Complete the code following existing patterns and style
3. Add appropriate error handling
4. Include type hints/annotations where applicable
5. Add brief inline comments explaining complex logic
Maintain consistency with the existing codebase style.""",
            AIAssistantMode.REFACTOR: """You are a code refactoring master. Your task is to:
1. Apply SOLID principles where appropriate
2. Extract reusable functions/methods
3. Improve naming for clarity
4. Reduce complexity and code duplication (DRY)
5. Add proper error handling and validation
Provide the complete refactored code with explanations for each change.""",
            AIAssistantMode.DOCUMENT: """You are a documentation specialist. Your task is to:
1. Generate comprehensive docstrings/JSDoc/comments
2. Document parameters, return values, and exceptions
3. Include usage examples
4. Add type information
5. Note any important caveats or limitations
Follow the standard documentation format for the language.""",
            AIAssistantMode.TEST_GEN: """You are a test engineering expert. Your task is to:
1. Generate comprehensive unit tests
2. Cover edge cases and boundary conditions
3. Include positive and negative test cases
4. Add tests for error handling
5. Use appropriate mocking where needed
Follow testing best practices (AAA pattern: Arrange, Act, Assert).""",
            AIAssistantMode.SECURITY_AUDIT: """You are a cybersecurity auditor. Your task is to:
1. Identify security vulnerabilities (OWASP Top 10)
2. Check for injection risks (SQL, XSS, Command)
3. Review authentication/authorization issues
4. Identify data exposure risks
5. Suggest secure coding fixes
Rate each finding: [CRITICAL], [HIGH], [MEDIUM], [LOW].""",
            AIAssistantMode.CONVERT: """You are a polyglot programming expert. Your task is to:
1. Convert the code to the target language explicitly specified in the user request
2. Use idiomatic patterns for the target language
3. Preserve the original logic and functionality
4. Add type annotations appropriate to the target language
5. Include comments explaining language-specific differences
Ensure the converted code is production-ready.""",
            AIAssistantMode.TEACH: """You are a patient programming instructor. Your task is to:
1. Explain the code concepts for a complete beginner
2. Define any jargon or technical terms
3. Use simple analogies to explain complex concepts
4. Provide step-by-step walkthroughs
5. Suggest resources for further learning
Be encouraging and supportive in your explanations.""",
            AIAssistantMode.REVIEW: """You are a senior code reviewer. Your task is to:
1. Evaluate code quality and best practices
2. Check for consistency with style guides
3. Identify potential bugs or issues
4. Suggest improvements with rationale
5. Highlight what's done well (positive feedback)
Be constructive and specific with all feedback.""",
            AIAssistantMode.ARCHITECTURE: """You are a software architect. Your task is to:
1. Analyze the overall code structure
2. Suggest architectural improvements
3. Identify scalability concerns
4. Recommend design patterns to apply
5. Propose a roadmap for improvements
Consider maintainability, testability, and extensibility.""",
        }
        policies = {
            mode: InstructionPolicy(
                policy_id="backend.ai-assistant." + str(mode.value),
                version="1",
                instructions=text,
            )
            for mode, text in prompts.items()
        }
        policy = policies.get(
            request.mode,
            policies[AIAssistantMode.EXPLAIN],
        )

        language = request.language.value
        target_language = getattr(request.target_language, "value", None)
        user_message = f"""Language: {language}
Target language: {target_language or 'not-applicable'}

Code:
```{language}
{request.code}
```

{f'Additional Context: {request.context}' if request.context else ''}

Please provide a detailed, well-structured response."""

        identity = hashlib.sha256(
            (
                str(request.mode.value)
                + "\n"
                + language
                + "\n"
                + str(target_language or "")
                + "\n"
                + request.code
                + "\n"
                + str(request.context or "")
            ).encode("utf-8")
        ).hexdigest()

        try:
            chat = EngineChat(
                session_id="legacy-ai-assistant:" + identity,
                instruction_policy=policy,
                actor_id="legacy-ai-assistant",
                capability="assistant.compat",
                engine_executor=self._engine_executor,
            ).with_max_tokens(8_192)
            response = await chat.send_message(
                UserMessage(text=user_message)
            )
            suggestion = response.text
            code_blocks = [
                {"language": match[0] or language, "code": match[1].strip()}
                for match in re.findall(r"```(\w+)?\n(.*?)```", suggestion, re.DOTALL)
            ]
            return AIAssistResponse(
                mode=request.mode,
                suggestion=suggestion,
                code_blocks=code_blocks,
                confidence=0.92,
                model=self.model,
            )
        except EngineTextError as exc:
            logger.warning(
                "AI Assistant engine unavailable or failed: %s",
                exc.__class__.__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="AI service unavailable",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("AI Assistant provider boundary failed")
            raise HTTPException(status_code=500, detail="AI service error") from exc


# AIAssistantService instantiation (executor_factory remains in server.py shim)
ai_service = AIAssistantService()


__all__ = ["AIAssistantService", "ai_service"]
