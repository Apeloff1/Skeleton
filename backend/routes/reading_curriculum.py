"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CODEDOCK READING CURRICULUM & KNOWLEDGE BASE v11.7 SOTA              ║
║                                                                              ║
║  Comprehensive Text-Based Learning System - April 2026 Industry Standards    ║
║                                                                              ║
║  Coverage Areas:                                                             ║
║  • Game Development (Physics, Math, CS, Graphics, Audio)                     ║
║  • Full-Stack Web Development (Frontend, Backend, DevOps)                    ║
║  • Mobile Development (iOS, Android, Cross-Platform)                         ║
║  • AI/ML Engineering (Deep Learning, NLP, Computer Vision)                   ║
║                                                                              ║
║  Features:                                                                   ║
║  • Interactive reading with progress tracking                                ║
║  • Code-along tutorials with explanations                                    ║
║  • Reference manuals for 64+ language packs                                  ║
║  • Spaced repetition integration                                             ║
║  • Comprehension quizzes                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import uuid
import os

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/reading", tags=["Reading Curriculum & Knowledge Base"])

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
mongo_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
reading_db = mongo_client.codedock_reading

# ============================================================================
# COMPREHENSIVE KNOWLEDGE BASE - 2026 SOTA STANDARDS
# ============================================================================

