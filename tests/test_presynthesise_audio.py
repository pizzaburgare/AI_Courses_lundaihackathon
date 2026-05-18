"""Tests for sequential TTS synthesis in _presynthesise_audio."""

import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.rendering.render import TTSSynthesisError, _presynthesise_audio


def _dummy_audio() -> tuple[np.ndarray, int]:
    return np.zeros(1000, dtype=np.float32), 22050


@pytest.fixture()
def audio_dir(tmp_path: Path) -> Path:
    d = tmp_path / "audio"
    d.mkdir()
    return d


def _run(texts: list[str], side_effects: list, audio_dir: Path) -> int:
    """Call _presynthesise_audio with _synthesize_with_timeout mocked."""
    engine = MagicMock()
    engine_patch = patch("src.tts.get_default_engine", return_value=engine)
    salt_patch = patch("src.rendering.audio._engine_cache_salt", return_value=None)
    synth_patch = patch("src.rendering.audio._synthesize_with_timeout", side_effect=side_effects)
    with engine_patch, salt_patch, synth_patch:
        return _presynthesise_audio(texts, audio_dir, {})


class TestSequentialSynthesis:
    def test_synthesizes_each_clip_once(self, audio_dir: Path) -> None:
        texts = ["hello", "world"]
        result = _run(texts, [_dummy_audio(), _dummy_audio()], audio_dir)
        assert result == len(texts)

    def test_writes_wav_files(self, audio_dir: Path) -> None:
        _run(["hello"], [_dummy_audio()], audio_dir)
        wavs = list(audio_dir.glob("*.wav"))
        assert len(wavs) == 1

    def test_raises_tts_error_on_runtime_error(self, audio_dir: Path) -> None:
        with pytest.raises(TTSSynthesisError, match="model weights corrupted"):
            _run(["hello"], [RuntimeError("model weights corrupted")], audio_dir)

    def test_raises_tts_error_on_timeout(self, audio_dir: Path) -> None:
        with pytest.raises(TTSSynthesisError, match="timed out"):
            timeout_err = RuntimeError("TTS synthesis timed out after 300s (3 words)")
            _run(["hello"], [timeout_err], audio_dir)

    def test_all_cached_skips_synthesis(self, audio_dir: Path) -> None:
        from src.core.cache import hash_text

        texts = ["hello"]
        key = hash_text("hello", salt=None)
        cached = audio_dir / f"{key}.wav"
        with wave.open(str(cached), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00" * 2000)

        result = _run(texts, [], audio_dir)

        assert result == 0

    def test_partial_cache_only_synthesizes_missing(self, audio_dir: Path) -> None:
        from src.core.cache import hash_text

        texts = ["cached", "missing"]
        key = hash_text("cached", salt=None)
        cached_file = audio_dir / f"{key}.wav"
        with wave.open(str(cached_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00" * 2000)

        result = _run(texts, [_dummy_audio()], audio_dir)

        assert result == 1
