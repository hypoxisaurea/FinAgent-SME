from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

for path in (PROJECT_ROOT,):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

collect_ignore_glob = ["manual_*.py", "manual/manual_*.py"]
