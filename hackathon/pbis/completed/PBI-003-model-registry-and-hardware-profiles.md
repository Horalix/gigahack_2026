# PBI-003: Prepare local model registry and 8/16 GB profiles

Parent: `hackathon/pbis/README.md`  
Status: COMPLETE  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-001

## Outcome

Make supported model/checkpoint changes configuration-driven and qualify required assets before runtime.

## Source of truth

`hackathon/03-models-and-performance.md`; existing `src-tauri/src/model_settings.rs`; current hardware user statements. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `services/meeting/models.py`, `config/profiles/laptop8.json`, `hospital16.json`, `cpu.json`, `models/manifest.json`, `scripts/hackathon/prepare-models.ps1`, configuration example.

## Intended changes

- Registry stores local paths, upstream revisions, hashes/licenses, runtime/backend, quantization and validated capabilities. Prepare assets online only through explicit setup command.
- Profiles select registered aliases. Environment establishes defaults; UI preference and explicit job selection are validated against deployment limits; freeze effective config per job.
- Start with full large-v3/faster-whisper INT8-FP16 beam 5 batch 1 and Qwen3.5-4B Q4_K_M. Verify actual GGUF/runtime/template; no invented compatible binary. Keep optional models uninstalled until needed.
- Inventory 3070 Ti Mobile / 8 GB / 24 GB RAM; separately inventory remote 5080 / 16 GB and its unknown system RAM. Query supported compute types; reserve headroom.
- Missing or corrupt assets fail preflight with no runtime download. Dropdown lists installed/compatible options and applies to subsequent jobs only.

## Acceptance

- Changing a supported model alias changes the next job without source edits; previous jobs retain their config.
- Corrupt/missing assets fail offline; manifests include licenses/hashes; prepared startup needs no network.

## Targeted validation

Config precedence, unavailable profile/backend, bad hash, frozen job config, one real load on laptop. Record remote profile as untested until executed.

## Exclude

New model-family adapters beyond selected baseline, downloading real hospital data, performance promises.

## Completion record

- Commit / changed files: uncommitted on `noomy/freepalestine`; registry/profiles/manifest, setup scripts, model guide/config example and `tests/test_models.py` are present. PBI stays OPEN.
- Commands and observed behavior: five focused registry tests pass within the 17-test service suite; Ruff and manifest/schema/PowerShell parsing pass. Local CTranslate2 supports `int8_float16` on the RTX 3070 Ti. The pinned 3.09 GB large-v3 and 2.74 GB Qwen GGUF passed SHA-256 checks under local app data. Large-v3 loaded and transcribed the permitted Medpark audio on the laptop GPU. The SHA-256-verified llama.cpp b11200 Windows CPU runtime loaded the GGUF with its embedded chat template and, with reasoning disabled, returned the expected JSON fields for a synthetic decision/owner/deadline prompt (9.5 generated tokens/s in this small CPU smoke test). Missing/corrupt asset, profile precedence, alias selection and frozen job configuration are covered by focused tests; runtime model access is local-only.
- Acceptance evidence / limitations: laptop ASR and CPU LLM loads are real. The Qwen GPU runtime and remote 16 GB host are not yet qualified; PBI-009/017 must measure the final LLM and end-to-end hardware paths. The CLI's JSON-schema grammar failed when used together with its chat wrapper, despite unconstrained JSON succeeding; PBI-009 must validate output and choose a compatible structured-output path. No performance or clinical accuracy claim follows from this PBI.
