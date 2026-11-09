"""
Enterprise Cluster Coordinator. Local multi-node style coordination via helix gossip.
No remote coin. Fail-closed.
"""
from typing import Dict, List
from .hive_chronicle import gossip
from .helix_persist import HelixPersist

class EnterpriseCluster:
    def __init__(self):
        self.nodes: List[str] = ["local-0"]
        self.helix = HelixPersist("chronicle/cluster.jsonl")

    def join(self, node: str) -> Dict:
        if node not in self.nodes:
            self.nodes.append(node)
            gossip(node)
            self.helix.append([{"node": node, "event": "join"}])
        return {"nodes": self.nodes, "joined": node}

    def status(self) -> Dict:
        return {"cluster_size": len(self.nodes), "nodes": self.nodes, "enterprise": True}
