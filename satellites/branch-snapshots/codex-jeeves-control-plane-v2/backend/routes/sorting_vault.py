"""
Sorting Vault - Central Hub for All Vault Systems
Version: 1.0.0 | The Master Organizer
Connects to: Code Vault, Asset Vault, Template Vault, Snippet Vault, Project Vault
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import hashlib

router = APIRouter(prefix="/api/sorting-vault", tags=["sorting-vault"])

# =============================================================================
# DATA MODELS
# =============================================================================

class VaultType(str, Enum):
    CODE = "code"
    ASSET = "asset"
    TEMPLATE = "template"
    SNIPPET = "snippet"
    PROJECT = "project"
    AI_GENERATED = "ai_generated"
    LEARNING = "learning"

class VaultItem(BaseModel):
    id: str
    name: str
    vault_type: VaultType
    category: str
    tags: List[str] = []
    size_bytes: int
    created_at: str
    modified_at: str
    metadata: Dict[str, Any] = {}
    preview: Optional[str] = None
    starred: bool = False
    archived: bool = False

class VaultFolder(BaseModel):
    id: str
    name: str
    color: str
    icon: str
    item_count: int
    vault_types: List[VaultType]
    created_at: str

class SortingRule(BaseModel):
    id: str
    name: str
    conditions: List[Dict[str, Any]]
    action: str  # move_to_folder, tag, archive, star
    target: str
    enabled: bool = True

class VaultConnection(BaseModel):
    vault_id: str
    vault_name: str
    vault_type: VaultType
    endpoint: str
    status: str  # connected, disconnected, syncing
    last_sync: str
    item_count: int
    size_mb: float

# =============================================================================
# SIMULATED VAULT DATA
# =============================================================================

class SortingVaultState:
    def __init__(self):
        self.items: List[VaultItem] = []
        self.folders: List[VaultFolder] = []
        self.rules: List[SortingRule] = []
        self.connections: List[VaultConnection] = []
        self._initialize_data()
    
    def _initialize_data(self):
        # Initialize connected vaults
        self.connections = [
            VaultConnection(
                vault_id="vault_code",
                vault_name="Code Vault",
                vault_type=VaultType.CODE,
                endpoint="/api/vault/code",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=156,
                size_mb=12.5
            ),
            VaultConnection(
                vault_id="vault_asset",
                vault_name="Asset Vault",
                vault_type=VaultType.ASSET,
                endpoint="/api/vault/assets",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=89,
                size_mb=245.8
            ),
            VaultConnection(
                vault_id="vault_template",
                vault_name="Template Vault",
                vault_type=VaultType.TEMPLATE,
                endpoint="/api/vault/templates",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=47,
                size_mb=3.2
            ),
            VaultConnection(
                vault_id="vault_snippet",
                vault_name="Snippet Vault",
                vault_type=VaultType.SNIPPET,
                endpoint="/api/vault/snippets",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=234,
                size_mb=1.8
            ),
            VaultConnection(
                vault_id="vault_project",
                vault_name="Project Vault",
                vault_type=VaultType.PROJECT,
                endpoint="/api/vault/projects",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=12,
                size_mb=156.4
            ),
            VaultConnection(
                vault_id="vault_ai",
                vault_name="AI Generated",
                vault_type=VaultType.AI_GENERATED,
                endpoint="/api/vault/ai",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=78,
                size_mb=8.9
            ),
            VaultConnection(
                vault_id="vault_learning",
                vault_name="Learning Vault",
                vault_type=VaultType.LEARNING,
                endpoint="/api/vault/learning",
                status="connected",
                last_sync=datetime.now().isoformat(),
                item_count=45,
                size_mb=2.1
            ),
        ]
        
        # Initialize folders
        self.folders = [
            VaultFolder(id="folder_recent", name="Recent", color="#3B82F6", icon="time", item_count=24, vault_types=[VaultType.CODE, VaultType.ASSET], created_at=datetime.now().isoformat()),
            VaultFolder(id="folder_starred", name="Starred", color="#F59E0B", icon="star", item_count=12, vault_types=[VaultType.CODE, VaultType.TEMPLATE, VaultType.SNIPPET], created_at=datetime.now().isoformat()),
            VaultFolder(id="folder_games", name="Game Dev", color="#8B5CF6", icon="game-controller", item_count=45, vault_types=[VaultType.CODE, VaultType.ASSET, VaultType.AI_GENERATED], created_at=datetime.now().isoformat()),
            VaultFolder(id="folder_web", name="Web Projects", color="#10B981", icon="globe", item_count=33, vault_types=[VaultType.CODE, VaultType.TEMPLATE], created_at=datetime.now().isoformat()),
            VaultFolder(id="folder_ai", name="AI Creations", color="#EC4899", icon="sparkles", item_count=78, vault_types=[VaultType.AI_GENERATED], created_at=datetime.now().isoformat()),
            VaultFolder(id="folder_archive", name="Archive", color="#6B7280", icon="archive", item_count=156, vault_types=list(VaultType), created_at=datetime.now().isoformat()),
        ]
        
        # Initialize sorting rules
        self.rules = [
            SortingRule(id="rule_1", name="Auto-star AI generated", conditions=[{"field": "vault_type", "operator": "equals", "value": "ai_generated"}], action="star", target="", enabled=True),
            SortingRule(id="rule_2", name="Archive old items", conditions=[{"field": "modified_at", "operator": "older_than", "value": "30d"}], action="archive", target="", enabled=True),
            SortingRule(id="rule_3", name="Tag game assets", conditions=[{"field": "tags", "operator": "contains", "value": "game"}], action="move_to_folder", target="folder_games", enabled=True),
        ]
        
        # Initialize sample items
        self.items = [
            VaultItem(id="item_1", name="player_controller.py", vault_type=VaultType.CODE, category="Scripts", tags=["game", "player", "python"], size_bytes=4520, created_at=datetime.now().isoformat(), modified_at=datetime.now().isoformat(), starred=True),
            VaultItem(id="item_2", name="hero_sprite.png", vault_type=VaultType.ASSET, category="Sprites", tags=["game", "character", "2d"], size_bytes=125000, created_at=datetime.now().isoformat(), modified_at=datetime.now().isoformat()),
            VaultItem(id="item_3", name="react_component.tsx", vault_type=VaultType.TEMPLATE, category="React", tags=["web", "react", "typescript"], size_bytes=2340, created_at=datetime.now().isoformat(), modified_at=datetime.now().isoformat()),
            VaultItem(id="item_4", name="api_handler.py", vault_type=VaultType.SNIPPET, category="API", tags=["backend", "fastapi", "async"], size_bytes=890, created_at=datetime.now().isoformat(), modified_at=datetime.now().isoformat()),
            VaultItem(id="item_5", name="npc_dialogue.json", vault_type=VaultType.AI_GENERATED, category="Game Data", tags=["game", "npc", "ai"], size_bytes=15600, created_at=datetime.now().isoformat(), modified_at=datetime.now().isoformat(), starred=True),
        ]

vault_state = SortingVaultState()

# =============================================================================
# API ROUTES - VAULT CONNECTIONS
# =============================================================================

@router.get("/connections")
async def get_vault_connections():
    """Get all connected vault systems"""
    total_items = sum(c.item_count for c in vault_state.connections)
    total_size = sum(c.size_mb for c in vault_state.connections)
    
    return {
        "connections": [c.dict() for c in vault_state.connections],
        "total_vaults": len(vault_state.connections),
        "total_items": total_items,
        "total_size_mb": round(total_size, 2),
        "all_synced": all(c.status == "connected" for c in vault_state.connections)
    }

@router.post("/connections/{vault_id}/sync")
async def sync_vault(vault_id: str):
    """Sync a specific vault"""
    connection = next((c for c in vault_state.connections if c.vault_id == vault_id), None)
    if not connection:
        raise HTTPException(status_code=404, detail=f"Vault '{vault_id}' not found")
    
    connection.last_sync = datetime.now().isoformat()
    connection.status = "connected"
    
    return {
        "success": True,
        "vault": connection.dict(),
        "message": f"Synced {connection.vault_name} successfully"
    }

@router.post("/connections/sync-all")
async def sync_all_vaults():
    """Sync all connected vaults"""
    synced = []
    for connection in vault_state.connections:
        connection.last_sync = datetime.now().isoformat()
        connection.status = "connected"
        synced.append(connection.vault_name)
    
    return {
        "success": True,
        "synced_vaults": synced,
        "total_synced": len(synced),
        "timestamp": datetime.now().isoformat()
    }

# =============================================================================
# API ROUTES - FOLDERS
# =============================================================================

@router.get("/folders")
async def get_folders():
    """Get all sorting folders"""
    return {
        "folders": [f.dict() for f in vault_state.folders],
        "total_folders": len(vault_state.folders)
    }

@router.post("/folders")
async def create_folder(name: str, color: str = "#3B82F6", icon: str = "folder"):
    """Create a new sorting folder"""
    folder_id = f"folder_{hashlib.md5(name.encode()).hexdigest()[:8]}"
    
    folder = VaultFolder(
        id=folder_id,
        name=name,
        color=color,
        icon=icon,
        item_count=0,
        vault_types=[],
        created_at=datetime.now().isoformat()
    )
    
    vault_state.folders.append(folder)
    
    return {
        "success": True,
        "folder": folder.dict(),
        "message": f"Created folder '{name}'"
    }

@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str):
    """Delete a sorting folder"""
    folder = next((f for f in vault_state.folders if f.id == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_id}' not found")
    
    vault_state.folders.remove(folder)
    
    return {
        "success": True,
        "deleted": folder_id,
        "message": f"Deleted folder '{folder.name}'"
    }

# =============================================================================
# API ROUTES - ITEMS
# =============================================================================

@router.get("/items")
async def get_items(
    vault_type: Optional[VaultType] = None,
    folder_id: Optional[str] = None,
    tag: Optional[str] = None,
    starred: Optional[bool] = None,
    archived: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0
):
    """Get items with filtering and sorting"""
    items = vault_state.items.copy()
    
    # Apply filters
    if vault_type:
        items = [i for i in items if i.vault_type == vault_type]
    if tag:
        items = [i for i in items if tag in i.tags]
    if starred is not None:
        items = [i for i in items if i.starred == starred]
    if archived is not None:
        items = [i for i in items if i.archived == archived]
    if search:
        search_lower = search.lower()
        items = [i for i in items if search_lower in i.name.lower() or any(search_lower in t.lower() for t in i.tags)]
    
    # Sort
    reverse = sort_order == "desc"
    items.sort(key=lambda x: getattr(x, sort_by, ""), reverse=reverse)
    
    # Paginate
    total = len(items)
    items = items[offset:offset + limit]
    
    return {
        "items": [i.dict() for i in items],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total
    }

@router.get("/items/{item_id}")
async def get_item(item_id: str):
    """Get a specific item"""
    item = next((i for i in vault_state.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    
    return {"item": item.dict()}

@router.post("/items/{item_id}/star")
async def toggle_star(item_id: str):
    """Toggle star status for an item"""
    item = next((i for i in vault_state.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    
    item.starred = not item.starred
    
    return {
        "success": True,
        "item_id": item_id,
        "starred": item.starred
    }

@router.post("/items/{item_id}/archive")
async def toggle_archive(item_id: str):
    """Toggle archive status for an item"""
    item = next((i for i in vault_state.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    
    item.archived = not item.archived
    
    return {
        "success": True,
        "item_id": item_id,
        "archived": item.archived
    }

@router.post("/items/{item_id}/move")
async def move_item(item_id: str, folder_id: str):
    """Move an item to a folder"""
    item = next((i for i in vault_state.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    
    folder = next((f for f in vault_state.folders if f.id == folder_id), None)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_id}' not found")
    
    # Update folder count
    folder.item_count += 1
    if item.vault_type not in folder.vault_types:
        folder.vault_types.append(item.vault_type)
    
    return {
        "success": True,
        "item_id": item_id,
        "folder_id": folder_id,
        "message": f"Moved '{item.name}' to '{folder.name}'"
    }

@router.post("/items/{item_id}/tag")
async def add_tag(item_id: str, tag: str):
    """Add a tag to an item"""
    item = next((i for i in vault_state.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    
    if tag not in item.tags:
        item.tags.append(tag)
    
    return {
        "success": True,
        "item_id": item_id,
        "tags": item.tags
    }

# =============================================================================
# API ROUTES - SORTING RULES
# =============================================================================

@router.get("/rules")
async def get_sorting_rules():
    """Get all sorting rules"""
    return {
        "rules": [r.dict() for r in vault_state.rules],
        "total_rules": len(vault_state.rules),
        "active_rules": len([r for r in vault_state.rules if r.enabled])
    }

@router.post("/rules")
async def create_sorting_rule(
    name: str,
    conditions: List[Dict[str, Any]],
    action: str,
    target: str = ""
):
    """Create a new sorting rule"""
    rule_id = f"rule_{hashlib.md5(name.encode()).hexdigest()[:8]}"
    
    rule = SortingRule(
        id=rule_id,
        name=name,
        conditions=conditions,
        action=action,
        target=target,
        enabled=True
    )
    
    vault_state.rules.append(rule)
    
    return {
        "success": True,
        "rule": rule.dict(),
        "message": f"Created rule '{name}'"
    }

@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str):
    """Enable/disable a sorting rule"""
    rule = next((r for r in vault_state.rules if r.id == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    
    rule.enabled = not rule.enabled
    
    return {
        "success": True,
        "rule_id": rule_id,
        "enabled": rule.enabled
    }

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a sorting rule"""
    rule = next((r for r in vault_state.rules if r.id == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    
    vault_state.rules.remove(rule)
    
    return {
        "success": True,
        "deleted": rule_id,
        "message": f"Deleted rule '{rule.name}'"
    }

@router.post("/rules/apply-all")
async def apply_all_rules():
    """Apply all enabled sorting rules to items"""
    applied = 0
    affected_items = []
    
    for rule in vault_state.rules:
        if not rule.enabled:
            continue
        
        for item in vault_state.items:
            # Simple condition matching
            match = True
            for condition in rule.conditions:
                field = condition.get("field")
                operator = condition.get("operator")
                value = condition.get("value")
                
                item_value = getattr(item, field, None)
                
                if operator == "equals" and item_value != value:
                    match = False
                elif operator == "contains" and isinstance(item_value, list) and value not in item_value:
                    match = False
            
            if match:
                # Apply action
                if rule.action == "star":
                    item.starred = True
                elif rule.action == "archive":
                    item.archived = True
                elif rule.action == "tag":
                    if rule.target and rule.target not in item.tags:
                        item.tags.append(rule.target)
                
                applied += 1
                affected_items.append(item.id)
    
    return {
        "success": True,
        "rules_applied": len([r for r in vault_state.rules if r.enabled]),
        "items_affected": applied,
        "affected_item_ids": affected_items
    }

# =============================================================================
# API ROUTES - ANALYTICS
# =============================================================================

@router.get("/analytics")
async def get_vault_analytics():
    """Get analytics for the sorting vault"""
    items = vault_state.items
    connections = vault_state.connections
    
    # Calculate stats
    type_counts = {}
    for item in items:
        type_counts[item.vault_type.value] = type_counts.get(item.vault_type.value, 0) + 1
    
    tag_counts = {}
    for item in items:
        for tag in item.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "overview": {
            "total_items": len(items),
            "total_vaults": len(connections),
            "starred_items": len([i for i in items if i.starred]),
            "archived_items": len([i for i in items if i.archived]),
            "total_size_mb": sum(c.size_mb for c in connections)
        },
        "by_vault_type": type_counts,
        "top_tags": [{"tag": t[0], "count": t[1]} for t in top_tags],
        "folder_stats": [
            {"id": f.id, "name": f.name, "count": f.item_count}
            for f in vault_state.folders
        ],
        "connection_health": {
            "connected": len([c for c in connections if c.status == "connected"]),
            "disconnected": len([c for c in connections if c.status == "disconnected"]),
            "syncing": len([c for c in connections if c.status == "syncing"])
        }
    }

@router.get("/search")
async def global_search(q: str, limit: int = 20):
    """Search across all vaults"""
    q_lower = q.lower()
    results = []
    
    for item in vault_state.items:
        score = 0
        if q_lower in item.name.lower():
            score += 10
        if any(q_lower in tag.lower() for tag in item.tags):
            score += 5
        if q_lower in item.category.lower():
            score += 3
        
        if score > 0:
            results.append({"item": item.dict(), "score": score})
    
    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]
    
    return {
        "query": q,
        "results": results,
        "total_found": len(results)
    }
