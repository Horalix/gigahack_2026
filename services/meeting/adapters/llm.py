"""Offline llama.cpp server adapter for bounded, schema-validated JSON generation."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..models import ModelAssetError, ModelConfigurationError, validate_assets


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _runtime_path(model: dict) -> Path:
    configured = os.environ.get("MOM_LLM_SERVER_EXECUTABLE")
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    if local_app_data:
        return (Path(local_app_data) / "SecureMOM" / "runtimes" / "llama-b11200-cpu" / name).resolve()
    return (Path(model["model_root"]).parent / "runtimes" / "llama-b11200-cpu" / name).resolve()


def _extract_json(output: str, required_key: str) -> dict:
    decoder = json.JSONDecoder()
    try:
        value = json.loads(output.strip())
        if isinstance(value, dict) and required_key in value:
            return value
    except json.JSONDecodeError:
        pass
    for match in re.finditer(r"\{", output):
        try:
            value, _ = decoder.raw_decode(output[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and required_key in value:
            return value
    raise LLMError("LLM_INVALID_OUTPUT", "The local model returned invalid structured output")


def _response_schema(required_key: str) -> dict:
    evidence = {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["segmentId", "quote"], "properties": {
                    "segmentId": {"type": "string"}, "quote": {"type": "string"}}}}
    if required_key == "events":
        properties = {"operation": {"type": "string", "enum": ["proposal", "confirmation", "amendment", "rejection", "cancellation", "discussion"]},
                      "kind": {"type": "string", "enum": ["decision", "action"]},
                      "text": {"type": "string"}, "ownerText": {"type": ["string", "null"]},
                      "dateExpression": {"type": ["string", "null"]}, "evidence": evidence,
                      "ownerEvidence": evidence, "dateEvidence": evidence}
        required = list(properties)
    elif required_key == "items":
        properties = {"kind": {"type": "string", "enum": ["decision", "action"]}, "text": {"type": "string"},
                      "status": {"type": "string", "enum": ["proposed", "confirmed", "rejected", "cancelled", "unresolved"]},
                      "ownerText": {"type": ["string", "null"]}, "originalDateExpression": {"type": ["string", "null"]},
                      "evidence": evidence, "ownerEvidence": evidence, "dateEvidence": evidence}
        required = list(properties)
    else:
        raise LLMError("LLM_INVALID_OUTPUT", "Unknown local model output schema")
    item_schema = {"type": "object", "additionalProperties": False, "required": required,
                   "properties": properties}
    if required_key == "events":
        item_schema["allOf"] = [
            {"if": {"properties": {"ownerText": {"type": "string"}}},
             "then": {"properties": {"ownerEvidence": {"minItems": 1}}}},
            {"if": {"properties": {"dateExpression": {"type": "string"}}},
             "then": {"properties": {"dateEvidence": {"minItems": 1}}}},
        ]
    else:
        item_schema["allOf"] = [
            {"if": {"properties": {"ownerText": {"type": "string"}}},
             "then": {"properties": {"ownerEvidence": {"minItems": 1}}}},
            {"if": {"properties": {"originalDateExpression": {"type": "string"}}},
             "then": {"properties": {"dateEvidence": {"minItems": 1}}}},
        ]
    return {"type": "object", "additionalProperties": False, "required": [required_key],
            "properties": {required_key: {"type": "array", "items": item_schema}}}


class LocalLLM:
    """Keep one localhost-only model process for the duration of a job."""

    def __init__(self, selected: dict, *, startup_timeout: float = 120, request_timeout: float = 180):
        if selected.get("backend") != "llama_cpp":
            raise LLMError("LLM_BACKEND_UNSUPPORTED", "The selected local LLM backend is unavailable")
        try:
            validate_assets({"models": {"llm": selected}}, kinds=("llm",))
        except (ModelAssetError, ModelConfigurationError) as exc:
            raise LLMError("MODEL_NOT_READY", "The selected local LLM asset failed verification") from exc
        self.selected = selected
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.process: subprocess.Popen | None = None
        self.base_url: str | None = None
        self.api_key: str | None = None

    def __enter__(self) -> "LocalLLM":
        executable = _runtime_path(self.selected)
        if not executable.is_file():
            raise LLMError("LLM_RUNTIME_NOT_READY", "The pinned local llama.cpp runtime is missing")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self.api_key = secrets.token_urlsafe(32)
        args = [str(executable), "-m", str(Path(self.selected["path"]).resolve()),
                "--host", "127.0.0.1", "--port", str(port),
                "--api-key", self.api_key,
                "-c", str(int(self.selected["context_size"])),
                "-ngl", str(int(self.selected.get("gpu_layers", 0)))]
        try:
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise LLMError("LLM_RUNTIME_FAILED", "The local LLM process could not be started") from exc
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.close()
                raise LLMError("LLM_RUNTIME_FAILED", "The local LLM process failed to start")
            try:
                health = urllib.request.Request(f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"})
                with urllib.request.urlopen(health, timeout=0.5) as response:
                    if response.status == 200:
                        return self
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        self.close()
        raise LLMError("LLM_START_TIMEOUT", "The local LLM exceeded its bounded startup time")

    def generate_json(self, prompt: str, required_key: str) -> dict:
        if not self.base_url or not self.process or self.process.poll() is not None:
            raise LLMError("LLM_RUNTIME_FAILED", "The local LLM process is not available")
        body = json.dumps({
            "model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "top_p": 1,
            "seed": 0,
            "max_tokens": int(self.selected["max_output_tokens"]),
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "meeting_" + required_key, "strict": True,
                "schema": _response_schema(required_key),
            }},
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}/v1/chat/completions", data=body,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {self.api_key}"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError("LLM_RUNTIME_FAILED", "The local LLM request failed") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            return _extract_json(content, required_key)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM_INVALID_OUTPUT", "The local model returned an invalid response") from exc

    def close(self) -> None:
        process, self.process = self.process, None
        self.base_url = None
        self.api_key = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def __exit__(self, *_exc) -> None:
        self.close()
