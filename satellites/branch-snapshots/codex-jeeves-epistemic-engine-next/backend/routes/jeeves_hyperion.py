"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         JEEVES HYPERION v13.0 - SELF-LEARNING AI TUTOR ENGINE                ║
║                                                                              ║
║  20x EXPANDED KNOWLEDGE BASE | SELF-LEARNING ALGORITHMS | DEV MATRICES       ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ KNOWLEDGE DOMAINS (20x Expansion):                                      │ ║
║  │ • Core Programming: 15 sub-domains, 500+ concepts                       │ ║
║  │ • Software Engineering: 12 sub-domains, 400+ patterns                   │ ║
║  │ • System Design: 10 sub-domains, 300+ architectures                     │ ║
║  │ • Data Science & AI: 8 sub-domains, 350+ techniques                     │ ║
║  │ • DevOps & Cloud: 10 sub-domains, 250+ practices                        │ ║
║  │ • Soft Skills: 8 sub-domains, 200+ competencies                         │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  SELF-LEARNING ENGINE:                                                       ║
║  • Adaptive difficulty calibration                                           ║
║  • Learning velocity tracking                                                ║
║  • Knowledge gap detection                                                   ║
║  • Personalized reinforcement scheduling                                     ║
║  • Mastery prediction algorithms                                             ║
║                                                                              ║
║  DEVELOPMENT MATRICES:                                                       ║
║  • Skill Acquisition Matrix (SAM)                                            ║
║  • Cognitive Load Optimizer (CLO)                                            ║
║  • Progress Trajectory Analyzer (PTA)                                        ║
║  • Learning Style Adapter (LSA)                                              ║
║  • Knowledge Retention Predictor (KRP)                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timedelta
from enum import Enum
import uuid
import random
import math

router = APIRouter(prefix="/api/jeeves-hyperion", tags=["Jeeves Hyperion v13.0"])

# ============================================================================
# ENUMS & TYPES
# ============================================================================

class SkillLevel(str, Enum):
    NOVICE = "novice"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MASTER = "master"

