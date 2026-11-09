"""Rosetta Challenge Mode — Translate code between languages, auto-graded via playground"""
from fastapi import APIRouter, Query
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone
import os, random

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/rosetta-challenge", tags=["rosetta-challenge"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}

EXEC_LANGS = ["Python", "JavaScript", "TypeScript", "Go", "Rust", "C", "C++"]
LANG_MAP = {"Python":"python","JavaScript":"javascript","TypeScript":"typescript","Go":"go","Rust":"rust","C":"c","C++":"cpp"}


@router.get("/generate")
async def generate_challenge(difficulty: str = Query("medium"), source_lang: str = None, target_lang: str = None):
    """Generate a Rosetta Challenge — translate code from one language to another."""
    if not source_lang:
        source_lang = random.choice(EXEC_LANGS)
    if not target_lang:
        remaining = [l for l in EXEC_LANGS if l != source_lang]
        target_lang = random.choice(remaining)

    concepts = ["variables", "functions", "loops", "conditionals", "arrays", "strings", "closures", "error_handling",
                "oop_classes", "iterators", "enums", "null_handling", "destructuring", "higher_order_functions", "recursion", "regex"]
    if difficulty == "hard":
        concepts += ["concurrency", "generics", "pattern_matching"]
    elif difficulty == "expert":
        concepts += ["concurrency", "generics", "pattern_matching", "async_await", "structs"]

    concept = random.choice(concepts)

    source_entry = await _db.rosetta_stone.find_one(
        {"concept": concept, "language": source_lang, "source": "handcrafted"}, PROJ
    )
    if not source_entry:
        source_entry = await _db.rosetta_stone.find_one(
            {"concept": concept, "language": source_lang}, PROJ
        )

    target_entry = await _db.rosetta_stone.find_one(
        {"concept": concept, "language": target_lang}, PROJ
    )

    if not source_entry or not target_entry:
        return {"error": "Could not generate challenge", "concept": concept}

    hint_lines = target_entry.get("code", "").split("\n")[:3]

    return {
        "challenge_id": f"rc_{concept}_{source_lang}_{target_lang}_{random.randint(1000,9999)}",
        "concept": concept,
        "concept_name": concept.replace("_", " ").title(),
        "difficulty": difficulty,
        "source_language": source_lang,
        "target_language": target_lang,
        "source_code": source_entry.get("code", ""),
        "source_lines": source_entry.get("code_lines", 0),
        "hint": "\n".join(hint_lines) + "\n// ... complete this code",
        "target_lines": target_entry.get("code_lines", 0),
    }


