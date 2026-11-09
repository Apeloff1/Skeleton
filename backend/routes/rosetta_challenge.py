"""Rosetta Challenge Mode — Translate code between languages, auto-graded via playground"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone
import difflib
import os, random, uuid

from core.exec_guard import code_execution_enabled, execution_disabled_message
from routes.gameforge_auth import get_current_user

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/rosetta-challenge", tags=["rosetta-challenge"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}

EXEC_LANGS = ["Python", "JavaScript", "TypeScript", "Go", "Rust", "C", "C++"]
LANG_MAP = {"Python":"python","JavaScript":"javascript","TypeScript":"typescript","Go":"go","Rust":"rust","C":"c","C++":"cpp"}


class ChallengeSubmission(BaseModel):
    challenge_id: str = Field(..., min_length=10, max_length=128, pattern=r"^rc_[A-Za-z0-9_-]+$")
    target_language: str = Field(..., min_length=1, max_length=32)
    user_code: str = Field(..., min_length=1, max_length=100_000)


def _owner(user: dict) -> str:
    if not user or user.get("disabled") or user.get("dev_mode"):
        raise HTTPException(status_code=401, detail="Sign in to use Rosetta challenges")
    owner = str(user.get("email") or user.get("user_id") or "").strip()
    if not owner:
        raise HTTPException(status_code=401, detail="Authenticated account identity is unavailable")
    return owner


@router.get("/generate")
async def generate_challenge(
    difficulty: str = Query("medium", pattern=r"^(easy|medium|hard|expert)$"),
    source_lang: str | None = Query(default=None, max_length=32),
    target_lang: str | None = Query(default=None, max_length=32),
    user: dict = Depends(get_current_user),
):
    """Generate a Rosetta Challenge — translate code from one language to another."""
    owner = _owner(user)
    if source_lang and source_lang not in EXEC_LANGS or target_lang and target_lang not in EXEC_LANGS:
        raise HTTPException(status_code=422, detail="Unsupported Rosetta language")
    if source_lang and target_lang and source_lang == target_lang:
        raise HTTPException(status_code=422, detail="Source and target languages must differ")
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
        raise HTTPException(status_code=503, detail=f"No reviewed Rosetta pair is available for {concept}")

    hint_lines = target_entry.get("code", "").split("\n")[:3]

    challenge_id = f"rc_{uuid.uuid4().hex}"
    await _db.rosetta_challenge_authority.insert_one({
        "challenge_id": challenge_id,
        "owner": owner,
        "concept": concept,
        "source_language": source_lang,
        "target_language": target_lang,
        "reference_code": target_entry.get("code", ""),
        "created_at": datetime.now(timezone.utc),
    })
    return {
        "challenge_id": challenge_id,
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
    submission: ChallengeSubmission,
    user: dict = Depends(get_current_user),
):
    """Submit a challenge solution — execute and grade."""
    owner = _owner(user)
    authority = await _db.rosetta_challenge_authority.find_one(
        {"challenge_id": submission.challenge_id, "owner": owner}, PROJ
    )
    if not authority:
        raise HTTPException(status_code=404, detail="Rosetta challenge not found for this account")
    if authority.get("target_language") != submission.target_language:
        raise HTTPException(status_code=409, detail="The submitted target language does not match this challenge")
    if not code_execution_enabled():
        raise HTTPException(status_code=503, detail=execution_disabled_message("Rosetta challenge execution"))

    challenge_id = submission.challenge_id
    target_language = submission.target_language
    user_code = submission.user_code

    lang_key = LANG_MAP.get(target_language, target_language.lower())

    import subprocess, tempfile
    env = {**os.environ, "PATH": f"{os.environ.get('PATH','')}:/usr/local/go/bin:/root/.cargo/bin", "GOCACHE": "/tmp/go-cache", "GOPATH": "/tmp/gopath"}
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
    except Exception:
        return {"compiled": False, "output": "", "error": "compile_failed", "score": 0}

    compiled = result.returncode == 0
    has_output = bool(result.stdout.strip())
    reference = str(authority.get("reference_code") or "")
    similarity = difflib.SequenceMatcher(None, "".join(user_code.split()), "".join(reference.split())).ratio() if reference else 0.0
    score = round((60 if compiled else 0) + similarity * 40)
    passed = bool(compiled and score >= 70)

    # Award XP
    try:
        from routes.xp_helper import award_xp
        xp = 50 if score >= 90 else 25 if passed else 0
        if xp:
            await award_xp(owner, "rosetta_challenge", f"rosetta_{target_language.lower()}", xp)
    except (ImportError, OSError, RuntimeError):
        pass

    # Save result
    await _db.rosetta_challenges.insert_one({
        "challenge_id": challenge_id, "user_id": owner,
        "target_language": target_language, "score": score,
        "compiled": compiled, "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "challenge_id": challenge_id,
        "compiled": compiled,
        "output": result.stdout[:2000] if result.stdout else "",
        "error": result.stderr[:1000] if result.stderr else None,
        "score": score,
        "passed": passed,
        "xp_awarded": 50 if score >= 90 else 25 if passed else 0,
        "feedback": "Excellent translation: it compiles and closely matches the reviewed implementation." if score >= 90 else
                    "The translation compiles and meets the structural acceptance threshold." if passed else
                    "Code has errors. Check the error output and try again." if not compiled else
                    "The code compiles, but it does not yet implement enough of the reviewed translation.",
    }


@router.get("/history/{user_id}")
async def challenge_history(
    user_id: str,
    limit: int = Query(20, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Get user's challenge history."""
    owner = _owner(user)
    if user_id not in {owner, "me"}:
        raise HTTPException(status_code=404, detail="Rosetta history not found")
    user_id = owner
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
