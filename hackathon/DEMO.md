# Notavra demo runbook

**Purpose:** show a clear local workflow with claims that match current evidence. Plan for 3 minutes. Use synthetic patient details and only the permitted challenge recording.

## Before the room

- Start from `codex/notavra-finalization` at commit `ea75e76` or a later reviewed commit; confirm branch and clean working tree.
- Run `scripts/hackathon/preflight.ps1 -ProfileId laptop8`. Verify the local Whisper and Qwen files, CUDA runtime and at least 8 GiB available system RAM. Select **Laptop · RTX 3070 Ti · 8 GB** and **Romanian** for the Romanian sample.
- Start Notavra and confirm the dashboard loads, authentication works, and the model profile is available. Do not download or change models during the demo.
- Use an explicitly synthetic patient and meeting title. Keep the challenge audio and transcript in app data; never copy them into the repository or slides.
- Have a previously generated HTML artifact and screenshots ready as a backup. Do not substitute them for a live run without labeling them as a prior run.

## Live path

1. Open the patient directory, search the synthetic patient, then open or create a meeting.
2. Upload the permitted Romanian audio, select Romanian and the laptop profile, and start transcription. If demonstrating microphone capture, show its level and locally acknowledged chunk count; the app transcribes a recording after Stop, so do not describe it as live captions.
3. Show the original-language transcript, decision/action cards and their source excerpts. Point out that items require human review.
4. Search for a passage and use its Play control to hear the corresponding source audio. Make one deliberate transcript correction only if the operator can confirm it against the audio; reprocess before approving.
5. Read the transcript and every suggested item. Then check the review confirmation and download the generated HTML minutes.
6. Show the generated file's revision and checksum. Affan owns any email-delivery demonstration on his branch.

## Narration cues

- “Audio and language models run on this computer; patient records and recordings stay in local app storage during this demo.”
- “The transcript is editable, decisions show their source excerpts, and the clinician approves the final file.”
- “The 8 GB configuration uses Whisper large-v3, FP16 and batch 2. Our current 11m43s sample benchmark takes about 47 seconds for ASR.”
- “That recording's reference is Microsoft-generated and not human-verified. Our reported WER is disagreement with that reference, not clinical accuracy.”

## If anything fails

- Use the saved screenshot/HTML and label them as output from an earlier run. Do not claim they came from the current run.
- If local inference fails, show the visible error and report the failed stage. Do not switch to a cloud API.
- If a suggested action is wrong or unsupported, leave it unresolved or correct it from the recording. Do not present an unreviewed item as fact.
- If the WAN/offline gate was not run in the final environment, say so plainly.