@router.post("/submit")
async def submit_challenge(
    challenge_id: str = Query(...),
    user_id: str = Query("default_user"),
    target_language: str = Query(...),
    user_code: str = Query(...),
):
    """Submit a challenge solution — execute and grade."""
    lang_key = LANG_MAP.get(target_language, target_language.lower())

    import subprocess, tempfile
    env = {**os.environ, "PATH": f"{os.environ.get('PATH','')}:/usr/local/go/bin:/root/.cargo/bin", "HOME": "/root", "GOCACHE": "/tmp/go-cache", "GOPATH": "/tmp/gopath"}
    timeout = 10

    try:
        if lang_key == "python":
            result = subprocess.run(["python3", "-c", user_code], capture_output=True, text=True, timeout=timeout, env=env)
        elif lang_key in ("javascript", "typescript"):
            result = subprocess.run(["node", "-e", user_code], capture_output=True, text=True, timeout=timeout, env=env)
        elif lang_key == "go":
            with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
                f.write(user_code); f.flush()
                result = subprocess.run(["go", "run", f.name], capture_output=True, text=True, timeout=timeout, env=env)
                os.unlink(f.name)
        elif lang_key == "rust":
            with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
                f.write(user_code); f.flush()
                bin_path = f.name.replace(".rs", "")
                comp = subprocess.run(["rustc", f.name, "-o", bin_path], capture_output=True, text=True, timeout=timeout, env=env)
                if comp.returncode == 0:
                    result = subprocess.run([bin_path], capture_output=True, text=True, timeout=timeout, env=env)
                    os.unlink(bin_path)
                else:
                    result = comp
                os.unlink(f.name)
        elif lang_key == "c":
            with tempfile.NamedTemporaryFile(suffix=".c", mode="w", delete=False) as f:
                f.write(user_code); f.flush()
                bin_path = f.name.replace(".c", "")
                comp = subprocess.run(["gcc", f.name, "-o", bin_path, "-lm"], capture_output=True, text=True, timeout=timeout, env=env)
                if comp.returncode == 0:
                    result = subprocess.run([bin_path], capture_output=True, text=True, timeout=timeout, env=env)
                    os.unlink(bin_path)
                else:
                    result = comp
                os.unlink(f.name)
        elif lang_key == "cpp":
            with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
                f.write(user_code); f.flush()
                bin_path = f.name.replace(".cpp", "")
                comp = subprocess.run(["g++", f.name, "-o", bin_path, "-std=c++17"], capture_output=True, text=True, timeout=timeout, env=env)
                if comp.returncode == 0:
                    result = subprocess.run([bin_path], capture_output=True, text=True, timeout=timeout, env=env)
                    os.unlink(bin_path)
                else:
                    result = comp
                os.unlink(f.name)
        else:
            return {"error": f"Language '{target_language}' not executable"}
    except subprocess.TimeoutExpired:
        return {"compiled": False, "output": "", "error": "Timeout (10s)", "score": 0}
    except Exception as e:
        return {"compiled": False, "output": "", "error": str(e), "score": 0}

    compiled = result.returncode == 0
    has_output = bool(result.stdout.strip())
    score = 0
    if compiled and has_output: score = 100
    elif compiled: score = 70
    elif result.stderr and "warning" in result.stderr.lower(): score = 30

    # Award XP
    try:
        from routes.xp_helper import award_xp
        xp = 50 if score == 100 else 25 if score >= 70 else 10
        await award_xp(user_id, "rosetta_challenge", f"rosetta_{target_language.lower()}", xp)
    except: pass

    # Save result
    await _db.rosetta_challenges.insert_one({
        "challenge_id": challenge_id, "user_id": user_id,
        "target_language": target_language, "score": score,
        "compiled": compiled, "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "challenge_id": challenge_id,
        "compiled": compiled,
        "output": result.stdout[:2000] if result.stdout else "",
        "error": result.stderr[:1000] if result.stderr else None,
        "score": score,
        "xp_awarded": 50 if score == 100 else 25 if score >= 70 else 10,
        "feedback": "Perfect! Code compiles and produces output." if score == 100 else
                    "Good! Code compiles but no output detected." if score >= 70 else
                    "Code has errors. Check the error output and try again." if not compiled else
                    "Partial credit.",
    }


@router.get("/history/{user_id}")
async def challenge_history(user_id: str, limit: int = Query(20, le=50)):
    """Get user's challenge history."""
    results = await _db.rosetta_challenges.find({"user_id": user_id}, PROJ).sort("timestamp", -1).limit(limit).to_list(limit)
    total = await _db.rosetta_challenges.count_documents({"user_id": user_id})
    perfect = await _db.rosetta_challenges.count_documents({"user_id": user_id, "score": 100})
    return {"history": results, "total": total, "perfect_scores": perfect}

@router.get("/")
async def list_rosetta_concepts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=100),
    language: str = None,
    concept: str = None
):
    """List Rosetta Stone entries with pagination and optional filtering."""
    query = {}
    if language:
        query["language"] = language
    if concept:
        query["concept"] = concept
        
    skip = (page - 1) * limit
    
    total = await _db.rosetta_stone.count_documents(query)
    entries = await _db.rosetta_stone.find(query, PROJ).skip(skip).limit(limit).to_list(limit)
    
    return {
        "entries": entries,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }
