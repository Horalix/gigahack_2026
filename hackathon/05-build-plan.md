# Priorities and acceptance

**The [PBI index](pbis/README.md) replaces the previous H01-H17 board and 48-hour schedule.** All new work is OPEN until verified. The deadline is today, 26 September 2026.

## Required before optional

| Gate | Work | PBIs |
|---|---|---|
| First real result | Contracts, durable API/jobs, local profiles, GPU transcription | 001-004 |
| Usable doctor app | Authentication, patient search/pagination, main-window dashboard, upload | 005-008 |
| Complete output | Grounded final decisions and deterministic file for Affan | 009-010 |
| Both input modes | Durable live recording and inline provisional transcript | 011-012 |
| Correctable output | Versioned edits, replay, selected replacements and undo | 013-014 |
| Demonstrable release | Data controls, offline launch, accuracy/hour benchmark, presentation | 015-017, 024 |

All are P0, including user-added patient search, live mode and manual corrections. No floating subtitle window in the doctor flow. Mailing implementation belongs exclusively to Affan.

## Completion evidence

- New audio/video produces original RO/RU/EN text, including genuine language switches.
- Source evidence supports decisions, owners and deadlines; rejected proposals and unknown fields are handled correctly.
- Patients are searchable with server pagination; links do not bypass object permissions or expose mixed-patient meetings.
- Live capture persists before inference; failed ASR does not silently lose speech.
- Manual edits preserve raw source and rebuild dependent output; stale files cannot remain ready.
- A prepared offline cold start processes new input. Models and frontend assets are local.
- A genuine one-hour upload reaches observed email receipt in <=900 seconds with Affan. File-ready alone does not prove this gate. Report live lag and Stop-to-receipt separately.
- Report actual hardware, model hashes, stage times, memory, language/critical-term errors and action correctness. Separate raw, machine-only and reviewed results.
- Keep real sensitive data outside Git/OneDrive. Demonstrate with permitted/synthetic material; real patient use needs PBI-022.

Detailed adverse cases and validation belong in each PBI. Old caption test results and mocked responses cannot close these gates.

## After P0

1. PBI-018: bounded AI flags and fast review; abandon the experiment if false flags or latency negate benefit.
2. PBI-019/020: anonymous speaker turns and manual naming/correction.
3. PBI-021: optional returning-speaker enrollment, subject to privacy gates.
4. PBI-022/023: real pilot and EU operational readiness. These are future release gates, not promises to finish legal/production qualification today.

Evidence replay is already part of review. Rich decision-history views, selective second ASR, PDF polish and live decision previews remain deferred ideas; create bounded child PBIs only after required work is stable. Do not build an EHR, clinical-order generator or shared multi-hospital SaaS today.

## Time and scope

Use the [same-day checkpoints](pbis/README.md#today-realistic-checkpoints). Close required gates before polish. If behind, report missing P0 work and let the user decide cuts; leave incomplete tasks OPEN. A reliable demo with honest measured limits is the goal, with no guaranteed competition result.
