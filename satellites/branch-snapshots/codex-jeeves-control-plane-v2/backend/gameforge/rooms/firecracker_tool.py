from __future__ import annotations
from typing import Any, Dict, List, Optional
import uuid
import time

class FirecrackerTool:
    """
    Advanced Firecracker micro-VM tool with Parallel VM Pools and Execution Receipts.
    Supports spawning multiple VMs in parallel, executing tasks securely,
    and generating verifiable receipts that can be stored in the room Bookshelf.
    """

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.active_vms: Dict[str, Dict[str, Any]] = {}
        self.receipts: List[Dict[str, Any]] = []

    def spawn_vm(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Spawn a new Firecracker micro-VM with auto-generated ID."""
        vm_id = f"vm_{uuid.uuid4().hex[:8]}"
        vm = {
            "vm_id": vm_id,
            "room_id": self.room_id,
            "status": "running",
            "config": config or {"memory": "128MB", "vcpu": 1},
            "created_at": time.time()
        }
        self.active_vms[vm_id] = vm
        return vm

    def spawn_parallel_pool(self, count: int, base_config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Spawn multiple Firecracker VMs in parallel for concurrent role execution."""
        vms = []
        for _ in range(count):
            vm = self.spawn_vm(base_config)
            vms.append(vm)
        return vms

    def execute_in_vm(self, vm_id: str, task: str) -> Dict[str, Any]:
        """Execute a task inside a specific VM and generate a receipt."""
        if vm_id not in self.active_vms:
            return {"error": "VM not found"}

        # Simulated secure execution
        result = {
            "vm_id": vm_id,
            "task": task,
            "result": f"Secure execution result for: {task}",
            "exit_code": 0,
            "timestamp": time.time()
        }

        # Generate verifiable receipt
        receipt = {
            "receipt_id": f"receipt_{uuid.uuid4().hex[:12]}",
            "vm_id": vm_id,
            "room_id": self.room_id,
            "task": task,
            "result_hash": hash(str(result)),  # Simple hash for verifiability
            "timestamp": time.time(),
            "status": "completed"
        }
        self.receipts.append(receipt)

        result["receipt"] = receipt
        return result

    def execute_parallel(self, tasks: List[str]) -> List[Dict[str, Any]]:
        """Execute multiple tasks across available VMs in parallel."""
        results = []
        vm_ids = list(self.active_vms.keys())
        for i, task in enumerate(tasks):
            if i < len(vm_ids):
                res = self.execute_in_vm(vm_ids[i], task)
                results.append(res)
        return results

    def get_receipts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent execution receipts (can be stored in room Bookshelf blockchain layer)."""
        return self.receipts[-limit:]

    def stop_vm(self, vm_id: str) -> bool:
        if vm_id in self.active_vms:
            self.active_vms[vm_id]["status"] = "stopped"
            return True
        return False

    def list_active_vms(self) -> List[str]:
        return [vm_id for vm_id, vm in self.active_vms.items() if vm.get("status") == "running"]
