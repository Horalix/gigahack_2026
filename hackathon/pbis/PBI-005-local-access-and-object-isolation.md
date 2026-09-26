# PBI-005: Protect patients, meetings and source media

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-001, PBI-002

## Outcome

Enforce local authentication and access checks before patient information is exposed.

## Source of truth

PBI-001; `hackathon/09-patient-data-and-eu.md`; proposed API/storage boundaries. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `services/meeting/auth.py`, `tests/test_access.py`; extend proposed API/storage; login component in `src/lib/components/meetings/` if needed.

## Intended changes

- Use maintained password hashing/session primitives, per-install credentials, HttpOnly/SameSite cookies and appropriate Secure behavior with HTTPS. No embedded shared default password or public login bypass.
- Roles: clinician/reviewer, administrator for configuration, and explicit object grants. Admin status alone must not imply unrestricted content access.
- Scope every meeting/patient/asset/job/export request server-side, including counts, search, source ranges and static-download paths. Patient linkage is separate from permission.
- Bind to loopback by default; explicit LAN mode requires trusted TLS and origin/CSRF controls. Authenticated admin can provision local accounts; security events omit raw content.
- One organization per deployment today; carry organization ID without claiming multi-tenant security.

## Acceptance

- An unassigned second user cannot discover records, counts or artifacts by guessing IDs, searching or replaying media.
- Logout/expiry invalidate access; direct native/local-service calls receive the same checks.

## Targeted validation

Two-user positive/negative route matrix; session expiry/logout; forged IDs/origins; source-media range/export authorization; patient link does not grant access.

## Exclude

Hospital SSO, bespoke cryptography, generic SaaS tenant platform, email authorization implementation.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

