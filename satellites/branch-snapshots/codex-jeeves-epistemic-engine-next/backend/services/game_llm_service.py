from core.databases import client as _SHARED_MONGO_CLIENT
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              GAME LLM SERVICE v15.5 - AI-POWERED GAME GENERATION             ║
║                                                                              ║
║  Centralized LLM service for all game development pipelines:                 ║
║  • NPC Generation & Dialogue                                                 ║
║  • Game Logic & Systems                                                      ║
║  • World Building & Management                                               ║
║  • Animation & VFX                                                           ║
║  • Economy & Monetization                                                    ║
║  • Narrative & Story                                                         ║
║  • Testing & QA                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import uuid
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from core.outcall_manager import outcalls
from loguru import logger

load_dotenv()

# Import emergent integrations
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("emergentintegrations not available - LLM features disabled")


class GameLLMService:
    """
    Centralized LLM service for game development pipelines.
    Provides specialized prompts and generation for various game systems.
    """
    
    def __init__(self, model: str = "gpt-4o", provider: str = "openai"):
        self.api_key = os.getenv("EMERGENT_LLM_KEY", "")
        self.model = model
        self.provider = provider
        self.available = LLM_AVAILABLE and bool(self.api_key)
        
        if not self.available:
            logger.warning("GameLLMService: LLM not available (missing key or library)")
    
    def _create_chat(self, system_message: str, session_id: Optional[str] = None) -> Optional[LlmChat]:
        """Create a new LLM chat instance with the specified system message."""
        if not self.available:
            return None
        
        try:
            chat = LlmChat(
                api_key=self.api_key,
                session_id=session_id or str(uuid.uuid4()),
                system_message=system_message
            ).with_model(self.provider, self.model)
            return chat
        except Exception as e:
            logger.error(f"Failed to create LLM chat: {e}")
            return None
    
    async def generate(self, system_prompt: str, user_prompt: str, session_id: Optional[str] = None,
                       rag_topic: Optional[str] = None, rag_language: Optional[str] = None,
                       rag_engine: Optional[str] = None, rag_genre: Optional[str] = None,
                       rag_juice: Optional[int] = None,
                       ml_config: Optional[Dict[str, Any]] = None,
                       matrices: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None,
                       build_id: Optional[str] = None) -> Dict[str, Any]:
        """Generic generation method. RAG context is now ALWAYS-ON unless rag_topic
        is explicitly set to "" (empty string). When no topic is provided we infer
        one from the first ~6 tokens of the user prompt so the agent stays grounded
        even in legacy call-sites that haven't been migrated yet.

        2026-05-15 — Threads Galaxy Studio build matrices + Advanced ML config
        into the system prompt so dial settings actually influence content output:
            • ml_config → natural-language ML directives (label smoothing, focal,
              DPO/KTO/LoRA hints, self-consistency k, MCTS planning depth, etc.)
            • matrices  → dict of matrix_key→{phase→{axis→int}}; we surface the
              top-priority phases per matrix as bullet directives.
            • build_id  → opt-in shortcut: when provided AND ml_config/matrices
              aren't explicitly passed, auto-loads them from the build doc. This
              lets any pipeline opt into matrix-aware generation by simply
              forwarding a build_id from its request body.
        All three are optional and backward compatible.
        """
        # ── Auto-load build context if build_id passed and explicit args missing ──
        if build_id and (ml_config is None and matrices is None):
            try:
                ctx = await load_build_context(build_id)
                if ctx:
                    ml_config = ctx.get("ml_config") or None
                    matrices  = ctx.get("matrices")  or None
            except Exception as e:
                logger.warning(f"generate(): build_id={build_id} context load failed: {e}")

        rag_block = ""
        # ── Default-on RAG (2026-05) ───────────────────────────────────
        if rag_topic is None:
            # Auto-derive topic from user prompt tokens
            try:
                first_tokens = " ".join(user_prompt.split()[:6]).strip()
                rag_topic = first_tokens[:64] if first_tokens else "game-build"
            except Exception:
                rag_topic = "game-build"
        if rag_topic:
            try:
                from services.agent_knowledge_rag import build_rag_context
                rag_block = await build_rag_context(
                    topic=rag_topic, language=rag_language,
                    engine=rag_engine, genre=rag_genre, take=5,
                )
                # ── Juice tier wiring: map 0-10 slider → tier name → look up ──
                if rag_juice is not None:
                    try:
                        from motor.motor_asyncio import AsyncIOMotorClient
                        import os
                        _cli = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
                        _db = _cli[os.environ.get("DB_NAME", "codedock")]
                        tier = ("subtle" if rag_juice <= 2 else
                                "medium" if rag_juice <= 5 else
                                "strong" if rag_juice <= 8 else "explosive")
                        juice_rows = await _db.visual_juice.find(
                            {"intensity": tier}, {"_id": 0}
                        ).limit(6).to_list(6)
                        if juice_rows:
                            rag_block += "\n\n### Visual-Juice Tier (slider="+str(rag_juice)+" → "+tier+")\n"
                            for r in juice_rows:
                                rag_block += f"• {r.get('effect','')}: {r.get('params','')}\n"
                    except Exception as je:
                        logger.warning(f"Juice tier wiring failed: {je}")
                if rag_block:
                    system_prompt = rag_block + "\n\n---\n\n" + system_prompt
            except Exception as e:
                logger.warning(f"RAG context retrieval failed: {e}")

        # ── ML Directive Block (2026-05-15) ─────────────────────────────
        ml_block = _format_ml_directives(ml_config) if ml_config else ""
        if ml_block:
            system_prompt = ml_block + "\n\n---\n\n" + system_prompt

        # ── Matrix Highlights Block (2026-05-15) ────────────────────────
        mtx_block = _format_matrix_highlights(matrices) if matrices else ""
        if mtx_block:
            system_prompt = mtx_block + "\n\n---\n\n" + system_prompt

        if outcalls.is_internal():
            simulated = await outcalls.generate_text(user_prompt, system_prompt)
            # Try to return JSON if the prompt asked for it, otherwise text
            if "{" in system_prompt or "{" in user_prompt:
                return {"success": True, "response": simulated, "fallback": False, "is_json_mock": True, "rag_chars": len(rag_block)}
            return {"success": True, "response": simulated, "fallback": False, "rag_chars": len(rag_block)}

        if not self.available:
            return {"success": False, "error": "LLM not available", "fallback": True}
        
        try:
            chat = self._create_chat(system_prompt, session_id)
            if not chat:
                return {"success": False, "error": "Failed to create chat", "fallback": True}
            
            response = await chat.send_message(UserMessage(text=user_prompt))
            return {"success": True, "response": response, "fallback": False, "rag_chars": len(rag_block)}
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return {"success": False, "error": str(e), "fallback": True}
    
    # =========================================================================
    # NPC & CHARACTER GENERATION
    # =========================================================================
    
    async def generate_npc(self, description: str, archetype: Optional[str] = None, 
                          include_dialogue: bool = True, include_quests: bool = False) -> Dict[str, Any]:
        """Generate a complete NPC with personality, dialogue, and optional quests."""
        system_prompt = """You are an expert game designer specializing in NPC creation.
Generate detailed, believable NPCs with rich personalities and engaging dialogue.
Always respond with valid JSON in the exact format requested."""
        
        dialogue_section = ""
        if include_dialogue:
            dialogue_section = '"dialogue": {"greeting": "...", "farewell": "...", "idle": ["..."], "combat": ["..."], "trade": ["..."]},'
        
        quest_section = ""
        if include_quests:
            quest_section = '"quests": [{"name": "...", "description": "...", "objectives": [...], "rewards": [...]}],'
        
        archetype_line = ""
        if archetype:
            archetype_line = f"Archetype: {archetype}"
        
        user_prompt = f"""Create a detailed NPC based on this description: "{description}"
{archetype_line}

Generate a JSON response with this structure:
{{
    "name": "NPC name",
    "title": "Optional title/role",
    "archetype": "merchant/warrior/mage/etc",
    "personality": {{
        "traits": ["list of 3-5 personality traits"],
        "values": ["what they care about"],
        "fears": ["what they fear"],
        "goals": ["their objectives"],
        "quirks": ["unique behaviors"]
    }},
    "appearance": {{
        "physical": "physical description",
        "clothing": "what they wear",
        "distinctive_features": ["notable features"]
    }},
    "backstory": "2-3 sentence backstory",
    "voice": {{
        "tone": "how they speak",
        "speech_patterns": ["unique phrases or patterns"],
        "vocabulary_level": "simple/moderate/sophisticated"
    }},
    {dialogue_section}
    {quest_section}
    "combat_stats": {{
        "level": 5,
        "health": 100,
        "damage": 15
    }}
}}"""
        
        result = await self.generate(system_prompt, user_prompt)
        if result["success"]:
            try:
                response_text = result["response"]
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                result["npc"] = json.loads(response_text.strip())
            except json.JSONDecodeError:
                result["npc_raw"] = result["response"]
        return result
    
    async def generate_npc_dialogue(self, npc_context: Dict[str, Any], situation: str, 
                                    player_input: Optional[str] = None) -> Dict[str, Any]:
        """Generate contextual NPC dialogue."""
        npc_name = npc_context.get('name', 'an NPC')
        npc_personality = npc_context.get('personality', {})
        npc_voice = npc_context.get('voice', {})
        
        system_prompt = f"""You are roleplaying as {npc_name}.
Personality: {json.dumps(npc_personality)}
Voice style: {json.dumps(npc_voice)}
Stay in character and respond naturally."""
        
        user_prompt = f"Situation: {situation}"
        if player_input:
            user_prompt += f'\nPlayer says: "{player_input}"'
        user_prompt += "\n\nRespond in character with 1-3 sentences."
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # GAME LOGIC & SYSTEMS
    # =========================================================================
    
    async def generate_combat_system(self, style: str, mechanics: List[str], 
                                     complexity: str = "moderate") -> Dict[str, Any]:
        """Generate a complete combat system design."""
        system_prompt = """You are an expert game systems designer specializing in combat mechanics.
Design balanced, engaging combat systems with clear rules and formulas.
Always respond with valid JSON."""
        
        mechanics_str = ', '.join(mechanics)
        
        user_prompt = f"""Design a {style} combat system with these mechanics: {mechanics_str}
Complexity level: {complexity}

Generate JSON with:
{{
    "system_name": "name",
    "type": "{style}",
    "core_mechanics": [
        {{"name": "...", "description": "...", "formula": "...", "code_snippet": "..."}}
    ],
    "damage_calculation": {{
        "formula": "base_damage * multiplier - defense",
        "factors": ["list of factors"],
        "code": "python code snippet"
    }},
    "status_effects": [
        {{"name": "...", "duration": 0, "effect": "...", "stack_behavior": "..."}}
    ],
    "balance_considerations": ["tips for balance"],
    "implementation_code": "complete Python class implementation"
}}"""
        
        result = await self.generate(system_prompt, user_prompt)
        if result["success"]:
            try:
                response_text = result["response"]
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                result["combat_system"] = json.loads(response_text.strip())
            except json.JSONDecodeError:
                result["combat_system_raw"] = result["response"]
        return result
    
    async def generate_progression_system(self, game_type: str, 
                                          progression_elements: List[str]) -> Dict[str, Any]:
        """Generate a progression/leveling system."""
        system_prompt = """You are an expert game designer specializing in player progression.
Design engaging progression systems that provide meaningful choices and rewards.
Always respond with valid JSON."""
        
        elements_str = ', '.join(progression_elements)
        
        user_prompt = f"""Design a progression system for a {game_type} game.
Include these elements: {elements_str}

Generate JSON with:
{{
    "xp_curve": {{"formula": "...", "level_requirements": [0, 100, 300, 600, 1000]}},
    "skill_trees": [{{"name": "...", "skills": [...]}}],
    "unlockables": [{{"level": 0, "rewards": [...]}}],
    "prestige_system": {{"enabled": true, "bonuses": [...]}},
    "implementation_code": "Python implementation"
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_game_rules(self, game_type: str, core_mechanics: List[str]) -> Dict[str, Any]:
        """Generate game rules and mechanics."""
        system_prompt = """You are an expert game designer.
