from __future__ import annotations

from typing import Any

from backend.data.db import (
    CREATED_AT_COLUMN,
    ERROR_LOG_TABLE_NAME,
    FEATURES_TABLE_NAME,
    SME_LIST_TABLE_NAME,
    create_db_engine,
    get_env_path,
    resolve_database_url,
)

__all__ = [
    "CompanyRegistryBuilderAgent",
    "CREATED_AT_COLUMN",
    "ERROR_LOG_TABLE_NAME",
    "FEATURES_TABLE_NAME",
    "SME_LIST_TABLE_NAME",
    "create_db_engine",
    "dart_collection_node",
    "execute_dart_pipeline",
    "get_env_path",
    "resolve_database_url",
]


def __getattr__(name: str) -> Any:
    if name in {"CompanyRegistryBuilderAgent", "dart_collection_node"}:
        from backend.agents.company_registry.agent import (
            CompanyRegistryBuilderAgent,
            dart_collection_node,
        )

        exports = {
            "CompanyRegistryBuilderAgent": CompanyRegistryBuilderAgent,
            "dart_collection_node": dart_collection_node,
        }
        return exports[name]

    if name == "execute_dart_pipeline":
        from backend.data.services.company_registry_pipeline import (
            execute_dart_pipeline,
        )

        return execute_dart_pipeline

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
