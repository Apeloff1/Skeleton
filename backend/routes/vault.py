"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CODEDOCK VAULT SYSTEM v11.0.0                              ║
║                                                                               ║
║  Secure Storage for Code, Assets, and Data:                                   ║
║  • Code Block Vault - Store and organize code snippets                        ║
║  • Asset Vault - Store images, files, and media                               ║
║  • Database Vault - Store structured data and schemas                         ║
║  • Learning Vault - Store progress, notes, and achievements                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid
import hashlib
import base64
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

router = APIRouter(prefix="/vault", tags=["Vault System"])

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client.codedock_vault

# Collections
code_vault = db.code_blocks
asset_vault = db.assets
database_vault = db.database_schemas
learning_vault = db.learning_data
activity_log = db.activity_log

# ============================================================================
# MODELS
# ============================================================================

class VaultType(str, Enum):
    CODE = "code"
    ASSET = "asset"
    DATABASE = "database"
    LEARNING = "learning"

class CodeLanguage(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    RUST = "rust"
    GO = "go"
    SQL = "sql"
    HTML = "html"
    CSS = "css"
    OTHER = "other"

class CodeBlockCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    code: str = Field(..., min_length=1)
    language: CodeLanguage = CodeLanguage.PYTHON
    tags: List[str] = []
    category: Optional[str] = None
    is_public: bool = False
    source: Optional[str] = None  # Where the code came from (course, project, etc.)

class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    asset_type: str  # image, document, audio, video, etc.
    content_base64: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}

class DatabaseSchemaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    schema_type: str = "relational"  # relational, document, graph, key-value
    tables: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    sql_script: Optional[str] = None
    tags: List[str] = []

class LearningDataCreate(BaseModel):
    data_type: str  # note, bookmark, achievement, milestone
    title: str
    content: Optional[str] = None
    course_id: Optional[str] = None
    related_items: List[str] = []
    metadata: Dict[str, Any] = {}

# ============================================================================
# ACTIVITY LOGGING
# ============================================================================

async def log_activity(
    action: str,
    vault_type: VaultType,
    item_id: str,
    user_id: str = "default_user",
    details: Dict[str, Any] = None
):
    """Log all vault activities for audit trail"""
    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "vault_type": vault_type.value,
        "item_id": item_id,
        "user_id": user_id,
        "details": details or {}
    }
    await activity_log.insert_one(log_entry)
    return log_entry

# ============================================================================
# VAULT INFO ENDPOINT
# ============================================================================

@router.get("/info")
async def get_vault_info():
    """Get information about all vaults"""
    code_count = await code_vault.count_documents({})
    asset_count = await asset_vault.count_documents({})
    db_count = await database_vault.count_documents({})
    learning_count = await learning_vault.count_documents({})
    log_count = await activity_log.count_documents({})
    
    return {
        "name": "CodeDock Vault System",
        "version": "11.0.0",
        "vaults": {
            "code_blocks": {
                "count": code_count,
                "description": "Store and organize code snippets, functions, and algorithms"
            },
            "assets": {
                "count": asset_count,
                "description": "Store images, documents, and media files"
            },
            "database_schemas": {
                "count": db_count,
                "description": "Store database designs, schemas, and SQL scripts"
            },
            "learning_data": {
                "count": learning_count,
                "description": "Store notes, bookmarks, and learning progress"
            }
        },
        "activity_logs": log_count,
        "features": [
            "Full-text search",
            "Tagging system",
            "Version history",
            "Activity logging",
            "Import/Export",
            "Sharing capabilities"
        ]
    }

# ============================================================================
# CODE BLOCK VAULT
# ============================================================================

