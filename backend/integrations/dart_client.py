from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from backend.common.env import get_backend_env_path, load_backend_env

try:
    from backend.opendartreader import OpenDartReader
except ModuleNotFoundError:
    OpenDartReader = None

OPEN_DART_API_KEY_ENV = "OPEN_DART_API_KEY"
OPEN_DART_API_BASE_URL = "https://opendart.fss.or.kr/api"


def resolve_dart_api_key(
    cli_api_key: str | None = None,
    *,
    env_path: str | Path | None = None,
) -> str:
    """CLI 인자 또는 환경 파일을 포함해 DART API 키를 해석한다."""
    if cli_api_key and cli_api_key.strip():
        return cli_api_key.strip()

    load_backend_env(override=True, env_path=env_path)
    api_key = get_dart_api_key(required=False)
    if api_key:
        return api_key

    candidate_path = get_backend_env_path(env_path)
    raise ValueError(
        "OPEN_DART_API_KEY가 없습니다. "
        f"{candidate_path} 또는 환경 변수에 값을 설정해주세요."
    )


def get_dart_api_key(*, required: bool = True) -> str | None:
    """환경에서 OPEN_DART_API_KEY를 읽어 반환한다."""
    api_key = os.getenv(OPEN_DART_API_KEY_ENV, "").strip()
    if api_key:
        return api_key
    if required:
        raise ValueError(f"환경변수 {OPEN_DART_API_KEY_ENV}가 설정되지 않았습니다.")
    return None


def get_dart_client() -> Any:
    """OpenDartReader 클라이언트를 생성한다."""
    if OpenDartReader is None:
        raise ModuleNotFoundError("opendartreader가 설치되어 있지 않습니다.")
    api_key = get_dart_api_key()
    return OpenDartReader(api_key)


def get_dart_json(
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """OpenDART REST API를 호출하고 JSON 응답을 반환한다."""
    request_params = dict(params or {})
    request_params.setdefault("crtfc_key", get_dart_api_key())
    url = f"{OPEN_DART_API_BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(url, params=request_params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise ConnectionError(f"DART API 호출 실패 endpoint={endpoint}") from exc
    except ValueError as exc:
        raise ValueError(f"DART API 응답이 올바른 JSON이 아닙니다. endpoint={endpoint}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"DART API 응답 형식이 dict가 아닙니다. endpoint={endpoint}")
    return payload


def get_dart_bytes(
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> bytes:
    """OpenDART REST API를 호출하고 바이너리 응답을 반환한다."""
    request_params = dict(params or {})
    request_params.setdefault("crtfc_key", get_dart_api_key())
    url = f"{OPEN_DART_API_BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(url, params=request_params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ConnectionError(f"DART API 호출 실패 endpoint={endpoint}") from exc

    return response.content


def fetch_dart_list_records(
    *,
    corp_code: str,
    bgn_de: str,
    end_de: str,
    page_count: int = 100,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """기업 공시 목록을 조회한다."""
    payload = get_dart_json(
        "list.json",
        params={
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": page_count,
        },
        timeout=timeout,
    )

    if payload.get("status") != "000":
        raise ValueError(f"DART 공시 목록 조회 실패: {payload.get('message')}")

    records = payload.get("list", [])
    if not isinstance(records, list):
        raise ValueError("DART 공시 목록 응답의 list 필드 형식이 올바르지 않습니다.")
    return records


def fetch_dart_document_zip(
    *,
    rcept_no: str,
    timeout: int = 30,
) -> bytes:
    """공시 문서 ZIP 바이너리를 다운로드한다."""
    return get_dart_bytes(
        "document.xml",
        params={"rcept_no": rcept_no},
        timeout=timeout,
    )
