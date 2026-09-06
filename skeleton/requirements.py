"""
Skeleton — Project requirements and environment configuration
"""

# Core requirements
core_requirements = """
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
""".strip()

# Development requirements
dev_requirements = """
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
mypy>=1.0.0
""".strip()

# Full requirements (all optional)
all_requirements = """
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
mypy>=1.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
""".strip()
