"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CODEDOCK IMAGE GENERATION PIPELINE v11.0.0                 ║
║                                                                               ║
║  Multi-Provider Image Generation System                                       ║
║  - OpenAI gpt-image-1                                                         ║
║  - Gemini Nano Banana                                                         ║
║  - Grok Imagine API                                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import uuid
import base64
import asyncio
import os

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

router = APIRouter(prefix="/imagine", tags=["Image Generation"])

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ── Style presets for one-tap, on-brand cover/key-art generation ──────────────
STYLE_PRESETS = {
    "photoreal":    {"label": "Photoreal",     "suffix": "photorealistic, ultra-detailed, cinematic lighting, 4k, sharp focus"},
    "anime":        {"label": "Anime",         "suffix": "anime key visual, vibrant cel shading, dynamic composition, studio quality"},
    "pixel":        {"label": "Pixel Art",     "suffix": "detailed pixel art, retro 16-bit game aesthetic, crisp pixels, vivid palette"},
    "oil_painting": {"label": "Oil Painting",  "suffix": "classical oil painting, rich brush strokes, dramatic chiaroscuro lighting"},
    "cyberpunk":    {"label": "Cyberpunk",     "suffix": "neon cyberpunk, rain-slicked streets, holographic glow, moody atmosphere"},
    "watercolor":   {"label": "Watercolor",    "suffix": "soft watercolor wash, dreamy gradients, hand-painted texture"},
    "comic":        {"label": "Comic",         "suffix": "bold comic book ink, halftone shading, high-contrast dramatic panel"},
    "lowpoly":      {"label": "Low Poly",      "suffix": "stylized low-poly 3D render, flat faceted shapes, soft studio lighting"},
    "fantasy":      {"label": "Epic Fantasy",  "suffix": "epic fantasy concept art, sweeping vista, volumetric god rays, painterly"},
    "noir":         {"label": "Noir",          "suffix": "high-contrast black and white noir, deep shadows, film grain, moody"},
}


def _cache_db():
    from core.databases import client as _MONGO
    return _MONGO[os.environ.get("DB_NAME", "test_database")]


def _cache_key(prompt: str, size: str, provider: str) -> str:
    import hashlib
    return hashlib.sha256(f"{provider}|{size}|{prompt}".encode("utf-8")).hexdigest()


async def _cache_get(key: str) -> Optional[dict]:
    try:
        doc = await _cache_db().image_cache.find_one({"_id": key}, {"_id": 0, "image": 1, "meta": 1})
        return doc
    except Exception:
        return None


async def _cache_put(key: str, image_b64: str, meta: dict) -> None:
    try:
        await _cache_db().image_cache.update_one(
            {"_id": key},
            {"$set": {"image": image_b64, "meta": meta,
                      "created_at": datetime.utcnow().isoformat()}},
            upsert=True)
    except Exception:
        pass


def _apply_preset(prompt: str, style_preset: Optional[str]) -> str:
    p = STYLE_PRESETS.get((style_preset or "").lower())
    return f"{prompt}, {p['suffix']}" if p else prompt

# ============================================================================
# REQUEST MODELS
# ============================================================================

class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=4000, description="Image description")
    provider: Literal["auto", "openai", "gemini", "grok"] = "auto"
    style: Optional[str] = Field(None, description="Art style (realistic, cartoon, anime, etc.)")
    size: Literal["256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"] = "1024x1024"
    quality: Literal["standard", "hd"] = "standard"
    count: int = Field(1, ge=1, le=4, description="Number of images to generate")
    negative_prompt: Optional[str] = Field(None, description="What to avoid in the image")
    style_preset: Optional[str] = Field(None, description="One-tap style preset id (photoreal, anime, pixel, …)")
    use_cache: bool = Field(True, description="Reuse a cached image for identical prompt+size+provider")

class ImageVariationRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded source image")
    prompt: Optional[str] = Field(None, description="Variation guidance")
    provider: Literal["openai", "gemini"] = "openai"
    count: int = Field(1, ge=1, le=4)

class ImageEditRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded source image")
    mask_base64: Optional[str] = Field(None, description="Base64 encoded mask (transparent areas will be edited)")
    prompt: str = Field(..., description="What to add/change")
    provider: Literal["openai", "gemini"] = "openai"

# ============================================================================
# PROVIDER IMPLEMENTATIONS
# ============================================================================

