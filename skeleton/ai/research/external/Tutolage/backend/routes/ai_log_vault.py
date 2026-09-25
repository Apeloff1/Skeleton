"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AI LOG VAULT & LOGSCRAPER SYSTEM                                            ║
║  Comprehensive AI Query Logging, Training Data Collection & Jeeves Training  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/ai-logs", tags=["AI Log Vault"])

# MongoDB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.codedock_logs

# Collections
ai_queries_collection = db.ai_queries
user_actions_collection = db.user_actions
training_data_collection = db.training_data
jeeves_memory_collection = db.jeeves_memory
logscraper_runs_collection = db.logscraper_runs

# ============================================================================
# DATA MODELS
# ============================================================================

class AIQueryLog(BaseModel):
    query_type: str  # chat, code_gen, debug, explain, etc.
    user_input: str
    ai_response: str
    model_used: str = "gpt-4o"
    context: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    success: bool = True
    response_time_ms: Optional[int] = None
    user_feedback: Optional[str] = None  # helpful, not_helpful, incorrect
    session_id: Optional[str] = None

class UserActionLog(BaseModel):
    action_type: str  # code_written, file_saved, challenge_completed, lesson_viewed, etc.
    action_data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None

class LogscraperConfig(BaseModel):
    include_ai_queries: bool = True
    include_user_actions: bool = True
    include_vault_data: bool = True
    include_curriculum_progress: bool = True
    time_range_hours: int = 24
    max_records: int = 10000

class JeevesTrainingData(BaseModel):
    patterns: List[Dict[str, Any]]
    user_preferences: Dict[str, Any]
    common_questions: List[str]
    effective_explanations: List[Dict[str, Any]]
    skill_assessments: Dict[str, Any]

# ============================================================================
# LOGGING ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_log_vault_info():
    """Get AI Log Vault system information"""
    # Get collection stats
    ai_count = await ai_queries_collection.count_documents({})
    actions_count = await user_actions_collection.count_documents({})
    training_count = await training_data_collection.count_documents({})
    memory_count = await jeeves_memory_collection.count_documents({})
    
    return {
        "name": "CodeDock AI Log Vault",
        "version": "11.2.0",
        "description": "Comprehensive AI query logging and Jeeves training system",
        "statistics": {
            "ai_queries_logged": ai_count,
            "user_actions_logged": actions_count,
            "training_records": training_count,
            "jeeves_memories": memory_count
        },
        "features": [
            "Real-time AI query logging",
            "User action tracking",
            "Automated logscraper",
            "Jeeves continuous learning",
            "Pattern recognition",
            "Personalized assistance"
        ],
        "collections": [
            "ai_queries",
            "user_actions",
            "training_data",
            "jeeves_memory",
            "logscraper_runs"
        ]
    }

@router.post("/query")
async def log_ai_query(log: AIQueryLog):
    """Log an AI query for training"""
    log_doc = {
        **log.dict(),
        "timestamp": datetime.utcnow(),
        "processed": False
    }
    
    result = await ai_queries_collection.insert_one(log_doc)
    
    return {
        "status": "logged",
        "log_id": str(result.inserted_id),
        "timestamp": log_doc["timestamp"].isoformat()
    }

@router.post("/action")
async def log_user_action(log: UserActionLog):
    """Log a user action for learning"""
    log_doc = {
        **log.dict(),
        "timestamp": datetime.utcnow(),
        "processed": False
    }
    
    result = await user_actions_collection.insert_one(log_doc)
    
    return {
        "status": "logged",
        "log_id": str(result.inserted_id),
        "timestamp": log_doc["timestamp"].isoformat()
    }

@router.post("/feedback/{log_id}")
async def add_query_feedback(log_id: str, feedback: str, comment: Optional[str] = None):
    """Add feedback to an AI query for training improvement"""
    from bson import ObjectId
    
    await ai_queries_collection.update_one(
        {"_id": ObjectId(log_id)},
        {
            "$set": {
                "user_feedback": feedback,
                "feedback_comment": comment,
                "feedback_timestamp": datetime.utcnow()
            }
        }
    )
    
    return {
        "status": "feedback_added",
        "log_id": log_id,
        "feedback": feedback
    }

