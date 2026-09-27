import json

from evaluation.benchmark import evaluate_manifest, score_critical_terms, _match_actions
from evaluation.asr_compare import score


def test_critical_term_counts_include_unexpected_occurrences():
    result = score_critical_terms(
        "Se administrează noradrenalină.",
        "Noradrenalină și noradrenalină.",
        [{"id": "drug", "canonical": "noradrenalină", "expectedCount": 1}],
    )
    assert result["truePositive"] == 1
    assert result["falsePositive"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 1


def test_decisions_use_one_to_one_matching_and_score_owner_date():
    gold = [{"id": "repeat", "phrases": ["va repeta testul"],
             "owner": "Dr Popescu", "date": "mâine"}]
    predictions = [
        {"text": "Dr Popescu va repeta testul mâine", "ownerLabel": "Dr Popescu",
         "originalDateExpression": "mâine"},
        {"text": "Dr Popescu va repeta testul mâine", "ownerLabel": None,
         "originalDateExpression": None},
    ]
    result = _match_actions(gold, predictions)
    assert (result["truePositive"], result["falsePositive"], result["falseNegative"]) == (1, 1, 0)
    assert result["ownerAndDateAccuracy"]["owner"]["accuracy"] == 1
    assert result["ownerAndDateAccuracy"]["date"]["accuracy"] == 1


def test_manifest_report_scores_without_copying_sensitive_text(tmp_path):
    reference = tmp_path / "reference.txt"
    hypothesis = tmp_path / "hypothesis.txt"
    gold = tmp_path / "gold.json"
    decisions = tmp_path / "decisions.json"
    manifest = tmp_path / "run.json"
    reference.write_text("Mâine se repetă testul.", encoding="utf-8")
    hypothesis.write_text("Mâine se repetă testul!", encoding="utf-8")
    gold.write_text(json.dumps({"criticalTerms": [], "items": []}), encoding="utf-8")
    decisions.write_text(json.dumps({"items": []}), encoding="utf-8")
    manifest.write_text(json.dumps({
        "suite": "synthetic",
        "referenceState": "synthetic",
        "referenceText": reference.name,
        "gold": gold.name,
        "runs": [{"name": "test", "transcript": hypothesis.name,
                  "decisions": decisions.name, "audioSeconds": 10,
                  "stageSeconds": {"asr": 2, "llm": 1},
                  "modelConfig": {"model": "local-test", "language": "ro", "path": "private/audio"}}],
    }), encoding="utf-8")

    report = evaluate_manifest(manifest)
    rendered = json.dumps(report, ensure_ascii=False)
    assert score(reference.read_text(encoding="utf-8"), hypothesis.read_text(encoding="utf-8"))["wer"] == 0
    assert report["runs"][0]["transcript"]["wer"] == 0
    assert report["runs"][0]["stageTotalSeconds"] == 3
    assert report["runs"][0]["stageRtf"] == 0.3
    assert report["runs"][0]["modelConfig"] == {"model": "local-test", "language": "ro"}
    assert "private/audio" not in rendered
    assert reference.read_text(encoding="utf-8") not in rendered
    assert hypothesis.read_text(encoding="utf-8") not in rendered
