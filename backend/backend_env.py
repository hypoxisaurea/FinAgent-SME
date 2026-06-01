from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILENAME = ".env"
DEFAULT_ENV_PATH = BACKEND_DIR / ENV_FILENAME
LEGACY_ENV_PATH = BACKEND_DIR / "agents" / ENV_FILENAME


def get_backend_env_path(env_path: str | Path | None = None) -> Path:
    if env_path is not None:
        return Path(env_path).expanduser().resolve()
    if DEFAULT_ENV_PATH.exists():
        return DEFAULT_ENV_PATH
    return LEGACY_ENV_PATH


def load_backend_env(
    *,
    override: bool = False,
    env_path: str | Path | None = None,
) -> Path:
    resolved_env_path = get_backend_env_path(env_path)
    if resolved_env_path.exists():
        load_dotenv(dotenv_path=resolved_env_path, override=override)
    return resolved_env_path
