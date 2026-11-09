#!/usr/bin/env python3
"""
Boardroom Vault System
Secure storage for game files with put, get, edit, and versioning.
"""

import os
import time
import hashlib
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class VaultEntry:
    file_id: str
    filename: str
    content_hash: str
    version: int
    timestamp: float
    metadata: Dict[str, Any]
    previous_version: Optional[str] = None

class BoardroomVault:
    def __init__(self, base_path: str = "/tmp/boardroom_vault"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        self.index_file = os.path.join(base_path, "vault_index.json")
        self.index: Dict[str, List[VaultEntry]] = self._load_index()

    def _load_index(self) -> Dict[str, List[VaultEntry]]:
        if os.path.exists(self.index_file):
            with open(self.index_file, "r") as f:
                data = json.load(f)
                # Convert back to VaultEntry objects
                return {
                    k: [VaultEntry(**item) for item in v]
                    for k, v in data.items()
                }
        return {}

    def _save_index(self):
        with open(self.index_file, "w") as f:
            serializable = {
                k: [asdict(item) for item in v]
                for k, v in self.index.items()
            }
            json.dump(serializable, f, indent=2)

    def _get_file_path(self, file_id: str, version: int) -> str:
        return os.path.join(self.base_path, f"{file_id}_v{version}")

    def put_file(self, filename: str, content: bytes, metadata: Dict = None) -> VaultEntry:
        """Store a new file or new version in the vault."""
        file_id = hashlib.sha256(filename.encode()).hexdigest()[:16]
        
        if file_id not in self.index:
            self.index[file_id] = []
        
        version = len(self.index[file_id]) + 1
        content_hash = hashlib.sha256(content).hexdigest()
        
        previous = self.index[file_id][-1].file_id if self.index[file_id] else None
        
        entry = VaultEntry(
            file_id=file_id,
            filename=filename,
            content_hash=content_hash,
            version=version,
            timestamp=time.time(),
            metadata=metadata or {},
            previous_version=previous
        )
        
        # Save actual file
        file_path = self._get_file_path(file_id, version)
        with open(file_path, "wb") as f:
            f.write(content)
        
        self.index[file_id].append(entry)
        self._save_index()
        
        print(f"[Vault] Stored {filename} (version {version})")
        return entry

    def get_file(self, file_id: str, version: Optional[int] = None) -> Optional[bytes]:
        """Retrieve file content."""
        if file_id not in self.index:
            return None
        
        if version is None:
            version = len(self.index[file_id])
        
        entries = self.index[file_id]
        if version < 1 or version > len(entries):
            return None
        
        file_path = self._get_file_path(file_id, version)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return f.read()
        return None

    def edit_file(self, file_id: str, new_content: bytes, metadata: Dict = None) -> Optional[VaultEntry]:
        """Create a new version by editing existing file."""
        if file_id not in self.index or not self.index[file_id]:
            return None
        
        latest = self.index[file_id][-1]
        return self.put_file(latest.filename, new_content, metadata)

    def list_files(self) -> List[Dict]:
        """List all files in vault with latest version info."""
        result = []
        for file_id, versions in self.index.items():
            if versions:
                latest = versions[-1]
                result.append({
                    "file_id": file_id,
                    "filename": latest.filename,
                    "latest_version": latest.version,
                    "last_updated": latest.timestamp,
                    "total_versions": len(versions)
                })
        return result

# Global vault instance
boardroom_vault = BoardroomVault()