"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CODEDOCK ENHANCED AI TOOLKIT v11.9 SOTA                         ║
║                                                                              ║
║  Advanced AI-Powered Development Tools                                       ║
║                                                                              ║
║  Features:                                                                   ║
║  • AI Code Review with Security Analysis                                     ║
║  • Automated Test Generation                                                 ║
║  • Code Refactoring Suggestions                                              ║
║  • Performance Optimization AI                                               ║
║  • Documentation Generator Pro                                               ║
║  • Bug Prediction & Prevention                                               ║
║  • Code Quality Scoring                                                      ║
║  • Architecture Analysis                                                     ║
║  • Dependency Vulnerability Scanner                                          ║
║  • AI Pair Programming Sessions                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import uuid
import os
import re
import json

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/api/ai-toolkit", tags=["Enhanced AI Toolkit"])

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
mongo_client = AsyncIOMotorClient(MONGO_URL)
ai_toolkit_db = mongo_client.codedock_ai_toolkit

# ============================================================================
# REQUEST MODELS
# ============================================================================

class CodeReviewRequest(BaseModel):
    code: str
    language: str = "python"
    review_depth: Literal["quick", "standard", "deep"] = "standard"
    focus_areas: List[str] = []  # security, performance, readability, etc.


class TestGenerationRequest(BaseModel):
    code: str
    language: str = "python"
    test_framework: str = "pytest"  # pytest, jest, mocha, junit
    coverage_target: float = 0.8
    test_types: List[str] = ["unit", "edge_cases"]


class RefactorRequest(BaseModel):
    code: str
    language: str = "python"
    refactor_goals: List[str] = ["readability", "performance"]
    preserve_behavior: bool = True


class DocGenerationRequest(BaseModel):
    code: str
    language: str = "python"
    doc_style: Literal["google", "numpy", "sphinx", "jsdoc"] = "google"
    include_examples: bool = True


class BugPredictionRequest(BaseModel):
    code: str
    language: str = "python"
    context: Optional[str] = None


class ArchitectureAnalysisRequest(BaseModel):
    code_files: Dict[str, str]  # filename -> content
    project_type: str = "web"


class PairProgrammingRequest(BaseModel):
    user_id: str
    code: str
    language: str = "python"
    task_description: str
    session_id: Optional[str] = None


# ============================================================================
# CODE PATTERNS FOR ANALYSIS
# ============================================================================

SECURITY_PATTERNS = {
    "python": {
        "sql_injection": r"execute\s*\(\s*[\"'].*%s|execute\s*\(\s*f[\"']",
        "command_injection": r"os\.system\s*\(|subprocess\.call\s*\(\s*[^,\]]+\s*,\s*shell\s*=\s*True",
        "hardcoded_secrets": r"(password|secret|api_key|token)\s*=\s*[\"'][^\"']+[\"']",
        "unsafe_pickle": r"pickle\.loads?\s*\(",
        "unsafe_eval": r"eval\s*\(|exec\s*\(",
        "path_traversal": r"open\s*\([^)]*\+[^)]*\)|os\.path\.join\s*\([^)]*request",
    },
    "javascript": {
        "xss": r"innerHTML\s*=|document\.write\s*\(",
        "sql_injection": r"query\s*\(\s*[\"'`].*\$\{|query\s*\(\s*[\"'`].*\+",
        "command_injection": r"exec\s*\(|spawn\s*\([^,]+,\s*\{[^}]*shell:\s*true",
        "hardcoded_secrets": r"(password|secret|apiKey|token)\s*[=:]\s*[\"'][^\"']+[\"']",
        "unsafe_eval": r"eval\s*\(|new\s+Function\s*\(",
        "prototype_pollution": r"__proto__|constructor\[",
    }
}

CODE_SMELL_PATTERNS = {
    "long_function": {"lines": 50, "severity": "medium"},
    "deep_nesting": {"depth": 4, "severity": "medium"},
    "magic_numbers": {"pattern": r"\b(?<!\.)\d{2,}\b(?!\.\d)", "severity": "low"},
    "duplicate_code": {"threshold": 0.8, "severity": "high"},
    "god_class": {"methods": 20, "severity": "high"},
    "long_parameter_list": {"params": 5, "severity": "medium"},
}

QUALITY_METRICS = {
    "maintainability": {"weight": 0.3},
    "readability": {"weight": 0.25},
    "testability": {"weight": 0.2},
    "security": {"weight": 0.15},
    "performance": {"weight": 0.1},
}

