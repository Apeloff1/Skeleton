"""
Git Operations Routes - Version Control API
Version: 2.0.0 | REAL git operations (subprocess) for Pro Tools

Each "project" maps to a real working directory under GIT_WORKSPACE_BASE.
All endpoints shell out to the system `git` binary, so results reflect
actual repository state (no simulation).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import asyncio
import os
import re

router = APIRouter(prefix="/api/git", tags=["git"])

# Persistent-ish workspace root for per-project repos.
GIT_WORKSPACE_BASE = Path(os.environ.get(
    "GIT_WORKSPACE_BASE", "/app/backend/.git_workspaces"))
GIT_WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)

# The "active" project repo (set by /init, defaults to a sandbox project).
_active = {"project": "default"}

_SAFE = re.compile(r"[^A-Za-z0-9_.\-]")


def _repo_dir(project: Optional[str] = None) -> Path:
    name = _SAFE.sub("_", (project or _active["project"]) or "default")
    if not name or name in {".", ".."} or ".." in name:
        name = "default"
    root = GIT_WORKSPACE_BASE.resolve()
    candidate = root.joinpath(name).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid project path")
    return candidate


async def _git(args: List[str], project: Optional[str] = None, cwd: Optional[Path] = None) -> dict:
    """Run a git command in the project repo; return code/stdout/stderr."""
    repo = cwd or _repo_dir(project)
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return {
        "code": proc.returncode,
        "stdout": out.decode("utf-8", "replace").strip(),
        "stderr": err.decode("utf-8", "replace").strip(),
    }


async def _is_repo(project: Optional[str] = None) -> bool:
    repo = _repo_dir(project)
    if not repo.exists():
        return False
    r = await _git(["rev-parse", "--is-inside-work-tree"], project)
    return r["code"] == 0 and r["stdout"] == "true"


async def _require_repo():
    if not await _is_repo():
        raise HTTPException(status_code=400, detail="Not a git repository. Run 'git init' first.")


async def _current_branch() -> str:
    r = await _git(["symbolic-ref", "--short", "HEAD"])
    if r["code"] == 0 and r["stdout"]:
        return r["stdout"]
    r2 = await _git(["rev-parse", "--abbrev-ref", "HEAD"])
    return r2["stdout"] or "main"


# =============================================================================
# DATA MODELS
# =============================================================================

class GitInitRequest(BaseModel):
    project_name: str
    default_branch: str = "main"

class GitCommitRequest(BaseModel):
    message: str
    files: List[str] = []   # Empty = all staged files
    amend: bool = False

class GitBranchRequest(BaseModel):
    name: str
    from_branch: Optional[str] = None

class GitMergeRequest(BaseModel):
    source_branch: str
    target_branch: str = "main"
    strategy: str = "merge"  # merge, rebase, squash

class GitRemoteRequest(BaseModel):
    name: str = "origin"
    url: str

class GitStashRequest(BaseModel):
    message: Optional[str] = None
    include_untracked: bool = False


# =============================================================================
# API ROUTES (real git)
# =============================================================================

@router.post("/init")
async def git_init(request: GitInitRequest):
    """Initialize a REAL Git repository for the project."""
    _active["project"] = request.project_name
    repo = _repo_dir(request.project_name)
    repo.mkdir(parents=True, exist_ok=True)
    r = await _git(["init", "-b", request.default_branch])
    if r["code"] != 0:
        # Older git may not support -b; fall back.
        await _git(["init"])
        await _git(["checkout", "-B", request.default_branch])
    # Ensure an identity exists so commits don't fail.
    await _git(["config", "user.email", "studio@galaxy.dev"])
    await _git(["config", "user.name", "Galaxy Studio"])
    # Seed an empty initial commit so HEAD is born — branch/checkout work immediately.
    await _git(["commit", "--allow-empty", "-m", "Initial commit"])
    return {
        "success": True,
        "message": f"Initialized empty Git repository for '{request.project_name}'",
        "default_branch": request.default_branch,
        "path": str(repo),
        "hint": "Run 'git add .' to stage files, then 'git commit' to save changes",
    }


@router.get("/status")
async def git_status():
    """Get REAL Git status."""
    if not await _is_repo():
        return {"initialized": False, "message": "Not a git repository. Run 'git init' first."}
    r = await _git(["status", "--porcelain=v1", "--branch"])
    staged, working, untracked = [], [], []
    for line in r["stdout"].splitlines():
        if line.startswith("##"):
            continue
        x, y, name = line[0], line[1], line[3:]
        if x == "?" and y == "?":
            untracked.append(name)
            continue
        if x != " ":
            staged.append(name)
        if y != " ":
            working.append(name)
    branch = await _current_branch()
    return {
        "initialized": True,
        "current_branch": branch,
        "staged_files": staged,
        "working_changes": working,
        "untracked_files": untracked,
        "clean": not (staged or working or untracked),
    }


@router.post("/add")
async def git_add(files: List[str] = []):
    """Stage files for commit (real)."""
    await _require_repo()
    targets = files if files else ["-A"]
    r = await _git(["add", *targets])
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "git add failed")
    return {"success": True, "staged": files or ["all files"],
            "message": f"Staged {len(files) if files else 'all'} file(s) for commit"}


@router.post("/commit")
async def git_commit(request: GitCommitRequest):
    """Commit staged changes (real)."""
    await _require_repo()
    args = ["commit", "-m", request.message]
    if request.amend:
        args.append("--amend")
    if request.files:
        args += ["--", *request.files]
    r = await _git(args)
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or r["stdout"] or "Nothing to commit")
    h = await _git(["rev-parse", "--short", "HEAD"])
    branch = await _current_branch()
    return {"success": True,
            "commit": {"hash": h["stdout"], "message": request.message, "branch": branch},
            "message": r["stdout"].splitlines()[0] if r["stdout"] else f"[{branch} {h['stdout']}] {request.message}"}


@router.get("/log")
async def git_log(limit: int = 10):
    """Get REAL commit history."""
    await _require_repo()
    r = await _git(["log", f"-{max(1, min(limit, 200))}",
                    "--pretty=format:%h\x1f%s\x1f%an\x1f%aI"])
    commits = []
    for line in r["stdout"].splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "message": parts[1],
                            "author": parts[2], "timestamp": parts[3]})
    total = await _git(["rev-list", "--count", "HEAD"])
    return {"commits": commits, "total_commits": int(total["stdout"] or 0),
            "current_branch": await _current_branch()}


@router.get("/branches")
async def git_branches():
    """List all branches (real)."""
    await _require_repo()
    r = await _git(["branch", "--format=%(refname:short)"])
    current = await _current_branch()
    names = [b.strip() for b in r["stdout"].splitlines() if b.strip()]
    return {"branches": [{"name": b, "current": b == current} for b in names], "current": current}


@router.post("/branch")
async def git_branch(request: GitBranchRequest):
    """Create a new branch (real)."""
    await _require_repo()
    args = ["branch", request.name]
    if request.from_branch:
        args.append(request.from_branch)
    r = await _git(args)
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "branch creation failed")
    return {"success": True, "branch": request.name,
            "from_branch": request.from_branch or await _current_branch(),
            "message": f"Created branch '{request.name}'"}


@router.post("/checkout/{branch_name}")
async def git_checkout(branch_name: str, create: bool = False):
    """Switch to a branch (real)."""
    await _require_repo()
    args = ["checkout"] + (["-B"] if create else []) + [branch_name]
    r = await _git(args)
    if r["code"] != 0:
        raise HTTPException(status_code=404, detail=r["stderr"] or f"Branch '{branch_name}' not found")
    return {"success": True, "branch": branch_name, "message": f"Switched to branch '{branch_name}'"}


@router.post("/merge")
async def git_merge(request: GitMergeRequest):
    """Merge branches (real)."""
    await _require_repo()
    await _git(["checkout", request.target_branch])
    args = ["merge"]
    if request.strategy == "squash":
        args.append("--squash")
    args.append(request.source_branch)
    r = await _git(args)
    if r["code"] != 0:
        raise HTTPException(status_code=409, detail=r["stderr"] or r["stdout"] or "merge failed")
    h = await _git(["rev-parse", "--short", "HEAD"])
    return {"success": True,
            "merge_commit": {"hash": h["stdout"], "branch": request.target_branch},
            "strategy": request.strategy,
            "message": f"Merged '{request.source_branch}' into '{request.target_branch}'"}


@router.delete("/branch/{branch_name}")
async def delete_branch(branch_name: str, force: bool = False):
    """Delete a branch (real)."""
    await _require_repo()
    if branch_name == await _current_branch():
        raise HTTPException(status_code=400, detail="Cannot delete current branch")
    r = await _git(["branch", "-D" if force else "-d", branch_name])
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "branch deletion failed")
    return {"success": True, "deleted": branch_name, "message": f"Deleted branch '{branch_name}'"}


@router.post("/stash")
async def git_stash(request: GitStashRequest):
    """Stash changes (real)."""
    await _require_repo()
    args = ["stash", "push"]
    if request.include_untracked:
        args.append("-u")
    if request.message:
        args += ["-m", request.message]
    r = await _git(args)
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "stash failed")
    return {"success": True, "message": r["stdout"] or "Saved working directory and index state"}


@router.get("/stash/list")
async def git_stash_list():
    """List stashes (real)."""
    await _require_repo()
    r = await _git(["stash", "list"])
    stashes = []
    for i, line in enumerate(r["stdout"].splitlines()):
        if line.strip():
            ref, _, msg = line.partition(":")
            stashes.append({"id": i, "ref": ref.strip(), "message": msg.strip()})
    return {"stashes": stashes, "count": len(stashes)}


@router.post("/stash/pop")
async def git_stash_pop(index: int = 0):
    """Apply and remove a stash (real)."""
    await _require_repo()
    r = await _git(["stash", "pop", f"stash@{{{index}}}"])
    if r["code"] != 0:
        raise HTTPException(status_code=404, detail=r["stderr"] or f"stash@{{{index}}} not found")
    return {"success": True, "message": r["stdout"] or f"Applied stash@{{{index}}} and dropped"}


@router.post("/remote/add")
async def add_remote(request: GitRemoteRequest):
    """Add a remote repository (real)."""
    await _require_repo()
    r = await _git(["remote", "add", request.name, request.url])
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "remote add failed")
    return {"success": True, "remote": request.name, "url": request.url,
            "message": f"Added remote '{request.name}' -> {request.url}"}


@router.get("/remotes")
async def list_remotes():
    """List remote repositories (real)."""
    await _require_repo()
    r = await _git(["remote", "-v"])
    seen, remotes = set(), []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in seen:
            seen.add(parts[0])
            remotes.append({"name": parts[0], "url": parts[1]})
    return {"remotes": remotes}


@router.post("/push")
async def git_push(remote: str = "origin", branch: Optional[str] = None, force: bool = False):
    """Push commits to a remote (real — requires a configured, reachable remote)."""
    await _require_repo()
    target = branch or await _current_branch()
    args = ["push", remote, target] + (["--force"] if force else [])
    r = await _git(args)
    return {"success": r["code"] == 0, "remote": remote, "branch": target,
            "force": force, "message": r["stdout"] or r["stderr"]}


@router.post("/pull")
async def git_pull(remote: str = "origin", branch: Optional[str] = None, rebase: bool = False):
    """Pull commits from a remote (real — requires a configured, reachable remote)."""
    await _require_repo()
    target = branch or await _current_branch()
    args = ["pull"] + (["--rebase"] if rebase else []) + [remote, target]
    r = await _git(args)
    return {"success": r["code"] == 0, "remote": remote, "branch": target,
            "strategy": "rebase" if rebase else "merge",
            "message": r["stdout"] or r["stderr"]}


@router.get("/diff")
async def git_diff(staged: bool = False):
    """Show REAL file differences (numstat summary)."""
    await _require_repo()
    args = ["diff", "--numstat"] + (["--cached"] if staged else [])
    r = await _git(args)
    summary, ins, dele = [], 0, 0
    for line in r["stdout"].splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            a = 0 if parts[0] == "-" else int(parts[0])
            d = 0 if parts[1] == "-" else int(parts[1])
            ins += a
            dele += d
            summary.append({"file": parts[2], "insertions": a, "deletions": d})
    return {"files_changed": len(summary), "insertions": ins, "deletions": dele,
            "staged": staged, "diff_summary": summary}


@router.post("/reset")
async def git_reset(mode: str = "mixed", target: str = "HEAD~1"):
    """Reset current HEAD to a specified state (real)."""
    await _require_repo()
    if mode not in ["soft", "mixed", "hard"]:
        raise HTTPException(status_code=400, detail="Mode must be soft, mixed, or hard")
    r = await _git(["reset", f"--{mode}", target])
    if r["code"] != 0:
        raise HTTPException(status_code=400, detail=r["stderr"] or "reset failed")
    h = await _git(["rev-parse", "--short", "HEAD"])
    return {"success": True, "mode": mode, "target": target,
            "message": f"HEAD is now at {h['stdout'] or 'initial'}"}
