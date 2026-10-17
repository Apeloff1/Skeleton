"""App foundation schema + migrations (canonical package: skeleton.persistence).

Tables: users, sessions, projects, builds, jobs, assets (see ``db.MIGRATIONS``).
"""
from skeleton.persistence.app_foundation.db import MIGRATIONS, Database

__all__ = ["MIGRATIONS", "Database"]
