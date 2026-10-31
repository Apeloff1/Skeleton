"""
Enterprise Dashboard Aggregator. Single call for health, SLA, queue, cluster, and G state.
"""
from typing import Dict
from .enterprise_gateway import get_gateway
from .enterprise_sla import EnterpriseSLA
from .enterprise_queue import EnterpriseQueue
from .enterprise_cluster import EnterpriseCluster
from .health_monitor import HealthMonitor

class EnterpriseDashboard:
    def __init__(self):
        self.gw = get_gateway()
        self.sla = EnterpriseSLA()
        self.queue = EnterpriseQueue()
        self.cluster = EnterpriseCluster()
        self.health = HealthMonitor()

    def render(self) -> Dict:
        return {
            "health": self.health.check(),
            "sla": self.sla.report(),
            "queue_size": self.queue.size(),
            "cluster": self.cluster.status(),
            "gateway": self.gw.status(),
            "enterprise": True
        }
