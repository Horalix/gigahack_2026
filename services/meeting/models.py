"""Local model registry and immutable per-job profile snapshots.

This module never downloads model assets. Provisioning is an explicit setup command;
call ``validate_assets`` at the runtime boundary before loading a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]
_PROFILES = _ROOT / "config" / "profiles"
_MANIFEST = _ROOT / "models" / "manifest.json"


class ModelConfigurationError(ValueError):
    """Raised when a profile/model choice is unknown or outside deployment limits."""


class ModelAssetError(RuntimeError):
    """Raised when required model files are absent or fail their pinned digest."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelConfigurationError(f"Could not read model configuration: {path}") from exc
    if not isinstance(value, dict):
        raise ModelConfigurationError(f"Expected an object in model configuration: {path}")
    return value


def _model_root() -> Path:
    configured = os.environ.get("MOM_MODEL_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "SecureMOM" / "models").resolve()
    return (Path.home() / ".local" / "share" / "secure-mom" / "models").resolve()


def resolve_profile(
    profile_id: str | None = None,
    *,
    asr_alias: str | None = None,
    llm_alias: str | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a detached, JSON-safe snapshot for a newly created job.

    ``profile_id`` is the caller's persisted UI preference or explicit job choice.
    When omitted, ``MOM_PROFILE`` is used, then ``laptop8``. Explicit model aliases
    and ``overrides`` take precedence over environment defaults, then profile
    settings. Every choice is checked against the chosen deployment profile.
    """
    selected_id = profile_id or os.environ.get("MOM_PROFILE") or "laptop8"
    if not isinstance(selected_id, str) or not selected_id:
        raise ModelConfigurationError("Profile ID must be a non-empty string.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", selected_id):
        raise ModelConfigurationError(f"Unknown model profile: {selected_id}")
    profile_file = _PROFILES / f"{selected_id}.json"
    if not profile_file.is_file():
        raise ModelConfigurationError(f"Unknown model profile: {selected_id}")

    profile = _read_json(profile_file)
    manifest = _read_json(_MANIFEST)
    registry = manifest.get("models")
    if not isinstance(registry, dict):
        raise ModelConfigurationError("Model manifest has no model registry.")
    limits = profile.get("limits", {})
    model_root = _model_root()

    def resolve_kind(kind: str, explicit_alias: str | None) -> dict[str, Any]:
        section = profile.get(kind)
        if not isinstance(section, dict):
            raise ModelConfigurationError(f"Profile {selected_id} has no {kind} settings.")
        env_name = "MOM_ASR_MODEL" if kind == "asr" else "MOM_LLM_MODEL"
        alias = explicit_alias or os.environ.get(env_name) or section.get("model_alias")
        if not isinstance(alias, str) or alias not in registry:
            raise ModelConfigurationError(f"Unknown {kind.upper()} model alias: {alias}")
        allowed = limits.get(f"allowed_{kind}_models", [])
        if alias not in allowed:
            raise ModelConfigurationError(
                f"Model {alias} is outside the {selected_id} deployment limits."
            )
        model = registry[alias]
        if model.get("task") != kind:
            raise ModelConfigurationError(f"Model {alias} cannot be used for {kind.upper()}.")
        if section.get("backend") != model.get("backend"):
            raise ModelConfigurationError(f"Profile {selected_id} selects an unsupported {kind.upper()} backend.")
        result = dict(model)
        result.update(section)
        env_settings = {
            "asr": {
                "compute_type": "MOM_ASR_COMPUTE_TYPE",
                "batch_size": "MOM_ASR_BATCH_SIZE",
                "beam_size": "MOM_ASR_BEAM_SIZE",
                "language": "MOM_ASR_LANGUAGE",
            },
            "llm": {
                "context_size": "MOM_LLM_CONTEXT_SIZE",
                "max_output_tokens": "MOM_LLM_MAX_OUTPUT_TOKENS",
                "runtime": "MOM_LLM_RUNTIME",
            },
        }[kind]
        kind_overrides = dict((overrides or {}).get(kind, {}))
        for setting, variable in env_settings.items():
            if variable in os.environ:
                raw = os.environ[variable]
                try:
                    kind_overrides.setdefault(setting, int(raw) if setting in {"batch_size", "beam_size", "context_size", "max_output_tokens"} else raw)
                except ValueError as exc:
                    raise ModelConfigurationError(f"Invalid integer in {variable}.") from exc
        for setting, value in kind_overrides.items():
            if setting in {"backend", "path", "model_root", "task", "artifact", "artifacts", "revision", "upstream", "sha256", "license"}:
                raise ModelConfigurationError(f"Job override cannot change protected model field {setting}.")
            if setting not in section:
                raise ModelConfigurationError(f"Unknown {kind.upper()} setting: {setting}")
            if isinstance(section[setting], bool) or type(value) is not type(section[setting]):
                raise ModelConfigurationError(f"Invalid type for {kind.upper()} setting {setting}.")
            result[setting] = value
        backend_env = os.environ.get("MOM_ASR_BACKEND" if kind == "asr" else "MOM_LLM_BACKEND")
        if backend_env and backend_env != model.get("backend"):
            raise ModelConfigurationError(f"Configured {kind.upper()} backend is not registered for {alias}.")
        if kind == "asr":
            if result.get("language", "auto") not in {"auto", "ro", "ru", "en"}:
                raise ModelConfigurationError("ASR language must be auto, ro, ru, or en.")
            if result["batch_size"] < 1 or result["batch_size"] > limits["max_asr_batch_size"]:
                raise ModelConfigurationError("ASR batch_size exceeds profile limits.")
            if result["beam_size"] < 1 or result["beam_size"] > limits["max_asr_beam_size"]:
                raise ModelConfigurationError("ASR beam_size exceeds profile limits.")
        else:
            if result.get("runtime", "cpu") not in {"cpu", "cuda12", "cuda13"}:
                raise ModelConfigurationError("LLM runtime must be cpu, cuda12, or cuda13.")
            if result["context_size"] < 1 or result["context_size"] > limits["max_llm_context_size"]:
                raise ModelConfigurationError("LLM context_size exceeds profile limits.")
            if result["max_output_tokens"] < 1 or result["max_output_tokens"] > limits["max_llm_output_tokens"]:
                raise ModelConfigurationError("LLM max_output_tokens exceeds profile limits.")
        result["alias"] = alias
        result["path"] = str(model_root / model["path"])
        result["model_root"] = str(model_root)
        result.pop("model_alias", None)
        return result

    snapshot = {
        "profile_id": selected_id,
        "hardware": dict(profile.get("hardware", {})),
        "limits": dict(limits),
        "scheduling": dict(profile.get("scheduling", {})),
        "models": {
            "asr": resolve_kind("asr", asr_alias),
            "llm": resolve_kind("llm", llm_alias),
        },
    }
    return snapshot


def profile_model_choices(profile_id: str, kind: str) -> list[dict[str, Any]]:
    """List installed models permitted by a profile for the workbench selector."""
    if kind not in {"asr", "llm"}:
        raise ModelConfigurationError(f"Unknown model kind: {kind}")
    profile = _read_json(_PROFILES / f"{profile_id}.json")
    manifest = _read_json(_MANIFEST)
    section = profile.get(kind, {})
    registry = manifest.get("models", {})
    root = _model_root()
    choices = []
    for alias in profile.get("limits", {}).get(f"allowed_{kind}_models", []):
        model = registry.get(alias)
        if (not isinstance(model, dict) or model.get("task") != kind
                or model.get("backend") != section.get("backend")):
            continue
        model_path = root / model["path"]
        artifacts = [model["artifact"]] if model.get("artifact") else model.get("artifacts", [])
        present = bool(artifacts) and all(
            (model_path / item["path"] if not model.get("artifact") else model_path).is_file()
            for item in artifacts
        )
        choices.append({
            "alias": alias,
            "label": model.get("display_name", alias),
            "available": present,
        })
    return choices


def validate_assets(config: dict[str, Any], kinds: tuple[str, ...] = ("asr", "llm")) -> None:
    """Check selected local files and pinned SHA-256 digests, without network."""
    models = config.get("models")
    if not isinstance(models, dict):
        raise ModelConfigurationError("Job model snapshot is missing its models object.")
    for kind in kinds:
        if kind not in {"asr", "llm"}:
            raise ModelConfigurationError(f"Unknown model kind: {kind}")
        model = models.get(kind)
        if not isinstance(model, dict):
            raise ModelConfigurationError(f"Job model snapshot is missing {kind.upper()}.")
        model_path = Path(model["path"]).resolve()
        root = Path(model["model_root"]).resolve()
        try:
            model_path.relative_to(root)
        except ValueError as exc:
            raise ModelConfigurationError(f"{kind.upper()} path escapes the model root.") from exc

        artifact = model.get("artifact")
        artifacts = model.get("artifacts")
        required = [artifact] if artifact else artifacts
        if not isinstance(required, list) or not required:
            raise ModelConfigurationError(f"{kind.upper()} manifest has no required assets.")
        for item in required:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ModelConfigurationError(f"Invalid {kind.upper()} artifact manifest entry.")
            local_file = model_path if artifact else (model_path / item["path"]).resolve()
            try:
                local_file.relative_to(root)
            except ValueError as exc:
                raise ModelConfigurationError(f"{kind.upper()} artifact escapes the model root.") from exc
            if not local_file.is_file():
                raise ModelAssetError(f"Required {kind.upper()} asset is missing: {local_file}")
            expected_size = item.get("size_bytes")
            if expected_size is not None and local_file.stat().st_size != expected_size:
                raise ModelAssetError(f"Size mismatch for {kind.upper()} asset: {local_file}")
            expected = item.get("sha256")
            if expected:
                digest = hashlib.sha256()
                with local_file.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise ModelAssetError(f"SHA-256 mismatch for {kind.upper()} asset: {local_file}")


def validate_runtime_capabilities(
    config: dict[str, Any], *, asr_compute_types: set[str] | None = None
) -> None:
    """Check dynamic backend capabilities after probing the installed runtime."""
    asr = config.get("models", {}).get("asr", {})
    compute_type = asr.get("compute_type")
    if asr_compute_types is not None and compute_type not in asr_compute_types:
        raise ModelConfigurationError(
            f"ASR compute type {compute_type!r} is not supported by the installed backend."
        )