@router.post("/code")
async def create_code_block(block: CodeBlockCreate, user_id: str = "default_user"):
    """Store a new code block in the vault"""
    block_id = str(uuid.uuid4())
    
    # Calculate hash for deduplication
    code_hash = hashlib.sha256(block.code.encode()).hexdigest()
    
    doc = {
        "id": block_id,
        "title": block.title,
        "description": block.description,
        "code": block.code,
        "language": block.language.value,
        "tags": block.tags,
        "category": block.category,
        "is_public": block.is_public,
        "source": block.source,
        "code_hash": code_hash,
        "line_count": len(block.code.splitlines()),
        "char_count": len(block.code),
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "version": 1,
        "versions": [{
            "version": 1,
            "code": block.code,
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    await code_vault.insert_one(doc)
    await log_activity("create", VaultType.CODE, block_id, user_id, {"title": block.title})
    
    # Remove MongoDB _id for JSON serialization
    doc.pop("_id", None)
    return {"status": "created", "id": block_id, "block": doc}

@router.get("/code")
async def list_code_blocks(
    user_id: str = "default_user",
    language: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """List code blocks with filtering"""
    query = {"user_id": user_id}
    
    if language:
        query["language"] = language
    if tag:
        query["tags"] = tag
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"code": {"$regex": search, "$options": "i"}}
        ]
    
    cursor = code_vault.find(query).skip(skip).limit(limit).sort("created_at", -1)
    blocks = await cursor.to_list(length=limit)
    
    # Remove MongoDB _id for JSON serialization
    for block in blocks:
        block.pop("_id", None)
    
    total = await code_vault.count_documents(query)
    
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "blocks": blocks
    }

@router.get("/code/{block_id}")
async def get_code_block(block_id: str):
    """Get a specific code block"""
    block = await code_vault.find_one({"id": block_id})
    if not block:
        raise HTTPException(status_code=404, detail="Code block not found")
    
    block.pop("_id", None)
    return block

@router.put("/code/{block_id}")
async def update_code_block(block_id: str, block: CodeBlockCreate, user_id: str = "default_user"):
    """Update a code block (creates new version)"""
    existing = await code_vault.find_one({"id": block_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Code block not found")
    
    new_version = existing.get("version", 1) + 1
    versions = existing.get("versions", [])
    versions.append({
        "version": new_version,
        "code": block.code,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    update = {
        "$set": {
            "title": block.title,
            "description": block.description,
            "code": block.code,
            "language": block.language.value,
            "tags": block.tags,
            "category": block.category,
            "is_public": block.is_public,
            "source": block.source,
            "code_hash": hashlib.sha256(block.code.encode()).hexdigest(),
            "line_count": len(block.code.splitlines()),
            "char_count": len(block.code),
            "updated_at": datetime.utcnow().isoformat(),
            "version": new_version,
            "versions": versions[-10:]  # Keep last 10 versions
        }
    }
    
    await code_vault.update_one({"id": block_id}, update)
    await log_activity("update", VaultType.CODE, block_id, user_id, {"new_version": new_version})
    
    return {"status": "updated", "id": block_id, "version": new_version}

@router.delete("/code/{block_id}")
async def delete_code_block(block_id: str, user_id: str = "default_user"):
    """Delete a code block"""
    result = await code_vault.delete_one({"id": block_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Code block not found")
    
    await log_activity("delete", VaultType.CODE, block_id, user_id)
    return {"status": "deleted", "id": block_id}

# ============================================================================
# ASSET VAULT
# ============================================================================

@router.post("/asset")
async def create_asset(asset: AssetCreate, user_id: str = "default_user"):
    """Store a new asset in the vault"""
    asset_id = str(uuid.uuid4())
    
    # Calculate size if base64 content provided
    size = 0
    if asset.content_base64:
        size = len(base64.b64decode(asset.content_base64))
    
    doc = {
        "id": asset_id,
        "name": asset.name,
        "description": asset.description,
        "asset_type": asset.asset_type,
        "content_base64": asset.content_base64,
        "url": asset.url,
        "tags": asset.tags,
        "metadata": asset.metadata,
        "size_bytes": size,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    await asset_vault.insert_one(doc)
    await log_activity("create", VaultType.ASSET, asset_id, user_id, {"name": asset.name, "type": asset.asset_type})
    
    # Remove MongoDB _id for JSON serialization
    doc.pop("_id", None)
    return {"status": "created", "id": asset_id, "asset": {**doc, "content_base64": "[STORED]" if asset.content_base64 else None}}

@router.get("/asset")
async def list_assets(
    user_id: str = "default_user",
    asset_type: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """List assets with filtering"""
    query = {"user_id": user_id}
    
    if asset_type:
        query["asset_type"] = asset_type
    if tag:
        query["tags"] = tag
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    cursor = asset_vault.find(query, {"content_base64": 0}).skip(skip).limit(limit).sort("created_at", -1)
    assets = await cursor.to_list(length=limit)
    
    for asset in assets:
        asset.pop("_id", None)
    
    total = await asset_vault.count_documents(query)
    
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "assets": assets
    }

@router.get("/asset/{asset_id}")
async def get_asset(asset_id: str, include_content: bool = True):
    """Get a specific asset"""
    projection = None if include_content else {"content_base64": 0}
    asset = await asset_vault.find_one({"id": asset_id}, projection)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    asset.pop("_id", None)
    return asset

@router.delete("/asset/{asset_id}")
async def delete_asset(asset_id: str, user_id: str = "default_user"):
    """Delete an asset"""
    result = await asset_vault.delete_one({"id": asset_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    await log_activity("delete", VaultType.ASSET, asset_id, user_id)
    return {"status": "deleted", "id": asset_id}

# ============================================================================
# DATABASE VAULT
# ============================================================================

@router.post("/database")
async def create_database_schema(schema: DatabaseSchemaCreate, user_id: str = "default_user"):
    """Store a new database schema in the vault"""
    schema_id = str(uuid.uuid4())
    
    doc = {
        "id": schema_id,
        "name": schema.name,
        "description": schema.description,
        "schema_type": schema.schema_type,
        "tables": schema.tables,
        "relationships": schema.relationships,
        "sql_script": schema.sql_script,
        "tags": schema.tags,
        "table_count": len(schema.tables),
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "version": 1,
        "versions": [{
            "version": 1,
            "tables": schema.tables,
            "sql_script": schema.sql_script,
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    await database_vault.insert_one(doc)
    await log_activity("create", VaultType.DATABASE, schema_id, user_id, {"name": schema.name})
    
    # Remove MongoDB _id for JSON serialization
    doc.pop("_id", None)
    return {"status": "created", "id": schema_id, "schema": doc}

@router.get("/database")
async def list_database_schemas(
    user_id: str = "default_user",
    schema_type: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """List database schemas"""
    query = {"user_id": user_id}
    
    if schema_type:
        query["schema_type"] = schema_type
    if tag:
        query["tags"] = tag
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    cursor = database_vault.find(query).skip(skip).limit(limit).sort("created_at", -1)
    schemas = await cursor.to_list(length=limit)
    
    for schema in schemas:
        schema.pop("_id", None)
    
    total = await database_vault.count_documents(query)
    
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "schemas": schemas
    }

@router.get("/database/{schema_id}")
async def get_database_schema(schema_id: str):
    """Get a specific database schema"""
    schema = await database_vault.find_one({"id": schema_id})
    if not schema:
        raise HTTPException(status_code=404, detail="Database schema not found")
    
    schema.pop("_id", None)
    return schema

@router.delete("/database/{schema_id}")
async def delete_database_schema(schema_id: str, user_id: str = "default_user"):
    """Delete a database schema"""
    result = await database_vault.delete_one({"id": schema_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Database schema not found")
    
    await log_activity("delete", VaultType.DATABASE, schema_id, user_id)
    return {"status": "deleted", "id": schema_id}

# ============================================================================
# LEARNING VAULT
# ============================================================================

@router.post("/learning")
async def create_learning_data(data: LearningDataCreate, user_id: str = "default_user"):
    """Store learning data (notes, bookmarks, achievements)"""
    data_id = str(uuid.uuid4())
    
    doc = {
        "id": data_id,
        "data_type": data.data_type,
        "title": data.title,
        "content": data.content,
        "course_id": data.course_id,
        "related_items": data.related_items,
        "metadata": data.metadata,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    await learning_vault.insert_one(doc)
    await log_activity("create", VaultType.LEARNING, data_id, user_id, {"type": data.data_type, "title": data.title})
    
    # Remove MongoDB _id for JSON serialization
    doc.pop("_id", None)
    return {"status": "created", "id": data_id, "data": doc}

@router.get("/learning")
async def list_learning_data(
    user_id: str = "default_user",
    data_type: Optional[str] = None,
    course_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """List learning data"""
    query = {"user_id": user_id}
    
    if data_type:
        query["data_type"] = data_type
    if course_id:
        query["course_id"] = course_id
    
    cursor = learning_vault.find(query).skip(skip).limit(limit).sort("created_at", -1)
    items = await cursor.to_list(length=limit)
    
    for item in items:
        item.pop("_id", None)
    
    total = await learning_vault.count_documents(query)
    
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "items": items
    }

@router.get("/learning/{data_id}")
async def get_learning_data(data_id: str):
    """Get specific learning data"""
    data = await learning_vault.find_one({"id": data_id})
    if not data:
        raise HTTPException(status_code=404, detail="Learning data not found")
    
    data.pop("_id", None)
    return data

# ============================================================================
# ACTIVITY LOG
# ============================================================================

@router.get("/activity")
async def get_activity_log(
    user_id: str = "default_user",
    vault_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """Get activity log with filtering"""
    query = {"user_id": user_id}
    
    if vault_type:
        query["vault_type"] = vault_type
    if action:
        query["action"] = action
    
    cursor = activity_log.find(query).skip(skip).limit(limit).sort("timestamp", -1)
    logs = await cursor.to_list(length=limit)
    
    for log in logs:
        log.pop("_id", None)
    
    total = await activity_log.count_documents(query)
    
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "logs": logs
    }

# ============================================================================
# STATISTICS
# ============================================================================

@router.get("/stats")
async def get_vault_stats(user_id: str = "default_user"):
    """Get comprehensive vault statistics"""
    
    # Code stats
    code_count = await code_vault.count_documents({"user_id": user_id})
    code_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$language",
            "count": {"$sum": 1},
            "total_lines": {"$sum": "$line_count"}
        }}
    ]
    code_by_lang = await code_vault.aggregate(code_pipeline).to_list(length=100)
    
    # Asset stats
    asset_count = await asset_vault.count_documents({"user_id": user_id})
    asset_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$asset_type",
            "count": {"$sum": 1},
            "total_size": {"$sum": "$size_bytes"}
        }}
    ]
    assets_by_type = await asset_vault.aggregate(asset_pipeline).to_list(length=100)
    
    # Database stats
    db_count = await database_vault.count_documents({"user_id": user_id})
    
    # Learning stats
    learning_count = await learning_vault.count_documents({"user_id": user_id})
    learning_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$data_type", "count": {"$sum": 1}}}
    ]
    learning_by_type = await learning_vault.aggregate(learning_pipeline).to_list(length=100)
    
    # Activity stats
    activity_count = await activity_log.count_documents({"user_id": user_id})
    
    return {
        "user_id": user_id,
        "code_blocks": {
            "total": code_count,
            "by_language": {item["_id"]: item for item in code_by_lang}
        },
        "assets": {
            "total": asset_count,
            "by_type": {item["_id"]: item for item in assets_by_type}
        },
        "database_schemas": {
            "total": db_count
        },
        "learning_data": {
            "total": learning_count,
            "by_type": {item["_id"]: item["count"] for item in learning_by_type}
        },
        "activity_logs": activity_count,
        "timestamp": datetime.utcnow().isoformat()
    }
