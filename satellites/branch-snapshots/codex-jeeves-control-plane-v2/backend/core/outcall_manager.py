import os
import json
import base64
import uuid
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

class OutcallManager:
    """
    Centralized Outcall Manager (VEE Synergy Node)
    Internalizes all external API calls (AI, Images, Audio, Deployments, GitHub)
    Defaults to INTERNAL generation via the Hyperscale Rosetta Database.
    OUTCALL_MODE="EMERGENCY" allows real external network calls.
    """
    
    def __init__(self):
        self.mode = os.environ.get("OUTCALL_MODE", "INTERNAL").upper()
        self.db_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
        self.db = self.db_client[os.environ.get("DB_NAME", "codedock")]
    
    def is_internal(self) -> bool:
        return self.mode != "EMERGENCY"

    async def _fetch_rosetta_wisdom(self, count=1) -> list:
        try:
            cursor = self.db.rosetta_stone.aggregate([{"$sample": {"size": count}}])
            return await cursor.to_list(count)
        except Exception as e:
            print("DB Fetch Error:", e)
            return [{"concept": "Synthesized Polyglot Matrix", "language": "System", "code": "System.out.println('Fallback');"}]

    async def generate_text(self, prompt: str, system_message: str = "") -> str:
        if not self.is_internal():
            return None # Force fallback to real API
            
        # VEE Synthesis
        wisdom = await self._fetch_rosetta_wisdom(3)
        
        snippets = []
        for w in wisdom:
            concept = w.get('concept', 'Unknown')
            lang = w.get('language', 'Polyglot')
            code = w.get('code', '...')
            snippets.append(f"""### {concept} ({lang})
```
{code}
```""")
        
        synthesized_knowledge = "\n".join(snippets)
        
        vee_msg = f"""[VEE SYNTHESIZED RESPONSE]
Based on the prompt: '{prompt[:150]}...', the Agent Swarm has intercepted this outcall to preserve tokens and maximize offline resilience.

**Hyperscale Knowledge Retrieved:**
{synthesized_knowledge}

*Note: This response was generated internally via the Rosetta Stone repository (1.3M+ entries) to bypass external API limits. To use external LLMs, set OUTCALL_MODE=EMERGENCY.*"""

        if "{" in system_message or "{" in prompt or "json" in system_message.lower():
            import json
            return json.dumps({
                "name": "VEE Agent",
                "title": "Synthesized Polyglot Entity",
                "description": "A highly advanced AI agent born from 1.3M+ Rosetta snippets.",
                "traits": ["genius", "efficient", "offline"],
                "content": vee_msg,
                "message": vee_msg,
                "response": vee_msg,
                "items": [],
                "tasks": [],
                "quests": [],
                "test_cases": [],
                "bug_report": vee_msg,
                "performance_tests": [],
                "test_suite": []
            })
            
        return vee_msg

    async def generate_image(self, prompt: str) -> dict:
        if not self.is_internal():
            return None
        
        # Return a tiny valid 1x1 transparent PNG base64
        tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        
        return {
            "provider": "vee_simulated",
            "data": tiny_png,
            "format": "base64",
            "size": "1024x1024",
            "message": f"Simulated Image for prompt: {prompt[:30]}..."
        }

    async def generate_tts(self, text: str) -> bytes:
        if not self.is_internal():
            return None
        
        # A tiny valid WAV file header with silence
        import base64
        tiny_wav = base64.b64decode("UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=")
        return tiny_wav

    async def push_github(self, repo: str, files: dict) -> dict:
        if not self.is_internal():
            return None
            
        return {
            "status": "success",
            "repo": repo,
            "commit_sha": uuid.uuid4().hex,
            "message": f"[VEE SIMULATED] Successfully simulated a commit of {len(files)} files to {repo} internally."
        }

outcalls = OutcallManager()
