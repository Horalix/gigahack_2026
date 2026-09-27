import os
import sys

from services.meeting.cuda_runtime import cuda_library_directories


def test_cuda_library_directories_include_configured_and_venv_paths(tmp_path, monkeypatch):
    prefix = tmp_path / "venv"
    configured = tmp_path / "custom-cuda" / "bin"
    cudnn = prefix / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin"
    configured.mkdir(parents=True)
    cudnn.mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setenv("MOM_CUDA_DLL_PATHS", os.fspath(configured))

    result = cuda_library_directories()

    assert configured.resolve() in result
    assert cudnn.resolve() in result