# ============================================================================
# LOGSCRAPER SYSTEM
# ============================================================================

@router.post("/scrape")
async def run_logscraper(config: LogscraperConfig, background_tasks: BackgroundTasks):
    """Run the logscraper to collect training data"""
    
    run_id = f"scrape_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    # Start scraping in background
    background_tasks.add_task(execute_logscraper, run_id, config)
    
    return {
        "status": "scraping_started",
        "run_id": run_id,
        "config": config.dict(),
        "message": "Logscraper running in background. Check /scrape/status/{run_id} for progress."
    }

async def execute_logscraper(run_id: str, config: LogscraperConfig):
    """Execute the logscraper process"""
    
    start_time = datetime.utcnow()
    cutoff_time = start_time - timedelta(hours=config.time_range_hours)
    
    scraped_data = {
        "ai_queries": [],
        "user_actions": [],
        "patterns": [],
        "insights": []
    }
    
    # Scrape AI queries
    if config.include_ai_queries:
        cursor = ai_queries_collection.find(
            {"timestamp": {"$gte": cutoff_time}}
        ).limit(config.max_records)
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc["timestamp"] = doc["timestamp"].isoformat()
            scraped_data["ai_queries"].append(doc)
    
    # Scrape user actions
    if config.include_user_actions:
        cursor = user_actions_collection.find(
            {"timestamp": {"$gte": cutoff_time}}
        ).limit(config.max_records)
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc["timestamp"] = doc["timestamp"].isoformat()
            scraped_data["user_actions"].append(doc)
    
    # Analyze patterns
    scraped_data["patterns"] = analyze_patterns(scraped_data)
    scraped_data["insights"] = generate_insights(scraped_data)
    
    # Save run results
    run_doc = {
        "run_id": run_id,
        "started_at": start_time,
        "completed_at": datetime.utcnow(),
        "config": config.dict(),
        "statistics": {
            "ai_queries_scraped": len(scraped_data["ai_queries"]),
            "user_actions_scraped": len(scraped_data["user_actions"]),
            "patterns_found": len(scraped_data["patterns"]),
            "insights_generated": len(scraped_data["insights"])
        },
        "status": "completed"
    }
    
    await logscraper_runs_collection.insert_one(run_doc)
    
    # Store training data
    if scraped_data["patterns"] or scraped_data["insights"]:
        training_doc = {
            "run_id": run_id,
            "timestamp": datetime.utcnow(),
            "data": scraped_data,
            "ready_for_training": True
        }
        await training_data_collection.insert_one(training_doc)

def analyze_patterns(data: Dict) -> List[Dict]:
    """Analyze scraped data for patterns"""
    patterns = []
    
    # Analyze query types
    query_types = {}
    for q in data.get("ai_queries", []):
        qt = q.get("query_type", "unknown")
        query_types[qt] = query_types.get(qt, 0) + 1
    
    if query_types:
        patterns.append({
            "type": "query_distribution",
            "data": query_types
        })
    
    # Analyze languages used
    languages = {}
    for q in data.get("ai_queries", []):
        lang = q.get("language", "unknown")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
    
    if languages:
        patterns.append({
            "type": "language_preference",
            "data": languages
        })
    
    # Analyze feedback patterns
    feedback_stats = {"helpful": 0, "not_helpful": 0, "no_feedback": 0}
    for q in data.get("ai_queries", []):
        fb = q.get("user_feedback")
        if fb == "helpful":
            feedback_stats["helpful"] += 1
        elif fb == "not_helpful":
            feedback_stats["not_helpful"] += 1
        else:
            feedback_stats["no_feedback"] += 1
    
    patterns.append({
        "type": "feedback_distribution",
        "data": feedback_stats
    })
    
    return patterns

