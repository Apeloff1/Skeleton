#!/usr/bin/env python3
"""
Enhanced Nexus Security Layer
More comprehensive security for the Knowledge Nexus.
"""

from security.nexus_security_layer import nexus_security
from typing import Dict, Any
import time
import hashlib

class EnhancedNexusSecurity:
    def __init__(self):
        self.base_security = nexus_security
        self.rate_limits = {}
        self.anomaly_log = []

    def check_rate_limit(self, agent_id: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        now = time.time()
        if agent_id not in self.rate_limits:
            self.rate_limits[agent_id] = []
        
        # Clean old requests
        self.rate_limits[agent_id] = [t for t in self.rate_limits[agent_id] if now - t < window_seconds]
        
        if len(self.rate_limits[agent_id]) >= max_requests:
            self.anomaly_log.append({
                "type": "rate_limit_exceeded",
                "agent_id": agent_id,
                "timestamp": now
            })
            return False
        
        self.rate_limits[agent_id].append(now)
        return True

    def detect_anomaly(self, action: str, details: Dict) -> bool:
        """Simple anomaly detection."""
        if "delete" in action.lower() and details.get("without_approval"):
            self.anomaly_log.append({
                "type": "suspicious_deletion",
                "details": details,
                "timestamp": time.time()
            })
            return True
        return False

    def generate_audit_hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()

    def log_access(self, agent_id: str, action: str, resource: str):
        self.base_security.access_log.append({
            "agent_id": agent_id,
            "action": action,
            "resource": resource,
            "timestamp": time.time()
        })

# Global enhanced security
enhanced_nexus_security = EnhancedNexusSecurity()