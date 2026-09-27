# Local evaluation

`benchmark.py` scores raw, pre-review app outputs against an independently prepared reference and gold annotation. It is offline and uses only the Python standard library plus the local scorer in `asr_compare.py`.

```powershell
python -m evaluation.benchmark C:\path\to\private-run.json --output C:\path\outside\repo\metrics.json
```

The manifest paths are relative to the manifest or absolute paths. Keep audio, transcripts, references, decision exports and manifests outside Git and synced folders. The report contains hashes and metrics, not transcript text; model configuration is allowlisted and filesystem paths are omitted.

Manifest shape:

```json
{
  "suite": "Romanian challenge sample",
  "referenceState": "human-verified",
  "audio": "audio.wav",
  "referenceText": "reference.txt",
  "gold": "gold.json",
  "runs": [{
    "name": "Whisper laptop8",
    "transcript": "whisper.txt",
    "decisions": "whisper-decisions.json",
    "modelConfig": {"model": "large-v3", "language": "ro"},
    "audioSeconds": 702.6,
    "stageSeconds": {"decode": 1.4, "asr": 44.8, "decisions": 70.2},
    "peakGpuUsedMiB": 4694
  }]
}
```

Gold JSON contains `criticalTerms` (`id`, `canonical`, optional `aliases`, `expectedCount`), `items` (`id`, human-authored `phrases`, optional expected `owner` and `date`), and `itemsComplete: true` only when a human has annotated the exhaustive action list. Without that explicit marker, action precision/recall is reported as unscored. Decision matching is one-to-one phrase matching after case and punctuation normalization; it is a reproducible screening metric, not semantic adjudication. Only annotated term spellings/counts are scored. Manually review false matches, clinical terms, numbers, negation, owner and date before making accuracy claims.

`referenceState` must say whether the reference is human-verified, machine-generated, or synthetic. WER/CER against an unverified machine transcript measure disagreement, not clinical accuracy. Never score edited transcripts as raw ASR, or compare runs with different source/reference hashes as an apples-to-apples pair.

The tiny [synthetic fixture](fixtures/synthetic-gold.json) and [tests](test_benchmark.py) validate metric behavior only; they are not medical evaluation data. A real one-hour upload-to-approved-file measurement still needs a genuine uninterrupted recording and delivery receipt. Do not repeat a short clip to claim the hour gate.
