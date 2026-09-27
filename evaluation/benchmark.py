"""Score local transcription and decision outputs against a reviewed manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .asr_compare import normalize, score

_MODEL_CONFIG_KEYS = {
    "model", "backend", "runtime", "language", "precision", "computeType", "compute_type",
    "beamSize", "beam_size", "batchSize", "batch_size", "contextSize", "context_size",
    "maxOutputTokens", "max_output_tokens", "chunkSeconds", "chunk_seconds",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _phrase_count(text: str, phrases: list[str]) -> int:
    normalized = f" {normalize(text)} "
    best = 0
    for phrase in phrases:
        phrase = normalize(phrase)
        if not phrase:
            continue
        needle = f" {phrase} "
        count, offset = 0, 0
        while (found := normalized.find(needle, offset)) >= 0:
            count += 1
            offset = found + len(needle) - 1
        best = max(best, count)
    return best


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _safe_model_config(config: object) -> dict | None:
    if not isinstance(config, dict):
        return None
    return {key: value for key, value in config.items()
            if key in _MODEL_CONFIG_KEYS and isinstance(value, (str, int, float, bool, type(None)))}


def score_critical_terms(reference: str, hypothesis: str, terms: list[dict[str, Any]]) -> dict:
    true_positive = false_positive = false_negative = 0
    results = []
    for term in terms:
        phrases = [term["canonical"], *term.get("aliases", [])]
        expected = term.get("expectedCount", 1)
        if type(expected) is not int or expected < 0:
            raise ValueError("critical term expectedCount must be a non-negative integer")
        actual = _phrase_count(hypothesis, phrases)
        matched = min(expected, actual)
        true_positive += matched
        false_positive += actual - matched
        false_negative += expected - matched
        results.append({"id": term["id"], "expected": expected, "found": actual,
                        "matched": matched})
    return {"truePositive": true_positive, "falsePositive": false_positive,
            "falseNegative": false_negative,
            "precision": _ratio(true_positive, true_positive + false_positive),
            "recall": _ratio(true_positive, true_positive + false_negative),
            "terms": results,
            "scope": "Only explicitly annotated terms and expected counts are scored."}


def _match_actions(gold: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict:
    normalized_predictions = [f" {normalize(item.get('text', ''))} " for item in predictions]
    candidates = []
    for item in gold:
        phrases = [f" {normalize(phrase)} " for phrase in item.get("phrases", []) if normalize(phrase)]
        candidates.append([index for index, text in enumerate(normalized_predictions)
                           if text and any(phrase in text for phrase in phrases)])

    # Maximum one-to-one matching keeps duplicate actions from inflating recall.
    assigned: dict[int, int] = {}

    def assign(gold_index: int, seen: set[int]) -> bool:
        for prediction_index in candidates[gold_index]:
            if prediction_index in seen:
                continue
            seen.add(prediction_index)
            previous = assigned.get(prediction_index)
            if previous is None or assign(previous, seen):
                assigned[prediction_index] = gold_index
                return True
        return False

    for gold_index in range(len(gold)):
        assign(gold_index, set())

    matches = {gold_index: prediction_index for prediction_index, gold_index in assigned.items()}
    true_positive = len(matches)
    false_positive = len(predictions) - true_positive
    false_negative = len(gold) - true_positive
    field_scores = {}
    for field, prediction_key in (("owner", "ownerLabel"), ("date", "originalDateExpression")):
        comparisons = []
        for gold_index, prediction_index in matches.items():
            if field not in gold[gold_index]:
                continue
            expected = gold[gold_index][field]
            actual = predictions[prediction_index].get(prediction_key)
            equal = normalize(expected) == normalize(actual) if expected is not None and actual is not None else expected is actual
            comparisons.append({"goldId": gold[gold_index]["id"], "correct": equal})
        field_scores[field] = {"correct": sum(row["correct"] for row in comparisons),
                               "scored": len(comparisons),
                               "accuracy": _ratio(sum(row["correct"] for row in comparisons), len(comparisons)),
                               "items": comparisons}
    return {"truePositive": true_positive, "falsePositive": false_positive,
            "falseNegative": false_negative,
            "precision": _ratio(true_positive, true_positive + false_positive),
            "recall": _ratio(true_positive, true_positive + false_negative),
            "f1": _ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative),
            "matches": [{"goldId": gold[index]["id"], "predictionIndex": prediction}
                        for index, prediction in sorted(matches.items())],
            "ownerAndDateAccuracy": field_scores,
            "matching": "One-to-one substring match against human-authored gold phrases after case/punctuation normalization."}


def evaluate_manifest(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def input_path(value: str) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else manifest_path.parent / path).resolve()

    reference_path = input_path(manifest["referenceText"])
    gold_path = input_path(manifest["gold"])
    reference = _read_text(reference_path)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    if not reference.strip():
        raise ValueError("Reference transcript is empty")
    if not isinstance(gold.get("criticalTerms", []), list) or not isinstance(gold.get("items", []), list):
        raise ValueError("Gold annotations must contain criticalTerms and items arrays")

    report = {"suite": manifest.get("suite", "unspecified"),
              "referenceState": manifest.get("referenceState", "unverified"),
              "audioSha256": _digest(input_path(manifest["audio"])) if manifest.get("audio") else None,
              "referenceSha256": _digest(reference_path), "goldSha256": _digest(gold_path),
              "runs": []}
    for run in manifest["runs"]:
        transcript_path = input_path(run["transcript"])
        predictions_path = input_path(run["decisions"])
        hypothesis = _read_text(transcript_path)
        decisions = json.loads(predictions_path.read_text(encoding="utf-8"))
        predicted_items = decisions.get("items") if isinstance(decisions, dict) else decisions
        if not isinstance(predicted_items, list):
            raise ValueError(f"Run {run.get('name', '?')} decisions must be an array or an object with items")
        run_report = {"name": run["name"], "transcriptSha256": _digest(transcript_path),
                      "decisionsSha256": _digest(predictions_path), "modelConfig": _safe_model_config(run.get("modelConfig")),
                      "audioSeconds": run.get("audioSeconds"), "stageSeconds": run.get("stageSeconds"),
                      "peakGpuUsedMiB": run.get("peakGpuUsedMiB"),
                      "transcript": score(reference, hypothesis),
                      "criticalTerms": score_critical_terms(reference, hypothesis, gold.get("criticalTerms", [])),
                      "decisions": _match_actions(gold.get("items", []), predicted_items)}
        audio_seconds = run_report["audioSeconds"]
        if audio_seconds and audio_seconds > 0 and isinstance(run_report["stageSeconds"], dict):
            total = sum(float(value) for value in run_report["stageSeconds"].values())
            run_report["stageTotalSeconds"] = round(total, 3)
            run_report["stageRtf"] = round(total / audio_seconds, 5)
        report["runs"].append(run_report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Private local manifest JSON")
    parser.add_argument("--output", type=Path, help="Write metrics JSON (contains hashes, not transcript text)")
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
