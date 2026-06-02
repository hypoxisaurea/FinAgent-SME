from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from site import getsitepackages
from urllib.parse import quote_plus


def _find_distribution_root() -> Path:
    for site_packages_dir in (Path(p) for p in getsitepackages()):
        dist_info_dirs = list(site_packages_dir.glob("opendartreader-*.dist-info"))
        init_file = site_packages_dir / "__init__.py"
        if dist_info_dirs and init_file.exists():
            return site_packages_dir
    raise ModuleNotFoundError(
        (
            "opendartreader 배포 파일을 찾지 못했습니다. "
            "`pip install opendartreader`를 확인해주세요."
        )
    )


def _load_vendor_package() -> object:
    package_name = "_opendartreader_vendor"
    if package_name in sys.modules:
        return sys.modules[package_name]

    distribution_root = _find_distribution_root()
    spec = importlib.util.spec_from_file_location(
        package_name,
        distribution_root / "__init__.py",
        submodule_search_locations=[str(distribution_root)],
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError("opendartreader 호환 패키지를 불러오지 못했습니다.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module


_vendor_module = _load_vendor_package()
_CACHE_DIR_ENV_NAME = "OPENDARTREADER_CACHE_DIR"


def _resolve_cache_dir() -> Path:
    configured_dir = os.getenv(_CACHE_DIR_ENV_NAME, "").strip()
    cache_dir = (
        Path(configured_dir).expanduser()
        if configured_dir
        else Path(tempfile.gettempdir()) / "opendartreader_cache"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _requests_get_cache(url: str, headers: dict[str, str] | None = None) -> str:
    cache_dir = _resolve_cache_dir()
    cache_file = cache_dir / quote_plus(url)
    if not cache_file.is_file() or cache_file.stat().st_size == 0:
        response = _vendor_module.dart_utils.requests.get(url, headers=headers)
        cache_file.write_text(response.text, encoding="utf-8")
        return response.text

    return cache_file.read_text(encoding="utf-8")


def _patched_init(self, api_key: str) -> None:
    cache_dir = _resolve_cache_dir()
    cache_file = cache_dir / (
        f"opendartreader_corp_codes_{datetime.today().strftime('%Y%m%d')}.pkl"
    )
    for stale_file in cache_dir.glob("opendartreader_corp_codes_*"):
        if stale_file == cache_file:
            continue
        stale_file.unlink()

    if not cache_file.exists():
        corp_codes_df = _vendor_module.dart_list.corp_codes(api_key)
        corp_codes_df.to_pickle(cache_file)

    self.corp_codes = _vendor_module.dart.pd.read_pickle(cache_file)
    self.api_key = api_key


_vendor_module.dart_utils._requests_get_cache = _requests_get_cache
_vendor_module.dart.OpenDartReader.__init__ = _patched_init
OpenDartReader = _vendor_module.OpenDartReader

__all__ = ["OpenDartReader"]
