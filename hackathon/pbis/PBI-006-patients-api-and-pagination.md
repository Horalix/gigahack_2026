# PBI-006: Create a minimal searchable patient directory

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-001, PBI-002, PBI-005

## Outcome

Let authorized doctors create/find a patient and inspect explicitly linked documentation.

## Source of truth

Latest patient-dashboard request; `hackathon/09-patient-data-and-eu.md`; PBI-001. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `services/meeting/patients.py`, migration through `storage.py`, `tests/test_patients.py`; synthetic seed fixture.

## Intended changes

- Store opaque patient ID, organization ID, display name, optional hospital reference, status and timestamps. No diagnosis, national ID, address or birth date unless a concrete later workflow needs it.
- Add authenticated create/update/list/detail and explicit patient-meeting linking. Link operations require both object permissions and operator confirmation. No name matching by LLM and no automatic patient creation from audio.
- Server-side name/reference search uses normalized Unicode search keys and parameterized queries. Apply authorization before filtering/count/limit. Stable ordering by normalized display name then ID.
- Cursor pagination with default 25/max 100, next cursor and has_more. Bind cursor to sort/filter; resetting search resets pagination. Limit query length and expose only authorized counts, if supplied.
- Return only authorized meeting references. A multi-patient meeting does not become readable through a patient link.

## Acceptance

- Create/update/restart works; authorized partial-name/reference search and pagination work with duplicate names and diacritics.
- Linked records cannot expose another patient's or another user's meeting content.

## Targeted validation

At least 1,000 synthetic rows; first/last/no-result pages; duplicate names; RO/Cyrillic case handling; changed filter/cursor; unauthorized records/counts; malicious query input.

## Exclude

Real patient import, full EHR, inferred diagnoses, patient-level summaries of mixed meetings, mailing.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

