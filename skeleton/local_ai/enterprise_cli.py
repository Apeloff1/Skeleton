"""
Enterprise CLI. python -m skeleton.local_ai.enterprise_cli
"""
import argparse
from .enterprise_gateway import get_gateway
from .enterprise_dashboard import EnterpriseDashboard

def main():
    parser = argparse.ArgumentParser(description="Enterprise Local AI CLI")
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--request", type=str)
    parser.add_argument("--cas", type=str, default="valid_cas_string_32chars_long_enough")
    args = parser.parse_args()
    if args.dashboard:
        print(EnterpriseDashboard().render())
    elif args.request:
        print(get_gateway().request(args.request, args.cas))
    else:
        print("Enterprise ready. --dashboard or --request")

if __name__ == "__main__":
    main()
