#!/usr/bin/env python3
"""
Concrete Database Implementations
Examples of specialized databases from the 14+ styles.
"""

from databases.database_abstraction_layer import BaseDatabase, DBRecord
from typing import Dict, Any, List
import time
import hashlib

class BlockchainProvenanceDB(BaseDatabase):
    def __init__(self):
        super().__init__("Blockchain Provenance DB")
        self.chain: List[Dict] = []

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        block = {
            "id": record_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "previous_hash": self.chain[-1]["hash"] if self.chain else "genesis"
        }
        block["hash"] = hashlib.sha256(str(block).encode()).hexdigest()
        self.chain.append(block)
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=block["timestamp"])

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

    def get_full_chain(self):
        return self.chain

class ComprehensiveLogbookDB(BaseDatabase):
    def __init__(self):
        super().__init__("Comprehensive Logbook DB")

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        log_entry = {
            "id": record_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time()
        }
        self.records[record_id] = DBRecord(**log_entry)

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

    def get_recent_logs(self, limit: int = 50):
        sorted_logs = sorted(self.records.values(), key=lambda x: x.timestamp, reverse=True)
        return sorted_logs[:limit]

class AnalyticsMetricsDB(BaseDatabase):
    def __init__(self):
        super().__init__("Analytics & Metrics DB")
        self.metrics = {}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())
        if isinstance(content, dict) and "metric_name" in content:
            self.metrics[content["metric_name"]] = content.get("value")

    def get_metric(self, metric_name: str):
        return self.metrics.get(metric_name)

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

# Factory extension
def get_specialized_database(db_name: str) -> BaseDatabase:
    if db_name == "blockchain_provenance":
        return BlockchainProvenanceDB()
    elif db_name == "comprehensive_logbook":
        return ComprehensiveLogbookDB()
    elif db_name == "analytics_metrics":
        return AnalyticsMetricsDB()
    else:
        from databases.database_abstraction_layer import create_database
        return create_database(db_name)

# Pre-instantiated common ones
blockchain_db = BlockchainProvenanceDB()
logbook_db = ComprehensiveLogbookDB()
analytics_db = AnalyticsMetricsDB()