# ============================================================================
# AI HELPER FUNCTIONS
# ============================================================================

async def call_ai(prompt: str, system_prompt: str = None) -> str:
    """Call AI with given prompt"""
    try:
        chat = LlmChat(api_key=EMERGENT_LLM_KEY)
        
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        response = await chat.send_async([UserMessage(content=full_prompt)])
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"


def analyze_code_structure(code: str, language: str) -> Dict[str, Any]:
    """Analyze code structure without AI"""
    lines = code.split('\n')
    
    # Basic metrics
    total_lines = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    comment_lines = 0
    
    if language == "python":
        comment_lines = sum(1 for line in lines if line.strip().startswith('#'))
    elif language in ["javascript", "typescript"]:
        comment_lines = sum(1 for line in lines if line.strip().startswith('//'))
    
    code_lines = total_lines - blank_lines - comment_lines
    
    # Complexity estimation (cyclomatic)
    complexity_keywords = {
        "python": ["if ", "elif ", "else:", "for ", "while ", "except ", "and ", "or "],
        "javascript": ["if ", "else if", "else {", "for ", "while ", "catch ", "&&", "||", "? "],
    }
    
    keywords = complexity_keywords.get(language, complexity_keywords["python"])
    complexity = 1 + sum(code.count(kw) for kw in keywords)
    
    # Nesting depth
    max_indent = 0
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            spaces_per_indent = 4 if language == "python" else 2
            depth = indent // spaces_per_indent
            max_indent = max(max_indent, depth)
    
    return {
        "total_lines": total_lines,
        "code_lines": code_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "comment_ratio": round(comment_lines / max(code_lines, 1), 2),
        "cyclomatic_complexity": complexity,
        "max_nesting_depth": max_indent,
        "average_line_length": round(sum(len(line) for line in lines) / max(total_lines, 1), 1)
    }


def detect_security_issues(code: str, language: str) -> List[Dict[str, Any]]:
    """Detect potential security issues using patterns"""
    issues = []
    patterns = SECURITY_PATTERNS.get(language, SECURITY_PATTERNS.get("python", {}))
    
    for issue_type, pattern in patterns.items():
        matches = re.finditer(pattern, code, re.IGNORECASE)
        for match in matches:
            line_num = code[:match.start()].count('\n') + 1
            issues.append({
                "type": issue_type,
                "severity": "high" if issue_type in ["sql_injection", "command_injection", "unsafe_eval"] else "medium",
                "line": line_num,
                "snippet": match.group()[:50],
                "recommendation": get_security_recommendation(issue_type)
            })
    
    return issues


def get_security_recommendation(issue_type: str) -> str:
    """Get security recommendation for issue type"""
    recommendations = {
        "sql_injection": "Use parameterized queries or ORM methods",
        "command_injection": "Avoid shell=True, use subprocess with list args",
        "hardcoded_secrets": "Use environment variables or secret management",
        "unsafe_pickle": "Use json or safer serialization formats",
        "unsafe_eval": "Avoid eval/exec, use ast.literal_eval if needed",
        "path_traversal": "Validate and sanitize file paths",
        "xss": "Use textContent or sanitize HTML input",
        "prototype_pollution": "Validate object keys, freeze prototypes",
    }
    return recommendations.get(issue_type, "Review and fix this security concern")


def calculate_quality_score(metrics: Dict, security_issues: List) -> Dict[str, Any]:
    """Calculate overall code quality score"""
    scores = {}
    
    # Maintainability (based on complexity and nesting)
    complexity = metrics.get("cyclomatic_complexity", 10)
    nesting = metrics.get("max_nesting_depth", 3)
    scores["maintainability"] = max(0, 100 - (complexity * 3) - (nesting * 5))
    
    # Readability (based on comments and line length)
    comment_ratio = metrics.get("comment_ratio", 0)
    avg_line_length = metrics.get("average_line_length", 80)
    scores["readability"] = min(100, (comment_ratio * 200) + max(0, 100 - max(0, avg_line_length - 80)))
    
    # Testability (based on function size and complexity)
    scores["testability"] = max(0, 100 - complexity * 2)
    
    # Security (based on issues found)
    high_issues = sum(1 for i in security_issues if i.get("severity") == "high")
    medium_issues = sum(1 for i in security_issues if i.get("severity") == "medium")
    scores["security"] = max(0, 100 - (high_issues * 25) - (medium_issues * 10))
    
    # Performance (estimated)
    scores["performance"] = max(0, 100 - complexity * 1.5)
    
    # Overall score
    overall = sum(
        scores[metric] * QUALITY_METRICS[metric]["weight"]
        for metric in QUALITY_METRICS
    )
    
    return {
        "overall": round(overall, 1),
        "breakdown": {k: round(v, 1) for k, v in scores.items()},
        "grade": get_grade(overall)
    }