async def generate_with_openai(prompt: str, size: str, quality: str, count: int) -> dict:
    """Generate images using OpenAI gpt-image-1"""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY)
        
        response = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            n=count,
            response_format="b64_json"
        )
        
        images = []
        for img_data in response.data:
            images.append({
                "data": img_data.b64_json,
                "format": "base64_png",
                "revised_prompt": getattr(img_data, 'revised_prompt', prompt)
            })
        
        return {
            "provider": "openai",
            "model": "gpt-image-1",
            "images": images,
            "status": "success"
        }
    except Exception as e:
        return {"provider": "openai", "error": str(e), "status": "failed"}

async def generate_with_gemini(prompt: str, style: Optional[str] = None) -> dict:
    """Generate REAL images using Gemini Nano Banana (gemini-3.1-flash-image-preview)
    via the Emergent universal key + emergentintegrations multimodal response."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        full_prompt = f"{prompt}. Style: {style}." if style else prompt

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"nano-banana-{uuid.uuid4().hex[:8]}",
            system_message="You are an expert visual artist that generates striking, detailed images.",
        ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])

        text, images = await chat.send_message_multimodal_response(
            UserMessage(text=full_prompt)
        )

        out_images = []
        for img in (images or []):
            data = img.get("data") if isinstance(img, dict) else None
            if data:
                out_images.append({
                    "data": data,
                    "format": "base64_png",
                    "mime_type": img.get("mime_type", "image/png"),
                })

        if out_images:
            return {
                "provider": "gemini",
                "model": "nano-banana/gemini-3.1-flash-image-preview",
                "images": out_images,
                "status": "success",
            }
        # No image came back — surface as failed so callers can fall back.
        return {"provider": "gemini", "status": "failed",
                "error": "no image returned", "note": (text or "")[:200]}
    except Exception as e:
        return {"provider": "gemini", "error": str(e), "status": "failed"}

async def generate_with_grok(prompt: str, style: Optional[str] = None) -> dict:
    """Generate images using Grok Imagine API"""
    try:
        from openai import AsyncOpenAI
        
        # Grok via xAI API
        client = AsyncOpenAI(
            api_key=EMERGENT_LLM_KEY,
            base_url="https://api.x.ai/v1"
        )
        
        full_prompt = f"{prompt}\n\nStyle: {style}" if style else prompt
        
        # Grok Imagine endpoint
        response = await client.images.generate(
            model="grok-2-vision-1212",  # Grok's image model
            prompt=full_prompt,
            n=1,
            response_format="b64_json"
        )
        
        images = []
        for img_data in response.data:
            images.append({
                "data": img_data.b64_json,
                "format": "base64_png"
            })
        
        return {
            "provider": "grok",
            "model": "grok-imagine",
            "images": images,
            "status": "success"
        }
    except Exception as e:
        # Fallback: Use Grok for prompt enhancement, then OpenAI for generation
        try:
            from openai import AsyncOpenAI
            xai_client = AsyncOpenAI(
                api_key=EMERGENT_LLM_KEY,
                base_url="https://api.x.ai/v1"
            )
            
            # Get Grok to enhance the prompt
            chat_response = await xai_client.chat.completions.create(
                model="grok-beta",
                messages=[
                    {"role": "system", "content": "You are Grok. Create vivid, detailed image prompts."},
                    {"role": "user", "content": f"Create a detailed image generation prompt for: {prompt}"}
                ]
            )
            enhanced = chat_response.choices[0].message.content
            
            # Generate with OpenAI using Grok's enhanced prompt
            openai_result = await generate_with_openai(enhanced, "1024x1024", "standard", 1)
            if openai_result.get("status") == "success":
                openai_result["provider"] = "grok+openai"
                openai_result["grok_enhanced_prompt"] = enhanced
                return openai_result
                
        except Exception:
            pass
            
        return {"provider": "grok", "error": str(e), "status": "failed"}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_imagine_info():
    """Get image generation pipeline information"""
    return {
        "name": "CodeDock Imagine Pipeline",
        "version": "11.0.0",
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI gpt-image-1",
                "capabilities": ["generation", "variation", "editing"],
                "sizes": ["256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"],
                "quality": ["standard", "hd"],
                "status": "active"
            },
            {
                "id": "gemini",
                "name": "Gemini Nano Banana",
                "capabilities": ["generation", "prompt_enhancement"],
                "sizes": ["1024x1024"],
                "status": "active"
            },
            {
                "id": "grok",
                "name": "Grok Imagine",
                "capabilities": ["generation", "prompt_enhancement"],
                "sizes": ["1024x1024"],
                "status": "active"
            }
        ],
        "styles": [
            "realistic", "photorealistic", "cartoon", "anime", "watercolor",
            "oil_painting", "digital_art", "3d_render", "pixel_art", "sketch",
            "cyberpunk", "fantasy", "sci-fi", "minimalist", "abstract"
        ],
        "max_prompt_length": 4000,
        "max_images_per_request": 4
    }

@router.post("/generate")
async def generate_images(request: ImageGenerationRequest):
    """Generate images from text prompt"""
    request_id = str(uuid.uuid4())
    
    # Build full prompt with style + optional one-tap preset
    full_prompt = request.prompt
    if request.style:
        full_prompt = f"{request.prompt}, {request.style} style"
    full_prompt = _apply_preset(full_prompt, request.style_preset)
    if request.negative_prompt:
        full_prompt += f". Avoid: {request.negative_prompt}"

    # ── Cache: reuse an identical prior render to save tokens ──
    ckey = _cache_key(full_prompt, request.size, request.provider)
    if request.use_cache:
        hit = await _cache_get(ckey)
        if hit and hit.get("image"):
            return {"id": request_id, "status": "success", "cached": True,
                    "provider": (hit.get("meta") or {}).get("provider"),
                    "model": (hit.get("meta") or {}).get("model"),
                    "images": [{"data": hit["image"], "format": "base64_png"}],
                    "prompt": request.prompt, "full_prompt": full_prompt,
                    "parameters": {"size": request.size, "quality": request.quality,
                                   "style": request.style, "style_preset": request.style_preset},
                    "timestamp": datetime.utcnow().isoformat()}

    # Auto-select provider or use specified
    if request.provider == "auto":
        # Gemini Nano Banana + OpenAI gpt-image-1 both work on the Emergent key.
        # (Grok needs a separate xAI key, so it's excluded from the auto chain.)
        result = await generate_with_gemini(full_prompt, request.style)
        if result.get("status") == "failed":
            result = await generate_with_openai(full_prompt, request.size, request.quality, request.count)
    elif request.provider == "openai":
        result = await generate_with_openai(full_prompt, request.size, request.quality, request.count)
    elif request.provider == "gemini":
        result = await generate_with_gemini(full_prompt, request.style)
    elif request.provider == "grok":
        result = await generate_with_grok(full_prompt, request.style)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # Persist successful renders to the image cache for instant reuse.
    imgs = result.get("images", []) if isinstance(result, dict) else []
    if result.get("status") == "success" and imgs and imgs[0].get("data"):
        await _cache_put(ckey, imgs[0]["data"],
                         {"provider": result.get("provider"), "model": result.get("model")})

    return {
        "id": request_id,
        "status": result.get("status", "unknown"),
        "cached": False,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "images": result.get("images", []),
        "prompt": request.prompt,
        "full_prompt": full_prompt,
        "parameters": {
            "size": request.size,
            "quality": request.quality,
            "style": request.style,
            "style_preset": request.style_preset,
        },
        "error": result.get("error"),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/presets")
async def list_style_presets():
    """List one-tap style presets for cover/key-art generation."""
    return {"presets": [{"id": k, "label": v["label"]} for k, v in STYLE_PRESETS.items()]}


class CoverRequest(BaseModel):
    pid: Optional[str] = None
    title: str = "Your Game"
    genre: Optional[str] = ""
    lore: Optional[str] = ""
    style: Optional[str] = "epic cinematic key art, dramatic lighting, highly detailed, 4k"
    style_preset: Optional[str] = None      # one-tap preset id (photoreal, anime, …)
    regenerate: bool = False                # bypass cache to mint a fresh variant


@router.post("/cover")
async def generate_cover(request: CoverRequest):
    """🖼️ Generate a cinematic cover/key-art for a game (Nano Banana, OpenAI fallback)
    and, when a pid is given, store it on the build for the gallery/marketplace/trailer.
    Supports one-tap style presets, caching, and forced regeneration."""
    bits = [f"Video game cover key art for '{request.title}'"]
    if request.genre:
        bits.append(f"genre: {request.genre}")
    if request.lore:
        bits.append(str(request.lore)[:300])
    prompt = ". ".join(bits) + ". No text, no watermark, vertical poster composition."
    full_prompt = f"{prompt}, {request.style}" if request.style else prompt
    full_prompt = _apply_preset(full_prompt, request.style_preset)

    # Cache (skip when regenerate=True so users can roll a fresh variant).
    ckey = _cache_key(full_prompt, "1024x1792", "cover")
    result = None
    if not request.regenerate:
        hit = await _cache_get(ckey)
        if hit and hit.get("image"):
            result = {"status": "success", "cached": True,
                      "provider": (hit.get("meta") or {}).get("provider"),
                      "model": (hit.get("meta") or {}).get("model"),
                      "images": [{"data": hit["image"], "format": "base64_png"}]}

    if result is None:
        result = await generate_with_gemini(full_prompt, request.style)
        if result.get("status") == "failed":
            result = await generate_with_openai(full_prompt, "1024x1792", "hd", 1)

    images = result.get("images", []) if isinstance(result, dict) else []
    cover_b64 = None
    if images:
        first = images[0]
        cover_b64 = first.get("data") or first.get("b64_json") or first.get("image_base64") or first.get("url")

    # Cache fresh renders for instant reuse.
    if cover_b64 and not result.get("cached"):
        await _cache_put(ckey, cover_b64,
                         {"provider": result.get("provider"), "model": result.get("model")})

    stored = False
    if request.pid and cover_b64:
        try:
            db = _cache_db()
            await db.playables.update_one(
                {"playable_id": request.pid},
                {"$set": {"cover_image": cover_b64, "cover_updated_at": datetime.utcnow().isoformat()}})
            stored = True
        except Exception:
            pass
    return {
        "status": result.get("status", "unknown"), "provider": result.get("provider"),
        "model": result.get("model"), "pid": request.pid, "stored": stored,
        "cached": bool(result.get("cached")), "style_preset": request.style_preset,
        "title": request.title, "images": images, "prompt": prompt,
        "error": result.get("error"),
    }

@router.post("/variation")
async def create_variation(request: ImageVariationRequest):
    """Create variations of an existing image"""
    request_id = str(uuid.uuid4())
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY)
        
        # Decode base64 image
        image_bytes = base64.b64decode(request.image_base64)
        
        response = await client.images.create_variation(
            image=image_bytes,
            n=request.count,
            size="1024x1024",
            response_format="b64_json"
        )
        
        variations = []
        for img_data in response.data:
            variations.append({
                "data": img_data.b64_json,
                "format": "base64_png"
            })
        
        return {
            "id": request_id,
            "status": "success",
            "provider": "openai",
            "variations": variations,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/edit")
async def edit_image(request: ImageEditRequest):
    """Edit an image with a mask and prompt"""
    request_id = str(uuid.uuid4())
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY)
        
        image_bytes = base64.b64decode(request.image_base64)
        mask_bytes = base64.b64decode(request.mask_base64) if request.mask_base64 else None
        
        kwargs = {
            "image": image_bytes,
            "prompt": request.prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json"
        }
        if mask_bytes:
            kwargs["mask"] = mask_bytes
        
        response = await client.images.edit(**kwargs)
        
        return {
            "id": request_id,
            "status": "success",
            "provider": "openai",
            "edited_image": {
                "data": response.data[0].b64_json,
                "format": "base64_png"
            },
            "prompt": request.prompt,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/enhance-prompt")
async def enhance_prompt(prompt: str, style: Optional[str] = None, provider: str = "grok"):
    """Enhance a prompt for better image generation"""
    request_id = str(uuid.uuid4())
    
    enhancement_prompt = f"""Create an enhanced, detailed image generation prompt based on:

Original: {prompt}
{f'Style: {style}' if style else ''}

Create a vivid, specific prompt that includes:
1. Main subject with precise details
2. Composition and framing
3. Lighting and atmosphere
4. Color palette
5. Background elements
6. Mood and emotion
7. Technical aspects (depth of field, angle, etc.)

Output only the enhanced prompt, no explanations."""

    try:
        if provider == "grok":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY, base_url="https://api.x.ai/v1")
            response = await client.chat.completions.create(
                model="grok-beta",
                messages=[
                    {"role": "system", "content": "You are an expert at creating detailed image prompts."},
                    {"role": "user", "content": enhancement_prompt}
                ]
            )
            enhanced = response.choices[0].message.content
        else:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"enhance-{uuid.uuid4().hex[:8]}",
                system_message="You are an expert at creating detailed image prompts."
            ).with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=enhancement_prompt))
            enhanced = response.content if hasattr(response, 'content') else str(response)
        
        return {
            "id": request_id,
            "original_prompt": prompt,
            "enhanced_prompt": enhanced,
            "style": style,
            "provider": provider,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