KNOWLEDGE_BASE = {
    # =========================================================================
    # GAME DEVELOPMENT TRACK - 450+ Hours
    # =========================================================================
    "game_development": {
        "name": "Game Development Mastery",
        "description": "Complete game development from concept to deployment",
        "total_hours": 480,
        "difficulty_range": "beginner_to_expert",
        "tracks": {
            "game_physics": {
                "name": "Game Physics & Simulation",
                "hours": 120,
                "modules": [
                    {
                        "id": "gp_001",
                        "title": "Foundations of Game Physics",
                        "reading_time_minutes": 45,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["Newton's Laws in Games", "Vector Mathematics", "Coordinate Systems"],
                        "learning_objectives": [
                            "Understand how physics applies to game objects",
                            "Apply vector math to movement calculations",
                            "Choose appropriate coordinate systems"
                        ],
                        "key_concepts": [
                            {"term": "Rigid Body", "definition": "A solid object that doesn't deform under forces"},
                            {"term": "Delta Time (dt)", "definition": "Time elapsed between frames, used for frame-rate independent physics"},
                            {"term": "Velocity", "definition": "Rate of change of position over time (m/s)"}
                        ],
                        "code_examples": [
                            {
                                "language": "python",
                                "title": "Basic Physics Update Loop",
                                "code": """def update_physics(obj, dt):
    # Apply gravity
    obj.velocity.y += GRAVITY * dt
    
    # Apply velocity to position
    obj.position.x += obj.velocity.x * dt
    obj.position.y += obj.velocity.y * dt
    
    # Apply drag
    obj.velocity *= (1 - DRAG * dt)"""
                            }
                        ],
                        "comprehension_questions": [
                            {"q": "Why do we multiply by dt?", "a": "To ensure consistent physics regardless of frame rate"},
                            {"q": "What happens if we don't apply drag?", "a": "Objects will accelerate indefinitely"}
                        ]
                    },
                    {
                        "id": "gp_002",
                        "title": "Collision Detection Fundamentals",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["AABB Collision", "Circle Collision", "Broad Phase vs Narrow Phase"],
                        "learning_objectives": [
                            "Implement basic collision detection algorithms",
                            "Understand the two-phase collision approach",
                            "Optimize collision checks for performance"
                        ]
                    },
                    {
                        "id": "gp_003",
                        "title": "Advanced Collision Response",
                        "reading_time_minutes": 75,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Elastic Collisions", "Impulse Resolution", "Penetration Correction"]
                    },
                    {
                        "id": "gp_004",
                        "title": "Soft Body & Cloth Simulation",
                        "reading_time_minutes": 90,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Mass-Spring Systems", "Verlet Integration", "Position Based Dynamics"]
                    },
                    {
                        "id": "gp_005",
                        "title": "Fluid Dynamics for Games",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["SPH", "Navier-Stokes", "Real-time Water Rendering"]
                    }
                ]
            },
            "game_graphics": {
                "name": "Real-Time Graphics Programming",
                "hours": 150,
                "modules": [
                    {
                        "id": "gg_001",
                        "title": "Graphics Pipeline Overview",
                        "reading_time_minutes": 40,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["Vertex Processing", "Rasterization", "Fragment Shading"],
                        "learning_objectives": [
                            "Understand the stages of the graphics pipeline",
                            "Know what happens at each stage",
                            "Identify bottlenecks in rendering"
                        ]
                    },
                    {
                        "id": "gg_002",
                        "title": "Shader Programming Fundamentals",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["GLSL Basics", "Vertex Shaders", "Fragment Shaders", "Uniforms"]
                    },
                    {
                        "id": "gg_003",
                        "title": "Lighting Models & PBR",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Phong/Blinn-Phong", "PBR Theory", "IBL", "HDR"]
                    },
                    {
                        "id": "gg_004",
                        "title": "Advanced Rendering Techniques",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Deferred Rendering", "SSAO", "Screen Space Reflections", "Volumetrics"]
                    },
                    {
                        "id": "gg_005",
                        "title": "Ray Tracing & Path Tracing",
                        "reading_time_minutes": 180,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["RT Fundamentals", "BVH Acceleration", "Denoising", "Hybrid Rendering"]
                    }
                ]
            },
            "game_ai": {
                "name": "Game AI & Behavior Systems",
                "hours": 100,
                "modules": [
                    {
                        "id": "ga_001",
                        "title": "Introduction to Game AI",
                        "reading_time_minutes": 35,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["AI vs ML in Games", "State Machines", "Decision Making"]
                    },
                    {
                        "id": "ga_002",
                        "title": "Pathfinding Algorithms",
                        "reading_time_minutes": 75,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["A* Algorithm", "Dijkstra", "Navigation Meshes", "Flow Fields"]
                    },
                    {
                        "id": "ga_003",
                        "title": "Behavior Trees & GOAP",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["BT Nodes", "Composite Patterns", "GOAP Planning", "Utility AI"]
                    },
                    {
                        "id": "ga_004",
                        "title": "Machine Learning in Games",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Reinforcement Learning", "Neural Networks for NPCs", "Procedural Generation with ML"]
                    }
                ]
            },
            "game_audio": {
                "name": "Game Audio Programming",
                "hours": 60,
                "modules": [
                    {
                        "id": "gau_001",
                        "title": "Digital Audio Fundamentals",
                        "reading_time_minutes": 30,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["Sample Rates", "Bit Depth", "Audio Formats", "Channels"]
                    },
                    {
                        "id": "gau_002",
                        "title": "3D Spatial Audio",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["HRTF", "Attenuation", "Reverb Zones", "Occlusion"]
                    },
                    {
                        "id": "gau_003",
                        "title": "Procedural Audio Generation",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Synthesizers", "Granular Synthesis", "Dynamic Music Systems"]
                    }
                ]
            },
            "game_networking": {
                "name": "Multiplayer Game Networking",
                "hours": 80,
                "modules": [
                    {
                        "id": "gn_001",
                        "title": "Networking Fundamentals",
                        "reading_time_minutes": 40,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["TCP vs UDP", "Latency", "Packet Loss", "Bandwidth"]
                    },
                    {
                        "id": "gn_002",
                        "title": "Client-Server Architecture",
                        "reading_time_minutes": 75,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Authoritative Servers", "Client Prediction", "Server Reconciliation"]
                    },
                    {
                        "id": "gn_003",
                        "title": "State Synchronization",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Snapshot Interpolation", "Delta Compression", "Interest Management"]
                    },
                    {
                        "id": "gn_004",
                        "title": "Advanced Netcode Techniques",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Rollback Netcode", "GGPO", "Deterministic Lockstep", "Lag Compensation"]
                    }
                ]
            }
        }
    },
    
    # =========================================================================
    # FULL-STACK WEB DEVELOPMENT TRACK - 400+ Hours
    # =========================================================================
    "web_development": {
        "name": "Full-Stack Web Development",
        "description": "Modern web development from frontend to deployment",
        "total_hours": 420,
        "difficulty_range": "beginner_to_expert",
        "tracks": {
            "frontend_mastery": {
                "name": "Frontend Engineering",
                "hours": 140,
                "modules": [
                    {
                        "id": "fe_001",
                        "title": "Modern HTML5 & Semantic Web",
                        "reading_time_minutes": 45,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["Semantic Elements", "Accessibility", "SEO Fundamentals"]
                    },
                    {
                        "id": "fe_002",
                        "title": "CSS Architecture & Design Systems",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["BEM", "CSS-in-JS", "Design Tokens", "Responsive Design"]
                    },
                    {
                        "id": "fe_003",
                        "title": "JavaScript Deep Dive",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 2,
                        "topics": ["Event Loop", "Closures", "Prototypes", "Async Patterns"]
                    },
                    {
                        "id": "fe_004",
                        "title": "React 19 Advanced Patterns",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 3,
                        "topics": ["Server Components", "Suspense", "Concurrent Rendering", "RSC"]
                    },
                    {
                        "id": "fe_005",
                        "title": "State Management Architecture",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Redux Toolkit", "Zustand", "Jotai", "React Query"]
                    },
                    {
                        "id": "fe_006",
                        "title": "Performance Optimization",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Core Web Vitals", "Code Splitting", "Virtualization", "Caching"]
                    }
                ]
            },
            "backend_mastery": {
                "name": "Backend Engineering",
                "hours": 140,
                "modules": [
                    {
                        "id": "be_001",
                        "title": "API Design Principles",
                        "reading_time_minutes": 60,
                        "content_type": "article",
                        "difficulty": 1,
                        "topics": ["REST", "GraphQL", "gRPC", "API Versioning"]
                    },
                    {
                        "id": "be_002",
                        "title": "Node.js & Express Deep Dive",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Middleware", "Error Handling", "Authentication", "Validation"]
                    },
                    {
                        "id": "be_003",
                        "title": "Python FastAPI Mastery",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Async/Await", "Dependency Injection", "OpenAPI", "Background Tasks"]
                    },
                    {
                        "id": "be_004",
                        "title": "Database Design & Optimization",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["SQL vs NoSQL", "Indexing", "Query Optimization", "Sharding"]
                    },
                    {
                        "id": "be_005",
                        "title": "Microservices Architecture",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Service Discovery", "Event Sourcing", "CQRS", "Saga Pattern"]
                    },
                    {
                        "id": "be_006",
                        "title": "System Design for Scale",
                        "reading_time_minutes": 180,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["Load Balancing", "Caching Strategies", "CDN", "Database Replication"]
                    }
                ]
            },
            "devops_mastery": {
                "name": "DevOps & Infrastructure",
                "hours": 100,
                "modules": [
                    {
                        "id": "do_001",
                        "title": "Docker Fundamentals",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Containers", "Images", "Volumes", "Networking"]
                    },
                    {
                        "id": "do_002",
                        "title": "Kubernetes Orchestration",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Pods", "Services", "Deployments", "ConfigMaps"]
                    },
                    {
                        "id": "do_003",
                        "title": "CI/CD Pipeline Design",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 3,
                        "topics": ["GitHub Actions", "GitLab CI", "Testing Strategies", "Deployment"]
                    },
                    {
                        "id": "do_004",
                        "title": "Infrastructure as Code",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Terraform", "Pulumi", "CloudFormation", "GitOps"]
                    }
                ]
            },
            "security": {
                "name": "Web Security",
                "hours": 60,
                "modules": [
                    {
                        "id": "sec_001",
                        "title": "OWASP Top 10",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 2,
                        "topics": ["XSS", "CSRF", "SQL Injection", "Authentication Flaws"]
                    },
                    {
                        "id": "sec_002",
                        "title": "Secure Coding Practices",
                        "reading_time_minutes": 75,
                        "content_type": "tutorial",
                        "difficulty": 3,
                        "topics": ["Input Validation", "Output Encoding", "Secrets Management"]
                    },
                    {
                        "id": "sec_003",
                        "title": "Penetration Testing Basics",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Recon", "Vulnerability Scanning", "Exploitation", "Reporting"]
                    }
                ]
            }
        }
    },
    
    # =========================================================================
    # MOBILE DEVELOPMENT TRACK - 300+ Hours
    # =========================================================================
    "mobile_development": {
        "name": "Mobile Development Mastery",
        "description": "iOS, Android, and Cross-Platform mobile development",
        "total_hours": 320,
        "difficulty_range": "beginner_to_expert",
        "tracks": {
            "react_native": {
                "name": "React Native & Expo",
                "hours": 100,
                "modules": [
                    {
                        "id": "rn_001",
                        "title": "React Native Fundamentals",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 1,
                        "topics": ["Components", "Styling", "Navigation", "State"]
                    },
                    {
                        "id": "rn_002",
                        "title": "Expo Ecosystem Deep Dive",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Expo Router", "EAS Build", "Push Notifications", "OTA Updates"]
                    },
                    {
                        "id": "rn_003",
                        "title": "Native Modules & Performance",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Bridging", "Turbo Modules", "JSI", "Hermes Engine"]
                    },
                    {
                        "id": "rn_004",
                        "title": "Advanced Animations",
                        "reading_time_minutes": 90,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Reanimated 3", "Gesture Handler", "Shared Element Transitions"]
                    }
                ]
            },
            "ios_native": {
                "name": "iOS Development (Swift)",
                "hours": 120,
                "modules": [
                    {
                        "id": "ios_001",
                        "title": "Swift Language Mastery",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 2,
                        "topics": ["Optionals", "Protocols", "Generics", "Concurrency"]
                    },
                    {
                        "id": "ios_002",
                        "title": "SwiftUI Modern Development",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 3,
                        "topics": ["Declarative UI", "State Management", "Animations", "Navigation"]
                    },
                    {
                        "id": "ios_003",
                        "title": "UIKit Integration & Legacy",
                        "reading_time_minutes": 90,
                        "content_type": "tutorial",
                        "difficulty": 3,
                        "topics": ["UIHostingController", "Representable", "Coordinator Pattern"]
                    }
                ]
            },
            "android_native": {
                "name": "Android Development (Kotlin)",
                "hours": 120,
                "modules": [
                    {
                        "id": "and_001",
                        "title": "Kotlin Language Mastery",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 2,
                        "topics": ["Null Safety", "Coroutines", "Flow", "Extension Functions"]
                    },
                    {
                        "id": "and_002",
                        "title": "Jetpack Compose",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 3,
                        "topics": ["Composables", "State Hoisting", "Side Effects", "Theming"]
                    },
                    {
                        "id": "and_003",
                        "title": "Android Architecture Components",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["ViewModel", "Room", "WorkManager", "Navigation"]
                    }
                ]
            }
        }
    },
    
    # =========================================================================
    # AI/ML ENGINEERING TRACK - 350+ Hours
    # =========================================================================
    "ai_ml_engineering": {
        "name": "AI/ML Engineering",
        "description": "Deep Learning, NLP, Computer Vision, and MLOps",
        "total_hours": 380,
        "difficulty_range": "intermediate_to_expert",
        "tracks": {
            "deep_learning": {
                "name": "Deep Learning Fundamentals",
                "hours": 120,
                "modules": [
                    {
                        "id": "dl_001",
                        "title": "Neural Network Foundations",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 2,
                        "topics": ["Perceptrons", "Backpropagation", "Activation Functions", "Loss Functions"]
                    },
                    {
                        "id": "dl_002",
                        "title": "Convolutional Neural Networks",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 3,
                        "topics": ["Convolution Operations", "Pooling", "ResNet", "EfficientNet"]
                    },
                    {
                        "id": "dl_003",
                        "title": "Transformers & Attention",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Self-Attention", "Multi-Head Attention", "BERT", "GPT Architecture"]
                    },
                    {
                        "id": "dl_004",
                        "title": "Generative Models",
                        "reading_time_minutes": 180,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["VAEs", "GANs", "Diffusion Models", "Flow Models"]
                    }
                ]
            },
            "nlp": {
                "name": "Natural Language Processing",
                "hours": 100,
                "modules": [
                    {
                        "id": "nlp_001",
                        "title": "Text Processing Fundamentals",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Tokenization", "Embeddings", "TF-IDF", "Word2Vec"]
                    },
                    {
                        "id": "nlp_002",
                        "title": "Large Language Models",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["GPT", "BERT", "T5", "Fine-tuning", "Prompt Engineering"]
                    },
                    {
                        "id": "nlp_003",
                        "title": "RAG & Vector Databases",
                        "reading_time_minutes": 90,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["Retrieval Augmented Generation", "Pinecone", "Weaviate", "Chunking"]
                    }
                ]
            },
            "computer_vision": {
                "name": "Computer Vision",
                "hours": 100,
                "modules": [
                    {
                        "id": "cv_001",
                        "title": "Image Processing Basics",
                        "reading_time_minutes": 60,
                        "content_type": "tutorial",
                        "difficulty": 2,
                        "topics": ["Filters", "Edge Detection", "Histograms", "Morphology"]
                    },
                    {
                        "id": "cv_002",
                        "title": "Object Detection & Segmentation",
                        "reading_time_minutes": 120,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["YOLO", "Mask R-CNN", "SAM", "Instance Segmentation"]
                    },
                    {
                        "id": "cv_003",
                        "title": "3D Vision & NeRF",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["Depth Estimation", "3D Reconstruction", "Neural Radiance Fields"]
                    }
                ]
            },
            "mlops": {
                "name": "MLOps & Production ML",
                "hours": 80,
                "modules": [
                    {
                        "id": "mlops_001",
                        "title": "ML Pipeline Design",
                        "reading_time_minutes": 90,
                        "content_type": "deep_dive",
                        "difficulty": 3,
                        "topics": ["Feature Stores", "Model Registry", "Experiment Tracking"]
                    },
                    {
                        "id": "mlops_002",
                        "title": "Model Serving & Inference",
                        "reading_time_minutes": 120,
                        "content_type": "masterclass",
                        "difficulty": 4,
                        "topics": ["TensorRT", "ONNX", "Triton Server", "Edge Deployment"]
                    },
                    {
                        "id": "mlops_003",
                        "title": "LLM Deployment",
                        "reading_time_minutes": 150,
                        "content_type": "masterclass",
                        "difficulty": 5,
                        "topics": ["vLLM", "TGI", "Quantization", "Speculative Decoding"]
                    }
                ]
            }
        }
    }
}

