"""
Skeleton Developer CLI - Main Entry Point

Usage:
    python -m skeleton developer <command> [options]
    python -m skeleton dev <command> [options]

Commands:
    scaffold    Create new project from template
    wizard      Interactive project builder
    health      Check system health
    visualize   Render blueprint diagrams
    extension   Manage extensions
"""

import sys
import argparse
from skeleton.developer.commands import CommandRegistry


def main():
    parser = argparse.ArgumentParser(
        prog="skeleton-dev",
        description="Skeleton Developer CLI - Build, scaffold, and manage projects"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scaffold command
    scaffold_parser = subparsers.add_parser("scaffold", help="Create project from template")
    scaffold_parser.add_argument("template", nargs="?", help="Template name")
    scaffold_parser.add_argument("--output", "-o", default=".", help="Output directory")
    scaffold_parser.add_argument("--name", "-n", help="Project name")
    scaffold_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing")

    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Interactive project builder")
    wizard_parser.add_argument("--mode", choices=["full", "quick", "expert"], default="full",
                               help="Wizard mode")

    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Visualize command
    viz_parser = subparsers.add_parser("visualize", help="Render blueprint diagrams")
    viz_parser.add_argument("target", nargs="?", help="Target blueprint or module")
    viz_parser.add_argument("--format", choices=["text", "json", "dot"], default="text",
                           help="Output format")

    # Extension command
    ext_parser = subparsers.add_parser("extension", help="Manage extensions")
    ext_parser.add_argument("action", choices=["list", "install", "remove", "update"],
                           help="Extension action")
    ext_parser.add_argument("name", nargs="?", help="Extension name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    registry = CommandRegistry()
    result = registry.execute(args.command, args)
    
    if result:
        print(result)


if __name__ == "__main__":
    main()