def generate_insights(data: Dict) -> List[Dict]:
    """Generate insights from scraped data"""
    insights = []
    
    total_queries = len(data.get("ai_queries", []))
    if total_queries > 0:
        insights.append({
            "type": "activity_level",
            "message": f"User made {total_queries} AI queries in the time period",
            "value": total_queries
        })
    
    # Find most common question types
    for pattern in data.get("patterns", []):
        if pattern["type"] == "query_distribution":
            most_common = max(pattern["data"].items(), key=lambda x: x[1], default=("none", 0))
            insights.append({
                "type": "common_query_type",
                "message": f"Most common query type: {most_common[0]}",
                "value": most_common
            })
    
    return insights

@router.get("/scrape/status/{run_id}")
async def get_scrape_status(run_id: str):
    """Get logscraper run status"""
    run = await logscraper_runs_collection.find_one({"run_id": run_id})
    
    if not run:
        return {"status": "running", "run_id": run_id}
    
    run["_id"] = str(run["_id"])
    return run

@router.get("/scrape/latest")
async def get_latest_scrape():
    """Get the latest logscraper run"""
    run = await logscraper_runs_collection.find_one(
        sort=[("completed_at", -1)]
    )
    
    if not run:
        return {"message": "No scraper runs found"}
    
    run["_id"] = str(run["_id"])
    return run

# ============================================================================
# JEEVES TRAINING SYSTEM
# ============================================================================

@router.post("/jeeves/train")
async def train_jeeves(background_tasks: BackgroundTasks):
    """Train Jeeves from collected data"""
    
    training_id = f"train_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    # Get latest training data
    training_data = await training_data_collection.find_one(
        {"ready_for_training": True},
        sort=[("timestamp", -1)]
    )
    
    if not training_data:
        return {
            "status": "no_data",
            "message": "No training data available. Run logscraper first."
        }
    
    # Process training
    jeeves_knowledge = await process_jeeves_training(training_data)
    
    # Store in Jeeves memory
    memory_doc = {
        "training_id": training_id,
        "timestamp": datetime.utcnow(),
        "knowledge": jeeves_knowledge,
        "source_run_id": training_data.get("run_id")
    }
    
    await jeeves_memory_collection.insert_one(memory_doc)
    
    # Mark training data as processed
    await training_data_collection.update_one(
        {"_id": training_data["_id"]},
        {"$set": {"ready_for_training": False, "processed_at": datetime.utcnow()}}
    )
    
    return {
        "status": "training_complete",
        "training_id": training_id,
        "knowledge_items": len(jeeves_knowledge.get("patterns", [])),
        "insights": len(jeeves_knowledge.get("insights", []))
    }

async def process_jeeves_training(training_data: Dict) -> Dict:
    """Process training data for Jeeves"""
    
    knowledge = {
        "patterns": [],
        "user_preferences": {},
        "effective_responses": [],
        "common_issues": [],
        "teaching_strategies": []
    }
    
    data = training_data.get("data", {})
    
    # Extract patterns
    knowledge["patterns"] = data.get("patterns", [])
    knowledge["insights"] = data.get("insights", [])
    
    # Find effective responses (those with positive feedback)
    for query in data.get("ai_queries", []):
        if query.get("user_feedback") == "helpful":
            knowledge["effective_responses"].append({
                "query_type": query.get("query_type"),
                "user_input": query.get("user_input", "")[:200],  # Truncate
                "response_snippet": query.get("ai_response", "")[:500],
                "context": query.get("context")
            })
    
    # Identify common issues (queries that needed multiple attempts)
    # This would require more sophisticated tracking in production
    
    return knowledge

@router.get("/jeeves/memory")
async def get_jeeves_memory():
    """Get Jeeves' current learned knowledge"""
    
    # Get latest memory
    memory = await jeeves_memory_collection.find_one(
        sort=[("timestamp", -1)]
    )
    
    if not memory:
        return {
            "status": "no_memory",
            "message": "Jeeves hasn't been trained yet"
        }
    
    memory["_id"] = str(memory["_id"])
    return memory