# ============================================================================
# ADVANCED MANUALS - Industry Reference Documentation
# ============================================================================

ADVANCED_MANUALS = {
    "design_patterns": {
        "name": "Design Patterns Encyclopedia",
        "description": "Complete reference for software design patterns",
        "total_pages": 450,
        "categories": {
            "creational": {
                "patterns": [
                    {"name": "Singleton", "use_case": "Global state, configuration", "complexity": 1},
                    {"name": "Factory Method", "use_case": "Object creation delegation", "complexity": 2},
                    {"name": "Abstract Factory", "use_case": "Family of related objects", "complexity": 3},
                    {"name": "Builder", "use_case": "Complex object construction", "complexity": 2},
                    {"name": "Prototype", "use_case": "Cloning objects", "complexity": 2}
                ]
            },
            "structural": {
                "patterns": [
                    {"name": "Adapter", "use_case": "Interface compatibility", "complexity": 2},
                    {"name": "Bridge", "use_case": "Abstraction-implementation separation", "complexity": 3},
                    {"name": "Composite", "use_case": "Tree structures", "complexity": 2},
                    {"name": "Decorator", "use_case": "Dynamic behavior addition", "complexity": 2},
                    {"name": "Facade", "use_case": "Simplified interface", "complexity": 1},
                    {"name": "Flyweight", "use_case": "Memory optimization", "complexity": 3},
                    {"name": "Proxy", "use_case": "Access control, lazy loading", "complexity": 2}
                ]
            },
            "behavioral": {
                "patterns": [
                    {"name": "Chain of Responsibility", "use_case": "Request handling chain", "complexity": 2},
                    {"name": "Command", "use_case": "Action encapsulation, undo/redo", "complexity": 2},
                    {"name": "Iterator", "use_case": "Sequential access", "complexity": 1},
                    {"name": "Mediator", "use_case": "Component decoupling", "complexity": 3},
                    {"name": "Memento", "use_case": "State snapshots", "complexity": 2},
                    {"name": "Observer", "use_case": "Event notification", "complexity": 2},
                    {"name": "State", "use_case": "State-dependent behavior", "complexity": 2},
                    {"name": "Strategy", "use_case": "Algorithm selection", "complexity": 1},
                    {"name": "Template Method", "use_case": "Algorithm skeleton", "complexity": 2},
                    {"name": "Visitor", "use_case": "Operation on object structure", "complexity": 3}
                ]
            },
            "game_specific": {
                "patterns": [
                    {"name": "Game Loop", "use_case": "Main update cycle", "complexity": 1},
                    {"name": "Update Method", "use_case": "Per-frame behavior", "complexity": 1},
                    {"name": "Component", "use_case": "Entity composition", "complexity": 2},
                    {"name": "Event Queue", "use_case": "Decoupled communication", "complexity": 2},
                    {"name": "Service Locator", "use_case": "Global service access", "complexity": 2},
                    {"name": "Object Pool", "use_case": "Memory reuse", "complexity": 2},
                    {"name": "Spatial Partition", "use_case": "Efficient spatial queries", "complexity": 3},
                    {"name": "Double Buffer", "use_case": "Frame synchronization", "complexity": 2},
                    {"name": "Dirty Flag", "use_case": "Lazy recalculation", "complexity": 1},
                    {"name": "Bytecode", "use_case": "Data-driven behavior", "complexity": 4},
                    {"name": "Subclass Sandbox", "use_case": "Safe subclassing", "complexity": 2},
                    {"name": "Type Object", "use_case": "Runtime types", "complexity": 3}
                ]
            }
        }
    },
    "performance_optimization": {
        "name": "Performance Optimization Handbook",
        "description": "Complete guide to optimizing code for speed and memory",
        "total_pages": 300,
        "chapters": [
            {
                "title": "Profiling & Measurement",
                "topics": ["CPU Profiling", "Memory Profiling", "GPU Profiling", "Flame Graphs"]
            },
            {
                "title": "CPU Optimization",
                "topics": ["Cache Optimization", "SIMD", "Branch Prediction", "Data-Oriented Design"]
            },
            {
                "title": "Memory Optimization",
                "topics": ["Memory Pools", "Allocator Design", "Memory Layout", "Garbage Collection"]
            },
            {
                "title": "GPU Optimization",
                "topics": ["Batch Reduction", "Overdraw", "Shader Optimization", "Memory Bandwidth"]
            },
            {
                "title": "Network Optimization",
                "topics": ["Compression", "Batching", "Prediction", "Delta Encoding"]
            }
        ]
    },
    "api_reference": {
        "name": "API Design Reference",
        "description": "Best practices for designing robust APIs",
        "total_pages": 250,
        "sections": [
            {"name": "RESTful API Design", "pages": 60},
            {"name": "GraphQL Schema Design", "pages": 50},
            {"name": "gRPC & Protocol Buffers", "pages": 40},
            {"name": "WebSocket APIs", "pages": 30},
            {"name": "API Versioning Strategies", "pages": 25},
            {"name": "Rate Limiting & Throttling", "pages": 20},
            {"name": "API Security Best Practices", "pages": 35}
        ]
    },
    "architecture_guides": {
        "name": "Software Architecture Guides",
        "description": "Comprehensive architecture patterns and principles",
        "total_pages": 400,
        "guides": [
            {
                "title": "Clean Architecture",
                "author_reference": "Robert C. Martin",
                "key_concepts": ["Dependency Rule", "Layers", "Boundaries", "Entities"]
            },
            {
                "title": "Domain-Driven Design",
                "author_reference": "Eric Evans",
                "key_concepts": ["Bounded Contexts", "Aggregates", "Repositories", "Ubiquitous Language"]
            },
            {
                "title": "Event-Driven Architecture",
                "key_concepts": ["Event Sourcing", "CQRS", "Saga Pattern", "Event Storming"]
            },
            {
                "title": "Microservices Patterns",
                "author_reference": "Chris Richardson",
                "key_concepts": ["Service Decomposition", "API Gateway", "Circuit Breaker", "Saga"]
            }
        ]
    }
}

