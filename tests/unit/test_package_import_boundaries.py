from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_import_probe(package_name: str, blocked_modules: list[str]) -> dict[str, bool]:
    module_list = ", ".join(f'"{module_name}"' for module_name in blocked_modules)
    code = f"""
import importlib
import json
import sys

importlib.import_module("{package_name}")

print(json.dumps({{
    module_name: module_name in sys.modules
    for module_name in [{module_list}]
}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return json.loads(completed.stdout)


def test_common_package_import_does_not_load_settings_module() -> None:
    result = _run_import_probe(
        "backend.common",
        ["backend.common.settings", "backend.common.api_client"],
    )

    assert result == {
        "backend.common.settings": False,
        "backend.common.api_client": False,
    }


def test_tools_package_import_does_not_load_tool_modules() -> None:
    result = _run_import_probe(
        "backend.tools",
        ["backend.tools.company_registry", "backend.tools.news"],
    )

    assert result == {
        "backend.tools.company_registry": False,
        "backend.tools.news": False,
    }


def test_data_services_package_import_does_not_load_service_modules() -> None:
    result = _run_import_probe(
        "backend.data.services",
        [
            "backend.data.services.company_registry_pipeline",
            "backend.data.services.workflow_job_service",
        ],
    )

    assert result == {
        "backend.data.services.company_registry_pipeline": False,
        "backend.data.services.workflow_job_service": False,
    }


def test_orchestrator_package_import_does_not_load_workflow_runtime() -> None:
    result = _run_import_probe(
        "backend.agents.orchestrator",
        ["backend.agents.orchestrator.orchestrator"],
    )

    assert result == {"backend.agents.orchestrator.orchestrator": False}
