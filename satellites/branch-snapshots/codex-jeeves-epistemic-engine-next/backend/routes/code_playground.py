from core.databases import client as _SHARED_MONGO_CLIENT
"""Code Playground — Execute code in sandboxed environment. Supports 6 languages."""
from fastapi import APIRouter
from pydantic import BaseModel
import subprocess, os, tempfile
from dotenv import load_dotenv

load_dotenv()
router = APIRouter(prefix="/api/playground", tags=["playground"])

class CodeRequest(BaseModel):
    language: str
    code: str

@router.post("/run")
async def run_code(req: CodeRequest):
    """Execute code. Supports Python, JavaScript, TypeScript, Go, Rust, C/C++."""
    lang = req.language.lower()
    code = req.code
    if len(code) > 10000:
        return {"output": "", "error": "Code too long (max 10000 chars)"}
    env = {**os.environ, "PATH": f"{os.environ.get('PATH','')}:/usr/local/go/bin:/root/.cargo/bin", "HOME": "/root", "GOCACHE": "/tmp/go-cache", "GOPATH": "/tmp/gopath"}
    try:
        if lang in ("python", "python3"):
            result = subprocess.run(["python3", "-c", code], capture_output=True, text=True, timeout=10, cwd="/tmp", env=env)
        elif lang in ("javascript", "js", "node"):
            result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10, cwd="/tmp", env=env)
        elif lang in ("typescript", "ts"):
            result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10, cwd="/tmp", env=env)
        elif lang in ("go", "golang"):
            with tempfile.NamedTemporaryFile(suffix=".go", mode="w", dir="/tmp", delete=False) as f:
                f.write(code); f.flush()
                result = subprocess.run(["go", "run", f.name], capture_output=True, text=True, timeout=15, cwd="/tmp", env=env)
                os.unlink(f.name)
        elif lang in ("rust", "rs"):
            with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", dir="/tmp", delete=False) as f:
                f.write(code); fname = f.name; f.flush()
                out_bin = fname.replace(".rs", "")
                comp = subprocess.run(["rustc", fname, "-o", out_bin], capture_output=True, text=True, timeout=30, cwd="/tmp", env=env)
                if comp.returncode != 0:
                    os.unlink(fname)
                    return {"output": "", "error": comp.stderr, "exit_code": comp.returncode, "language": lang}
                result = subprocess.run([out_bin], capture_output=True, text=True, timeout=10, cwd="/tmp", env=env)
                os.unlink(fname)
                try: os.unlink(out_bin)
                except: pass
        elif lang in ("c", "cpp", "c++"):
            ext = ".c" if lang == "c" else ".cpp"
            compiler = "gcc" if lang == "c" else "g++"
            with tempfile.NamedTemporaryFile(suffix=ext, mode="w", dir="/tmp", delete=False) as f:
                f.write(code); fname = f.name; f.flush()
                out_bin = fname.replace(ext, "")
                comp = subprocess.run([compiler, fname, "-o", out_bin, "-lm"], capture_output=True, text=True, timeout=15, cwd="/tmp", env=env)
                if comp.returncode != 0:
                    os.unlink(fname)
                    return {"output": "", "error": comp.stderr, "exit_code": comp.returncode, "language": lang}
                result = subprocess.run([out_bin], capture_output=True, text=True, timeout=10, cwd="/tmp", env=env)
                os.unlink(fname)
                try: os.unlink(out_bin)
                except: pass
        else:
            return {"output": "", "error": f"Language '{lang}' not supported. Use python, javascript, typescript, go, rust, c, or cpp."}
        # Auto-award XP for code execution
        xp_type = "playground_clean" if result.returncode == 0 and not result.stderr else "playground_run"
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            _xp_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
            _xp_db = _xp_client[os.environ.get('DB_NAME', 'codedock')]
            from datetime import datetime, timezone
            xp_amount = 15 if xp_type == "playground_clean" else 10
            await _xp_db.user_gamification.update_one(
                {"user_id": "default_user"},
                {"$inc": {"total_xp": xp_amount, "activities_count": 1, f"domain_xp.{lang}": xp_amount},
                 "$set": {"last_active": datetime.now(timezone.utc).isoformat()},
                 "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True
            )
        except: pass
        return {"output": result.stdout, "error": result.stderr if result.stderr else None, "exit_code": result.returncode, "language": lang, "xp_awarded": 15 if result.returncode == 0 else 10}
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "Execution timed out (10s limit)", "exit_code": -1}
    except Exception as e:
        return {"output": "", "error": str(e), "exit_code": -1}

@router.get("/languages")
async def get_supported_languages():
    return {"languages": [
        {"id": "python", "name": "Python 3", "available": True},
        {"id": "javascript", "name": "Node.js", "available": True},
        {"id": "typescript", "name": "TypeScript (via Node)", "available": True},
        {"id": "go", "name": "Go 1.22", "available": True},
        {"id": "rust", "name": "Rust 1.95", "available": True},
        {"id": "c", "name": "C (GCC)", "available": True},
        {"id": "cpp", "name": "C++ (G++)", "available": True},
    ]}