Create clear, balanced game rules with proper edge case handling.
Always respond with valid JSON."""
        
        mechanics_str = ', '.join(core_mechanics)
        
        user_prompt = f"""Design game rules for a {game_type} game with mechanics: {mechanics_str}

Generate JSON with:
{{
    "game_name": "...",
    "core_rules": [{{"rule": "...", "exceptions": [...]}}],
    "turn_structure": {{"phases": [...], "actions_per_turn": 1}},
    "win_conditions": [...],
    "lose_conditions": [...],
    "edge_cases": [{{"scenario": "...", "resolution": "..."}}]
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # WORLD BUILDING & MANAGEMENT
    # =========================================================================
    
    async def generate_world_region(self, biome: str, size: str, 
                                    features: List[str],
                                    build_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a world region with locations, NPCs, and quests."""
        system_prompt = """You are an expert world builder for games.
Create immersive, detailed game worlds with interesting locations and encounters.
Always respond with valid JSON."""
        
        features_str = ', '.join(features)
        
        user_prompt = f"""Design a {size} {biome} region with these features: {features_str}

Generate JSON with:
{{
    "region_name": "...",
    "description": "...",
    "biome": "{biome}",
    "locations": [
        {{
            "name": "...",
            "type": "town/dungeon/landmark/etc",
            "description": "...",
            "npcs": ["npc names"],
            "encounters": ["possible encounters"],
            "loot_table": ["possible loot"]
        }}
    ],
    "ambient": {{"weather_patterns": [...], "wildlife": [...], "sounds": [...]}},
    "secrets": ["hidden areas or items"],
    "streaming_chunks": [{{"id": "...", "priority": 1, "dependencies": []}}]
}}"""
        
        return await self.generate(system_prompt, user_prompt, build_id=build_id)
    
    async def generate_level_design(self, level_type: str, objectives: List[str],
                                    difficulty: str = "medium",
                                    build_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a complete level design."""
        system_prompt = """You are an expert level designer.
Create engaging, well-paced levels with clear objectives and interesting challenges.
Always respond with valid JSON."""
        
        objectives_str = ', '.join(objectives)
        
        user_prompt = f"""Design a {level_type} level with difficulty: {difficulty}
Objectives: {objectives_str}

Generate JSON with:
{{
    "level_name": "...",
    "layout": {{"rooms": [...], "corridors": [...], "checkpoints": [...]}},
    "objectives": [{{"primary": true, "description": "...", "triggers": [...]}}],
    "enemies": [{{"type": "...", "count": 0, "spawn_points": [...]}}],
    "puzzles": [{{"type": "...", "solution": "...", "hints": [...]}}],
    "pacing": [{{"section": "...", "intensity": "low/medium/high", "duration": "..."}}],
    "boss_encounter": {{"name": "...", "phases": [...], "mechanics": [...]}}
}}"""
        
        return await self.generate(system_prompt, user_prompt, build_id=build_id)
    
    # =========================================================================
    # ANIMATION & VFX
    # =========================================================================
    
    async def generate_animation_sequence(self, character_type: str, 
                                          animation_name: str,
                                          style: str = "realistic") -> Dict[str, Any]:
        """Generate animation keyframes and timing."""
        system_prompt = """You are an expert game animator.
Design smooth, expressive animations with proper timing and anticipation.
Always respond with valid JSON with keyframe data."""
        
        user_prompt = f"""Create a {style} {animation_name} animation for a {character_type}.

Generate JSON with:
{{
    "animation_name": "{animation_name}",
    "duration_frames": 30,
    "fps": 30,
    "looping": true,
    "keyframes": [
        {{
            "frame": 0,
            "bones": {{
                "spine": {{"rotation": [0,0,0], "position": [0,0,0]}},
                "left_arm": {{"rotation": [0,0,0]}},
                "right_arm": {{"rotation": [0,0,0]}}
            }}
        }}
    ],
    "events": [{{"frame": 0, "event": "footstep_left"}}],
    "blend_settings": {{"in_time": 0.2, "out_time": 0.2}},
    "root_motion": {{"enabled": true, "extract_rotation": true}}
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_vfx_system(self, effect_type: str, 
                                  visual_style: str) -> Dict[str, Any]:
        """Generate a VFX particle system configuration."""
        system_prompt = """You are an expert VFX artist for games.
Design visually stunning, performant particle effects.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a {visual_style} {effect_type} VFX system.

Generate JSON with:
{{
    "effect_name": "...",
    "emitters": [
        {{
            "name": "...",
            "shape": "point/sphere/cone/etc",
            "emission_rate": 100,
            "lifetime": {{"min": 1.0, "max": 2.0}},
            "velocity": {{"initial": [0, 1, 0], "over_lifetime": [0, 0.5, 0]}},
            "size": {{"start": 1.0, "end": 0.0, "curve": "linear"}},
            "color": {{"start": "#ffffff", "end": "#000000", "curve": "linear"}}
        }}
    ],
    "rendering": {{"blend_mode": "additive", "material": "particle_default", "sorting": "by_distance"}},
    "performance": {{"max_particles": 1000, "lod_distances": [10, 50, 100]}}
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # ECONOMY & MONETIZATION
    # =========================================================================
    
    async def generate_economy_design(self, game_type: str, 
                                      monetization_model: str) -> Dict[str, Any]:
        """Generate a complete game economy design."""
        system_prompt = """You are an expert game economist.
Design balanced, engaging economies that respect player time and money.
Always respond with valid JSON."""
        
        user_prompt = f"""Design an economy for a {game_type} game with {monetization_model} monetization.

Generate JSON with:
{{
    "currencies": [
        {{"name": "gold", "type": "soft", "earn_rates": ["quests", "enemies"], "sinks": ["items", "upgrades"]}}
    ],
    "pricing_tiers": [{{"item_type": "common", "price_range": [10, 100]}}],
    "progression_gates": [{{"level": 10, "cost": 500, "bypass_option": "premium"}}],
    "balance_rules": ["list of economy rules"],
    "anti_inflation_measures": ["measures to control inflation"],
    "monetization": {{
        "model": "{monetization_model}",
        "ethical_guidelines": ["guidelines"],
        "conversion_points": ["where to offer purchases"]
    }}
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_monetization_strategy(self, game_type: str,
                                             target_audience: str) -> Dict[str, Any]:
        """Generate an ethical monetization strategy."""
        system_prompt = """You are an expert in ethical game monetization.
Design fair monetization that enhances player experience without exploitation.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a monetization strategy for a {game_type} targeting {target_audience}.

Generate JSON with:
{{
    "strategy_name": "...",
    "primary_model": "free_to_play/premium/subscription",
    "revenue_streams": [{{"type": "cosmetics", "pricing": [...], "value_proposition": "..."}}],
    "ethical_guidelines": [...],
    "player_protection": [{{"measure": "...", "implementation": "..."}}],
    "analytics_metrics": ["key metrics to track"]
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # NARRATIVE & STORY
    # =========================================================================
    
    async def generate_story_branch(self, context: str, choices: List[str],
                                    tone: str = "dramatic") -> Dict[str, Any]:
        """Generate a narrative branch with multiple outcomes."""
        system_prompt = f"""You are an expert narrative designer.
Create compelling, branching narratives with meaningful choices.
Tone: {tone}
Always respond with valid JSON."""
        
        choices_str = ', '.join(choices)
        
        user_prompt = f"""Context: {context}
Player choices: {choices_str}

Generate JSON with:
{{
    "scene_description": "...",
    "dialogue": [{{"speaker": "...", "text": "...", "emotion": "..."}}],
    "choices": [
        {{
            "text": "...",
            "consequence": "immediate/delayed",
            "alignment_shift": {{"good": 0, "evil": 0}},
            "outcome": "..."
        }}
    ],
    "branch_outcomes": [
        {{"choice_id": 0, "next_scene": "...", "state_changes": [...]}}
    ]
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_quest(self, quest_type: str, difficulty: str,
                            setting: str) -> Dict[str, Any]:
        """Generate a complete quest with objectives and rewards."""
        system_prompt = """You are an expert quest designer.
Create engaging quests with clear objectives and meaningful rewards.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a {difficulty} {quest_type} quest in a {setting} setting.

Generate JSON with:
{{
    "quest_name": "...",
    "quest_giver": "...",
    "description": "...",
    "type": "{quest_type}",
    "objectives": [
        {{"id": 1, "type": "kill/collect/escort/etc", "target": "...", "count": 1, "optional": false}}
    ],
    "stages": [{{"id": 1, "description": "...", "objectives": [1]}}],
    "dialogue": {{
        "accept": "...",
        "progress": "...",
        "complete": "..."
    }},
    "rewards": {{
        "xp": 100,
        "gold": 50,
        "items": ["..."],
        "reputation": {{"faction": "...", "amount": 10}}
    }},
    "failure_conditions": ["..."],
    "hidden_objectives": ["bonus objectives"]
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_dialogue_tree(self, character_name: str,
                                     character_personality: str,
                                     topics: List[str]) -> Dict[str, Any]:
        """Generate a complete dialogue tree for an NPC."""
        system_prompt = """You are an expert dialogue writer for games.
Create engaging, branching dialogue that reveals character and advances story.
Always respond with valid JSON."""
        
        topics_str = ', '.join(topics)
        
        user_prompt = f"""Create a dialogue tree for {character_name}.
Personality: {character_personality}
Topics to cover: {topics_str}

Generate JSON with:
{{
    "character": "{character_name}",
    "root_node": {{
        "id": "greeting",
        "text": "...",
        "options": [{{"text": "...", "leads_to": "topic_1"}}]
    }},
    "nodes": {{
        "topic_1": {{
            "text": "...",
            "emotion": "neutral",
            "options": [...]
        }}
    }},
    "bark_lines": ["idle dialogue lines"],
    "combat_lines": ["lines during combat"]
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # TESTING & QA
    # =========================================================================
    
    async def generate_test_cases(self, feature: str, 
                                  test_type: str = "functional") -> Dict[str, Any]:
        """Generate test cases for a game feature."""
        system_prompt = """You are an expert QA engineer for games.
Create comprehensive test cases that cover edge cases and common issues.
Always respond with valid JSON."""
        
        user_prompt = f"""Generate {test_type} test cases for: {feature}

Generate JSON with:
{{
    "feature": "{feature}",
    "test_suite": {{
        "name": "...",
        "priority": "critical/high/medium/low",
        "test_cases": [
            {{
                "id": "TC001",
                "name": "...",
                "preconditions": ["..."],
                "steps": ["..."],
                "expected_result": "...",
                "test_data": {{}}
            }}
        ]
    }},
    "edge_cases": ["list of edge cases to test"],
    "performance_benchmarks": {{"metric": "fps", "threshold": 60}},
    "automation_script": "Python test automation code"
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_bug_report_template(self, game_type: str) -> Dict[str, Any]:
        """Generate a bug report template."""
        system_prompt = """You are a QA expert.
Create comprehensive bug report templates.
Always respond with valid JSON."""
        
        user_prompt = f"""Create a bug report template for a {game_type} game.

Generate JSON with:
{{
    "template_name": "...",
    "required_fields": [...],
    "severity_levels": [...],
    "categories": [...],
    "reproduction_template": "..."
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # AI BEHAVIOR
    # =========================================================================
    
    async def generate_ai_behavior(self, agent_type: str, 
                                   behavior_style: str) -> Dict[str, Any]:
        """Generate AI behavior trees and decision logic."""
        system_prompt = """You are an expert game AI programmer.
Design intelligent, believable AI behaviors with proper decision-making.
Always respond with valid JSON."""
        
        user_prompt = f"""Design AI behavior for a {behavior_style} {agent_type}.

Generate JSON with:
{{
    "agent_type": "{agent_type}",
    "behavior_tree": {{
        "root": {{
            "type": "selector",
            "children": [
                {{
                    "type": "sequence",
                    "name": "combat_behavior",
                    "condition": "enemy_detected",
                    "children": ["assess_threat", "choose_action", "execute"]
                }}
            ]
        }}
    }},
    "utility_scores": [
        {{"action": "attack", "considerations": ["health", "distance", "ammo"], "weight": 1.0}}
    ],
    "perception": {{
        "sight_range": 20,
        "hearing_range": 10,
        "detection_factors": ["light", "noise", "movement"]
    }},
    "state_machine": {{
        "states": ["idle", "patrol", "alert", "combat", "flee"],
        "transitions": [{{"from": "idle", "to": "alert", "condition": "noise_heard"}}]
    }},
    "implementation_code": "Python AI controller class"
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    async def generate_npc_memory_system(self, memory_type: str) -> Dict[str, Any]:
        """Generate an NPC memory system design."""
        system_prompt = """You are an expert in game AI memory systems.
Design realistic memory systems that make NPCs feel alive.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a {memory_type} memory system for NPCs.

Generate JSON with:
{{
    "memory_type": "{memory_type}",
    "short_term": {{
        "capacity": 10,
        "decay_rate": 0.1,
        "importance_threshold": 0.5
    }},
    "long_term": {{
        "consolidation_rules": [...],
        "retrieval_cues": [...]
    }},
    "relationship_memory": {{
        "tracked_entities": ["player", "npcs", "factions"],
        "sentiment_range": [-100, 100]
    }},
    "implementation_code": "Python memory system class"
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # SERVER & BACKEND
    # =========================================================================
    
    async def generate_server_architecture(self, game_type: str,
                                           player_capacity: int,
                                           build_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate multiplayer server architecture."""
        system_prompt = """You are an expert in multiplayer game server architecture.
Design scalable, low-latency server systems.
Always respond with valid JSON."""
        
        user_prompt = f"""Design server architecture for a {game_type} game with {player_capacity} concurrent players.

Generate JSON with:
{{
    "architecture_type": "dedicated/peer_to_peer/hybrid",
    "server_components": [...],
    "network_model": {{
        "tick_rate": 64,
        "interpolation": true,
        "prediction": true
    }},
    "scaling_strategy": {{
        "horizontal": true,
        "regions": [...]
    }},
    "security_measures": [...],
    "implementation_notes": "..."
}}"""
        
        return await self.generate(system_prompt, user_prompt, build_id=build_id)
    
    # =========================================================================
    # DIRECTOR & PACING
    # =========================================================================
    
    async def generate_director_system(self, game_type: str) -> Dict[str, Any]:
        """Generate a dynamic director system (like L4D's AI Director)."""
        system_prompt = """You are an expert in dynamic difficulty and pacing systems.
Design intelligent director systems that create engaging experiences.
Always respond with valid JSON."""
        
        user_prompt = f"""Design an AI Director system for a {game_type} game.

Generate JSON with:
{{
    "director_type": "intensity_based/narrative_driven/hybrid",
    "pacing_curve": {{
        "phases": ["buildup", "peak", "respite"],
        "duration_ranges": {{}}
    }},
    "intensity_metrics": [...],
    "spawn_rules": [...],
    "player_adaptation": {{
        "skill_tracking": true,
        "frustration_detection": true
    }},
    "implementation_code": "Python director class"
}}"""
        
        return await self.generate(system_prompt, user_prompt)
    
    # =========================================================================
    # HARDWARE & OPTIMIZATION
    # =========================================================================
    
    async def generate_optimization_profile(self, target_platform: str,
                                            target_fps: int) -> Dict[str, Any]:
        """Generate hardware optimization recommendations."""
        system_prompt = """You are an expert in game performance optimization.
Provide practical optimization strategies for different platforms.
Always respond with valid JSON."""
        
        user_prompt = f"""Create an optimization profile for {target_platform} targeting {target_fps} FPS.

Generate JSON with:
{{
    "platform": "{target_platform}",
    "target_fps": {target_fps},
    "graphics_settings": {{
        "resolution": "...",
        "quality_presets": [...]
    }},
    "optimization_techniques": [...],
    "memory_budget": {{
        "textures_mb": 512,
        "meshes_mb": 256
    }},
    "profiling_tools": [...],
    "common_bottlenecks": [...]
}}"""
        
        return await self.generate(system_prompt, user_prompt)


# Global instance
_game_llm_service: Optional[GameLLMService] = None


def get_game_llm_service(model: str = "gpt-4o", provider: str = "openai") -> GameLLMService:
    """Get or create the global GameLLMService instance."""
    global _game_llm_service
    if _game_llm_service is None:
        _game_llm_service = GameLLMService(model=model, provider=provider)
    return _game_llm_service


# ─────────────────────────────────────────────────────────────────────
# 2026-05-15 — Galaxy Studio matrix + ML-config prompt injection helpers
# ─────────────────────────────────────────────────────────────────────

def _format_ml_directives(ml_config: Optional[Dict[str, Any]]) -> str:
    """Convert an ml_config dict (Cross-Entropy / Fine-Tuning / In-Context dials)
    into natural-language directives prepended to the system prompt. Keeps
    the agent grounded in the user's chosen ML configuration without leaking
    raw numbers when not useful."""
    if not isinstance(ml_config, dict) or not ml_config:
        return ""
    lines: List[str] = ["### Galaxy Studio · Advanced ML Directives"]
    # Cross-Entropy customisation
    ls = ml_config.get("label_smoothing")
    if isinstance(ls, (int, float)) and ls > 0:
        if ls >= 0.08:
            lines.append("• High label smoothing → hedge confidence; offer multiple plausible variants per concept.")
        else:
            lines.append("• Light label smoothing → small uncertainty buffer; avoid overconfident factual claims.")
    fg = ml_config.get("focal_gamma")
    if isinstance(fg, (int, float)) and fg > 0:
        lines.append(f"• Focal-loss gamma={fg} → spend extra detail on edge-case / rare phases; do not skimp on hard examples.")
    cetemp = ml_config.get("ce_temperature")
    if isinstance(cetemp, (int, float)):
        if cetemp >= 0.8:
            lines.append("• High CE temperature → favour creative, divergent solutions.")
        elif cetemp <= 0.3:
            lines.append("• Low CE temperature → favour deterministic, by-the-book solutions.")
    lt = ml_config.get("loss_type")
    if isinstance(lt, str) and lt:
        lines.append(f"• Loss strategy: {lt} → tune content style accordingly (focal=emphasise rare/hard examples; ce=balanced).")
    # Fine-tuning preferences (DPO / ORPO / KTO + LoRA / QLoRA)
    pref = ml_config.get("preference_finetune")
    if isinstance(pref, list) and pref:
        names = ", ".join(str(p) for p in pref[:4])
        lines.append(f"• Preference-tuning active ({names}) → choose the option that a careful user would prefer; avoid lazy filler.")
    lora_r = ml_config.get("lora_r")
    if isinstance(lora_r, int) and lora_r:
        if lora_r >= 32:
            lines.append("• High LoRA rank → deep specialisation; bring genre-specific nuance and uncommon vocabulary.")
        else:
            lines.append("• Low LoRA rank → keep adaptations lean; stay close to the base style.")
    if ml_config.get("qlora_4bit"):
        lines.append("• 4-bit QLoRA active → favour compact, dense phrasing; avoid token bloat.")
    ftm = ml_config.get("fine_tune_mode")
    if isinstance(ftm, str) and ftm:
        lines.append(f"• Fine-tune mode: {ftm}.")
    # In-Context Learning Log-Probs + Self-Consistency + MCTS
    icl_d = ml_config.get("icl_logprobs_depth")
    if isinstance(icl_d, int) and icl_d >= 6:
        lines.append("• Deep in-context log-probs analysis → walk through your reasoning briefly before final output; double-check claims.")
    sc_k = ml_config.get("self_consistency_k")
    if isinstance(sc_k, int) and sc_k >= 4:
        lines.append(f"• Self-consistency k={sc_k} → internally enumerate {sc_k} candidate paths and select the most internally-consistent one.")
    mcts_d = ml_config.get("mcts_depth")
    if isinstance(mcts_d, int) and mcts_d >= 3:
        lines.append(f"• MCTS planning depth={mcts_d} → plan {mcts_d} logical steps ahead before committing to a final structure.")
    icl_s = ml_config.get("icl_samples")
    if isinstance(icl_s, int) and icl_s >= 8:
        lines.append(f"• ICL sample budget={icl_s} → ground each major choice in concrete in-context examples (don't generalise blindly).")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


# Per-matrix axis-priority key used to pick "top" dials when surfacing highlights.
_MATRIX_PRIORITY_AXIS = {
    "mechanics_matrix":     "complexity",
    "world_matrix":         "complexity",
    "art_matrix":           "fidelity",
    "audio_matrix":         "fidelity",
    "tech_matrix":          "priority",
    "monetisation_matrix":  "fairness",
    "qa_matrix":            "coverage",
    "agent_matrix":         "weight",
    "vector_db_matrix":     "priority",
    "plagiarism_matrix":    "sensitivity",
    "rdbms_matrix":         "priority",
    "styles_matrix":        "fidelity",
    "mutation_matrix":      "magnitude",
    "unique_flair_matrix":  "showmanship",
}

# Human-readable matrix titles for prompt clarity
_MATRIX_TITLES = {
    "mechanics_matrix":     "Mechanics",
    "world_matrix":         "World",
    "art_matrix":           "Art",
    "audio_matrix":         "Audio",
    "tech_matrix":          "Tech",
    "monetisation_matrix":  "Monetisation",
    "qa_matrix":            "QA",
    "agent_matrix":         "Agent/ML",
    "vector_db_matrix":     "Vector DBs",
    "plagiarism_matrix":    "Plagiarism/Stylometry",
    "rdbms_matrix":         "Relational DBs",
    "styles_matrix":        "Styles",
    "mutation_matrix":      "Mutation",
    "unique_flair_matrix":  "Unique Flair",
}


# Per-matrix max-scale hints — axes that scale 0..1000 are output-amplifying
# and should be communicated to the LLM as "high impact" dials, not raw ints.
_MATRIX_HIGH_SCALE_AXES: Dict[str, set] = {
    "mechanics_matrix":     {"count", "complexity", "intricacy", "secrets"},
    "world_matrix":         {"count", "complexity", "intricacy", "secrets"},
    "agent_matrix":         {"weight", "samples", "context_depth", "self_consistency"},
    "mutation_matrix":      {"rate", "magnitude", "novelty"},
    "unique_flair_matrix":  {"rarity", "showmanship", "lore_depth", "discovery", "replay_value"},
}


def _axis_max_for(mkey: str, axis_id: str) -> int:
    """Return the max scale used by the questionnaire for a given axis. Used to
    normalise raw integer dials into 0-100 percentages for prompt clarity."""
    if axis_id in _MATRIX_HIGH_SCALE_AXES.get(mkey, set()):
        return 1000
    # Temperature is /100 on the agent side (range 0-200 ⇒ 0.0-2.0)
    if mkey == "agent_matrix" and axis_id == "temperature":
        return 200
    return 100


def _format_matrix_highlights(matrices: Optional[Dict[str, Dict[str, Dict[str, int]]]],
                              per_matrix_top_k: int = 4) -> str:
    """Convert raw matrix payload {matrix_key:{phase_id:{axis:int}}} into a
    compact "top dials per matrix" bullet block. Surfaces only the highest
    priority phases (by the matrix's primary axis) so the prompt stays small.

    2026-05-15 SOTA: emits both raw values AND scale-normalised percentages so
    the LLM correctly weights 0-100 vs 0-1000 axes. Critical axes (quests /
    secrets / easter eggs / mutation) are tagged as ★ to draw model attention.
    """
    if not isinstance(matrices, dict) or not matrices:
        return ""
    out: List[str] = ["### Galaxy Studio · User-Tuned Matrix Highlights"]
    for mkey, phases in matrices.items():
        if not isinstance(phases, dict) or not phases:
            continue
        title = _MATRIX_TITLES.get(mkey, mkey.replace("_", " ").title())
        prio_axis = _MATRIX_PRIORITY_AXIS.get(mkey, "complexity")
        high_scale = _MATRIX_HIGH_SCALE_AXES.get(mkey, set())
        # Sort phases by priority-axis value desc, fallback to sum-of-axes
        def _phase_score(phase_axes: Dict[str, Any]) -> float:
            if not isinstance(phase_axes, dict):
                return 0.0
            try:
                v = phase_axes.get(prio_axis)
                if isinstance(v, (int, float)):
                    # Normalise so 1000-scale and 100-scale axes compare fairly
                    scale = 1000 if prio_axis in high_scale else 100
                    return (float(v) / scale) * 1000.0
                # Fallback: percentage-normalised sum
                total = 0.0
                for ax, vv in phase_axes.items():
                    if isinstance(vv, (int, float)):
                        sc = 1000 if ax in high_scale else 100
                        total += (float(vv) / sc) * 100.0
                return total
            except Exception:
                return 0.0
        ranked = sorted(phases.items(), key=lambda kv: _phase_score(kv[1]), reverse=True)
        # Drop phases that are all-zero — they carry no signal
        ranked = [(p, a) for p, a in ranked if _phase_score(a) > 0]
        top = ranked[:per_matrix_top_k]
        if not top:
            continue
        bullets = []
        for phase_id, axes in top:
            if not isinstance(axes, dict):
                continue
            # Render top 3 axes per phase with scale-aware annotation
            axes_top = sorted(
                ((a, v) for a, v in axes.items() if isinstance(v, (int, float)) and v > 0),
                key=lambda kv: kv[1] / (1000.0 if kv[0] in high_scale else 100.0),
                reverse=True
            )[:3]
            parts = []
            for a, v in axes_top:
                scale = 1000 if a in high_scale else 100
                pct = int(round((float(v) / scale) * 100))
                star = "★" if a in high_scale and pct >= 60 else ""
                parts.append(f"{a}={int(v)}/{scale}({pct}%){star}")
            axes_str = ", ".join(parts)
            bullets.append(f"{phase_id}[{axes_str}]")
        if bullets:
            out.append(f"• **{title}** — focus: {'; '.join(bullets)}.")
    if len(out) == 1:
        return ""
    out.append(
        "→ Treat the above as the user's explicit priority dials. "
        "Higher percentages = more attention/quality/detail. "
        "★-tagged axes are HIGH-IMPACT output amplifiers (e.g. quests, secrets, "
        "easter eggs, mutation magnitude, agent sampling) — they MUST shape the "
        "volume, density, and richness of generated content."
    )
    return "\n".join(out)


async def load_build_context(build_id: str) -> Dict[str, Any]:
    """Fetch a Galaxy Studio build doc and return {ml_config, matrices} ready to
    pass into GameLLMService.generate(). Safe-on-failure (returns empty dict)."""
    try:
        from services.database import db as _db
        b = await _db.galaxy_builds.find_one(
            {"build_id": build_id},
            {"_id": 0, "build_id": 1, "ml_config": 1,
             "mechanics_matrix": 1, "world_matrix": 1, "art_matrix": 1,
             "audio_matrix": 1, "tech_matrix": 1, "monetisation_matrix": 1,
             "qa_matrix": 1, "agent_matrix": 1, "vector_db_matrix": 1,
             "plagiarism_matrix": 1, "rdbms_matrix": 1, "styles_matrix": 1,
             "mutation_matrix": 1, "unique_flair_matrix": 1}
        )
        # IMPORTANT: distinguish "missing build" (find_one → None) from
        # "build exists but has no matrices/ml_config" (find_one → {build_id}).
        # `if not b` would incorrectly treat the latter as missing.
        if b is None:
            return {}
        ml = b.pop("ml_config", None)
        b.pop("build_id", None)
        matrices = {k: v for k, v in b.items() if isinstance(v, dict) and v}
        return {"ml_config": ml or {}, "matrices": matrices, "found": True}
    except Exception as e:
        logger.warning(f"load_build_context failed for {build_id}: {e}")
        return {}
