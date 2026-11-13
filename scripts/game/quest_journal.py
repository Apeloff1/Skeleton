"""Repository-local compatibility entrypoint for the installed quest CLI."""
from skeleton.game.gameplay.quest_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
