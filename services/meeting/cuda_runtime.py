"""Windows CUDA library discovery shared by preflight and ASR loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_HANDLES = []
_REQUIRED_DLLS = ("cublas64_12.dll", "cudnn_ops64_9.dll", "zlibwapi.dll")


def cuda_library_directories() -> list[Path]:
    """Return configured and venv-local NVIDIA DLL directories, in load order."""
    configured = os.environ.get("MOM_CUDA_DLL_PATHS", "")
    paths = [Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip()]
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    paths.extend(sorted((site_packages / "nvidia").glob("*/bin")))
    paths.append(site_packages / "torch" / "lib")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        paths.extend(sorted(Path(local_app_data).glob("Programs/Python/Python*/Lib/site-packages/torch/lib")))
    unique: dict[str, Path] = {}
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_dir():
            unique.setdefault(os.fspath(resolved).casefold(), resolved)
    return list(unique.values())


def configure_cuda_dll_search() -> tuple[bool, str | None]:
    """Register CUDA DLL directories before CTranslate2 is imported on Windows."""
    if os.name != "nt":
        return True, None
    directories = cuda_library_directories()
    os.environ["PATH"] = os.pathsep.join(
        [*(os.fspath(path) for path in directories), os.environ.get("PATH", "")]
    )
    found = {name.casefold(): False for name in _REQUIRED_DLLS}
    for directory in directories:
        for name in _REQUIRED_DLLS:
            found[name.casefold()] |= (directory / name).is_file()
        try:
            _DLL_HANDLES.append(os.add_dll_directory(os.fspath(directory)))
        except (FileNotFoundError, OSError):
            continue
    missing = [name for name, present in found.items() if not present]
    if missing:
        return False, "Missing CUDA runtime libraries: " + ", ".join(missing)
    return True, None
