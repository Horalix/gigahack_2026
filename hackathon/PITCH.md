# Notavra — pitch notes

## 60-second version

Clinical teams lose time turning multilingual meetings into accurate, usable follow-up. Notavra turns a local audio recording into an editable transcript, evidence-linked decisions and actions, and a clinician-approved minutes file. It keeps source audio available during review, so a doctor can search a phrase, replay its timestamp, correct the wording and regenerate the output. In this prototype, ASR and decision extraction run locally, with no runtime cloud inference.

Our measured Romanian sample favored Whisper large-v3 over the two tested OmniASR variants. With the 8 GB laptop profile, a standalone batch-2 ASR probe took about 47 seconds for an 11m43s recording and scored 51.64% WER against a Microsoft-generated transcript. That reference is not human-verified, so this score measures disagreement, not clinical accuracy. The integrated app took 123 seconds upload-to-ready for the same sample. A duration soak made by repeating the challenge clip to 60 minutes reached `ready` in 19m04s without OOM, with 2.63 GiB minimum available RAM; this is not a genuine hour-long meeting or quality test. We are presenting a local workflow and an honest measurement, not a clinically validated product.

## 3-minute arc

1. **Problem:** meeting audio is not a useful clinical/operational record until the transcript and follow-up are reviewable.
2. **Workflow:** find a patient, open a meeting, upload audio, choose Romanian, run local ASR and local decision extraction.
3. **Trust:** every suggested action has source evidence; the transcript can be searched, replayed at its timestamp and corrected; a person must review before approval.
4. **Output:** approval produces a checksummed HTML file tied to the transcript revision. Affan demonstrates any email delivery separately.
5. **Evidence:** show the bounded Whisper/OmniASR comparison and laptop batch-2 timing. State that the Microsoft reference is unverified, the 5080 configuration is untested, and the hour-duration result used repeated challenge audio; it is not a genuine hour-long meeting or 15-minute qualification.
6. **Boundary:** the demo uses synthetic patient details and authorized challenge audio. This prototype is not GDPR-certified or for real patient care.

## Answers to likely judge questions

- **Is any ASR/LLM call sent to a cloud service?** Runtime ASR and decision extraction use local model files. The final release still needs the disconnected-start/egress check.
- **Why Whisper over OmniASR?** On the same Romanian audio and saved reference, current Whisper batch 2 scored 51.64% WER; Omni LLM scored 66.9%, and Omni CTC scored 72.6%. CTC did not support the same explicit Romanian language control. These are machine-reference disagreement results, not a claim of clinical accuracy.
- **Does one hour finish in 15 minutes?** We did not qualify the 15-minute target. The repeated-clip duration soak took 19m04s and reached `ready`; no email-delivery timing has been measured. The user has asked us not to spend more time testing this speed target.
- **Is it ready for a hospital?** No. Local access controls and deletion exist, but GDPR/legal review, retention policy, backup/key handling, clinical validation, 5080 qualification and deployment review remain.
