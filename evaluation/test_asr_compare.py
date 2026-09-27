import wave

from evaluation.asr_compare import create_windows, score


def test_metric_reference_cases_and_unicode():
    assert score("same Romanian cuvânt", "SAME, Romanian cuvânt!")["wer"] == 0
    result = score("a b c", "a x c d")
    assert result["werEdits"] == 2
    assert result["referenceWords"] == 3
    assert result["wer"] == 2 / 3
    assert score("a b", "")["wer"] == 1
    assert score("ședință", "sedinta")["cer"] > 0


def test_fixed_windows_cover_every_input_sample_without_overlap(tmp_path):
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * (65 * 16000 + 123))
    windows = create_windows(source, tmp_path / "windows")
    frames = []
    for path in windows:
        with wave.open(str(path), "rb") as window:
            frames.append(window.getnframes())
    assert frames == [30 * 16000, 30 * 16000, 5 * 16000 + 123]
    assert sum(frames) == 65 * 16000 + 123
