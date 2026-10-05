"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      ENHANCED AI BIBLE v15.5 - COMPREHENSIVE GAME DEVELOPMENT CURRICULUM     ║
║                                                                              ║
║  The definitive guide to AI-powered game development in 2026:                ║
║  • Complete curriculum structure                                             ║
║  • Advanced 2026 standards                                                   ║
║  • Best practices and patterns                                               ║
║  • Industry-ready knowledge                                                  ║
║  • Hands-on project guides                                                   ║
║  • Career progression paths                                                  ║
║  • AI-powered learning assistance                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
import uuid

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/ai-bible", tags=["Enhanced AI Bible v15.5"])

# ============================================================================
# THE ENHANCED AI BIBLE CURRICULUM
# ============================================================================

AI_BIBLE_CURRICULUM = {
    "title": "The AI Bible for Game Building - 2026 Edition",
    "version": "15.5",
    "last_updated": "2026-03",
    "total_modules": 12,
    "estimated_completion_hours": 500,
    
    "introduction": {
        "vision": "Master the art of AI-powered game development with cutting-edge 2026 techniques",
        "philosophy": "Learn by building, iterate rapidly, embrace AI as a creative partner",
        "prerequisites": [
            "Basic programming knowledge (any language)",
            "Familiarity with game concepts",
            "Curiosity and willingness to experiment"
        ]
    },
    
    "modules": [
        {
            "id": 1,
            "name": "Foundations of AI Game Development",
            "description": "Understanding the intersection of AI and game development",
            "duration_hours": 30,
            "topics": [
                {
                    "name": "The AI-First Development Paradigm",
                    "concepts": [
                        "AI as a creative partner, not just a tool",
                        "Prompt engineering for game assets",
                        "Iterative AI-assisted design",
                        "Balancing AI generation with human creativity"
                    ]
                },
                {
                    "name": "Game Development Fundamentals 2026",
                    "concepts": [
                        "Modern game engines overview (Unity, Unreal, Godot)",
                        "Cross-platform development strategies",
                        "Performance-first architecture",
                        "Asset pipeline optimization"
                    ]
                },
                {
                    "name": "AI Tools Ecosystem",
                    "concepts": [
                        "Text-to-code generators (GPT-5, Claude 4)",
                        "Image generation (DALL-E 4, Midjourney v7)",
                        "3D model generation (Neural Radiance Fields)",
                        "Audio synthesis and music generation"
                    ]
                }
            ],
            "projects": [
                "Create a simple game concept using AI brainstorming",
                "Generate basic game assets with AI tools",
                "Build a prototype using AI-generated code"
            ]
        },
        {
            "id": 2,
            "name": "AI-Powered Game Design",
            "description": "Leveraging AI for creative game design processes",
            "duration_hours": 45,
            "topics": [
                {
                    "name": "Procedural Content Generation",
                    "concepts": [
                        "Wave Function Collapse algorithms",
                        "Perlin noise and terrain generation",
                        "AI-driven level design",
                        "Dynamic difficulty adjustment"
                    ]
                },
                {
                    "name": "Narrative AI Systems",
                    "concepts": [
                        "Dynamic dialogue generation",
                        "Story branching with AI",
                        "Character personality modeling",
                        "Emergent narrative systems"
                    ]
                },
                {
                    "name": "Player Experience Design",
                    "concepts": [
                        "AI-driven playtesting",
                        "Sentiment analysis for player feedback",
                        "Personalized game experiences",
                        "Accessibility through AI"
                    ]
                }
            ],
            "projects": [
                "Build a procedural dungeon generator",
                "Create an AI-driven NPC dialogue system",
                "Implement dynamic difficulty adjustment"
            ]
        },
        {
            "id": 3,
            "name": "Game AI Programming",
            "description": "Implementing intelligent behaviors in games",
            "duration_hours": 60,
            "topics": [
                {
                    "name": "Behavior Systems",
                    "concepts": [
                        "Finite State Machines (FSM)",
                        "Behavior Trees",
                        "Goal-Oriented Action Planning (GOAP)",
                        "Utility AI systems"
                    ]
                },
                {
                    "name": "Pathfinding & Navigation",
                    "concepts": [
                        "A* and its variants",
                        "Navigation meshes",
                        "Hierarchical pathfinding",
                        "Steering behaviors"
                    ]
                },
                {
                    "name": "Machine Learning in Games",
                    "concepts": [
                        "Reinforcement learning for NPCs",
                        "Imitation learning from players",
                        "Neural network integration",
                        "Real-time ML inference"
                    ]
                }
            ],
            "projects": [
                "Implement a complete behavior tree system",
                "Create an AI opponent using reinforcement learning",
                "Build a navigation system with dynamic obstacles"
            ]
        },
        {
            "id": 4,
            "name": "Graphics & Visual AI",
            "description": "AI-enhanced graphics and visual effects",
            "duration_hours": 50,
            "topics": [
                {
                    "name": "Neural Rendering",
                    "concepts": [
                        "NeRF (Neural Radiance Fields)",
                        "Gaussian Splatting",
                        "AI upscaling (DLSS, FSR)",
                        "Neural texture synthesis"
                    ]
                },
                {
                    "name": "AI Art Generation",
                    "concepts": [
                        "Texture generation with AI",
                        "Character design pipelines",
                        "Environment art creation",
                        "Style transfer techniques"
                    ]
                },
                {
                    "name": "Real-time Visual Effects",
                    "concepts": [
                        "AI-driven particle systems",
                        "Procedural animation",
                        "Dynamic lighting with AI",
                        "Post-processing with ML"
                    ]
                }
            ],
            "projects": [
                "Create a complete texture set with AI",
                "Implement neural upscaling in a game",
                "Build an AI-driven VFX system"
            ]
        },
        {
            "id": 5,
            "name": "Audio & Music AI",
            "description": "AI-powered audio design and music composition",
            "duration_hours": 35,
            "topics": [
                {
                    "name": "Procedural Audio",
                    "concepts": [
                        "Procedural sound effects",
                        "Dynamic soundscapes",
                        "AI voice synthesis",
                        "Spatial audio with AI"
                    ]
                },
                {
                    "name": "Music Generation",
                    "concepts": [
                        "AI music composition",
                        "Adaptive music systems",
                        "Stem-based dynamic mixing",
                        "Emotional music mapping"
                    ]
                }
            ],
            "projects": [
                "Create an adaptive music system",
                "Build procedural ambient soundscapes",
                "Implement AI voice for NPCs"
            ]
        },
        {
            "id": 6,
            "name": "Multiplayer & Networking",
            "description": "AI applications in multiplayer game development",
            "duration_hours": 45,
            "topics": [
                {
                    "name": "AI for Multiplayer",
                    "concepts": [
                        "AI-powered matchmaking",
                        "Bot behavior in multiplayer",
                        "Cheat detection with ML",
                        "AI moderation systems"
                    ]
                },
                {
                    "name": "Network Architecture",
                    "concepts": [
                        "Client-server optimization",
                        "Lag compensation with AI",
                        "Predictive networking",
                        "Scalable server architecture"
                    ]
                }
            ],
            "projects": [
                "Build an AI matchmaking system",
                "Create intelligent game bots",
                "Implement AI-based cheat detection"
            ]
        },
        {
            "id": 7,
            "name": "Game Economy & Balancing",
            "description": "AI-driven game economy and balance systems",
            "duration_hours": 40,
            "topics": [
                {
                    "name": "Economy Design",
                    "concepts": [
                        "AI-driven economy balancing",
                        "Dynamic pricing systems",
                        "Reward optimization",
                        "Monetization with ethics"
                    ]
                },
                {
                    "name": "Game Balance",
                    "concepts": [
                        "Automated playtesting",
                        "Balance data analysis",
                        "AI-assisted tuning",
                        "Meta prediction"
                    ]
                }
            ],
            "projects": [
                "Design a self-balancing economy",
                "Create an automated balance testing system",
                "Build an ethical monetization model"
            ]
        },
        {
            "id": 8,
            "name": "Testing & Quality Assurance",
            "description": "AI-powered testing and QA processes",
            "duration_hours": 35,
            "topics": [
                {
                    "name": "Automated Testing",
                    "concepts": [
                        "AI exploratory testing",
                        "Visual regression testing",
                        "Performance profiling with AI",
                        "Bug prediction systems"
                    ]
                },
                {
                    "name": "QA Pipelines",
                    "concepts": [
                        "CI/CD for games",
                        "Automated build validation",
                        "AI-assisted bug triage",
                        "Player behavior simulation"
                    ]
                }
            ],
            "projects": [
                "Build an AI game testing bot",
                "Create automated visual testing",
                "Implement predictive bug detection"
            ]
        },
        {
            "id": 9,
            "name": "Performance Optimization",
            "description": "AI-driven performance optimization techniques",
            "duration_hours": 40,
            "topics": [
                {
                    "name": "Profiling & Analysis",
                    "concepts": [
                        "AI-powered profiling",
                        "Bottleneck detection",
                        "Memory optimization",
                        "GPU utilization analysis"
                    ]
                },
                {
                    "name": "Optimization Techniques",
                    "concepts": [
                        "LOD system optimization",
                        "Culling and batching",
                        "Asset streaming strategies",
                        "Cross-platform optimization"
                    ]
                }
            ],
            "projects": [
                "Profile and optimize a game",
                "Implement intelligent LOD systems",
                "Build adaptive quality settings"
            ]
        },
        {
            "id": 10,
            "name": "Live Operations & Analytics",
            "description": "AI for live games and player analytics",
            "duration_hours": 35,
            "topics": [
                {
                    "name": "Player Analytics",
                    "concepts": [
                        "Player segmentation with ML",
                        "Churn prediction",
                        "Lifetime value modeling",
                        "A/B testing optimization"
                    ]
                },
                {
                    "name": "Live Ops",
                    "concepts": [
                        "AI content scheduling",
                        "Personalized offers",
                        "Community sentiment analysis",
                        "Automated event management"
                    ]
                }
            ],
            "projects": [
                "Build a player analytics dashboard",
                "Create a churn prediction model",
                "Implement personalized content delivery"
            ]
        },
        {
            "id": 11,
            "name": "Advanced AI Topics",
            "description": "Cutting-edge AI techniques for games",
            "duration_hours": 45,
            "topics": [
                {
                    "name": "Emerging Technologies",
                    "concepts": [
                        "Large Language Models in games",
                        "Multimodal AI systems",
                        "AI NPCs with memory",
                        "Embodied AI agents"
                    ]
                },
                {
                    "name": "Research Applications",
                    "concepts": [
                        "Generative world building",
                        "AI game masters",
                        "Emergent gameplay systems",
                        "AI collaboration in development"
                    ]
                }
            ],
            "projects": [
                "Create an LLM-powered game master",
                "Build an AI with persistent memory",
                "Implement emergent narrative system"
            ]
        },
        {
            "id": 12,
            "name": "Capstone: Full Game Development",
            "description": "Build a complete game using all learned techniques",
            "duration_hours": 60,
            "topics": [
                {
                    "name": "Project Planning",
                    "concepts": [
                        "Scope management with AI",
                        "Team coordination",
                        "Milestone planning",
                        "Risk assessment"
                    ]
                },
                {
                    "name": "Full Development Cycle",
                    "concepts": [
                        "Prototype to production",
                        "Polish and iteration",
                        "Launch preparation",
                        "Post-launch support"
                    ]
                }
            ],
            "projects": [
                "Design a complete game with AI assistance",
                "Build and iterate on the game",
                "Polish and prepare for release",
                "Create post-launch content plan"
            ]
        }
    ],
    
    "best_practices": {
        "ai_integration": [
            "Use AI as a starting point, not the final product",
            "Iterate on AI outputs to match your vision",
            "Document your prompt engineering process",
            "Version control AI-generated assets",
            "Validate AI outputs for quality and consistency"
        ],
        "development_workflow": [
            "Start with core gameplay, add AI enhancement later",
            "Test AI features thoroughly across platforms",
            "Monitor AI system performance in real-time",
            "Have fallbacks for AI-dependent systems",
            "Balance AI complexity with maintainability"
        ],
        "ethical_considerations": [
            "Be transparent about AI use in your game",
            "Ensure AI systems don't perpetuate biases",
            "Protect player data in AI analytics",
            "Design AI monetization ethically",
            "Consider AI environmental impact"
        ]
    },
    
    "career_paths": [
        {
            "title": "AI Game Designer",
            "description": "Design game systems leveraging AI capabilities",
            "key_skills": ["Game design", "AI tools", "Prompt engineering", "Player psychology"]
        },
        {
            "title": "Game AI Programmer",
            "description": "Implement intelligent game systems and behaviors",
            "key_skills": ["Programming", "ML frameworks", "Behavior systems", "Performance optimization"]
        },
        {
            "title": "Technical Artist (AI)",
            "description": "Bridge AI tools with art production pipelines",
            "key_skills": ["Art fundamentals", "AI generation tools", "Pipeline development", "Shader programming"]
        },
        {
            "title": "AI Game Producer",
            "description": "Manage AI-integrated game development projects",
            "key_skills": ["Project management", "AI tool assessment", "Team coordination", "Risk management"]
        }
    ],
    
    "resources": {
        "books": [
            "AI Game Programming Wisdom (Series)",
            "Procedural Content Generation in Games",
            "Game AI Pro (Series)",
            "Artificial Intelligence for Games"
        ],
        "communities": [
            "r/gameai",
            "AI Game Dev Discord",
            "Procedural Generation Community",
            "Game AI Conference"
        ],
        "tools": [
            "Unity ML-Agents",
            "Unreal Learning Agents",
            "OpenAI Gym",
            "Stable Diffusion",
            "Midjourney",
            "ChatGPT/Claude"
        ]
    }
}


