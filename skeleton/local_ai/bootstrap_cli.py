"""
CLI bootstrap for local AI. python -m skeleton.local_ai.bootstrap_cli
"""
import argparse
from . import get_complete

def main():
    parser = argparse.ArgumentParser(description="Local AI Boilerplate Bootstrap")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    ai = get_complete()
    if args.status:
        print(ai.status())
    else:
        print("Local AI ready. Use --status for report.")

if __name__ == "__main__":
    main()
