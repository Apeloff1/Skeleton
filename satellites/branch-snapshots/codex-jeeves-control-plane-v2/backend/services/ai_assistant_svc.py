"""
services/ai_assistant_svc.py — GROK-enhanced AI Assistant service.

Extracted from server.py (Feb 2026 Phase-9). Self-contained except for
``AIAssistantMode`` enum (still in server.py) and ``AIAssistRequest`` /
``AIAssistResponse`` Pydantic models (now in models/code_runtime.py).
Imports lazily to break circular import.

server.py keeps a back-compat shim so ``from server import ai_service``
continues to work.
"""
from __future__ import annotations

import os
import uuid

from fastapi import HTTPException


def _ai_modes():
    """Lazy access to server.AIAssistantMode enum."""
    from server import AIAssistantMode  # noqa: PLC0415
    return AIAssistantMode


def _llm_chat():
    """Lazy import of LlmChat / UserMessage."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: PLC0415
    return LlmChat, UserMessage


# Pydantic request/response shapes
from models.code_runtime import AIAssistRequest, AIAssistResponse  # noqa: E402


AIAssistantMode = _ai_modes()  # eager-resolve at module-load time (server.py already loaded)


class AIAssistantService:
    """
    ============================================================================
    GROK-ENHANCED AI ASSISTANT SERVICE
    Optimized prompts for maximum compatibility with advanced LLMs
    ============================================================================
    """
    def __init__(self):
        self.api_key = os.environ.get('EMERGENT_LLM_KEY')
        self.model = "gpt-4o"
        
    async def assist(self, request: AIAssistRequest) -> AIAssistResponse:
        if not self.api_key:
            raise HTTPException(status_code=503, detail="AI service not configured")
        
        # GROK-ENHANCED PROMPTS: Structured for maximum clarity and detail
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
            
            AIAssistantMode.CONVERT: f"""You are a polyglot programming expert. Your task is to:
1. Convert the code to {request.target_language or 'Python'}
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
        
        try:
            chat = LlmChat(
                api_key=self.api_key,
                session_id=f"codedock-{uuid.uuid4().hex[:8]}",
                system_message=prompts.get(request.mode, prompts[AIAssistantMode.EXPLAIN])
            ).with_model("openai", self.model)
            
            # Enhanced user message with more context
            user_message = f"""Language: {request.language.value}

Code:
```{request.language.value}
{request.code}
```

{f'Additional Context: {request.context}' if request.context else ''}

Please provide a detailed, well-structured response."""
            
            response = await chat.send_message(UserMessage(text=user_message))
            
            code_blocks = []
            for match in re.findall(r'```(\w+)?\n(.*?)```', response, re.DOTALL):
                code_blocks.append({"language": match[0] or request.language.value, "code": match[1].strip()})
            
            return AIAssistResponse(mode=request.mode, suggestion=response, code_blocks=code_blocks, confidence=0.92, model=self.model)
        except Exception as e:
            logger.error(f"AI Assistant error: {e}")
            raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

#====================================================================================================
# AIAssistantService instantiation (executor_factory was left in server.py — see shim)
#====================================================================================================

ai_service = AIAssistantService()


__all__ = ["AIAssistantService", "ai_service"]
