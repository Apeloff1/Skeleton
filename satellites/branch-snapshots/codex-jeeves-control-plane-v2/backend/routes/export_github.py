"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CODEDOCK EXPORT & GITHUB INTEGRATION v11.8                      ║
║                                                                              ║
║  Features:                                                                   ║
║  • PDF Export (code files, projects, documentation)                          ║
║  • GitHub Integration (push, pull, clone with PAT)                           ║
║  • Project Packaging                                                         ║
║  • AI Interaction Logging                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from core.outcall_manager import outcalls
import uuid
import os
import base64
import httpx

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/export", tags=["Export & GitHub Integration"])


@router.get("/github/actions-log")
async def list_github_actions(limit: int = 30):
    """Surface stored GitHub Actions export events (github_actions was written but never read)."""
    rows = await export_db.github_actions.find({}, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 100))
    return {"actions": rows, "count": len(rows)}

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
mongo_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
export_db = mongo_client.codedock_export
logs_db = mongo_client.codedock_logs

# ============================================================================
# REQUEST MODELS
# ============================================================================

class PDFExportRequest(BaseModel):
    content: str
    filename: str = "code_export"
    content_type: str = "code"  # code, documentation, project
    language: Optional[str] = "python"
    include_line_numbers: bool = True
    syntax_highlighting: bool = True


class GitHubPushRequest(BaseModel):
    token: str
    repo_owner: str
    repo_name: str
    file_path: str
    content: str
    commit_message: str = "Update from CodeDock"
    branch: str = "main"


class GitHubPullRequest(BaseModel):
    token: str
    repo_owner: str
    repo_name: str
    file_path: str
    branch: str = "main"


class GitHubRepoRequest(BaseModel):
    token: str
    repo_name: str
    description: Optional[str] = "Created with CodeDock"
    private: bool = False


class AIInteractionLog(BaseModel):
    user_id: str
    interaction_type: str  # code_generation, debugging, tutoring, etc.
    prompt: str
    response: str
    model_used: Optional[str] = "gpt-4o"
    tokens_used: Optional[int] = 0
    was_helpful: Optional[bool] = None
    context: Dict[str, Any] = {}


# ============================================================================
# PDF EXPORT ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_export_info():
    """Get export system info"""
    return {
        "name": "CodeDock Export & GitHub Integration v11.8",
        "description": "Export to PDF, integrate with GitHub",
        "capabilities": [
            "PDF code export with syntax highlighting",
            "Project documentation export",
            "GitHub push/pull with PAT",
            "Repository creation",
            "AI interaction logging",
            "Export history tracking"
        ],
        "supported_formats": ["pdf", "json", "markdown", "zip"],
        "github_features": [
            "Push files to repository",
            "Pull files from repository",
            "Create new repositories",
            "Branch management",
            "Commit with custom messages"
        ]
    }


@router.post("/pdf")
async def export_to_pdf(request: PDFExportRequest):
    """
    Generate PDF-ready content (returns base64 encoded data)
    Note: Actual PDF generation would require a library like reportlab
    This returns formatted content that can be rendered client-side
    """
    
    # Generate formatted content
    lines = request.content.split('\n')
    formatted_lines = []
    
    for i, line in enumerate(lines, 1):
        if request.include_line_numbers:
            formatted_lines.append(f"{i:4d} | {line}")
        else:
            formatted_lines.append(line)
    
    formatted_content = '\n'.join(formatted_lines)
    
    # Create export record
    export_record = {
        "export_id": f"exp_{uuid.uuid4().hex[:12]}",
        "export_type": "pdf",
        "filename": request.filename,
        "content_type": request.content_type,
        "language": request.language,
        "lines": len(lines),
        "characters": len(request.content),
        "created_at": datetime.utcnow()
    }
    
    await export_db.exports.insert_one(export_record)
    
    # Return PDF-ready data
    return {
        "export_id": export_record["export_id"],
        "filename": f"{request.filename}.pdf",
        "content_type": request.content_type,
        "formatted_content": formatted_content,
        "metadata": {
            "lines": len(lines),
            "characters": len(request.content),
            "language": request.language,
            "exported_at": datetime.utcnow().isoformat()
        },
        "pdf_data": {
            "title": request.filename,
            "content": formatted_content,
            "syntax_highlighting": request.syntax_highlighting,
            "line_numbers": request.include_line_numbers
        }
    }


@router.post("/markdown")
async def export_to_markdown(
    content: str,
    title: str = "CodeDock Export",
    include_toc: bool = True
):
    """Export content as markdown"""
    
    markdown = f"# {title}\n\n"
    markdown += f"*Exported from CodeDock on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n\n"
    markdown += "---\n\n"
    markdown += content
    
    return {
        "markdown": markdown,
        "filename": f"{title.lower().replace(' ', '_')}.md",
        "characters": len(markdown)
    }