@router.post("/jeeves/remember")
async def add_jeeves_memory(memory_type: str, content: Dict[str, Any]):
    """Add a specific memory to Jeeves"""
    
    memory_doc = {
        "type": memory_type,
        "content": content,
        "timestamp": datetime.utcnow(),
        "source": "direct_input"
    }
    
    result = await jeeves_memory_collection.insert_one(memory_doc)
    
    return {
        "status": "memory_added",
        "memory_id": str(result.inserted_id),
        "type": memory_type
    }

# ============================================================================
# APP LAUNCH TRAINING TRIGGER
# ============================================================================

@router.post("/startup-train")
async def startup_training(background_tasks: BackgroundTasks):
    """Trigger training on app startup - scrapes all vaults and trains Jeeves"""
    
    startup_id = f"startup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    # Run comprehensive scraping
    config = LogscraperConfig(
        include_ai_queries=True,
        include_user_actions=True,
        include_vault_data=True,
        include_curriculum_progress=True,
        time_range_hours=168,  # Last week
        max_records=50000
    )
    
    background_tasks.add_task(execute_startup_training, startup_id, config)
    
    return {
        "status": "startup_training_initiated",
        "startup_id": startup_id,
        "message": "Comprehensive vault scraping and Jeeves training started"
    }

async def execute_startup_training(startup_id: str, config: LogscraperConfig):
    """Execute comprehensive startup training"""
    
    # Run logscraper
    await execute_logscraper(f"{startup_id}_scrape", config)
    
    # Get the training data
    training_data = await training_data_collection.find_one(
        {"ready_for_training": True},
        sort=[("timestamp", -1)]
    )
    
    if training_data:
        # Process and store Jeeves knowledge
        knowledge = await process_jeeves_training(training_data)
        
        memory_doc = {
            "training_id": startup_id,
            "timestamp": datetime.utcnow(),
            "knowledge": knowledge,
            "type": "startup_training",
            "comprehensive": True
        }
        
        await jeeves_memory_collection.insert_one(memory_doc)
        
        # Mark as processed
        await training_data_collection.update_one(
            {"_id": training_data["_id"]},
            {"$set": {"ready_for_training": False, "processed_at": datetime.utcnow()}}
        )

# ============================================================================
# STATISTICS & ANALYTICS
# ============================================================================

@router.get("/stats")
async def get_log_statistics():
    """Get comprehensive log statistics"""
    
    # Time ranges
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    stats = {
        "ai_queries": {
            "total": await ai_queries_collection.count_documents({}),
            "last_24h": await ai_queries_collection.count_documents({"timestamp": {"$gte": day_ago}}),
            "last_7d": await ai_queries_collection.count_documents({"timestamp": {"$gte": week_ago}}),
            "last_30d": await ai_queries_collection.count_documents({"timestamp": {"$gte": month_ago}})
        },
        "user_actions": {
            "total": await user_actions_collection.count_documents({}),
            "last_24h": await user_actions_collection.count_documents({"timestamp": {"$gte": day_ago}}),
            "last_7d": await user_actions_collection.count_documents({"timestamp": {"$gte": week_ago}}),
            "last_30d": await user_actions_collection.count_documents({"timestamp": {"$gte": month_ago}})
        },
        "training_runs": await logscraper_runs_collection.count_documents({}),
        "jeeves_memories": await jeeves_memory_collection.count_documents({})
    }
    
    return stats

@router.get("/export")
async def export_training_data(format: str = "json", limit: int = 1000):
    """Export training data for external use"""
    
    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "ai_queries": [],
        "patterns": []
    }
    
    # Get AI queries
    cursor = ai_queries_collection.find().limit(limit)
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "timestamp" in doc:
            doc["timestamp"] = doc["timestamp"].isoformat()
        data["ai_queries"].append(doc)
    
    # Get latest patterns
    training = await training_data_collection.find_one(sort=[("timestamp", -1)])
    if training:
        data["patterns"] = training.get("data", {}).get("patterns", [])
    
    return data