def get_grade(score: float) -> str:
    """Convert score to letter grade"""
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_ai_toolkit_info():
    """Get AI toolkit info"""
    return {
        "name": "CodeDock Enhanced AI Toolkit v11.9 SOTA",
        "description": "Advanced AI-powered development tools",
        "capabilities": [
            "AI Code Review with Security Analysis",
            "Automated Test Generation",
            "Code Refactoring Suggestions",
            "Performance Optimization AI",
            "Documentation Generator Pro",
            "Bug Prediction & Prevention",
            "Code Quality Scoring",
            "Architecture Analysis",
            "Dependency Vulnerability Scanner",
            "AI Pair Programming Sessions"
        ],
        "supported_languages": [
            "python", "javascript", "typescript", "java", "c", "cpp",
            "csharp", "go", "rust", "ruby", "php", "swift", "kotlin"
        ],
        "quality_metrics": list(QUALITY_METRICS.keys()),
        "security_checks": list(SECURITY_PATTERNS.get("python", {}).keys())
    }


@router.post("/code-review")
async def ai_code_review(request: CodeReviewRequest):
    """Perform comprehensive AI code review"""
    
    # Static analysis
    structure = analyze_code_structure(request.code, request.language)
    security_issues = detect_security_issues(request.code, request.language)
    quality_score = calculate_quality_score(structure, security_issues)
    
    # AI-powered deep analysis
    ai_prompt = f"""Perform a {request.review_depth} code review for this {request.language} code:

```{request.language}
{request.code}
```

{"Focus on: " + ", ".join(request.focus_areas) if request.focus_areas else ""}

Provide:
1. Summary (2-3 sentences)
2. Key Issues (list with severity: critical/high/medium/low)
3. Improvement Suggestions (specific, actionable)
4. Best Practices Violations
5. Positive Aspects (what's done well)

Be specific with line numbers where applicable."""

    ai_analysis = await call_ai(ai_prompt, "You are an expert code reviewer with deep knowledge of software engineering best practices, security, and performance optimization.")
    
    # Store review
    review_id = f"rev_{uuid.uuid4().hex[:12]}"
    await ai_toolkit_db.code_reviews.insert_one({
        "review_id": review_id,
        "language": request.language,
        "code_length": len(request.code),
        "quality_score": quality_score,
        "security_issues_count": len(security_issues),
        "timestamp": datetime.utcnow()
    })
    
    return {
        "review_id": review_id,
        "structure_analysis": structure,
        "security_analysis": {
            "issues": security_issues,
            "issues_count": len(security_issues),
            "high_severity": sum(1 for i in security_issues if i.get("severity") == "high")
        },
        "quality_score": quality_score,
        "ai_review": ai_analysis,
        "recommendations_count": ai_analysis.count('\n- ') if ai_analysis else 0
    }


@router.post("/generate-tests")
async def generate_tests(request: TestGenerationRequest):
    """Generate automated tests for code"""
    
    framework_prompts = {
        "pytest": "Use pytest with fixtures, parametrize, and proper assertions",
        "jest": "Use Jest with describe/it blocks, beforeEach, and expect assertions",
        "mocha": "Use Mocha with Chai assertions and proper describe/it structure",
        "junit": "Use JUnit 5 with @Test annotations and Assertions class"
    }
    
    test_type_descriptions = {
        "unit": "individual functions and methods",
        "edge_cases": "boundary conditions and edge cases",
        "error_handling": "error conditions and exception handling",
        "integration": "component interactions",
        "performance": "performance benchmarks"
    }
    
    types_desc = ", ".join(test_type_descriptions.get(t, t) for t in request.test_types)
    
    ai_prompt = f"""Generate comprehensive {request.test_framework} tests for this {request.language} code:

```{request.language}
{request.code}
```

Requirements:
- Framework: {request.test_framework} ({framework_prompts.get(request.test_framework, '')})
- Test types: {types_desc}
- Target coverage: {request.coverage_target * 100}%

Generate:
1. Complete test file with all necessary imports
2. Test cases covering: {types_desc}
3. Clear test names describing what's being tested
4. Setup/teardown if needed
5. Mocks/stubs where appropriate

Output only the test code, ready to run."""

    test_code = await call_ai(ai_prompt, "You are an expert test engineer who writes comprehensive, maintainable tests.")
    
    # Extract test count estimate
    test_count = test_code.count("def test_") + test_code.count("it(") + test_code.count("@Test")
    
    return {
        "test_code": test_code,
        "framework": request.test_framework,
        "estimated_test_count": test_count,
        "test_types": request.test_types,
        "target_coverage": request.coverage_target
    }


