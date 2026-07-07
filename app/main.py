"""NEXUS Agent OS — Main entry point."""
import sys
import os

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load Hermes .env so the server can reach the API server
def _load_hermes_env():
    for env_path in [os.path.expanduser("~/.hermes/.env"), ".env"]:
        if not os.path.exists(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)

_load_hermes_env()

from server import main

if __name__ == "__main__":
    main()
