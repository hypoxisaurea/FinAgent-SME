from __future__ import annotations

import os

DEFAULT_BACKEND_URL = "http://localhost:8000"
BACKEND_URL_ENV_NAME = "FINAGENT_BACKEND_URL"


def get_backend_url() -> str:
    """Streamlit 서버가 호출할 backend base URL을 반환한다."""
    configured_url = os.getenv(BACKEND_URL_ENV_NAME, "").strip()
    return (configured_url or DEFAULT_BACKEND_URL).rstrip("/")