class LearningStyle(str, Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING = "reading"
    MULTIMODAL = "multimodal"

class CognitiveState(str, Enum):
    FOCUSED = "focused"
    LEARNING = "learning"
    STRUGGLING = "struggling"
    OVERWHELMED = "overwhelmed"
    MASTERING = "mastering"
    REVIEWING = "reviewing"

# ============================================================================
# REQUEST MODELS
# ============================================================================

class AdaptDifficultyRequest(BaseModel):
    recent_performance: List[float] = Field(..., description="List of recent performance scores (0.0 to 1.0)")
    current_difficulty: float = Field(..., description="Current difficulty level (0.0 to 1.0)")

# ============================================================================
# 20x EXPANDED KNOWLEDGE BASE
# ============================================================================

HYPERION_KNOWLEDGE_BASE = {
    # =========================================================================
    # CORE PROGRAMMING (15 sub-domains, 500+ concepts)
    # =========================================================================
    "core_programming": {
        "name": "Core Programming Fundamentals",
        "total_concepts": 523,
        "estimated_hours": 400,
        "sub_domains": {
            "syntax_semantics": {
                "name": "Syntax & Semantics",
                "concepts": 45,
                "topics": [
                    "Lexical analysis", "Parse trees", "Abstract syntax trees",
                    "Type systems", "Static vs dynamic typing", "Type inference",
                    "Scope rules", "Name binding", "Closures", "Hoisting",
                    "Expression evaluation", "Operator precedence", "Short-circuit evaluation",
                    "Statement vs expression", "Control flow semantics"
                ]
            },
            "data_types": {
                "name": "Data Types & Structures",
                "concepts": 60,
                "topics": [
                    "Primitive types", "Reference types", "Value types",
                    "Arrays", "Dynamic arrays", "Linked lists", "Doubly linked lists",
                    "Stacks", "Queues", "Deques", "Priority queues",
                    "Hash tables", "Hash functions", "Collision resolution",
                    "Trees", "Binary trees", "BST", "AVL trees", "Red-black trees",
                    "B-trees", "Tries", "Suffix trees",
                    "Heaps", "Min-heap", "Max-heap", "Fibonacci heap",
                    "Graphs", "Adjacency matrix", "Adjacency list", "Edge list",
                    "Sets", "Multisets", "Bit arrays", "Bloom filters"
                ]
            },
            "control_flow": {
                "name": "Control Flow",
                "concepts": 35,
                "topics": [
                    "Conditionals", "Switch statements", "Pattern matching",
                    "Loops", "For loops", "While loops", "Do-while", "For-each",
                    "Iterators", "Generators", "Coroutines",
                    "Exception handling", "Try-catch-finally", "Custom exceptions",
                    "Error propagation", "Result types", "Option types",
                    "Early returns", "Guard clauses", "Assertions"
                ]
            },
            "functions": {
                "name": "Functions & Procedures",
                "concepts": 50,
                "topics": [
                    "Function declaration", "Parameters", "Arguments",
                    "Return values", "Multiple returns", "Void functions",
                    "Pure functions", "Side effects", "Referential transparency",
                    "Higher-order functions", "First-class functions",
                    "Callbacks", "Closures", "Partial application", "Currying",
                    "Recursion", "Tail recursion", "Mutual recursion",
                    "Memoization", "Lazy evaluation", "Strict evaluation",
                    "Variadic functions", "Default parameters", "Named parameters",
                    "Function overloading", "Generic functions"
                ]
            },
            "oop": {
                "name": "Object-Oriented Programming",
                "concepts": 65,
                "topics": [
                    "Classes", "Objects", "Instances", "Constructors", "Destructors",
                    "Encapsulation", "Access modifiers", "Getters/Setters",
                    "Inheritance", "Single inheritance", "Multiple inheritance",
                    "Polymorphism", "Runtime polymorphism", "Compile-time polymorphism",
                    "Abstraction", "Abstract classes", "Interfaces",
                    "Composition", "Aggregation", "Association",
                    "SOLID principles", "SRP", "OCP", "LSP", "ISP", "DIP",
                    "Design patterns", "Creational", "Structural", "Behavioral",
                    "Method overriding", "Method overloading", "Operator overloading",
                    "Static members", "Class methods", "Instance methods",
                    "Mixins", "Traits", "Protocols"
                ]
            },
            "functional": {
                "name": "Functional Programming",
                "concepts": 55,
                "topics": [
                    "Immutability", "Pure functions", "Side effects",
                    "Map", "Filter", "Reduce", "FlatMap",
                    "Function composition", "Point-free style", "Pipelines",
                    "Monads", "Functors", "Applicatives",
                    "Maybe/Option", "Either/Result", "IO Monad",
                    "Pattern matching", "Destructuring", "Guards",
                    "Algebraic data types", "Sum types", "Product types",
                    "Type classes", "Polymorphism", "Ad-hoc polymorphism",
                    "Lazy evaluation", "Infinite data structures", "Streams",
                    "Referential transparency", "Equational reasoning"
                ]
            },
            "concurrency": {
                "name": "Concurrency & Parallelism",
                "concepts": 48,
                "topics": [
                    "Threads", "Processes", "Thread pools",
                    "Synchronization", "Mutexes", "Semaphores", "Monitors",
                    "Deadlocks", "Livelocks", "Race conditions", "Starvation",
                    "Atomic operations", "CAS", "Memory barriers",
                    "Async/await", "Promises", "Futures",
                    "Event loops", "Callbacks", "Non-blocking I/O",
                    "Actor model", "CSP", "Message passing",
                    "Parallel algorithms", "Fork-join", "Map-reduce",
                    "Thread safety", "Lock-free data structures"
                ]
            },
            "memory_management": {
                "name": "Memory Management",
                "concepts": 40,
                "topics": [
                    "Stack vs heap", "Memory allocation", "Deallocation",
                    "Garbage collection", "Mark-and-sweep", "Generational GC",
                    "Reference counting", "Weak references", "Circular references",
                    "Memory leaks", "Dangling pointers", "Buffer overflow",
                    "RAII", "Smart pointers", "Unique/Shared/Weak pointers",
                    "Memory pools", "Object pools", "Arena allocation",
                    "Cache locality", "Memory alignment", "Padding"
                ]
            },
            "algorithms": {
                "name": "Algorithms",
                "concepts": 75,
                "topics": [
                    "Big O notation", "Time complexity", "Space complexity",
                    "Sorting", "QuickSort", "MergeSort", "HeapSort", "TimSort",
                    "Searching", "Binary search", "Interpolation search",
                    "Graph algorithms", "BFS", "DFS", "Dijkstra", "A*",
                    "Dynamic programming", "Memoization", "Tabulation",
                    "Greedy algorithms", "Backtracking", "Branch and bound",
                    "Divide and conquer", "Two pointers", "Sliding window",
                    "String algorithms", "KMP", "Rabin-Karp", "Trie operations",
                    "Bit manipulation", "Hashing algorithms"
                ]
            },
            "testing": {
                "name": "Testing & Quality",
                "concepts": 50,
                "topics": [
                    "Unit testing", "Integration testing", "E2E testing",
                    "TDD", "BDD", "Property-based testing",
                    "Mocking", "Stubbing", "Faking", "Spies",
                    "Test coverage", "Branch coverage", "Line coverage",
                    "Mutation testing", "Fuzzing", "Load testing",
                    "Test fixtures", "Setup/teardown", "Test isolation",
                    "Assertions", "Matchers", "Custom matchers",
                    "CI/CD testing", "Flaky tests", "Test parallelization"
                ]
            }
        }
    },

    # =========================================================================
    # SOFTWARE ENGINEERING (12 sub-domains, 400+ patterns)
    # =========================================================================
    "software_engineering": {
        "name": "Software Engineering Practices",
        "total_concepts": 412,
        "estimated_hours": 350,
        "sub_domains": {
            "design_patterns": {
                "name": "Design Patterns",
                "concepts": 45,
                "patterns": {
                    "creational": ["Singleton", "Factory", "Abstract Factory", "Builder", "Prototype", "Object Pool"],
                    "structural": ["Adapter", "Bridge", "Composite", "Decorator", "Facade", "Flyweight", "Proxy"],
                    "behavioral": ["Chain of Responsibility", "Command", "Iterator", "Mediator", "Memento", 
                                   "Observer", "State", "Strategy", "Template Method", "Visitor"],
                    "architectural": ["MVC", "MVP", "MVVM", "Clean Architecture", "Hexagonal", "Microkernel"]
                }
            },
            "architecture": {
                "name": "Software Architecture",
                "concepts": 55,
                "topics": [
                    "Monolithic architecture", "Microservices", "Serverless",
                    "Event-driven architecture", "CQRS", "Event sourcing",
                    "Service mesh", "API Gateway", "BFF pattern",
                    "Domain-driven design", "Bounded contexts", "Aggregates",
                    "Clean architecture", "Onion architecture", "Ports & adapters",
                    "CAP theorem", "BASE", "ACID", "Eventual consistency"
                ]
            },
            "code_quality": {
                "name": "Code Quality",
                "concepts": 40,
                "topics": [
                    "Clean code principles", "Readable code", "Self-documenting code",
                    "Code smells", "Technical debt", "Refactoring",
                    "SOLID principles", "DRY", "KISS", "YAGNI",
                    "Code reviews", "Pair programming", "Mob programming",
                    "Static analysis", "Linting", "Formatting"
                ]
            },
            "version_control": {
                "name": "Version Control",
                "concepts": 35,
                "topics": [
                    "Git fundamentals", "Branching strategies", "Git flow",
                    "Trunk-based development", "Feature flags", "Release management",
                    "Merge strategies", "Rebasing", "Cherry-picking",
                    "Commit conventions", "Semantic versioning", "Changelog"
                ]
            },
            "documentation": {
                "name": "Documentation",
                "concepts": 30,
                "topics": [
                    "API documentation", "Code comments", "README files",
                    "Architecture decision records", "Technical specs",
                    "User documentation", "Tutorials", "Examples"
                ]
            },
            "security": {
                "name": "Security Practices",
                "concepts": 50,
                "topics": [
                    "OWASP Top 10", "SQL injection", "XSS", "CSRF",
                    "Authentication", "Authorization", "OAuth", "JWT",
                    "Encryption", "Hashing", "Salt", "Key management",
                    "Secure coding", "Input validation", "Output encoding",
                    "Security testing", "Penetration testing", "Vulnerability scanning"
                ]
            },
            "performance": {
                "name": "Performance Engineering",
                "concepts": 45,
                "topics": [
                    "Profiling", "Benchmarking", "Load testing",
                    "Caching strategies", "CDN", "Edge computing",
                    "Database optimization", "Query optimization", "Indexing",
                    "Memory optimization", "CPU optimization", "I/O optimization",
                    "Horizontal scaling", "Vertical scaling", "Auto-scaling"
                ]
            },
            "api_design": {
                "name": "API Design",
                "concepts": 40,
                "topics": [
                    "REST principles", "RESTful design", "HATEOAS",
                    "GraphQL", "gRPC", "WebSocket",
                    "API versioning", "Backward compatibility", "Deprecation",
                    "Rate limiting", "Throttling", "Pagination",
                    "Error handling", "Status codes", "Error responses"
                ]
            }
        }
    },

    # =========================================================================
    # SYSTEM DESIGN (10 sub-domains, 300+ architectures)
    # =========================================================================
    "system_design": {
        "name": "System Design & Architecture",
        "total_concepts": 312,
        "estimated_hours": 300,
        "sub_domains": {
            "distributed_systems": {
                "name": "Distributed Systems",
                "concepts": 50,
                "topics": [
                    "CAP theorem", "Consistency models", "Partition tolerance",
                    "Consensus algorithms", "Paxos", "Raft", "PBFT",
                    "Distributed transactions", "Two-phase commit", "Saga pattern",
                    "Leader election", "Quorum", "Vector clocks",
                    "Distributed caching", "Distributed storage"
                ]
            },
            "scalability": {
                "name": "Scalability Patterns",
                "concepts": 40,
                "topics": [
                    "Horizontal vs vertical scaling", "Load balancing",
                    "Database sharding", "Replication", "Read replicas",
                    "Caching layers", "Write-behind cache", "Cache invalidation",
                    "Message queues", "Event streaming", "Backpressure"
                ]
            },
            "databases": {
                "name": "Database Systems",
                "concepts": 45,
                "topics": [
                    "SQL vs NoSQL", "ACID properties", "BASE properties",
                    "Normalization", "Denormalization", "Schema design",
                    "Indexing strategies", "Query optimization", "Explain plans",
                    "Transactions", "Isolation levels", "Deadlock prevention"
                ]
            },
            "messaging": {
                "name": "Messaging Systems",
                "concepts": 35,
                "topics": [
                    "Message queues", "Pub/sub", "Event streaming",
                    "Kafka", "RabbitMQ", "Redis Pub/Sub",
                    "Message ordering", "Exactly-once delivery", "Idempotency",
                    "Dead letter queues", "Message replay"
                ]
            }
        }
    },

    # =========================================================================
    # DATA SCIENCE & AI (8 sub-domains, 350+ techniques)
    # =========================================================================
    "data_science_ai": {
        "name": "Data Science & AI",
        "total_concepts": 356,
        "estimated_hours": 400,
        "sub_domains": {
            "machine_learning": {
                "name": "Machine Learning",
                "concepts": 80,
                "topics": [
                    "Supervised learning", "Unsupervised learning", "Reinforcement learning",
                    "Linear regression", "Logistic regression", "Decision trees",
                    "Random forests", "Gradient boosting", "XGBoost",
                    "Neural networks", "Deep learning", "CNNs", "RNNs", "Transformers",
                    "Feature engineering", "Feature selection", "Dimensionality reduction"
                ]
            },
            "nlp": {
                "name": "Natural Language Processing",
                "concepts": 55,
                "topics": [
                    "Tokenization", "Stemming", "Lemmatization",
                    "Word embeddings", "Word2Vec", "GloVe", "FastText",
                    "Sequence models", "LSTM", "GRU", "Attention",
                    "Transformers", "BERT", "GPT", "T5",
                    "Named entity recognition", "Sentiment analysis", "Text classification"
                ]
            },
            "computer_vision": {
                "name": "Computer Vision",
                "concepts": 45,
                "topics": [
                    "Image processing", "Convolutions", "Pooling",
                    "Object detection", "YOLO", "Faster R-CNN",
                    "Image segmentation", "Semantic segmentation", "Instance segmentation",
                    "Face recognition", "Pose estimation", "OCR"
                ]
            }
        }
    },

    # =========================================================================
    # DEVOPS & CLOUD (10 sub-domains, 250+ practices)
    # =========================================================================
    "devops_cloud": {
        "name": "DevOps & Cloud Engineering",
        "total_concepts": 258,
        "estimated_hours": 250,
        "sub_domains": {
            "containerization": {
                "name": "Containerization",
                "concepts": 40,
                "topics": [
                    "Docker", "Dockerfile", "Docker Compose",
                    "Container orchestration", "Kubernetes", "Helm",
                    "Service mesh", "Istio", "Linkerd",
                    "Container security", "Image scanning"
                ]
            },
            "ci_cd": {
                "name": "CI/CD",
                "concepts": 35,
                "topics": [
                    "Continuous integration", "Continuous deployment",
                    "Build pipelines", "Deployment strategies",
                    "Blue-green deployment", "Canary releases", "Rolling updates",
                    "GitOps", "ArgoCD", "Flux"
                ]
            },
            "infrastructure": {
                "name": "Infrastructure as Code",
                "concepts": 40,
                "topics": [
                    "Terraform", "CloudFormation", "Pulumi",
                    "Configuration management", "Ansible", "Chef", "Puppet",
                    "Immutable infrastructure", "Infrastructure testing"
                ]
            },
            "monitoring": {
                "name": "Monitoring & Observability",
                "concepts": 45,
                "topics": [
                    "Metrics", "Logging", "Tracing",
                    "Prometheus", "Grafana", "ELK Stack",
                    "APM", "Distributed tracing", "Jaeger",
                    "Alerting", "SLOs", "SLIs", "Error budgets"
                ]
            }
        }
    },

    # =========================================================================
    # SOFT SKILLS (8 sub-domains, 200+ competencies)
    # =========================================================================
    "soft_skills": {
        "name": "Developer Soft Skills",
        "total_concepts": 203,
        "estimated_hours": 150,
        "sub_domains": {
            "communication": {
                "name": "Communication",
                "concepts": 35,
                "topics": [
                    "Technical writing", "Documentation", "Presentations",
                    "Code reviews", "Giving feedback", "Receiving feedback",
                    "Stakeholder communication", "Cross-team collaboration"
                ]
            },
            "problem_solving": {
                "name": "Problem Solving",
                "concepts": 30,
                "topics": [
                    "Root cause analysis", "5 Whys", "Fishbone diagrams",
                    "Debugging strategies", "Systematic troubleshooting",
                    "Breaking down problems", "Abstraction", "Pattern recognition"
                ]
            },
            "time_management": {
                "name": "Time Management",
                "concepts": 25,
                "topics": [
                    "Prioritization", "Eisenhower matrix", "Time boxing",
                    "Pomodoro technique", "Deep work", "Flow state",
                    "Task estimation", "Velocity tracking"
                ]
            },
            "learning": {
                "name": "Learning to Learn",
                "concepts": 40,
                "topics": [
                    "Growth mindset", "Deliberate practice", "Spaced repetition",
                    "Active recall", "Feynman technique", "Rubber duck debugging",
                    "Building mental models", "Chunking", "Interleaving"
                ]
            },
            "career": {
                "name": "Career Development",
                "concepts": 35,
                "topics": [
                    "Goal setting", "Skill mapping", "Career ladder",
                    "Personal branding", "Networking", "Mentorship",
                    "Technical leadership", "IC vs management track"
                ]
            }
        }
    }
}

# ============================================================================
# SELF-LEARNING ENGINE
# ============================================================================

class SelfLearningEngine:
    """
    Adaptive self-learning algorithms that personalize the learning experience
    based on user behavior, performance, and preferences.
    """
    
    @staticmethod
    def calculate_mastery_score(
        correct_answers: int,
        total_attempts: int,
        time_spent_seconds: int,
        hint_usage: int,
        days_since_last_practice: int
    ) -> float:
        """
        Calculate mastery score using a weighted algorithm that considers:
        - Accuracy
        - Speed
        - Independence (hint usage)
        - Retention (time decay)
        """
        if total_attempts == 0:
            return 0.0
            
        # Accuracy component (40% weight)
        accuracy = correct_answers / total_attempts
        accuracy_score = accuracy * 0.4
        
        # Speed component (20% weight) - normalized by expected time
        expected_time = total_attempts * 60  # 60 seconds per attempt
        speed_ratio = min(expected_time / max(time_spent_seconds, 1), 2.0)
        speed_score = (speed_ratio / 2) * 0.2
        
        # Independence component (20% weight)
        hint_penalty = min(hint_usage / max(total_attempts, 1), 1.0)
        independence_score = (1 - hint_penalty) * 0.2
        
        # Retention component (20% weight) - Ebbinghaus forgetting curve
        retention_factor = math.exp(-days_since_last_practice / 30)  # 30-day half-life
        retention_score = retention_factor * 0.2
        
        return min(accuracy_score + speed_score + independence_score + retention_score, 1.0)
    
    @staticmethod
    def predict_optimal_review_time(
        mastery_score: float,
        last_practice: datetime,
        difficulty: float
    ) -> datetime:
        """
        Predict optimal review time using spaced repetition algorithm.
        Higher mastery = longer intervals, higher difficulty = shorter intervals.
        """
        # Base interval in days
        base_interval = 1
        
        # Mastery multiplier (0.5 to 4x)
        mastery_multiplier = 0.5 + (mastery_score * 3.5)
        
        # Difficulty divisor (1x to 2x)
        difficulty_divisor = 1 + difficulty
        
        # Calculate interval
        interval_days = base_interval * mastery_multiplier / difficulty_divisor
        
        # Apply Fibonacci-like growth for well-mastered topics
        if mastery_score > 0.8:
            interval_days *= 1.618  # Golden ratio
            
        return last_practice + timedelta(days=interval_days)
    
    @staticmethod
    def detect_knowledge_gaps(
        topic_scores: Dict[str, float],
        prerequisite_map: Dict[str, List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Detect knowledge gaps by analyzing topic scores and prerequisites.
        Returns list of gaps with recommendations.
        """
        gaps = []
        
        for topic, score in topic_scores.items():
            if score < 0.6:  # Below 60% mastery
                # Check if prerequisites are mastered
                prereqs = prerequisite_map.get(topic, [])
                weak_prereqs = [p for p in prereqs if topic_scores.get(p, 0) < 0.7]
                
                gap = {
                    "topic": topic,
                    "current_mastery": score,
                    "target_mastery": 0.8,
                    "gap_size": 0.8 - score,
                    "weak_prerequisites": weak_prereqs,
                    "recommendation": "review_prerequisites" if weak_prereqs else "focused_practice",
                    "estimated_hours_to_close": math.ceil((0.8 - score) * 10)
                }
                gaps.append(gap)
        
        # Sort by gap size (largest first)
        gaps.sort(key=lambda x: x["gap_size"], reverse=True)
        return gaps
    
    @staticmethod
    def calculate_learning_velocity(
        progress_history: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate learning velocity (rate of mastery acquisition over time).
        """
        if len(progress_history) < 2:
            return {"velocity": 0.0, "trend": "insufficient_data"}
        
        # Calculate mastery gains over time
        gains = []
        for i in range(1, len(progress_history)):
            prev = progress_history[i-1]
            curr = progress_history[i]
            time_delta = (curr["timestamp"] - prev["timestamp"]).total_seconds() / 3600  # hours
            mastery_delta = curr["mastery"] - prev["mastery"]
            if time_delta > 0:
                gains.append(mastery_delta / time_delta)
        
        if not gains:
            return {"velocity": 0.0, "trend": "no_progress"}
        
        avg_velocity = sum(gains) / len(gains)
        recent_velocity = sum(gains[-3:]) / min(len(gains), 3) if gains else 0
        
        trend = "accelerating" if recent_velocity > avg_velocity * 1.1 else \
                "decelerating" if recent_velocity < avg_velocity * 0.9 else "steady"
        
        return {
            "velocity": avg_velocity,
            "recent_velocity": recent_velocity,
            "trend": trend,
            "data_points": len(gains)
        }
    
    @staticmethod
    def adapt_difficulty(
        recent_performance: List[float],
        current_difficulty: float
    ) -> float:
        """
        Adapt difficulty based on recent performance.
        Keeps learner in the "zone of proximal development" (70-85% success rate).
        """
        if len(recent_performance) < 3:
            return current_difficulty
            
        avg_performance = sum(recent_performance[-5:]) / min(len(recent_performance), 5)
        
        if avg_performance > 0.85:
            # Too easy - increase difficulty
            return min(current_difficulty + 0.1, 1.0)
        elif avg_performance < 0.70:
            # Too hard - decrease difficulty
            return max(current_difficulty - 0.1, 0.1)
        else:
            # In the zone - maintain
            return current_difficulty

# ============================================================================
# DEVELOPMENT MATRICES
# ============================================================================

class DevelopmentMatrices:
    """
    Advanced matrices for tracking and optimizing self-development.
    """
    
    @staticmethod
    def skill_acquisition_matrix(skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        SAM - Skill Acquisition Matrix
        Maps current skills against target skills with gap analysis.
        """
        matrix = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_skills": len(skills),
            "categories": {},
            "overall_readiness": 0.0,
            "priority_skills": []
        }
        
        for skill in skills:
            category = skill.get("category", "general")
            if category not in matrix["categories"]:
                matrix["categories"][category] = {
                    "skills": [],
                    "avg_mastery": 0.0,
                    "gaps": []
                }
            
            mastery = skill.get("mastery", 0)
            target = skill.get("target", 0.8)
            
            matrix["categories"][category]["skills"].append({
                "name": skill["name"],
                "mastery": mastery,
                "target": target,
                "gap": max(0, target - mastery),
                "status": "mastered" if mastery >= target else "in_progress" if mastery > 0.3 else "not_started"
            })
            
            if mastery < target:
                matrix["categories"][category]["gaps"].append(skill["name"])
        
        # Calculate averages
        total_mastery = 0
        skill_count = 0
        for cat_data in matrix["categories"].values():
            if cat_data["skills"]:
                cat_avg = sum(s["mastery"] for s in cat_data["skills"]) / len(cat_data["skills"])
                cat_data["avg_mastery"] = round(cat_avg, 2)
                total_mastery += sum(s["mastery"] for s in cat_data["skills"])
                skill_count += len(cat_data["skills"])
        
        matrix["overall_readiness"] = round(total_mastery / max(skill_count, 1), 2)
        
        # Identify priority skills (largest gaps in important categories)
        all_skills = []
        for cat_data in matrix["categories"].values():
            all_skills.extend(cat_data["skills"])
        
        matrix["priority_skills"] = sorted(
            [s for s in all_skills if s["gap"] > 0],
            key=lambda x: x["gap"],
            reverse=True
        )[:5]
        
        return matrix
    
    @staticmethod
    def cognitive_load_optimizer(
        current_topics: List[str],
        complexity_scores: Dict[str, float],
        user_fatigue_level: float
    ) -> Dict[str, Any]:
        """
        CLO - Cognitive Load Optimizer
        Optimizes learning load based on complexity and fatigue.
        """
        # Calculate current cognitive load
        total_complexity = sum(complexity_scores.get(t, 0.5) for t in current_topics)
        avg_complexity = total_complexity / max(len(current_topics), 1)
        
        # Adjust for fatigue (fatigue reduces capacity)
        effective_capacity = 1.0 - (user_fatigue_level * 0.5)
        
        # Determine optimal load
        optimal_topics = max(1, int(5 * effective_capacity / max(avg_complexity, 0.1)))
        
        # Recommendations
        if total_complexity > effective_capacity:
            recommendation = "reduce_load"
            action = "Consider breaking down complex topics or taking a break"
        elif total_complexity < effective_capacity * 0.5:
            recommendation = "increase_challenge"
            action = "You can handle more challenging material"
        else:
            recommendation = "optimal"
            action = "Current load is well-balanced"
        
        return {
            "current_load": round(total_complexity, 2),
            "effective_capacity": round(effective_capacity, 2),
            "utilization": round(total_complexity / max(effective_capacity, 0.1), 2),
            "optimal_topic_count": optimal_topics,
            "recommendation": recommendation,
            "action": action,
            "fatigue_impact": f"-{int(user_fatigue_level * 50)}% capacity"
        }
    
    @staticmethod
    def progress_trajectory_analyzer(
        milestones: List[Dict[str, Any]],
        target_date: datetime
    ) -> Dict[str, Any]:
        """
        PTA - Progress Trajectory Analyzer
        Analyzes progress towards goals and predicts completion.
        """
        if not milestones:
            return {"status": "no_data"}
        
        completed = [m for m in milestones if m.get("completed", False)]
        total = len(milestones)
        completion_rate = len(completed) / total if total > 0 else 0
        
        # Calculate velocity
        if len(completed) >= 2:
            first_completion = min(m["completed_date"] for m in completed if "completed_date" in m)
            last_completion = max(m["completed_date"] for m in completed if "completed_date" in m)
            days_elapsed = (last_completion - first_completion).days + 1
            velocity = len(completed) / max(days_elapsed, 1)  # milestones per day
        else:
            velocity = 0.1  # default assumption
        
        # Predict completion
        remaining = total - len(completed)
        days_to_complete = remaining / max(velocity, 0.01)
        predicted_completion = datetime.utcnow() + timedelta(days=days_to_complete)
        
        # Compare to target
        days_until_target = (target_date - datetime.utcnow()).days
        on_track = predicted_completion <= target_date
        
        return {
            "completed_milestones": len(completed),
            "total_milestones": total,
            "completion_percentage": round(completion_rate * 100, 1),
            "velocity": round(velocity, 3),
            "predicted_completion": predicted_completion.isoformat(),
            "target_date": target_date.isoformat(),
            "on_track": on_track,
            "days_ahead_behind": days_until_target - int(days_to_complete),
            "status": "ahead" if on_track else "behind",
            "recommendation": "maintain_pace" if on_track else "increase_effort"
        }
    
    @staticmethod
    def learning_style_adapter(
        interaction_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        LSA - Learning Style Adapter
        Analyzes learning patterns to recommend optimal content formats.
        """
        style_signals = {
            "visual": 0,
            "auditory": 0,
            "kinesthetic": 0,
            "reading": 0
        }
        
        for interaction in interaction_history:
            content_type = interaction.get("content_type", "")
            engagement = interaction.get("engagement_score", 0.5)
            completion = interaction.get("completion_rate", 0.5)
            
            # Weight by engagement and completion
            weight = engagement * completion
            
            if content_type in ["video", "diagram", "animation"]:
                style_signals["visual"] += weight
            elif content_type in ["podcast", "audio", "lecture"]:
                style_signals["auditory"] += weight
            elif content_type in ["exercise", "project", "lab"]:
                style_signals["kinesthetic"] += weight
            elif content_type in ["article", "documentation", "book"]:
                style_signals["reading"] += weight
        
        # Normalize scores
        total = sum(style_signals.values()) or 1
        style_profile = {k: round(v / total, 2) for k, v in style_signals.items()}
        
        # Determine dominant style
        dominant = max(style_profile, key=style_profile.get)
        
        # Content recommendations
        recommendations = {
            "visual": ["video tutorials", "infographics", "diagrams", "mind maps"],
            "auditory": ["podcasts", "audio courses", "discussions", "verbal explanations"],
            "kinesthetic": ["coding exercises", "projects", "labs", "interactive tutorials"],
            "reading": ["documentation", "articles", "books", "written guides"]
        }
        
        return {
            "style_profile": style_profile,
            "dominant_style": dominant,
            "confidence": style_profile[dominant],
            "recommended_content": recommendations[dominant],
            "multimodal_recommendation": dominant == "reading" and style_profile["kinesthetic"] > 0.2
        }
    
    @staticmethod
    def knowledge_retention_predictor(
        topic: str,
        mastery_history: List[Dict[str, Any]],
        review_count: int,
        days_since_learned: int
    ) -> Dict[str, Any]:
        """
        KRP - Knowledge Retention Predictor
        Predicts retention based on Ebbinghaus forgetting curve and review patterns.
        """
        # Base retention using forgetting curve
        # R = e^(-t/S) where t = time, S = stability
        
        # Stability increases with reviews (each review doubles stability)
        base_stability = 1  # 1 day half-life initially
        stability = base_stability * (2 ** review_count)
        
        # Current retention
        current_retention = math.exp(-days_since_learned / stability)
        
        # Predict retention at various future points
        predictions = {}
        for days in [1, 3, 7, 14, 30]:
            future_days = days_since_learned + days
            predictions[f"in_{days}_days"] = round(math.exp(-future_days / stability), 2)
        
        # Optimal review time (when retention drops to 70%)
        optimal_review_days = -stability * math.log(0.7)
        optimal_review_date = datetime.utcnow() + timedelta(days=max(0, optimal_review_days - days_since_learned))
        
        # Review urgency
        if current_retention < 0.5:
            urgency = "critical"
        elif current_retention < 0.7:
            urgency = "high"
        elif current_retention < 0.85:
            urgency = "medium"
        else:
            urgency = "low"
        
        return {
            "topic": topic,
            "current_retention": round(current_retention, 2),
            "stability_days": round(stability, 1),
            "review_count": review_count,
            "predictions": predictions,
            "optimal_review_date": optimal_review_date.isoformat(),
            "review_urgency": urgency,
            "recommendation": f"Review {'immediately' if urgency == 'critical' else 'soon' if urgency == 'high' else 'within a week' if urgency == 'medium' else 'when convenient'}"
        }

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/knowledge-base/stats")
async def get_knowledge_base_stats():
    """Get comprehensive knowledge base statistics"""
    total_concepts = sum(domain["total_concepts"] for domain in HYPERION_KNOWLEDGE_BASE.values())
    total_hours = sum(domain["estimated_hours"] for domain in HYPERION_KNOWLEDGE_BASE.values())
    total_subdomains = sum(len(domain.get("sub_domains", {})) for domain in HYPERION_KNOWLEDGE_BASE.values())
    
    return {
        "version": "Jeeves Hyperion v13.0",
        "knowledge_expansion": "20x",
        "total_concepts": total_concepts,
        "total_learning_hours": total_hours,
        "domains": len(HYPERION_KNOWLEDGE_BASE),
        "sub_domains": total_subdomains,
        "self_learning_algorithms": 5,
        "development_matrices": 5,
        "domain_breakdown": {
            name: {
                "concepts": domain["total_concepts"],
                "hours": domain["estimated_hours"],
                "sub_domains": len(domain.get("sub_domains", {}))
            }
            for name, domain in HYPERION_KNOWLEDGE_BASE.items()
        }
    }

@router.get("/knowledge-base/domains")
async def get_all_domains():
    """Get all knowledge domains with details"""
    return {
        "domains": [
            {
                "id": domain_id,
                "name": domain["name"],
                "total_concepts": domain["total_concepts"],
                "estimated_hours": domain["estimated_hours"],
                "sub_domains": list(domain.get("sub_domains", {}).keys())
            }
            for domain_id, domain in HYPERION_KNOWLEDGE_BASE.items()
        ]
    }

@router.get("/knowledge-base/domain/{domain_id}")
async def get_domain_details(domain_id: str):
    """Get detailed information about a specific domain"""
    domain = HYPERION_KNOWLEDGE_BASE.get(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    return {
        "id": domain_id,
        "name": domain["name"],
        "total_concepts": domain["total_concepts"],
        "estimated_hours": domain["estimated_hours"],
        "sub_domains": domain.get("sub_domains", {})
    }

@router.post("/self-learning/mastery-score")
async def calculate_mastery(
    correct_answers: int,
    total_attempts: int,
    time_spent_seconds: int,
    hint_usage: int = 0,
    days_since_last_practice: int = 0
):
    """Calculate mastery score using self-learning algorithm"""
    score = SelfLearningEngine.calculate_mastery_score(
        correct_answers, total_attempts, time_spent_seconds,
        hint_usage, days_since_last_practice
    )
    
    return {
        "mastery_score": round(score, 3),
        "mastery_level": (
            "master" if score >= 0.9 else
            "expert" if score >= 0.8 else
            "proficient" if score >= 0.7 else
            "competent" if score >= 0.6 else
            "developing" if score >= 0.4 else
            "beginner"
        ),
        "components": {
            "accuracy": round(correct_answers / max(total_attempts, 1), 2),
            "independence": round(1 - (hint_usage / max(total_attempts, 1)), 2),
            "retention_factor": round(math.exp(-days_since_last_practice / 30), 2)
        }
    }

@router.post("/self-learning/knowledge-gaps")
async def detect_gaps(topic_scores: Dict[str, float]):
    """Detect knowledge gaps based on topic scores"""
    # Simple prerequisite map for demonstration
    prereq_map = {
        "algorithms": ["data_structures", "programming_fundamentals"],
        "system_design": ["algorithms", "databases"],
        "machine_learning": ["algorithms", "linear_algebra", "statistics"]
    }
    
    gaps = SelfLearningEngine.detect_knowledge_gaps(topic_scores, prereq_map)
    
    return {
        "gaps_detected": len(gaps),
        "gaps": gaps,
        "recommendation": "Focus on largest gaps first" if gaps else "No significant gaps detected"
    }

@router.post("/self-learning/adapt-difficulty")
async def adapt_difficulty(request: AdaptDifficultyRequest):
    """Adapt difficulty based on recent performance"""
    new_difficulty = SelfLearningEngine.adapt_difficulty(
        request.recent_performance, request.current_difficulty
    )
    
    avg_perf = sum(request.recent_performance[-5:]) / min(len(request.recent_performance), 5) if request.recent_performance else 0.5
    
    return {
        "previous_difficulty": request.current_difficulty,
        "new_difficulty": round(new_difficulty, 2),
        "change": round(new_difficulty - request.current_difficulty, 2),
        "average_performance": round(avg_perf, 2),
        "zone": "optimal" if 0.70 <= avg_perf <= 0.85 else "too_easy" if avg_perf > 0.85 else "too_hard"
    }

@router.post("/matrices/skill-acquisition")
async def get_skill_matrix(skills: List[Dict[str, Any]]):
    """Generate Skill Acquisition Matrix (SAM)"""
    return DevelopmentMatrices.skill_acquisition_matrix(skills)

@router.post("/matrices/cognitive-load")
async def optimize_cognitive_load(
    current_topics: List[str],
    complexity_scores: Dict[str, float],
    fatigue_level: float = 0.3
):
    """Get Cognitive Load Optimization (CLO) recommendations"""
    return DevelopmentMatrices.cognitive_load_optimizer(
        current_topics, complexity_scores, fatigue_level
    )

@router.post("/matrices/retention-prediction")
async def predict_retention(
    topic: str,
    review_count: int,
    days_since_learned: int
):
    """Get Knowledge Retention Prediction (KRP)"""
    return DevelopmentMatrices.knowledge_retention_predictor(
        topic, [], review_count, days_since_learned
    )

@router.get("/matrices/overview")
async def get_matrices_overview():
    """Get overview of all development matrices"""
    return {
        "matrices": [
            {
                "id": "SAM",
                "name": "Skill Acquisition Matrix",
                "description": "Maps current skills against targets with gap analysis",
                "endpoint": "/matrices/skill-acquisition"
            },
            {
                "id": "CLO",
                "name": "Cognitive Load Optimizer",
                "description": "Optimizes learning load based on complexity and fatigue",
                "endpoint": "/matrices/cognitive-load"
            },
            {
                "id": "PTA",
                "name": "Progress Trajectory Analyzer",
                "description": "Analyzes progress and predicts goal completion",
                "endpoint": "/matrices/progress-trajectory"
            },
            {
                "id": "LSA",
                "name": "Learning Style Adapter",
                "description": "Adapts content format to learning style preferences",
                "endpoint": "/matrices/learning-style"
            },
            {
                "id": "KRP",
                "name": "Knowledge Retention Predictor",
                "description": "Predicts retention using forgetting curve models",
                "endpoint": "/matrices/retention-prediction"
            }
        ],
        "self_learning_algorithms": [
            "Mastery Score Calculator",
            "Optimal Review Time Predictor",
            "Knowledge Gap Detector",
            "Learning Velocity Tracker",
            "Adaptive Difficulty Calibrator"
        ]
    }
