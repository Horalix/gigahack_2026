import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.meeting.models import (
    ModelAssetError,
    ModelConfigurationError,
    resolve_profile,
    validate_assets,
    validate_runtime_capabilities,
)


class ModelRegistryTests(unittest.TestCase):
    def test_profile_returns_detached_snapshot_with_runtime_settings(self):
        with patch.dict(os.environ, {"MOM_MODEL_ROOT": "C:/models", "MOM_PROFILE": "cpu"}):
            laptop = resolve_profile("laptop8")
            cpu = resolve_profile()

        self.assertEqual(laptop["profile_id"], "laptop8")
        self.assertEqual(laptop["models"]["asr"]["compute_type"], "int8_float16")
        self.assertEqual(laptop["models"]["asr"]["batch_size"], 1)
        self.assertEqual(laptop["models"]["asr"]["beam_size"], 5)
        self.assertEqual(cpu["profile_id"], "cpu")
        laptop["models"]["asr"]["beam_size"] = 1
        self.assertEqual(resolve_profile("laptop8")["models"]["asr"]["beam_size"], 5)

    def test_environment_and_job_overrides_are_validated_by_profile(self):
        with patch.dict(os.environ, {"MOM_ASR_BATCH_SIZE": "2"}):
            config = resolve_profile("laptop8", overrides={"asr": {"beam_size": 3}})
        self.assertEqual(config["models"]["asr"]["batch_size"], 2)
        self.assertEqual(config["models"]["asr"]["beam_size"], 3)
        with self.assertRaises(ModelConfigurationError):
            resolve_profile("cpu", asr_alias="missing-model")
        with self.assertRaises(ModelConfigurationError):
            resolve_profile("laptop8", overrides={"asr": {"path": "C:/elsewhere/model"}})
        with self.assertRaises(ModelConfigurationError):
            resolve_profile("cpu", overrides={"asr": {"batch_size": 2}})

    def test_missing_and_corrupt_models_fail_offline(self):
        config = resolve_profile("cpu")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asr_path = root / "asr"
            asr_path.mkdir()
            llm_path = root / "model.gguf"
            llm_path.write_bytes(b"model fixture")
            config["models"]["asr"].update(model_root=str(root), path=str(asr_path))
            config["models"]["llm"].update(
                model_root=str(root), path=str(llm_path),
                artifact={"path": llm_path.name, "sha256": hashlib.sha256(b"model fixture").hexdigest()},
            )
            with self.assertRaises(ModelAssetError):
                validate_assets(config)
            (asr_path / "model.bin").write_bytes(b"asr fixture")
            config["models"]["asr"]["artifacts"] = [{"path": "model.bin", "sha256": hashlib.sha256(b"asr fixture").hexdigest()}]
            validate_assets(config)
            config["models"]["asr"]["artifacts"] = [{"path": "model.bin", "sha256": hashlib.sha256(b"correct").hexdigest()}]
            with self.assertRaises(ModelAssetError):
                validate_assets(config)

    def test_unknown_profile_fails(self):
        with self.assertRaises(ModelConfigurationError):
            resolve_profile("unknown")

    def test_runtime_compute_type_is_checked_against_backend_probe(self):
        config = resolve_profile("laptop8")
        validate_runtime_capabilities(config, asr_compute_types={"int8_float16"})
        with self.assertRaises(ModelConfigurationError):
            validate_runtime_capabilities(config, asr_compute_types={"int8"})


if __name__ == "__main__":
    unittest.main()
