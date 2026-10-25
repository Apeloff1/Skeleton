"""
Operational CLI. python -m skeleton.local_ai.cli_ops
Exposes full stack status, generate, and health.
"""
import argparse
from .full_stack import get_stack

def main():
    parser = argparse.ArgumentParser(description="Local AI Full Stack CLI")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--generate", type=str)
    parser.add_argument("--cas", type=str, default="valid_cas_string_16chars")
    args = parser.parse_args()
    stack = get_stack()
    if args.status:
        print(stack.health.check())
    elif args.generate:
        print(stack.run(args.generate, args.cas))
    else:
        print("Ready. Use --status or --generate")

if __name__ == "__main__":
    main()
