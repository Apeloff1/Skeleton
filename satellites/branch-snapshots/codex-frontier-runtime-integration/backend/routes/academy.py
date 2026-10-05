"""
Academy Routes - Comprehensive Learning Content API
Version: 2.0.0 | Extended Curriculum
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/academy", tags=["academy"])

# =============================================================================
# DATA MODELS
# =============================================================================

class LessonContent(BaseModel):
    id: str
    title: str
    description: str
    duration_minutes: int
    difficulty: str  # beginner, intermediate, advanced, expert
    topics: List[str]
    prerequisites: List[str] = []
    resources: List[Dict[str, str]] = []

class CourseModule(BaseModel):
    id: str
    name: str
    description: str
    lessons: List[LessonContent]
    total_hours: float

class AcademyTopic(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    color: str
    total_hours: int
    modules: List[CourseModule]
    certifications: List[str] = []

# =============================================================================
# KNOWLEDGE BIBLES DATA
# =============================================================================

KNOWLEDGE_BIBLES = {
    "system_design": AcademyTopic(
        id="system_design",
        name="System Design Bible",
        description="Master large-scale system architecture patterns",
        icon="git-branch",
        color="#3B82F6",
        total_hours=180,
        modules=[
            CourseModule(
                id="sd_fundamentals",
                name="Fundamentals",
                description="Core system design concepts",
                total_hours=30,
                lessons=[
                    LessonContent(id="sd_1", title="Scalability Basics", description="Horizontal vs Vertical scaling", duration_minutes=45, difficulty="beginner", topics=["scaling", "architecture"]),
                    LessonContent(id="sd_2", title="Load Balancing", description="Distribute traffic effectively", duration_minutes=60, difficulty="intermediate", topics=["load-balancer", "nginx", "haproxy"]),
                    LessonContent(id="sd_3", title="Caching Strategies", description="Redis, Memcached, CDN", duration_minutes=75, difficulty="intermediate", topics=["redis", "caching", "cdn"]),
                    LessonContent(id="sd_4", title="Database Sharding", description="Partition data across servers", duration_minutes=90, difficulty="advanced", topics=["sharding", "partitioning"]),
                    LessonContent(id="sd_5", title="Message Queues", description="Kafka, RabbitMQ, SQS", duration_minutes=60, difficulty="intermediate", topics=["kafka", "rabbitmq", "async"]),
                ]
            ),
            CourseModule(
                id="sd_patterns",
                name="Design Patterns",
                description="Common architectural patterns",
                total_hours=50,
                lessons=[
                    LessonContent(id="sd_p1", title="Microservices", description="Service-oriented architecture", duration_minutes=120, difficulty="advanced", topics=["microservices", "docker", "kubernetes"]),
                    LessonContent(id="sd_p2", title="Event Sourcing", description="Event-driven architecture", duration_minutes=90, difficulty="advanced", topics=["events", "cqrs"]),
                    LessonContent(id="sd_p3", title="API Gateway", description="Centralized API management", duration_minutes=60, difficulty="intermediate", topics=["api", "gateway", "kong"]),
                ]
            ),
        ],
        certifications=["AWS Solutions Architect", "Google Cloud Professional"]
    ),
    "ml_ai": AcademyTopic(
        id="ml_ai",
        name="ML/AI Bible",
        description="Complete machine learning and AI mastery",
        icon="hardware-chip",
        color="#8B5CF6",
        total_hours=400,
        modules=[
            CourseModule(
                id="ml_foundations",
                name="ML Foundations",
                description="Mathematical foundations of ML",
                total_hours=80,
                lessons=[
                    LessonContent(id="ml_1", title="Linear Algebra for ML", description="Vectors, matrices, transformations", duration_minutes=120, difficulty="beginner", topics=["math", "linear-algebra"]),
                    LessonContent(id="ml_2", title="Probability & Statistics", description="Distributions, Bayes theorem", duration_minutes=90, difficulty="beginner", topics=["probability", "statistics"]),
                    LessonContent(id="ml_3", title="Calculus for ML", description="Gradients and optimization", duration_minutes=90, difficulty="intermediate", topics=["calculus", "optimization"]),
                ]
            ),
            CourseModule(
                id="ml_supervised",
                name="Supervised Learning",
                description="Classification and regression",
                total_hours=100,
                lessons=[
                    LessonContent(id="ml_s1", title="Linear Regression", description="Predictive modeling basics", duration_minutes=60, difficulty="beginner", topics=["regression", "sklearn"]),
                    LessonContent(id="ml_s2", title="Decision Trees", description="Tree-based algorithms", duration_minutes=75, difficulty="intermediate", topics=["trees", "random-forest"]),
                    LessonContent(id="ml_s3", title="Neural Networks", description="Deep learning fundamentals", duration_minutes=120, difficulty="advanced", topics=["neural-networks", "pytorch", "tensorflow"]),
                    LessonContent(id="ml_s4", title="Transformers", description="Attention mechanisms", duration_minutes=150, difficulty="expert", topics=["transformers", "bert", "gpt"]),
                ]
            ),
            CourseModule(
                id="ml_deep",
                name="Deep Learning",
                description="Advanced neural architectures",
                total_hours=120,
                lessons=[
                    LessonContent(id="ml_d1", title="CNNs", description="Computer vision", duration_minutes=90, difficulty="advanced", topics=["cnn", "vision", "resnet"]),
                    LessonContent(id="ml_d2", title="RNNs & LSTMs", description="Sequence modeling", duration_minutes=90, difficulty="advanced", topics=["rnn", "lstm", "gru"]),
                    LessonContent(id="ml_d3", title="GANs", description="Generative models", duration_minutes=120, difficulty="expert", topics=["gan", "generation"]),
                    LessonContent(id="ml_d4", title="Reinforcement Learning", description="Agent-based learning", duration_minutes=150, difficulty="expert", topics=["rl", "q-learning", "ppo"]),
                ]
            ),
        ],
        certifications=["TensorFlow Developer", "AWS ML Specialty", "Google ML Engineer"]
    ),
    "security": AcademyTopic(
        id="security",
        name="Security Bible",
        description="Cybersecurity essentials and best practices",
        icon="shield",
        color="#EF4444",
        total_hours=220,
        modules=[
            CourseModule(
                id="sec_fundamentals",
                name="Security Fundamentals",
                description="Core security concepts",
                total_hours=40,
                lessons=[
                    LessonContent(id="sec_1", title="CIA Triad", description="Confidentiality, Integrity, Availability", duration_minutes=45, difficulty="beginner", topics=["fundamentals"]),
                    LessonContent(id="sec_2", title="Cryptography Basics", description="Encryption, hashing, signatures", duration_minutes=90, difficulty="intermediate", topics=["crypto", "encryption"]),
                    LessonContent(id="sec_3", title="Authentication", description="OAuth, JWT, MFA", duration_minutes=60, difficulty="intermediate", topics=["auth", "oauth", "jwt"]),
                ]
            ),
            CourseModule(
                id="sec_offensive",
                name="Offensive Security",
                description="Ethical hacking techniques",
                total_hours=80,
                lessons=[
                    LessonContent(id="sec_o1", title="Penetration Testing", description="Methodology and tools", duration_minutes=120, difficulty="advanced", topics=["pentest", "kali"]),
                    LessonContent(id="sec_o2", title="Web Vulnerabilities", description="OWASP Top 10", duration_minutes=90, difficulty="advanced", topics=["owasp", "xss", "sqli"]),
                    LessonContent(id="sec_o3", title="Network Attacks", description="Man-in-the-middle, sniffing", duration_minutes=90, difficulty="advanced", topics=["network", "wireshark"]),
                ]
            ),
        ],
        certifications=["CISSP", "CEH", "OSCP", "CompTIA Security+"]
    ),
    "devops": AcademyTopic(
        id="devops",
        name="DevOps Bible",
        description="CI/CD, containers, and cloud infrastructure",
        icon="cloud",
        color="#10B981",
        total_hours=280,
        modules=[
            CourseModule(
                id="devops_containers",
                name="Containers & Orchestration",
                description="Docker and Kubernetes mastery",
                total_hours=80,
                lessons=[
                    LessonContent(id="do_1", title="Docker Fundamentals", description="Images, containers, compose", duration_minutes=90, difficulty="beginner", topics=["docker", "containers"]),
                    LessonContent(id="do_2", title="Kubernetes Basics", description="Pods, services, deployments", duration_minutes=120, difficulty="intermediate", topics=["kubernetes", "k8s"]),
                    LessonContent(id="do_3", title="Helm Charts", description="Package management for K8s", duration_minutes=60, difficulty="intermediate", topics=["helm", "charts"]),
                    LessonContent(id="do_4", title="Service Mesh", description="Istio and Linkerd", duration_minutes=90, difficulty="advanced", topics=["istio", "service-mesh"]),
                ]
            ),
            CourseModule(
                id="devops_cicd",
                name="CI/CD Pipelines",
                description="Automated deployment workflows",
                total_hours=60,
                lessons=[
                    LessonContent(id="do_c1", title="GitHub Actions", description="Workflow automation", duration_minutes=60, difficulty="beginner", topics=["github", "actions"]),
                    LessonContent(id="do_c2", title="Jenkins", description="Enterprise CI/CD", duration_minutes=90, difficulty="intermediate", topics=["jenkins", "pipelines"]),
                    LessonContent(id="do_c3", title="GitOps", description="ArgoCD and Flux", duration_minutes=75, difficulty="advanced", topics=["gitops", "argocd"]),
                ]
            ),
        ],
        certifications=["CKA", "CKS", "AWS DevOps Pro", "Terraform Associate"]
    ),
    "frontend": AcademyTopic(
        id="frontend",
        name="Frontend Bible",
        description="Modern web frontend development",
        icon="tablet-portrait",
        color="#F59E0B",
        total_hours=350,
        modules=[
            CourseModule(
                id="fe_react",
                name="React Mastery",
                description="Complete React ecosystem",
                total_hours=120,
                lessons=[
                    LessonContent(id="fe_r1", title="React Fundamentals", description="Components, props, state", duration_minutes=90, difficulty="beginner", topics=["react", "jsx"]),
                    LessonContent(id="fe_r2", title="Hooks Deep Dive", description="useState, useEffect, custom hooks", duration_minutes=120, difficulty="intermediate", topics=["hooks", "state"]),
                    LessonContent(id="fe_r3", title="State Management", description="Redux, Zustand, Jotai", duration_minutes=90, difficulty="intermediate", topics=["redux", "zustand"]),
                    LessonContent(id="fe_r4", title="Next.js", description="Server-side rendering", duration_minutes=120, difficulty="advanced", topics=["nextjs", "ssr"]),
                ]
            ),
            CourseModule(
                id="fe_styling",
                name="Modern Styling",
                description="CSS-in-JS and design systems",
                total_hours=60,
                lessons=[
                    LessonContent(id="fe_s1", title="Tailwind CSS", description="Utility-first CSS", duration_minutes=60, difficulty="beginner", topics=["tailwind", "css"]),
                    LessonContent(id="fe_s2", title="Styled Components", description="CSS-in-JS patterns", duration_minutes=45, difficulty="intermediate", topics=["styled-components"]),
                    LessonContent(id="fe_s3", title="Design Systems", description="Building component libraries", duration_minutes=90, difficulty="advanced", topics=["design-system", "storybook"]),
                ]
            ),
        ],
        certifications=["Meta Frontend Developer", "React Certification"]
    ),
    "backend": AcademyTopic(
        id="backend",
        name="Backend Bible",
        description="Server-side development mastery",
        icon="server",
        color="#6366F1",
        total_hours=420,
        modules=[
            CourseModule(
                id="be_node",
                name="Node.js Ecosystem",
                description="JavaScript backend development",
                total_hours=100,
                lessons=[
                    LessonContent(id="be_n1", title="Node.js Fundamentals", description="Event loop, modules, streams", duration_minutes=90, difficulty="beginner", topics=["nodejs", "javascript"]),
                    LessonContent(id="be_n2", title="Express.js", description="REST API development", duration_minutes=75, difficulty="intermediate", topics=["express", "rest"]),
                    LessonContent(id="be_n3", title="NestJS", description="Enterprise Node.js", duration_minutes=120, difficulty="advanced", topics=["nestjs", "typescript"]),
                ]
            ),
            CourseModule(
                id="be_python",
                name="Python Backend",
                description="FastAPI and Django",
                total_hours=100,
                lessons=[
                    LessonContent(id="be_p1", title="FastAPI", description="Modern Python APIs", duration_minutes=90, difficulty="intermediate", topics=["fastapi", "python"]),
                    LessonContent(id="be_p2", title="Django", description="Full-featured framework", duration_minutes=120, difficulty="intermediate", topics=["django", "orm"]),
                    LessonContent(id="be_p3", title="Async Python", description="asyncio, aiohttp", duration_minutes=90, difficulty="advanced", topics=["async", "asyncio"]),
                ]
            ),
            CourseModule(
                id="be_go",
                name="Go Backend",
                description="High-performance services",
                total_hours=80,
                lessons=[
                    LessonContent(id="be_g1", title="Go Fundamentals", description="Goroutines, channels", duration_minutes=90, difficulty="intermediate", topics=["go", "concurrency"]),
                    LessonContent(id="be_g2", title="Gin Framework", description="REST APIs in Go", duration_minutes=60, difficulty="intermediate", topics=["gin", "rest"]),
                    LessonContent(id="be_g3", title="gRPC", description="High-performance RPC", duration_minutes=90, difficulty="advanced", topics=["grpc", "protobuf"]),
                ]
            ),
        ],
        certifications=["AWS Backend Developer", "Node.js Certification"]
    ),
    "database": AcademyTopic(
        id="database",
        name="Database Bible",
        description="SQL, NoSQL, and data modeling",
        icon="server",
        color="#EC4899",
        total_hours=200,
        modules=[
            CourseModule(
                id="db_sql",
                name="SQL Mastery",
                description="Relational databases",
                total_hours=70,
                lessons=[
                    LessonContent(id="db_s1", title="SQL Fundamentals", description="Queries, joins, subqueries", duration_minutes=90, difficulty="beginner", topics=["sql", "postgres"]),
                    LessonContent(id="db_s2", title="Database Design", description="Normalization, ER diagrams", duration_minutes=75, difficulty="intermediate", topics=["design", "modeling"]),
                    LessonContent(id="db_s3", title="Query Optimization", description="Indexes, explain plans", duration_minutes=90, difficulty="advanced", topics=["optimization", "indexes"]),
                    LessonContent(id="db_s4", title="Transactions", description="ACID, isolation levels", duration_minutes=60, difficulty="intermediate", topics=["transactions", "acid"]),
                ]
            ),
            CourseModule(
                id="db_nosql",
                name="NoSQL Databases",
                description="Document, key-value, graph",
                total_hours=70,
                lessons=[
                    LessonContent(id="db_n1", title="MongoDB", description="Document databases", duration_minutes=90, difficulty="intermediate", topics=["mongodb", "document"]),
                    LessonContent(id="db_n2", title="Redis", description="In-memory data store", duration_minutes=60, difficulty="intermediate", topics=["redis", "caching"]),
                    LessonContent(id="db_n3", title="Neo4j", description="Graph databases", duration_minutes=90, difficulty="advanced", topics=["neo4j", "graph"]),
                    LessonContent(id="db_n4", title="DynamoDB", description="AWS NoSQL service", duration_minutes=75, difficulty="intermediate", topics=["dynamodb", "aws"]),
                ]
            ),
        ],
        certifications=["AWS Database Specialty", "MongoDB Certified Developer"]
    ),
    "graphics": AcademyTopic(
        id="graphics",
        name="Graphics Academy",
        description="OpenGL, WebGL, and shader programming",
        icon="color-palette",
        color="#F97316",
        total_hours=280,
        modules=[
            CourseModule(
                id="gfx_fundamentals",
                name="Graphics Fundamentals",
                description="Core 3D graphics concepts",
                total_hours=60,
                lessons=[
                    LessonContent(id="gfx_1", title="3D Math", description="Vectors, matrices, quaternions", duration_minutes=120, difficulty="intermediate", topics=["math", "3d"]),
                    LessonContent(id="gfx_2", title="Rendering Pipeline", description="Vertex to pixel", duration_minutes=90, difficulty="intermediate", topics=["pipeline", "rendering"]),
                    LessonContent(id="gfx_3", title="Lighting Models", description="Phong, PBR", duration_minutes=90, difficulty="advanced", topics=["lighting", "pbr"]),
                ]
            ),
            CourseModule(
                id="gfx_shaders",
                name="Shader Programming",
                description="GLSL and HLSL",
                total_hours=100,
                lessons=[
                    LessonContent(id="gfx_s1", title="GLSL Basics", description="Vertex and fragment shaders", duration_minutes=90, difficulty="intermediate", topics=["glsl", "shaders"]),
                    LessonContent(id="gfx_s2", title="Post-Processing", description="Bloom, blur, DOF", duration_minutes=75, difficulty="advanced", topics=["post-processing", "effects"]),
                    LessonContent(id="gfx_s3", title="Ray Marching", description="SDF and procedural graphics", duration_minutes=120, difficulty="expert", topics=["raymarching", "sdf"]),
                ]
            ),
        ],
        certifications=["Unity Graphics Certification"]
    ),
}

# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/topics")
async def get_all_topics():
    """Get list of all academy topics"""
    topics = []
    for key, topic in KNOWLEDGE_BIBLES.items():
        topics.append({
            "id": topic.id,
            "name": topic.name,
            "description": topic.description,
            "icon": topic.icon,
            "color": topic.color,
            "total_hours": topic.total_hours,
            "module_count": len(topic.modules),
            "certifications": topic.certifications
        })
    return {"topics": topics, "total_count": len(topics)}

@router.get("/topic/{topic_id}")
async def get_topic_details(topic_id: str):
    """Get detailed content for a specific topic"""
    if topic_id not in KNOWLEDGE_BIBLES:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    
    topic = KNOWLEDGE_BIBLES[topic_id]
    return {
        "topic": topic.dict(),
        "total_lessons": sum(len(m.lessons) for m in topic.modules),
        "estimated_completion_weeks": topic.total_hours // 10  # 10 hrs/week
    }

@router.get("/topic/{topic_id}/module/{module_id}")
async def get_module_content(topic_id: str, module_id: str):
    """Get lessons for a specific module"""
    if topic_id not in KNOWLEDGE_BIBLES:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    
    topic = KNOWLEDGE_BIBLES[topic_id]
    module = next((m for m in topic.modules if m.id == module_id), None)
    
    if not module:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")
    
    return {"module": module.dict(), "topic_name": topic.name}

@router.get("/language-tracks")
async def get_language_tracks():
    """Get available programming language learning tracks"""
    tracks = [
        {
            "id": "python",
            "name": "Python Track",
            "description": "From basics to advanced Python",
            "total_hours": 200,
            "levels": ["Beginner", "Intermediate", "Advanced", "Expert"],
            "topics": ["Syntax", "OOP", "Async", "Data Science", "Web", "ML"],
            "projects": 15,
            "icon": "logo-python",
            "color": "#3776AB"
        },
        {
            "id": "javascript",
            "name": "JavaScript Track",
            "description": "Full JavaScript ecosystem mastery",
            "total_hours": 250,
            "levels": ["Beginner", "Intermediate", "Advanced", "Expert"],
            "topics": ["ES6+", "Node.js", "React", "TypeScript", "Testing"],
            "projects": 20,
            "icon": "logo-javascript",
            "color": "#F7DF1E"
        },
        {
            "id": "rust",
            "name": "Rust Track",
            "description": "Systems programming with Rust",
            "total_hours": 180,
            "levels": ["Beginner", "Intermediate", "Advanced"],
            "topics": ["Ownership", "Lifetimes", "Concurrency", "WebAssembly"],
            "projects": 12,
            "icon": "construct",
            "color": "#DEA584"
        },
        {
            "id": "go",
            "name": "Go Track",
            "description": "Cloud-native development with Go",
            "total_hours": 150,
            "levels": ["Beginner", "Intermediate", "Advanced"],
            "topics": ["Goroutines", "Channels", "Web Services", "CLI Tools"],
            "projects": 10,
            "icon": "rocket",
            "color": "#00ADD8"
        },
        {
            "id": "cpp",
            "name": "C++ Track",
            "description": "Performance-critical applications",
            "total_hours": 300,
            "levels": ["Beginner", "Intermediate", "Advanced", "Expert"],
            "topics": ["Modern C++", "STL", "Templates", "Game Engines"],
            "projects": 15,
            "icon": "code",
            "color": "#00599C"
        }
    ]
    return {"tracks": tracks, "total_tracks": len(tracks)}

@router.get("/daily-challenge")
async def get_daily_challenge():
    """Get today's coding challenge"""
    # In a real app, this would rotate daily
    return {
        "id": f"dc_{datetime.now().strftime('%Y%m%d')}",
        "title": "Two Sum Variants",
        "difficulty": "medium",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        "examples": [
            {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]"},
            {"input": "nums = [3,2,4], target = 6", "output": "[1,2]"}
        ],
        "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
        "hints": ["Try using a hash map for O(n) solution"],
        "topics": ["Array", "Hash Table"],
        "submissions_today": 1247,
        "success_rate": 68.5
    }

