# PBI-022: Prepare the privacy and ethics gate for a real pilot

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: Before real patient use; evidence inventory starts today  
Owner: CEO with hospital controller/DPO/legal reviewer; AI drafts evidence  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-001, PBI-005, PBI-015; does not block synthetic demo

## Outcome

Turn privacy intentions into an accountable hospital-specific pilot decision.

## Source of truth

`hackathon/09-patient-data-and-eu.md` official references, current data flow and deployed behavior. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `hackathon/pilot/data-inventory.md`, `privacy-checklist.md`, `risk-register.md`, `intended-use.md` and impact-assessment worksheet; use actual implementation evidence.

## Intended changes

- Inventory purposes, data categories, roles, recipients, residency, access, retention, deletion/backup limits and suppliers. Determine GDPR applicability and local hospital/member-state requirements with accountable reviewer.
- Record Article 6 basis and applicable Article 9 condition for health/identifying biometric use; distinguish recording notice/consent UI from legal determination. Screen DPIA/DPO requirements; complete required assessments before pilot.
- Plan notices, rights/rectification/access requests, processor agreements where relevant, incident response, breach-assessment procedure and cross-border access restrictions.
- Review intended purpose for AI Act/MDR classification using current authoritative guidance; do not assume every hospital app is a medical device or exempt it by naming it a note-taker.
- Evaluate bias by language/accent, automation bias, correction burden, false identity matching and access inequity. No secondary training by default.

## Acceptance

- Each pilot condition has owner/evidence/status and unresolved items block real-patient release. CEO claims are consistent with reviewed intended use and actual tests.

## Targeted validation

Tabletop access/rectification/deletion and incident scenarios; hospital/DPO review recorded. AI cannot self-certify legal compliance.

## Exclude

Legal conclusions by coding agent, guaranteed CE/GDPR certification, independent mailing design.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