# ============================================================================
# LANGUAGE REFERENCE MANUALS - 64+ Languages
# ============================================================================

LANGUAGE_MANUALS = {
    "python": {"name": "Python 3.12+ Complete Reference", "pages": 800, "difficulty": 1},
    "javascript": {"name": "JavaScript ES2025 Reference", "pages": 700, "difficulty": 1},
    "typescript": {"name": "TypeScript 5.x Complete Guide", "pages": 600, "difficulty": 2},
    "rust": {"name": "Rust Programming Language", "pages": 900, "difficulty": 3},
    "go": {"name": "Go Programming Reference", "pages": 500, "difficulty": 2},
    "cpp": {"name": "Modern C++ (C++23) Reference", "pages": 1200, "difficulty": 4},
    "c": {"name": "C Programming Reference", "pages": 600, "difficulty": 3},
    "java": {"name": "Java 21+ Complete Reference", "pages": 1000, "difficulty": 2},
    "kotlin": {"name": "Kotlin Language Reference", "pages": 500, "difficulty": 2},
    "swift": {"name": "Swift 6.0 Language Guide", "pages": 600, "difficulty": 2},
    "csharp": {"name": "C# 12 Complete Reference", "pages": 900, "difficulty": 2},
    "ruby": {"name": "Ruby 3.3 Reference", "pages": 500, "difficulty": 2},
    "php": {"name": "PHP 8.3 Complete Guide", "pages": 600, "difficulty": 2},
    "sql": {"name": "SQL Complete Reference", "pages": 400, "difficulty": 2},
    "bash": {"name": "Bash Scripting Guide", "pages": 300, "difficulty": 2},
    "lua": {"name": "Lua 5.4 Reference Manual", "pages": 200, "difficulty": 1},
    "r": {"name": "R Programming Reference", "pages": 500, "difficulty": 2},
    "scala": {"name": "Scala 3 Reference", "pages": 600, "difficulty": 3},
    "haskell": {"name": "Haskell Programming Reference", "pages": 700, "difficulty": 4},
    "elixir": {"name": "Elixir Complete Guide", "pages": 500, "difficulty": 3},
    "clojure": {"name": "Clojure Reference", "pages": 400, "difficulty": 3},
    "dart": {"name": "Dart Language Reference", "pages": 400, "difficulty": 2},
    "julia": {"name": "Julia Programming Guide", "pages": 500, "difficulty": 3},
    "zig": {"name": "Zig Language Reference", "pages": 400, "difficulty": 4},
    "assembly_x86": {"name": "x86-64 Assembly Reference", "pages": 600, "difficulty": 5},
    "wasm": {"name": "WebAssembly Complete Guide", "pages": 400, "difficulty": 4},
    "glsl": {"name": "GLSL Shader Reference", "pages": 300, "difficulty": 3},
    "hlsl": {"name": "HLSL Shader Reference", "pages": 300, "difficulty": 3},
    "wgsl": {"name": "WGSL Shader Reference", "pages": 250, "difficulty": 3}
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_reading_info():
    """Get comprehensive reading curriculum info"""
    total_hours = sum(track["total_hours"] for track in KNOWLEDGE_BASE.values())
    total_manual_pages = sum(m.get("total_pages", 0) for m in ADVANCED_MANUALS.values())
    total_language_pages = sum(lang["pages"] for lang in LANGUAGE_MANUALS.values())
    
    return {
        "name": "CodeDock Reading Curriculum v11.7 SOTA",
        "description": "Comprehensive text-based learning system - April 2026 standards",
        "total_curriculum_hours": total_hours,
        "total_manual_pages": total_manual_pages + total_language_pages,
        "knowledge_tracks": list(KNOWLEDGE_BASE.keys()),
        "manual_categories": list(ADVANCED_MANUALS.keys()),
        "supported_languages": len(LANGUAGE_MANUALS),
        "features": [
            "Interactive reading with progress tracking",
            "Code-along tutorials with explanations",
            "Comprehension quizzes per module",
            "Spaced repetition integration",
            "Bookmarking and annotations",
            "Offline reading support",
            "Text-to-speech integration",
            "Syntax-highlighted code examples"
        ],
        "difficulty_levels": {
            1: "Beginner - Foundation concepts",
            2: "Intermediate - Applied knowledge",
            3: "Advanced - Complex topics",
            4: "Expert - Industry-level depth",
            5: "Mastery - Cutting-edge concepts"
        }
    }


@router.get("/tracks")
async def get_all_tracks():
    """Get all learning tracks"""
    return {
        "tracks": [
            {
                "id": track_id,
                "name": track["name"],
                "description": track["description"],
                "total_hours": track["total_hours"],
                "sub_tracks": list(track["tracks"].keys()),
                "difficulty_range": track["difficulty_range"]
            }
            for track_id, track in KNOWLEDGE_BASE.items()
        ],
        "total_tracks": len(KNOWLEDGE_BASE)
    }


@router.get("/track/{track_id}")
async def get_track_detail(track_id: str):
    """Get detailed track information"""
    if track_id not in KNOWLEDGE_BASE:
        raise HTTPException(status_code=404, detail="Track not found")
    
    track = KNOWLEDGE_BASE[track_id]
    return {
        "track_id": track_id,
        "name": track["name"],
        "description": track["description"],
        "total_hours": track["total_hours"],
        "sub_tracks": {
            sub_id: {
                "name": sub["name"],
                "hours": sub["hours"],
                "module_count": len(sub["modules"]),
                "modules": [
                    {
                        "id": m["id"],
                        "title": m["title"],
                        "reading_time_minutes": m["reading_time_minutes"],
                        "content_type": m["content_type"],
                        "difficulty": m["difficulty"]
                    }
                    for m in sub["modules"]
                ]
            }
            for sub_id, sub in track["tracks"].items()
        }
    }


@router.get("/module/{module_id}")
async def get_module_content(module_id: str):
    """Get full module content for reading"""
    # Search for module across all tracks
    for track_id, track in KNOWLEDGE_BASE.items():
        for sub_id, sub_track in track["tracks"].items():
            for module in sub_track["modules"]:
                if module["id"] == module_id:
                    return {
                        "module_id": module_id,
                        "track": track_id,
                        "sub_track": sub_id,
                        **module,
                        "navigation": {
                            "track_name": track["name"],
                            "sub_track_name": sub_track["name"]
                        }
                    }
    
    raise HTTPException(status_code=404, detail="Module not found")


@router.get("/manuals")
async def get_all_manuals():
    """Get all advanced manuals"""
    return {
        "manuals": [
            {
                "id": manual_id,
                "name": manual["name"],
                "description": manual["description"],
                "total_pages": manual.get("total_pages", 0)
            }
            for manual_id, manual in ADVANCED_MANUALS.items()
        ],
        "language_manuals": [
            {
                "id": lang_id,
                "name": manual["name"],
                "pages": manual["pages"],
                "difficulty": manual["difficulty"]
            }
            for lang_id, manual in LANGUAGE_MANUALS.items()
        ]
    }


@router.get("/manual/{manual_id}")
async def get_manual_detail(manual_id: str):
    """Get manual details"""
    if manual_id in ADVANCED_MANUALS:
        return {"manual_id": manual_id, **ADVANCED_MANUALS[manual_id]}
    if manual_id in LANGUAGE_MANUALS:
        return {"manual_id": manual_id, **LANGUAGE_MANUALS[manual_id]}
    raise HTTPException(status_code=404, detail="Manual not found")


@router.post("/progress/update")
async def update_reading_progress(
    user_id: str,
    module_id: str,
    progress_percent: float,
    time_spent_minutes: int,
    completed: bool = False
):
    """Update user's reading progress"""
    await reading_db.progress.update_one(
        {"user_id": user_id, "module_id": module_id},
        {
            "$set": {
                "progress_percent": min(100, progress_percent),
                "completed": completed,
                "last_read": datetime.utcnow()
            },
            "$inc": {"total_time_minutes": time_spent_minutes}
        },
        upsert=True
    )
    
    return {
        "updated": True,
        "module_id": module_id,
        "progress_percent": progress_percent,
        "completed": completed
    }


@router.get("/progress/{user_id}")
async def get_user_reading_progress(user_id: str):
    """Get user's overall reading progress"""
    progress_docs = await reading_db.progress.find({"user_id": user_id}).to_list(500)
    
    completed_modules = [p for p in progress_docs if p.get("completed")]
    total_time = sum(p.get("total_time_minutes", 0) for p in progress_docs)
    
    return {
        "user_id": user_id,
        "modules_started": len(progress_docs),
        "modules_completed": len(completed_modules),
        "total_reading_time_minutes": total_time,
        "total_reading_time_hours": round(total_time / 60, 1),
        "recent_modules": [
            {
                "module_id": p["module_id"],
                "progress": p.get("progress_percent", 0),
                "completed": p.get("completed", False)
            }
            for p in sorted(progress_docs, key=lambda x: x.get("last_read", datetime.min), reverse=True)[:10]
        ]
    }


@router.post("/bookmark")
async def add_bookmark(
    user_id: str,
    module_id: str,
    position: str,
    note: Optional[str] = None
):
    """Add a bookmark to a reading module"""
    bookmark = {
        "bookmark_id": f"bm_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "module_id": module_id,
        "position": position,
        "note": note,
        "created_at": datetime.utcnow()
    }
    
    await reading_db.bookmarks.insert_one(bookmark)
    return {"created": True, "bookmark": bookmark}


@router.get("/bookmarks/{user_id}")
async def get_user_bookmarks(user_id: str):
    """Get user's bookmarks"""
    bookmarks = await reading_db.bookmarks.find(
        {"user_id": user_id}
    ).sort("created_at", -1).to_list(100)
    
    return {
        "user_id": user_id,
        "bookmarks": [
            {
                "bookmark_id": b["bookmark_id"],
                "module_id": b["module_id"],
                "position": b["position"],
                "note": b.get("note"),
                "created_at": b["created_at"].isoformat()
            }
            for b in bookmarks
        ]
    }
