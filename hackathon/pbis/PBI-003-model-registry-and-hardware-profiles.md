# PBI-003: Prepare local model registry and 8/16 GB profiles

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
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

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

