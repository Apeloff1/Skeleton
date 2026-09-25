"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CODEDOCK AI PIPELINE SYSTEM v11.0.0                     ║
║                                                                            ║
║  Complete Text-to-Asset Pipeline with Multi-Provider AI                    ║
║  - OpenAI GPT-4o & gpt-image-1                                             ║
║  - Gemini Nano Banana                                                       ║
║  - Grok Imagine API                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from enum import Enum
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.engine_text import EngineTextError, EngineTextRequest, execute_engine_text


ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

log = logging.getLogger("codedock.ai_pipeline")
router = APIRouter(prefix="/pipeline", tags=["AI Pipeline"])

class AIProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    GROK = "grok"
    AUTO = "auto"


class PipelineType(str, Enum):
    TEXT_TO_CODE = "text_to_code"
    TEXT_TO_IMAGE = "text_to_image"
    CODE_TO_EXPLANATION = "code_to_explanation"
    CODE_TO_TESTS = "code_to_tests"
    CODE_TO_DOCS = "code_to_docs"
    CODE_TO_APP = "code_to_app"
    CODE_TO_GAME = "code_to_game"
    REFACTOR = "refactor"
    DEBUG = "debug"
    OPTIMIZE = "optimize"


class TextToCodeRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=5000)
    language: str = Field("python", min_length=1, max_length=100)
    framework: Optional[str] = Field(None, max_length=100)
    requirements: Optional[List[str]] = Field(default_factory=list, max_length=50)
    context: Optional[str] = Field(None, max_length=100000)
    provider: AIProvider = AIProvider.AUTO


class TextToImageRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=2000)
    provider: AIProvider = AIProvider.AUTO
    style: Optional[str] = None
    size: str = "1024x1024"
    quality: str = "standard"
    count: int = Field(1, ge=1, le=4)


class CodeToAppRequest(BaseModel):
    code: str = Field(..., min_length=10, max_length=500000)
    language: str = Field("python", min_length=1, max_length=100)
    app_type: Literal["cli", "web", "api", "mobile", "game", "desktop"] = "web"
    target_platform: Optional[str] = Field(None, max_length=100)
    include_tests: bool = True
    include_docs: bool = True
    include_deployment: bool = True


class CodeAnalysisRequest(BaseModel):
    code: str = Field(..., min_length=10, max_length=500000)
    analysis_type: Literal["explain", "test", "document", "debug", "optimize", "refactor"] = "explain"
    language: str = Field("python", min_length=1, max_length=100)
    detail_level: Literal["brief", "standard", "comprehensive"] = "standard"


class PipelineResponse(BaseModel):
    id: str
    pipeline_type: str
    status: str
    result: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: str


def _pipeline_http_error(operation: str, exc: Exception) -> HTTPException:
    """Create a stable public failure without exposing provider/library details."""
    log.warning("AI pipeline %s failed: %s", operation, type(exc).__name__)
    return HTTPException(status_code=500, detail="AI pipeline request failed")