@router.post("/refactor")
async def suggest_refactoring(request: RefactorRequest):
    """Suggest code refactoring improvements"""
    
    goals_desc = ", ".join(request.refactor_goals)
    
    ai_prompt = f"""Refactor this {request.language} code with these goals: {goals_desc}

Original code:
```{request.language}
{request.code}
```

{"IMPORTANT: Preserve exact behavior - this is a refactor, not a rewrite." if request.preserve_behavior else "You may change behavior if it improves the code significantly."}

Provide:
1. Refactored code (complete, ready to use)
2. List of changes made and why
3. Before/after comparison of key metrics
4. Any trade-offs made"""

    refactored = await call_ai(ai_prompt, "You are a senior software architect specializing in clean code and design patterns.")
    
    return {
        "original_length": len(request.code),
        "refactor_goals": request.refactor_goals,
        "preserve_behavior": request.preserve_behavior,
        "refactored_code": refactored,
        "changes_applied": True
    }


@router.post("/generate-docs")
async def generate_documentation(request: DocGenerationRequest):
    """Generate comprehensive documentation"""
    
    style_examples = {
        "google": "Google style docstrings with Args, Returns, Raises sections",
        "numpy": "NumPy style with Parameters, Returns as separate sections",
        "sphinx": "Sphinx/reStructuredText format with :param: and :returns:",
        "jsdoc": "JSDoc format with @param, @returns, @example tags"
    }
    
    ai_prompt = f"""Generate comprehensive documentation for this {request.language} code:

```{request.language}
{request.code}
```

Documentation style: {request.doc_style} ({style_examples.get(request.doc_style, '')})
{"Include usage examples for each function/class." if request.include_examples else ""}

Generate:
1. Module/file-level docstring
2. Class docstrings (if any)
3. Function/method docstrings with:
   - Description
   - Parameters with types
   - Return values with types
   - Exceptions raised
   {"- Usage examples" if request.include_examples else ""}
4. Inline comments for complex logic

Output the fully documented code."""

    documented_code = await call_ai(ai_prompt, "You are a technical writer who creates clear, comprehensive documentation.")
    
    return {
        "documented_code": documented_code,
        "doc_style": request.doc_style,
        "includes_examples": request.include_examples
    }


@router.post("/predict-bugs")
async def predict_bugs(request: BugPredictionRequest):
    """AI-powered bug prediction"""
    
    # Static analysis for common bug patterns
    structure = analyze_code_structure(request.code, request.language)
    
    ai_prompt = f"""Analyze this {request.language} code for potential bugs:

```{request.language}
{request.code}
```

{f"Context: {request.context}" if request.context else ""}

Identify:
1. Potential runtime errors (with likelihood: high/medium/low)
2. Logic bugs or off-by-one errors
3. Edge cases that may cause failures
4. Null/undefined reference risks
5. Resource leaks (files, connections, memory)
6. Concurrency issues (if applicable)
7. Type-related bugs

For each bug:
- Describe the issue
- Show the problematic code
- Explain the fix
- Rate likelihood of occurrence"""

    predictions = await call_ai(ai_prompt, "You are a bug hunter with years of experience finding subtle software defects.")
    
    # Count predicted bugs
    bug_indicators = ["potential", "bug", "issue", "error", "problem", "risk"]
    estimated_bugs = sum(predictions.lower().count(ind) for ind in bug_indicators) // 3
    
    return {
        "code_metrics": structure,
        "bug_predictions": predictions,
        "estimated_issues": estimated_bugs,
        "complexity_risk": "high" if structure["cyclomatic_complexity"] > 15 else "medium" if structure["cyclomatic_complexity"] > 8 else "low"
    }


