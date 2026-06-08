from __future__ import annotations

import os
from urllib.parse import quote_plus

from backend.common.env import get_backend_env_path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

DB_URL_ENV_NAME = "DATABASE_URL"
DB_HOST_ENV_NAME = "POSTGRES_HOST"
DB_PORT_ENV_NAME = "POSTGRES_PORT"
DB_USER_ENV_NAME = "POSTGRES_USER"
DB_PASSWORD_ENV_NAME = "POSTGRES_PASSWORD"
DB_NAME_ENV_NAME = "POSTGRES_DB"
SME_LIST_TABLE_NAME = "sme_list"
COMPANY_PROFILE_TABLE_NAME = "company_profiles"
FEATURES_TABLE_NAME = "financial_features"
ERROR_LOG_TABLE_NAME = "financial_error_logs"
CREATED_AT_COLUMN = "created_at"


def get_env_path(env_file: str | None) -> str:
    """백엔드 환경 파일 경로를 반환한다."""
    return get_backend_env_path(env_file)


def resolve_database_url() -> str:
    """환경 변수에서 PostgreSQL 연결 URL을 해석한다."""
    database_url = os.getenv(DB_URL_ENV_NAME, "").strip()
    if database_url:
        return database_url

    host = os.getenv(DB_HOST_ENV_NAME, "localhost").strip()
    port = os.getenv(DB_PORT_ENV_NAME, "5432").strip()
    user = os.getenv(DB_USER_ENV_NAME, "").strip()
    password = os.getenv(DB_PASSWORD_ENV_NAME, "").strip()
    database = os.getenv(DB_NAME_ENV_NAME, "").strip()

    if not user or not password or not database:
        raise ValueError(
            "PostgreSQL 연결 정보를 찾지 못했습니다. .env 파일에 "
            "DATABASE_URL 또는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB "
            "값을 설정해주세요."
        )

    quoted_password = quote_plus(password)
    return f"postgresql+psycopg2://{user}:{quoted_password}@{host}:{port}/{database}"


def create_db_engine() -> Engine:
    """애플리케이션 공통 SQLAlchemy 엔진을 생성한다."""
    return create_engine(resolve_database_url())
