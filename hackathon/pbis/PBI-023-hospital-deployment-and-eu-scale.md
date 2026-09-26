# PBI-023: Qualify hospital deployment and expansion

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: After hackathon / before scaled deployment  
Owner: You + hospital IT; CEO defines rollout countries  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-016, PBI-017, PBI-022

## Outcome

Scale a proven installation without losing access isolation or repeatability.

## Source of truth

`hackathon/09-patient-data-and-eu.md`; actual deployment/benchmark results. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Propose `deploy/`, signed/versioned deployment manifests, migration/restore tools and `hackathon/pilot/operations.md`; refine into smaller country/infrastructure tasks after pilot decisions.

## Intended changes

- Start isolated per-hospital installations. Qualify hardware profiles, offline upgrade/rollback, backup/restore, secrets/key ownership and operator runbook.
- Load-test authorized indexed patient pagination and durable jobs. Introduce PostgreSQL/workers only when concurrency/storage evidence justifies replacing SQLite; preserve contract/idempotency.
- Gate pooled multi-tenant hosting behind demonstrated tenant isolation, per-tenant keys/policies and reviewed residency/support access. No cloud dependency in on-premise profile.
- Add country/language/date/timezone/terminology packs with evidence and permissions; assess model/runtime licenses, SBOM/security updates, medical-software obligations for approved intended use.
- Plan optional EHR/FHIR adapters behind actual hospital contracts and identifiers, without automated clinical orders.

## Acceptance

- Representative hospital rollout survives restore/upgrade/rollback and authorized load; residual security/legal/country gaps are explicit before expansion.

## Targeted validation

Two-hospital isolation, migration rollback, restored records/access/deletion state, key recovery, disconnected upgrades, measured load and language regressions.

## Exclude

Kubernetes by default, production release today, speculative high-end-only compute, mail service redesign.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

