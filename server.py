import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from web_server import run_server, app

if __name__ == "__main__":
    run_server()
