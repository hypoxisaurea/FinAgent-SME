from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from site import getsitepackages


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
OpenDartReader = _vendor_module.OpenDartReader

__all__ = ["OpenDartReader"]
