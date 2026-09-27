import sys
import types

import pytest

from services.meeting.adapters.asr import ASRError, transcribe_audio


def test_consumes_all_segments_and_preserves_source_offsets(tmp_path, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"fixture")
    decoded = tmp_path / "audio.wav"
    decoded.write_bytes(b"fixture")
    yielded = []

    class FakeWhisper:
        def __init__(self, path, **kwargs):
            assert path == str(model_dir)
            assert kwargs["local_files_only"] is True

        def transcribe(self, path, **kwargs):
            assert kwargs["task"] == "transcribe"
            assert kwargs["language"] is None
            assert kwargs["multilingual"] is True
            assert kwargs["word_timestamps"] is True

            def segments():
                for start, end, text in [(0.2, 1.2, "Salut"), (1.4, 2.0, " привет"), (2.1, 2.8, " hello")]:
                    yielded.append(text)
                    word = types.SimpleNamespace(start=start, end=end, word=text, probability=0.8)
                    yield types.SimpleNamespace(start=start, end=end, text=text, words=[word])

            return segments(), types.SimpleNamespace(language="ro")

    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_supported_compute_types=lambda device: {"int8"}))
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisper,
        BatchedInferencePipeline=lambda model: model))
    config = {"models": {"asr": {"path": str(model_dir), "backend": "faster_whisper", "device": "cpu",
        "compute_type": "int8", "batch_size": 1, "beam_size": 5, "word_timestamps": True}}}
    progress = []
    result = transcribe_audio(decoded, {"id": "asset-1", "duration_ms": 3300, "source_offset_ms": 500}, config, progress.append)
    assert yielded == ["Salut", " привет", " hello"]
    assert [s["startMs"] for s in result["segments"]] == [700, 1900, 2600]
    assert result["segments"][-1]["endMs"] == 3300
    assert all(s["words"][0]["startMs"] >= s["startMs"] for s in result["segments"])
    assert progress[-1] == 3300
    assert result["metrics"]["detectedLanguage"] == "ro"


def test_missing_local_model_fails_without_download(tmp_path):
    config = {"models": {"asr": {"path": str(tmp_path / "missing"), "backend": "faster_whisper"}}}
    with pytest.raises(ASRError, match="missing") as error:
        transcribe_audio(tmp_path / "audio.wav", {"duration_ms": 1000}, config)
    assert error.value.code == "MODEL_NOT_READY"


def test_romanian_selection_disables_language_detection(tmp_path, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"fixture")
    decoded = tmp_path / "audio.wav"
    decoded.write_bytes(b"fixture")

    class FakeWhisper:
        def __init__(self, *args, **kwargs): pass
        def transcribe(self, path, **kwargs):
            assert kwargs["language"] == "ro"
            assert kwargs["multilingual"] is False
            segment = types.SimpleNamespace(start=0, end=1, text="Bună ziua", words=[])
            return iter([segment]), types.SimpleNamespace(language="ro")

    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_supported_compute_types=lambda device: {"int8"}))
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisper,
        BatchedInferencePipeline=lambda model: model))
    config = {"models": {"asr": {"path": str(model_dir), "backend": "faster_whisper", "device": "cpu",
        "compute_type": "int8", "batch_size": 1, "beam_size": 5, "word_timestamps": True, "language": "ro"}}}
    result = transcribe_audio(decoded, {"id": "asset-ro", "duration_ms": 1000}, config)
    assert result["segments"][0]["language"] == "ro"
