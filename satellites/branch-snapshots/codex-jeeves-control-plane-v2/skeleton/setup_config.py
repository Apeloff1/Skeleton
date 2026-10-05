"""
Skeleton — Setup and installation configuration

This file provides package metadata and installation helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Package metadata
PACKAGE_NAME = "skeleton"
VERSION = "16.0.0"
CODENAME = "Skeleton"
AUTHOR = "Tutolage"
DESCRIPTION = "AI game engine and agent orchestration framework"
LICENSE = "MIT"
PYTHON_REQUIRES = ">=3.11"

# Core dependencies (minimal)
CORE_DEPENDENCIES: List[str] = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
]

# Optional dependencies by feature
OPTIONAL_DEPENDENCIES: Dict[str, List[str]] = {
    "dev": [
        "pytest>=7.0.0",
        "pytest-asyncio>=0.21.0",
        "black>=23.0.0",
        "mypy>=1.0.0",
    ],
    "docs": [
        "mkdocs>=1.5.0",
        "mkdocs-material>=9.0.0",
    ],
    "ml": [
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
    ],
    "all": [],  # Populated below
}

# Populate 'all' with all optional deps
OPTIONAL_DEPENDENCIES["all"] = sorted(set(
    dep for deps in OPTIONAL_DEPENDENCIES.values() for dep in deps
))

# Entry points for CLI
ENTRY_POINTS: Dict[str, str] = {
    "skeleton": "skeleton.__main__:main",
    "skeleton-dev": "skeleton.developer.cli:main",
}

# Package classifiers
CLASSIFIERS: List[str] = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Topic :: Games/Entertainment",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]


def get_setup_config() -> Dict[str, Any]:
    """Return setup.py-compatible configuration dict."""
    return {
        "name": PACKAGE_NAME,
        "version": VERSION,
        "description": DESCRIPTION,
        "author": AUTHOR,
        "license": LICENSE,
        "python_requires": PYTHON_REQUIRES,
        "install_requires": CORE_DEPENDENCIES,
        "extras_require": OPTIONAL_DEPENDENCIES,
        "entry_points": {"console_scripts": [f"{k}={v}" for k, v in ENTRY_POINTS.items()]},
        "classifiers": CLASSIFIERS,
        "packages": [
            "skeleton",
            "skeleton.acquired",
            "skeleton.agents",
            "skeleton.api",
            "skeleton.config",
            "skeleton.context",
            "skeleton.cortex",
            "skeleton.deploy",
            "skeleton.developer",
            "skeleton.forge",
            "skeleton.galaxy",
            "skeleton.integrations",
            "skeleton.intelligence",
            "skeleton.jeeves",
            "skeleton.kernel",
            "skeleton.memory",
            "skeleton.observability",
            "skeleton.organism",
            "skeleton.pipelines",
            "skeleton.resilience",
            "skeleton.retrieval",
            "skeleton.social",
            "skeleton.swarm",
            "skeleton.testing",
            "skeleton.vault",
        ],
    }
