#!/usr/bin/env python3
"""
Git + GitHub Integration for Snowball / Boardroom Vault
Enables version control of game files, commits from builds, and GitHub pushes.
"""

import os
import subprocess
import time
from typing import Optional, List, Dict
from gameforge.boardroom.persistent_vault import boardroom_vault

class GitGitHubIntegration:
    def __init__(self, repo_path: str = "/tmp/gameforge_repo"):
        self.repo_path = repo_path
        os.makedirs(repo_path, exist_ok=True)
        self._ensure_git_repo()

    def _ensure_git_repo(self):
        # Resilient to the repo dir being wiped (e.g. ephemeral /tmp cleared on
        # a fork/restart) — recreate + re-init on demand so git ops never fail
        # with "not a git repository".
        os.makedirs(self.repo_path, exist_ok=True)
        if not os.path.isdir(os.path.join(self.repo_path, ".git")):
            try:
                subprocess.run(["git", "init", "-b", "main"], cwd=self.repo_path, check=True, capture_output=True)
            except Exception:  # noqa: BLE001 — older git without -b
                subprocess.run(["git", "init"], cwd=self.repo_path, capture_output=True)
                subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"],
                               cwd=self.repo_path, capture_output=True)
            print("[Git] Initialized new repository")
        # Ensure a local commit identity so commits never fail with "who are you"
        subprocess.run(["git", "config", "user.email", "cns@gameforge.local"],
                       cwd=self.repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "GameForge CNS"],
                       cwd=self.repo_path, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"],
                       cwd=self.repo_path, capture_output=True)

    def commit_file_from_vault(self, file_id: str, version: int, commit_message: str) -> bool:
        """Take a file from Boardroom Vault and commit it to Git."""
        self._ensure_git_repo()
        content = boardroom_vault.get_file(file_id, version)
        if not content:
            print(f"[Git] File {file_id} version {version} not found in vault")
            return False

        # Get filename from vault listing
        filename = None
        for entry in boardroom_vault.list_files():
            if entry.get("file_id") == file_id:
                filename = entry.get("filename")
                break

        if not filename:
            filename = f"{file_id}.bin"

        file_path = os.path.join(self.repo_path, filename)
        with open(file_path, "wb") as f:
            f.write(content)

        # Git add + commit
        subprocess.run(["git", "add", filename], cwd=self.repo_path, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"[Git] Committed {filename}: {commit_message}")
            return True
        else:
            print(f"[Git] Commit failed: {result.stderr}")
            return False

    def push_to_github(self, remote_url: str, branch: str = "main") -> bool:
        """Push current repo to GitHub."""
        try:
            # Set remote if not exists
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.repo_path,
                capture_output=True
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "remote", "add", "origin", remote_url],
                    cwd=self.repo_path,
                    check=True
                )

            subprocess.run(["git", "push", "-u", "origin", branch], cwd=self.repo_path, check=True)
            print(f"[GitHub] Pushed to {remote_url}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[GitHub] Push failed: {e}")
            return False

    def get_commit_history(self, limit: int = 10) -> List[str]:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--oneline"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        return result.stdout.strip().split("\n") if result.stdout else []

# Global integration
git_github = GitGitHubIntegration()