# ============================================================================
# GITHUB INTEGRATION ENDPOINTS
# ============================================================================

@router.post("/github/push")
async def push_to_github(request: GitHubPushRequest):
    """Push a file to a GitHub repository"""
    
    headers = {
        "Authorization": f"Bearer {request.token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    api_url = f"https://api.github.com/repos/{request.repo_owner}/{request.repo_name}/contents/{request.file_path}"
    
    async with httpx.AsyncClient() as client:
        # Check if file exists (to get SHA for update)
        existing_sha = None
        try:
            check_res = await client.get(api_url, headers=headers, params={"ref": request.branch})
            if check_res.status_code == 200:
                existing_sha = check_res.json().get("sha")
        except Exception:
            pass
        
        # Prepare content
        content_bytes = request.content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        payload = {
            "message": request.commit_message,
            "content": content_base64,
            "branch": request.branch
        }
        
        if existing_sha:
            payload["sha"] = existing_sha
        
        # Push to GitHub
        try:
            res = await client.put(api_url, headers=headers, json=payload)
            
            if res.status_code in [200, 201]:
                data = res.json()
                
                # Log the action
                await export_db.github_actions.insert_one({
                    "action": "push",
                    "repo": f"{request.repo_owner}/{request.repo_name}",
                    "file_path": request.file_path,
                    "branch": request.branch,
                    "commit_sha": data.get("commit", {}).get("sha"),
                    "timestamp": datetime.utcnow()
                })
                
                return {
                    "success": True,
                    "message": "File pushed successfully",
                    "commit_sha": data.get("commit", {}).get("sha"),
                    "file_url": data.get("content", {}).get("html_url"),
                    "updated": existing_sha is not None
                }
            else:
                error_msg = res.json().get("message", "Unknown error")
                raise HTTPException(status_code=res.status_code, detail=f"GitHub API error: {error_msg}")
                
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to connect to GitHub: {str(e)}")


@router.post("/github/pull")
async def pull_from_github(request: GitHubPullRequest):
    """Pull a file from a GitHub repository"""
    
    headers = {
        "Authorization": f"Bearer {request.token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    api_url = f"https://api.github.com/repos/{request.repo_owner}/{request.repo_name}/contents/{request.file_path}"
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(api_url, headers=headers, params={"ref": request.branch})
            
            if res.status_code == 200:
                data = res.json()
                
                # Decode content
                content_base64 = data.get("content", "")
                content = base64.b64decode(content_base64).decode('utf-8')
                
                # Log the action
                await export_db.github_actions.insert_one({
                    "action": "pull",
                    "repo": f"{request.repo_owner}/{request.repo_name}",
                    "file_path": request.file_path,
                    "branch": request.branch,
                    "sha": data.get("sha"),
                    "timestamp": datetime.utcnow()
                })
                
                return {
                    "success": True,
                    "file_path": request.file_path,
                    "content": content,
                    "sha": data.get("sha"),
                    "size": data.get("size"),
                    "encoding": data.get("encoding"),
                    "html_url": data.get("html_url")
                }
            elif res.status_code == 404:
                raise HTTPException(status_code=404, detail="File not found in repository")
            else:
                error_msg = res.json().get("message", "Unknown error")
                raise HTTPException(status_code=res.status_code, detail=f"GitHub API error: {error_msg}")
                
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to connect to GitHub: {str(e)}")


@router.post("/github/create-repo")
async def create_github_repo(request: GitHubRepoRequest):
    """Create a new GitHub repository"""
    
    headers = {
        "Authorization": f"Bearer {request.token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {
        "name": request.repo_name,
        "description": request.description,
        "private": request.private,
        "auto_init": True  # Initialize with README
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post("https://api.github.com/user/repos", headers=headers, json=payload)
            
            if res.status_code == 201:
                data = res.json()
                
                # Log the action
                await export_db.github_actions.insert_one({
                    "action": "create_repo",
                    "repo": data.get("full_name"),
                    "private": request.private,
                    "timestamp": datetime.utcnow()
                })
                
                return {
                    "success": True,
                    "message": "Repository created successfully",
                    "repo_name": data.get("full_name"),
                    "repo_url": data.get("html_url"),
                    "clone_url": data.get("clone_url"),
                    "private": data.get("private")
                }
            else:
                error_msg = res.json().get("message", "Unknown error")
                raise HTTPException(status_code=res.status_code, detail=f"GitHub API error: {error_msg}")
                
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to connect to GitHub: {str(e)}")


@router.get("/github/repos")
async def list_github_repos(token: str, per_page: int = 30, page: int = 1):
    """List user's GitHub repositories"""
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                "https://api.github.com/user/repos",
                headers=headers,
                params={"per_page": per_page, "page": page, "sort": "updated"}
            )
            
            if res.status_code == 200:
                repos = res.json()
                return {
                    "success": True,
                    "count": len(repos),
                    "repos": [
                        {
                            "name": r.get("name"),
                            "full_name": r.get("full_name"),
                            "description": r.get("description"),
                            "private": r.get("private"),
                            "url": r.get("html_url"),
                            "default_branch": r.get("default_branch"),
                            "updated_at": r.get("updated_at")
                        }
                        for r in repos
                    ]
                }
            else:
                error_msg = res.json().get("message", "Unknown error")
                raise HTTPException(status_code=res.status_code, detail=f"GitHub API error: {error_msg}")
                
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to connect to GitHub: {str(e)}")


# ============================================================================
# AI INTERACTION LOGGING ENDPOINTS
# ============================================================================

@router.post("/log-ai-interaction")
async def log_ai_interaction(interaction: AIInteractionLog):
    """Log an AI interaction for Jeeves learning"""
    
    log_entry = {
        "log_id": f"ai_{uuid.uuid4().hex[:12]}",
        "user_id": interaction.user_id,
        "interaction_type": interaction.interaction_type,
        "prompt": interaction.prompt[:2000],  # Truncate long prompts
        "response": interaction.response[:5000],  # Truncate long responses
        "model_used": interaction.model_used,
        "tokens_used": interaction.tokens_used,
        "was_helpful": interaction.was_helpful,
        "context": interaction.context,
        "timestamp": datetime.utcnow()
    }
    
    await logs_db.ai_interactions.insert_one(log_entry)
    
    # Also log to logscraper user actions
    await logs_db.user_actions.insert_one({
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        "user_id": interaction.user_id,
        "action_type": "ai_code_generated" if interaction.interaction_type == "code_generation" else "jeeves_asked",
        "action_data": {
            "interaction_type": interaction.interaction_type,
            "model": interaction.model_used,
            "tokens": interaction.tokens_used
        },
        "timestamp": datetime.utcnow(),
        "processed": False
    })
    
    return {
        "logged": True,
        "log_id": log_entry["log_id"],
        "message": "AI interaction logged successfully"
    }


@router.get("/ai-interactions/{user_id}")
async def get_user_ai_interactions(user_id: str, limit: int = 50):
    """Get user's AI interaction history"""
    
    interactions = await logs_db.ai_interactions.find(
        {"user_id": user_id}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    # Calculate stats
    total = len(interactions)
    helpful_count = sum(1 for i in interactions if i.get("was_helpful") is True)
    total_tokens = sum(i.get("tokens_used", 0) for i in interactions)
    
    # Group by type
    by_type = {}
    for i in interactions:
        t = i.get("interaction_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    
    return {
        "user_id": user_id,
        "total_interactions": total,
        "helpful_percentage": (helpful_count / total * 100) if total > 0 else 0,
        "total_tokens_used": total_tokens,
        "by_type": by_type,
        "recent_interactions": [
            {
                "log_id": i["log_id"],
                "type": i.get("interaction_type"),
                "prompt_preview": i.get("prompt", "")[:100] + "...",
                "model": i.get("model_used"),
                "was_helpful": i.get("was_helpful"),
                "timestamp": i.get("timestamp").isoformat() if i.get("timestamp") else None
            }
            for i in interactions[:10]
        ]
    }


@router.post("/ai-feedback")
async def submit_ai_feedback(log_id: str, was_helpful: bool, feedback: Optional[str] = None):
    """Submit feedback for an AI interaction"""
    
    result = await logs_db.ai_interactions.update_one(
        {"log_id": log_id},
        {
            "$set": {
                "was_helpful": was_helpful,
                "user_feedback": feedback,
                "feedback_at": datetime.utcnow()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Interaction not found")
    
    return {
        "updated": True,
        "log_id": log_id,
        "was_helpful": was_helpful
    }


@router.get("/export-history/{user_id}")
async def get_export_history(user_id: str, limit: int = 20):
    """Get user's export history"""
    
    exports = await export_db.exports.find().sort("created_at", -1).limit(limit).to_list(limit)
    
    return {
        "total": len(exports),
        "exports": [
            {
                "export_id": e["export_id"],
                "type": e.get("export_type"),
                "filename": e.get("filename"),
                "created_at": e.get("created_at").isoformat() if e.get("created_at") else None
            }
            for e in exports
        ]
    }
