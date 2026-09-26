# PBI-005: Protect patients, meetings and source media

Parent: `hackathon/pbis/README.md`  
Status: COMPLETE  
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

- Commit: uncommitted working-tree changes on `noomy/freepalestine`.
- Changed: `services/meeting/auth.py`, `auth_cli.py`, `api.py`, `contracts.py`, `storage.py`, dependency pins, service README, and access/job tests.
- Validation: `python -m pytest services/meeting/tests -q` — 21 passed; `python -m ruff check services/meeting` — clean.
- Implemented per-install Argon2id password hashing, generic login errors, short-lived hashed server-side sessions, logout/expiry, account provisioning/deactivation, explicit owner/editor/viewer meeting grants, organization and meeting checks on meeting/job routes, loopback-only binding checks, trusted-origin enforcement, and removal of the synthetic principal bypass.
- Tested two-user isolation, viewer write denial, administrator-without-content-grant, grant/revoke, forged IDs, session expiry/logout, cookie flags, account suspension, remote-client/origin rejection, and generic login failures.
- Limitations: no source-media download/range or export route exists yet; any added route must enforce the same grants. Tauri UI login/cookie behavior has not been manually exercised, and no GDPR/clinical deployment approval is implied. LAN access, hospital SSO, and distributed tenant security remain out of scope.
