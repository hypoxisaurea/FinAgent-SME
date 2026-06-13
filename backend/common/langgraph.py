from __future__ import annotations

import os
import warnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

LANGGRAPH_STRICT_MSGPACK_ENV_NAME = "LANGGRAPH_STRICT_MSGPACK"
LANGGRAPH_IMPORT_GUARD = True

os.environ.setdefault(LANGGRAPH_STRICT_MSGPACK_ENV_NAME, "true")
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version\..*",
    category=LangChainPendingDeprecationWarning,
    module=r"langgraph\.cache\.base(\..*)?",
)


def configure_langgraph_environment() -> None:
    """LangGraph import 전에 안전한 serializer 기본값을 강제한다."""
    os.environ.setdefault(LANGGRAPH_STRICT_MSGPACK_ENV_NAME, "true")
