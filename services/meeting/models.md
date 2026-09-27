# Local model registry

`models/manifest.json` pins model aliases, upstream revisions, license metadata, and weight SHA-256 digests. `config/profiles/` selects aliases and hardware/runtime limits. Profiles are copied into a JSON-safe job snapshot by `resolve_profile`; later profile changes do not mutate a saved snapshot.

```python
from services.meeting.models import resolve_profile, validate_assets

job_config = resolve_profile(profile_id="laptop8")
# Persist job_config before enqueuing. Runtime must call validate_assets(job_config)
# before model load; this only reads local files and never downloads.
validate_assets(job_config)
```

Precedence is explicit job profile/model/settings, persisted UI profile (passed as `profile_id`), environment defaults, then `laptop8` profile defaults. Aliases and model settings are rejected when unknown or outside the selected profile limits. The ASR runtime must query `ctranslate2.get_supported_compute_types("cuda")` (or the selected device) and pass that set to `validate_runtime_capabilities` before loading.

`POST /api/meetings/{id}/jobs` accepts `profileId`, `asrModelAlias`, and `llmModelAlias` for the next job. The service records the resolved profile in that job; changing environment defaults or a UI selection afterward does not change work already queued.

`GET /api/profiles` returns per-profile `asrModels` and `llmModels` choices filtered by profile allowlists, backend compatibility, and local asset presence. The workbench sends selected aliases with uploads, reprocessing, and live ASR previews. `MOM_ASR_MODEL` and `MOM_LLM_MODEL` remain the defaults; explicit job selections take precedence. The current profiles expose Whisper large-v3 and Qwen3.5 4B only.

Prepare model files only through the explicit online setup command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hackathon/prepare-models.ps1 -Model ASR
```

Pass `-Model LLM` or `-Model All` to select other assets. Model files live outside this checkout by default under `%LOCALAPPDATA%/SecureMOM/models`. Runtime startup is offline and fails closed for a missing or corrupt required asset.

The registry records the reported 3070 Ti Mobile / 8 GB / 24 GB laptop and 5080 / 16 GB remote host. Remote system RAM is unknown; neither profile has been measured on its named hardware here. Qwen3.5 Q4_K_M is pinned as a GGUF candidate, but the exact llama.cpp build, embedded chat template behavior, constrained JSON behavior and a real local load remain unqualified. The model files are not in the repository.

For the pending Qwen qualification on this Windows laptop, the [official `llama.cpp` `b11200` CPU release](https://github.com/ggml-org/llama.cpp/releases/tag/b11200) archive (`llama-b11200-bin-win-cpu-x64.zip`, SHA-256 `b958c2f249b59335048a57993802b292faeffaee55555b71e59616d6c2c399ca`) was verified and unpacked outside the checkout. Its CLI reports build 11200 / commit `81bc6b83f`. This verifies runtime provenance only; Qwen load and the laptop GPU profile still need tests.