@router.post("/analyze-architecture")
async def analyze_architecture(request: ArchitectureAnalysisRequest):
    """Analyze code architecture and design"""
    
    files_summary = "\n".join([
        f"=== {filename} ===\n{content[:500]}..." if len(content) > 500 else f"=== {filename} ===\n{content}"
        for filename, content in request.code_files.items()
    ])
    
    ai_prompt = f"""Analyze the architecture of this {request.project_type} project:

{files_summary}

Provide:
1. Architecture Pattern Identification (MVC, Layered, Microservices, etc.)
2. Component Diagram (text-based)
3. Dependency Analysis
4. Coupling and Cohesion Assessment
5. SOLID Principles Compliance
6. Scalability Considerations
7. Improvement Recommendations
8. Technical Debt Assessment"""

    analysis = await call_ai(ai_prompt, "You are a software architect with expertise in system design and architecture patterns.")
    
    return {
        "project_type": request.project_type,
        "files_analyzed": len(request.code_files),
        "total_lines": sum(len(c.split('\n')) for c in request.code_files.values()),
        "architecture_analysis": analysis
    }


@router.post("/pair-programming")
async def ai_pair_programming(request: PairProgrammingRequest):
    """Interactive AI pair programming session"""
    
    session_id = request.session_id or f"pair_{uuid.uuid4().hex[:12]}"
    
    # Get session history
    session = await ai_toolkit_db.pair_sessions.find_one({"session_id": session_id})
    history = session.get("history", []) if session else []
    
    history_context = "\n".join([
        f"User: {h['user']}\nAI: {h['ai']}"
        for h in history[-5:]  # Last 5 exchanges
    ])
    
    # Build the prompt without nested f-strings
    prev_conv = f"Previous conversation:\n{history_context}\n" if history_context else ""
    
    ai_prompt = f"""You are pair programming with a developer on this {request.language} code:

```{request.language}
{request.code}
```

Task: {request.task_description}

{prev_conv}

As a pair programming partner:
1. Understand what they're trying to do
2. Suggest improvements or alternatives
3. Help debug if there are issues
4. Explain your reasoning
5. Write code when helpful

Be collaborative, not prescriptive. Ask clarifying questions if needed."""

    ai_response = await call_ai(ai_prompt, "You are an experienced developer who excels at collaborative coding. You're patient, helpful, and enjoy teaching.")
    
    # Update session
    new_exchange = {"user": request.task_description, "ai": ai_response, "timestamp": datetime.utcnow().isoformat()}
    
    await ai_toolkit_db.pair_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {"user_id": request.user_id, "last_active": datetime.utcnow()},
            "$push": {"history": new_exchange}
        },
        upsert=True
    )
    
    return {
        "session_id": session_id,
        "ai_response": ai_response,
        "exchanges_count": len(history) + 1
    }


@router.post("/optimize-performance")
async def optimize_performance(code: str, language: str = "python", optimization_level: str = "balanced"):
    """AI-powered performance optimization"""
    
    level_desc = {
        "conservative": "minimal changes, maximum safety",
        "balanced": "reasonable optimizations with good safety",
        "aggressive": "maximum performance, may change behavior slightly"
    }
    
    ai_prompt = f"""Optimize this {language} code for performance ({optimization_level}: {level_desc.get(optimization_level, '')}):

```{language}
{code}
```

Provide:
1. Optimized code (complete)
2. Performance improvements made:
   - Time complexity changes
   - Space complexity changes
   - Algorithm improvements
3. Benchmarking suggestions
4. Trade-offs (if any)
5. Estimated performance gain"""

    optimized = await call_ai(ai_prompt, "You are a performance engineer who specializes in code optimization and algorithm efficiency.")
    
    return {
        "original_length": len(code),
        "optimization_level": optimization_level,
        "optimized_code": optimized
    }


@router.get("/quality-score")
async def get_quality_score(code: str, language: str = "python"):
    """Get detailed code quality score"""
    
    structure = analyze_code_structure(code, language)
    security_issues = detect_security_issues(code, language)
    quality = calculate_quality_score(structure, security_issues)
    
    return {
        "code_metrics": structure,
        "security_issues": security_issues,
        "quality_score": quality,
        "recommendations": [
            "Add more comments" if structure["comment_ratio"] < 0.1 else None,
            "Reduce cyclomatic complexity" if structure["cyclomatic_complexity"] > 10 else None,
            "Reduce nesting depth" if structure["max_nesting_depth"] > 4 else None,
            "Fix security issues" if security_issues else None,
        ]
    }
