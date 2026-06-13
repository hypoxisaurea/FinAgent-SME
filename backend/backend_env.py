"""Legacy compatibility shim for backend.common.env.

신규 코드는 `backend.common.env`를 직접 사용한다.
"""

from pathlib import Path

import backend.common.env as common_env

BACKEND_DIR = common_env.BACKEND_DIR
ENV_FILENAME = common_env.ENV_FILENAME
DEFAULT_ENV_PATH = common_env.DEFAULT_ENV_PATH
LEGACY_ENV_PATH = common_env.LEGACY_ENV_PATH


def _sync_common_env_constants() -> None:
    common_env.BACKEND_DIR = BACKEND_DIR
    common_env.ENV_FILENAME = ENV_FILENAME
    common_env.DEFAULT_ENV_PATH = DEFAULT_ENV_PATH
    common_env.LEGACY_ENV_PATH = LEGACY_ENV_PATH


def get_backend_env_path(env_path: str | Path | None = None) -> Path:
    """호환성을 위해 canonical env resolver를 위임 호출한다."""
    _sync_common_env_constants()
    return common_env.get_backend_env_path(env_path)


def load_backend_env(
    *,
    override: bool = False,
    env_path: str | Path | None = None,
) -> Path:
    """호환성을 위해 canonical env loader를 위임 호출한다."""
    _sync_common_env_constants()
    return common_env.load_backend_env(override=override, env_path=env_path)
