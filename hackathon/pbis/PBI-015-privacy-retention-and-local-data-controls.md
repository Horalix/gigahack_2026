# PBI-015: Control local sensitive data and retention

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today; synthetic-data demonstration  
Owner: You; CEO records policy assumptions  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-002, PBI-005, PBI-010, PBI-013

## Outcome

Make stored data, retention and deletion behavior inspectable before a hospital pilot.

## Source of truth

`hackathon/09-patient-data-and-eu.md`; existing secure-deletion limits in README and engineering notes. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/retention.py`, `audit.py`, `tests/test_retention.py`; update storage/settings/launch docs.

## Intended changes

- Set an explicit demo retention policy separately for audio, transcript, artifacts and optional voice templates. Policy is configurable and visibly unapproved for real hospital deployment until reviewed.
- Keep data/model templates outside Git and synced checkout; no raw transcript/patient names in standard logs, filenames or crash reports. Audit actor/object/action/time/revision, not sensitive content.
- Implement authorized record purge with job cancellation/locking to prevent deleted data being regenerated. Distinguish unlink/archive from actual erasure and from legal-hold restrictions.
- Inventory derivatives/caches/exports/backups. Make deleted app-managed assets inaccessible; report external copies and Affan-owned artifacts as outside this component's deletion assurance.
- Document disk encryption/key ownership and backup handling; never treat SQLite secure_delete or soft-delete as complete physical erasure.

## Acceptance

- Deleting a synthetic meeting cancels work, revokes its source/results and prevents replay/re-export; minimum audit survives under documented policy.
- Deleting a patient does not silently erase a shared multi-patient meeting; unresolved scope is surfaced for authorized review.

## Targeted validation

Purge during processing, linked/shared records, retained legal hold, expired asset cleanup, unauthorized delete, backup/derivative inventory and privacy-safe logs.

## Exclude

Claims of GDPR certification, wiping other people's files, changing host encryption automatically, deleting Affan's system data.

## Completion record

- Commit / changed files: `ef3fb6d` plus current branch follow-up; owner-only purge, best-effort cleanup queue, audit with transcript revision, administrator audit view, and a visible manual-retention demo policy. Dashboard confirms scope before deleting.
- Commands and observed behavior: `python -m pytest services/meeting/tests/test_retention.py -q` (3 passed); `python -m pytest services/meeting/tests evaluation -q` (63 passed). Tests verify source audio, interrupted capture chunks, transcript segments, decision results, artifact records/files, transcript checkpoints, and orphaned files under the meeting artifact directory are removed; the meeting and artifact download are inaccessible after deletion; a minimal audit survives; a running job blocks deletion; and an ungranted user cannot delete the meeting.
- Acceptance evidence / limitations: implementation is present, but the new migration, audit UI and display have not been run. The policy is visible but not configurable and automatic expiry is off. Patient-level deletion, key erasure, backups, SSD snapshots, downloaded files and legal holds are not covered. The workbench/README explicitly state this is not GDPR certification. Keep this PBI OPEN.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