async def call_gpt4o(
    prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Generate text through the canonical Skeleton engine boundary."""

    default_system = (
        "You are an expert programmer and software architect. Provide helpful, "
        "accurate, and well-documented code and explanations."
    )
    instructions = system_prompt or default_system
    material = hashlib.sha256(
        (instructions + "\n" + prompt).encode("utf-8")
    ).hexdigest()
    try:
        response = await execute_engine_text(
            EngineTextRequest(
                instructions=instructions,
                prompt=prompt,
                idempotency_key="ai-pipeline:" + material,
                actor_id="ai-pipeline",
                capability="assistant.compat",
                verification_profile="assistant_proposal",
                max_output_tokens=max_tokens,
                purpose="ai-pipeline-text-generation",
            )
        )
        return response.text
    except EngineTextError as exc:
        log.warning("AI pipeline text engine failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="AI text generation failed",
        ) from None


async def generate_image_openai(prompt: str, size: str = "1024x1024") -> Dict[str, Any]:
    """Generate an image while keeping upstream error text behind the API boundary."""
    from routes.image_generation import generate_with_gemini, generate_with_openai

    try:
        result = await generate_with_gemini(prompt)
        if result.get("status") == "failed":
            result = await generate_with_openai(prompt, size, "standard", 1)
        imgs = result.get("images", []) if isinstance(result, dict) else []
        if imgs and imgs[0].get("data"):
            return {
                "provider": result.get("provider"),
                "model": result.get("model"),
                "data": imgs[0]["data"],
                "format": "base64",
                "size": size,
            }
        return {
            "error": "image generation failed",
            "provider": result.get("provider") if isinstance(result, dict) else "openai",
        }
    except Exception as exc:
        log.warning("AI pipeline image provider failed: %s", type(exc).__name__)
        return {"error": "image generation failed", "provider": "openai"}


async def generate_image_gemini(prompt: str) -> Dict[str, Any]:
    """Generate an image without forwarding Gemini failure payloads."""
    from routes.image_generation import generate_with_gemini

    try:
        result = await generate_with_gemini(prompt)
        imgs = result.get("images", []) if isinstance(result, dict) else []
        if imgs and imgs[0].get("data"):
            return {
                "provider": "gemini",
                "model": result.get("model"),
                "data": imgs[0]["data"],
                "format": "base64",
            }
        return {"error": "image generation failed", "provider": "gemini"}
    except Exception as exc:
        log.warning("AI pipeline Gemini image provider failed: %s", type(exc).__name__)
        return {"error": "image generation failed", "provider": "gemini"}


async def call_grok(prompt: str, task_type: str = "general") -> str:
    """Reject undeclared Grok execution instead of borrowing another provider key."""
    del prompt, task_type
    raise HTTPException(
        status_code=409,
        detail="Grok is not declared by the active AI construction contract",
    )



@router.get("/info")
async def get_pipeline_info():
    """Get information about the AI Pipeline system."""
    return {
        "name": "CodeDock AI Pipeline",
        "version": "11.0.0",
        "providers": [
            {"id": "openai", "name": "OpenAI GPT-4o & gpt-image-1", "status": "active"},
            {"id": "gemini", "name": "Gemini 2.0 Flash & Nano Banana", "status": "undeclared"},
            {"id": "grok", "name": "xAI Grok Imagine", "status": "undeclared"},
        ],
        "pipelines": [
            {"id": "text_to_code", "name": "Text → Code", "description": "Generate code from natural language"},
            {"id": "text_to_image", "name": "Text → Image", "description": "Generate images from descriptions"},
            {"id": "code_to_explanation", "name": "Code → Explanation", "description": "Explain code in detail"},
            {"id": "code_to_tests", "name": "Code → Tests", "description": "Generate unit tests"},
            {"id": "code_to_docs", "name": "Code → Documentation", "description": "Generate documentation"},
            {"id": "code_to_app", "name": "Code → App", "description": "Build complete applications"},
            {"id": "code_to_game", "name": "Code → Game", "description": "Build games from descriptions"},
            {"id": "refactor", "name": "Refactor", "description": "Improve code structure"},
            {"id": "debug", "name": "Debug", "description": "Find and fix bugs"},
            {"id": "optimize", "name": "Optimize", "description": "Optimize performance"},
        ],
        "capabilities": {
            "max_code_length": 50000,
            "max_prompt_length": 5000,
            "supported_languages": 64,
            "image_sizes": ["256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"],
        },
    }


@router.post("/text-to-code", response_model=PipelineResponse)
async def text_to_code(request: TextToCodeRequest):
    """Generate code from a natural-language description."""
    request_id = str(uuid.uuid4())
    system_prompt = f"""You are an expert {request.language} developer. Generate production-ready code.

Requirements:
- Clean, readable, well-documented code
- Follow best practices and design patterns
- Include error handling
- Add type hints where applicable
- Include docstrings

{f'Framework: {request.framework}' if request.framework else ''}
{f'Additional requirements: {", ".join(request.requirements)}' if request.requirements else ''}"""
    user_prompt = f"""Generate {request.language} code for:

{request.description}

{f'Context: {request.context}' if request.context else ''}

Provide complete, working code with explanations."""

    try:
        if request.provider == AIProvider.GROK:
            code = await call_grok(user_prompt, "code")
        else:
            code = await call_gpt4o(user_prompt, system_prompt)
        return PipelineResponse(
            id=request_id,
            pipeline_type="text_to_code",
            status="success",
            result={"code": code, "language": request.language, "framework": request.framework},
            metadata={
                "provider": "openai",
                "requested_provider": request.provider.value,
                "tokens_estimated": len(code.split()) * 1.3,
            },
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _pipeline_http_error("text-to-code", exc) from None


@router.post("/text-to-image", response_model=PipelineResponse)
async def text_to_image(request: TextToImageRequest):
    """Generate images from text descriptions."""
    request_id = str(uuid.uuid4())
    enhanced_prompt = request.prompt
    if request.style:
        enhanced_prompt = f"{request.prompt}, in {request.style} style"

    try:
        images: list[dict[str, Any]] = []
        if request.provider in [AIProvider.OPENAI, AIProvider.AUTO]:
            for _ in range(request.count):
                img = await generate_image_openai(enhanced_prompt, request.size)
                if "error" not in img:
                    images.append(img)
        if request.provider == AIProvider.GEMINI or (
            request.provider == AIProvider.AUTO and not images
        ):
            gemini_result = await generate_image_gemini(enhanced_prompt)
            if "error" not in gemini_result:
                images.append(gemini_result)

        return PipelineResponse(
            id=request_id,
            pipeline_type="text_to_image",
            status="success" if images else "partial",
            result={"images": images, "count": len(images), "prompt": enhanced_prompt},
            metadata={
                "provider": request.provider.value,
                "size": request.size,
                "style": request.style,
            },
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _pipeline_http_error("text-to-image", exc) from None


@router.post("/code-to-app", response_model=PipelineResponse)
async def code_to_app(request: CodeToAppRequest):
    """Transform code into a complete application package."""
    request_id = str(uuid.uuid4())
    app_prompt = f"""Transform this {request.language} code into a complete {request.app_type} application:

```{request.language}
{request.code}
```

Generate a complete application package including:
1. Main application code (refactored and production-ready)
2. Project structure with all necessary files
3. Configuration files (package.json, requirements.txt, etc.)
4. {'Unit tests' if request.include_tests else ''}
5. {'Documentation (README.md, API docs)' if request.include_docs else ''}
6. {'Deployment configuration (Docker, CI/CD)' if request.include_deployment else ''}

Target platform: {request.target_platform or 'cross-platform'}

Provide the complete package with all files and their contents."""

    try:
        result = await call_gpt4o(app_prompt)
        return PipelineResponse(
            id=request_id,
            pipeline_type="code_to_app",
            status="success",
            result={
                "package": result,
                "app_type": request.app_type,
                "language": request.language,
                "features": {
                    "tests": request.include_tests,
                    "docs": request.include_docs,
                    "deployment": request.include_deployment,
                },
            },
            metadata={"provider": "openai", "platform": request.target_platform},
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _pipeline_http_error("code-to-app", exc) from None


@router.post("/code-to-game", response_model=PipelineResponse)
async def code_to_game(request: CodeToAppRequest):
    """Transform code or a description into a complete game."""
    request_id = str(uuid.uuid4())
    game_prompt = f"""Create a complete game based on this code/description:

```{request.language}
{request.code}
```

Generate a fully playable game including:
1. Game logic and mechanics
2. Player controls and input handling
3. Graphics/rendering code (or ASCII art for terminal games)
4. Sound effects placeholders
5. Score system
6. Game states (menu, playing, paused, game over)
7. Complete project structure

Make it fun, engaging, and polished!"""

    try:
        result = await call_gpt4o(game_prompt)
        return PipelineResponse(
            id=request_id,
            pipeline_type="code_to_game",
            status="success",
            result={
                "game": result,
                "type": request.app_type,
                "language": request.language,
            },
            metadata={"provider": "openai", "game_type": "inferred"},
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _pipeline_http_error("code-to-game", exc) from None


@router.post("/analyze", response_model=PipelineResponse)
async def analyze_code(request: CodeAnalysisRequest):
    """Analyze code: explain, test, document, debug, optimize, or refactor."""
    request_id = str(uuid.uuid4())
    analysis_prompts = {
        "explain": f"""Explain this {request.language} code in detail:

```{request.language}
{request.code}
```

Provide {'a brief overview' if request.detail_level == 'brief' else 'a comprehensive explanation including' if request.detail_level == 'comprehensive' else 'an explanation of'}:
- What the code does
- How it works step by step
- Key concepts used
- Potential improvements""",
        "test": f"""Generate comprehensive unit tests for this {request.language} code:

```{request.language}
{request.code}
```

Include:
- Unit tests for all functions/methods
- Edge cases and boundary conditions
- Mock objects where needed
- Test documentation""",
        "document": f"""Generate complete documentation for this {request.language} code:

```{request.language}
{request.code}
```

Include:
- Module/class docstrings
- Function/method documentation
- Parameter descriptions
- Return value documentation
- Usage examples
- README content""",
        "debug": f"""Debug this {request.language} code and identify all issues:

```{request.language}
{request.code}
```

Provide:
- List of bugs/issues found
- Root cause analysis
- Step-by-step fixes
- Corrected code""",
        "optimize": f"""Optimize this {request.language} code for performance:

```{request.language}
{request.code}
```

Analyze and improve:
- Time complexity
- Space complexity
- Memory usage
- Code efficiency
- Provide optimized version with explanations""",
        "refactor": f"""Refactor this {request.language} code for better structure:

```{request.language}
{request.code}
```

Apply:
- SOLID principles
- Design patterns where appropriate
- Clean code practices
- Better naming conventions
- Modular structure""",
    }

    try:
        prompt = analysis_prompts.get(request.analysis_type, analysis_prompts["explain"])
        result = await call_gpt4o(prompt)
        return PipelineResponse(
            id=request_id,
            pipeline_type=f"code_to_{request.analysis_type}",
            status="success",
            result={
                "analysis": result,
                "type": request.analysis_type,
                "language": request.language,
                "detail_level": request.detail_level,
            },
            metadata={"provider": "openai", "code_length": len(request.code)},
            timestamp=datetime.utcnow().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _pipeline_http_error("analyze", exc) from None


@router.get("/providers")
async def get_providers():
    """Get all available AI providers and their capabilities."""
    return {
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI",
                "models": {"text": "gpt-4o", "image": "gpt-image-1"},
                "capabilities": [
                    "text_generation",
                    "image_generation",
                    "code_generation",
                    "analysis",
                ],
                "status": "active",
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "models": {"text": "gemini-2.0-flash", "image": "nano-banana"},
                "capabilities": ["text_generation", "image_generation", "multimodal"],
                "status": "undeclared",
            },
            {
                "id": "grok",
                "name": "xAI Grok",
                "models": {"text": "grok-beta", "image": "grok-imagine"},
                "capabilities": ["text_generation", "image_generation", "reasoning"],
                "status": "undeclared",
            },
        ]
    }