@router.get("/interview-problems")
async def get_interview_problems():
    """Get FAANG-level interview problems"""
    return {
        "categories": [
            {"id": "arrays", "name": "Arrays & Strings", "count": 85, "difficulty_dist": {"easy": 25, "medium": 40, "hard": 20}},
            {"id": "linked_lists", "name": "Linked Lists", "count": 35, "difficulty_dist": {"easy": 10, "medium": 15, "hard": 10}},
            {"id": "trees", "name": "Trees & Graphs", "count": 95, "difficulty_dist": {"easy": 20, "medium": 45, "hard": 30}},
            {"id": "dp", "name": "Dynamic Programming", "count": 120, "difficulty_dist": {"easy": 15, "medium": 55, "hard": 50}},
            {"id": "system_design", "name": "System Design", "count": 50, "difficulty_dist": {"medium": 20, "hard": 30}},
            {"id": "behavioral", "name": "Behavioral", "count": 80, "difficulty_dist": {"easy": 40, "medium": 40}},
        ],
        "total_problems": 500,
        "companies": ["Google", "Meta", "Amazon", "Apple", "Netflix", "Microsoft", "Stripe", "Airbnb"]
    }

@router.get("/certifications")
async def get_certifications():
    """Get available certifications"""
    return {
        "certifications": [
            {
                "id": "tutolage_fullstack",
                "name": "Tutolage Full-Stack Developer",
                "description": "Complete web development certification",
                "requirements": ["Complete 5 projects", "Pass final exam (80%+)", "Peer code review"],
                "validity_years": 2,
                "badge_color": "#8B5CF6"
            },
            {
                "id": "tutolage_gamedev",
                "name": "Tutolage Game Developer",
                "description": "Game development certification",
                "requirements": ["Build 3 games", "Complete all game pipelines", "Publish to store"],
                "validity_years": 2,
                "badge_color": "#EC4899"
            },
            {
                "id": "tutolage_ml",
                "name": "Tutolage ML Engineer",
                "description": "Machine learning certification",
                "requirements": ["Complete ML track", "Deploy 2 ML models", "Kaggle competition"],
                "validity_years": 2,
                "badge_color": "#10B981"
            }
        ]
    }

@router.get("/cheat-sheets")
async def get_cheat_sheets():
    """Get quick reference cheat sheets"""
    return {
        "cheat_sheets": [
            {"id": "git", "name": "Git Commands", "category": "DevOps", "pages": 2},
            {"id": "sql", "name": "SQL Queries", "category": "Database", "pages": 4},
            {"id": "regex", "name": "Regular Expressions", "category": "Programming", "pages": 2},
            {"id": "docker", "name": "Docker CLI", "category": "DevOps", "pages": 3},
            {"id": "kubernetes", "name": "Kubernetes", "category": "DevOps", "pages": 4},
            {"id": "python", "name": "Python Syntax", "category": "Languages", "pages": 3},
            {"id": "javascript", "name": "JavaScript ES6+", "category": "Languages", "pages": 3},
            {"id": "react", "name": "React Hooks", "category": "Frontend", "pages": 2},
            {"id": "css", "name": "CSS Flexbox/Grid", "category": "Frontend", "pages": 2},
            {"id": "linux", "name": "Linux Commands", "category": "Systems", "pages": 4},
        ],
        "total_sheets": 100
    }