# ============================================================================
# REQUEST MODELS
# ============================================================================

class ModuleRequest(BaseModel):
    module_id: int = Field(..., ge=1, le=12)


class TopicRequest(BaseModel):
    module_id: int = Field(..., ge=1, le=12)
    topic_index: int = Field(..., ge=0)


class ProgressRequest(BaseModel):
    user_id: str
    module_id: int
    progress_percent: float = Field(..., ge=0.0, le=100.0)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Enhanced AI Bible."""
    return {
        "title": AI_BIBLE_CURRICULUM["title"],
        "version": AI_BIBLE_CURRICULUM["version"],
        "total_modules": AI_BIBLE_CURRICULUM["total_modules"],
        "estimated_hours": AI_BIBLE_CURRICULUM["estimated_completion_hours"],
        "introduction": AI_BIBLE_CURRICULUM["introduction"],
        "career_paths": AI_BIBLE_CURRICULUM["career_paths"]
    }


@router.get("/curriculum")
async def get_full_curriculum():
    """Get the complete AI Bible curriculum."""
    return {
        "success": True,
        "curriculum": AI_BIBLE_CURRICULUM
    }


@router.get("/modules")
async def get_modules():
    """Get list of all modules."""
    modules = [
        {
            "id": m["id"],
            "name": m["name"],
            "description": m["description"],
            "duration_hours": m["duration_hours"],
            "topic_count": len(m["topics"]),
            "project_count": len(m["projects"])
        }
        for m in AI_BIBLE_CURRICULUM["modules"]
    ]
    return {
        "success": True,
        "modules": modules
    }


@router.get("/module/{module_id}")
async def get_module(module_id: int):
    """Get detailed information about a specific module."""
    if module_id < 1 or module_id > 12:
        return {"success": False, "error": "Module not found"}
    
    module = AI_BIBLE_CURRICULUM["modules"][module_id - 1]
    return {
        "success": True,
        "module": module
    }


@router.get("/best-practices")
async def get_best_practices():
    """Get best practices for AI game development."""
    return {
        "success": True,
        "best_practices": AI_BIBLE_CURRICULUM["best_practices"]
    }


@router.get("/resources")
async def get_resources():
    """Get recommended resources."""
    return {
        "success": True,
        "resources": AI_BIBLE_CURRICULUM["resources"]
    }


@router.get("/career-paths")
async def get_career_paths():
    """Get career path information."""
    return {
        "success": True,
        "career_paths": AI_BIBLE_CURRICULUM["career_paths"]
    }


@router.post("/progress/update")
async def update_progress(request: ProgressRequest):
    """Update user progress (stub for future implementation)."""
    return {
        "success": True,
        "message": f"Progress updated for user {request.user_id}: Module {request.module_id} at {request.progress_percent}%"
    }


@router.get("/search")
async def search_curriculum(query: str):
    """Search the curriculum for specific topics."""
    results = []
    query_lower = query.lower()
    
    for module in AI_BIBLE_CURRICULUM["modules"]:
        if query_lower in module["name"].lower() or query_lower in module["description"].lower():
            results.append({
                "type": "module",
                "module_id": module["id"],
                "name": module["name"],
                "match": "title/description"
            })
        
        for topic in module["topics"]:
            if query_lower in topic["name"].lower():
                results.append({
                    "type": "topic",
                    "module_id": module["id"],
                    "name": topic["name"],
                    "match": "topic name"
                })
            
            for concept in topic["concepts"]:
                if query_lower in concept.lower():
                    results.append({
                        "type": "concept",
                        "module_id": module["id"],
                        "topic": topic["name"],
                        "concept": concept,
                        "match": "concept"
                    })
    
    return {
        "success": True,
        "query": query,
        "results": results[:20]  # Limit to 20 results
    }


# ============================================================================
# AI-POWERED LEARNING ENDPOINTS (LLM Integration)
# ============================================================================

class AIExplainRequest(BaseModel):
    """Request for AI-powered concept explanation"""
    topic: str = Field(..., description="Topic to explain")
    skill_level: str = Field(default="intermediate", description="beginner/intermediate/advanced")
    context: Optional[str] = None
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


class AIProjectRequest(BaseModel):
    """Request for AI-powered project generation"""
    module_id: int = Field(..., description="Module ID")
    skill_level: str = Field(default="intermediate")
    time_hours: int = Field(default=5, description="Available time in hours")
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


class AIQuizRequest(BaseModel):
    """Request for AI-powered quiz generation"""
    topic: str = Field(..., description="Topic for quiz")
    num_questions: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="medium")
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


class AIMentorRequest(BaseModel):
    """Request for AI-powered mentorship Q&A"""
    question: str = Field(..., description="Question for the AI mentor")
    context: Optional[str] = None
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


@router.post("/ai/explain")
async def ai_explain_concept(request: AIExplainRequest):
    """
    Get AI-powered explanation of any game development concept.
    Uses GPT-4o to provide clear, personalized explanations.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = f"""You are Jeeves, an expert game development tutor from Tutolage Academy.
Explain concepts clearly at the {request.skill_level} level.
Use practical game development examples.
Be encouraging and supportive."""
        
        context_info = f"\nAdditional context: {request.context}" if request.context else ""
        
        user_prompt = f"""Explain the following game development concept: "{request.topic}"
{context_info}

Provide:
1. A clear explanation suitable for a {request.skill_level} developer
2. A practical game development example
3. Common pitfalls to avoid
4. Next steps for learning more"""
        
        result = await llm_service.generate(system_prompt, user_prompt, build_id=request.build_id)
        
        if result["success"]:
            return {
                "success": True,
                "topic": request.topic,
                "skill_level": request.skill_level,
                "explanation": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": False,
                "error": "AI explanation unavailable",
                "fallback": f"Please refer to the curriculum for information on {request.topic}"
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI explanation failed: {str(e)}")


@router.post("/ai/project")
async def ai_generate_project(request: AIProjectRequest):
    """
    Generate a personalized project based on curriculum module.
    """
    try:
        llm_service = get_game_llm_service()
        
        # Find the module
        module = None
        for m in AI_BIBLE_CURRICULUM["modules"]:
            if m["id"] == request.module_id:
                module = m
                break
        
        if not module:
            raise HTTPException(status_code=404, detail=f"Module {request.module_id} not found")
        
        system_prompt = """You are an expert game development instructor.
Create practical, achievable projects that reinforce learning.
Always respond with valid JSON."""
        
        user_prompt = f"""Create a project for module: "{module['name']}"
Topics covered: {', '.join([t['name'] for t in module['topics']])}
Skill level: {request.skill_level}
Available time: {request.time_hours} hours

Generate JSON with:
{{
    "project_name": "...",
    "description": "...",
    "learning_objectives": ["..."],
    "steps": [
        {{"step": 1, "title": "...", "description": "...", "estimated_time_hours": 1}}
    ],
    "deliverables": ["..."],
    "bonus_challenges": ["..."],
    "resources_needed": ["..."]
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt)
        
        if result["success"]:
            return {
                "success": True,
                "module_id": request.module_id,
                "module_name": module["name"],
                "project": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "module_id": request.module_id,
                "project": module.get("projects", ["Build a project based on module concepts"])[0],
                "ai_generated": False
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI project generation failed: {str(e)}")


@router.post("/ai/quiz")
async def ai_generate_quiz(request: AIQuizRequest):
    """
    Generate a quiz to test knowledge on a topic.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = """You are an expert game development educator.
Create challenging but fair quiz questions that test understanding, not memorization.
Always respond with valid JSON."""
        
        user_prompt = f"""Create a {request.difficulty} quiz on: "{request.topic}"
Number of questions: {request.num_questions}

Generate JSON with:
{{
    "quiz_title": "...",
    "topic": "{request.topic}",
    "questions": [
        {{
            "id": 1,
            "type": "multiple_choice",
            "question": "...",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "correct_answer": "A",
            "explanation": "..."
        }}
    ],
    "passing_score": 70,
    "time_limit_minutes": {request.num_questions * 2}
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt, build_id=request.build_id)
        
        if result["success"]:
            return {
                "success": True,
                "topic": request.topic,
                "quiz": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": False,
                "error": "Quiz generation unavailable"
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI quiz generation failed: {str(e)}")


@router.post("/ai/mentor")
async def ai_mentor_chat(question: str, context: Optional[str] = None, build_id: Optional[str] = None):
    """
    Chat with Jeeves AI mentor about game development.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = """You are Jeeves, a wise and patient AI mentor from Tutolage Academy.
You specialize in teaching game development with AI tools.
Be encouraging, provide practical advice, and use game development examples.
Keep responses concise but helpful."""
        
        context_info = f"\nContext: {context}" if context else ""
        
        user_prompt = f"Student question: {question}{context_info}"
        
        result = await llm_service.generate(system_prompt, user_prompt, build_id=build_id)
        
        if result["success"]:
            return {
                "success": True,
                "question": question,
                "response": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": False,
                "error": "Mentor unavailable",
                "fallback": "Please check the curriculum or try again later."
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI mentor chat failed: {str(e)}")


@router.get("/ai/learning-path")
async def ai_generate_learning_path(goal: str, current_level: str = "beginner", available_hours_weekly: int = 10, build_id: Optional[str] = None):
    """
    Generate a personalized learning path based on goals.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = """You are an expert educational curriculum designer.
Create practical, achievable learning paths for game development.
Always respond with valid JSON."""
        
        modules_summary = [{"id": m["id"], "name": m["name"], "hours": m["duration_hours"]} 
                          for m in AI_BIBLE_CURRICULUM["modules"]]
        
        user_prompt = f"""Create a learning path for someone who wants to: "{goal}"
Current skill level: {current_level}
Available hours per week: {available_hours_weekly}

Available modules: {modules_summary}

Generate JSON with:
{{
    "learning_path_name": "...",
    "goal": "{goal}",
    "estimated_weeks": 0,
    "phases": [
        {{
            "phase": 1,
            "name": "...",
            "duration_weeks": 2,
            "modules": [1, 2],
            "milestones": ["..."]
        }}
    ],
    "weekly_schedule": {{
        "recommended_hours": {available_hours_weekly},
        "breakdown": {{"theory": 40, "practice": 50, "projects": 10}}
    }},
    "success_criteria": ["..."]
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt, build_id=build_id)
        
        if result["success"]:
            return {
                "success": True,
                "goal": goal,
                "learning_path": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Return default path
            return {
                "success": True,
                "goal": goal,
                "learning_path": {
                    "name": "Standard Game Dev Path",
                    "modules": [1, 2, 3, 4, 5],
                    "estimated_weeks": 20
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Learning path generation failed: {str(e)}")

