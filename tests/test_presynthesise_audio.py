"""Tests for adaptive TTS batch-size behaviour in _presynthesise_audio."""

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from src.rendering.render import TTSSynthesisError, _presynthesise_audio


def _dummy_audio() -> tuple[np.ndarray, int]:
    return np.zeros(1000, dtype=np.float32), 22050


def _engine_mock(side_effects: list) -> MagicMock:
    engine = MagicMock()
    engine.synthesize_batch.side_effect = side_effects
    return engine


@pytest.fixture()
def audio_dir(tmp_path: Path) -> Path:
    d = tmp_path / "audio"
    d.mkdir()
    return d


def _run(texts: list[str], engine: MagicMock, audio_dir: Path, batch_size: int = 8) -> int:
    """Call _presynthesise_audio with mocked TTS internals."""
    env_patch = patch.dict(os.environ, {"TTS_BATCH_SIZE": str(batch_size)})
    engine_patch = patch("src.tts.get_default_engine", return_value=engine)
    salt_patch = patch("src.rendering.audio._engine_cache_salt", return_value=None)
    with env_patch, engine_patch, salt_patch:
        return _presynthesise_audio(texts, audio_dir, {})


class TestAdaptiveBatching:
    def test_single_batch_when_no_oom(self, audio_dir: Path) -> None:
        texts = ["hello", "world"]
        engine = _engine_mock([[_dummy_audio(), _dummy_audio()]])

        _run(texts, engine, audio_dir, batch_size=8)

        engine.synthesize_batch.assert_called_once_with(texts)

    def test_halves_batch_on_oom_and_retries(self, audio_dir: Path) -> None:
        """batch_size=2 → OOM → retries each clip at batch_size=1."""
        texts = ["a", "b"]
        oom = RuntimeError("MPS backend out of memory: tried to allocate 1 GiB")
        engine = _engine_mock([oom, [_dummy_audio()], [_dummy_audio()]])

        _run(texts, engine, audio_dir, batch_size=2)

        assert engine.synthesize_batch.call_args_list == [
            call(["a", "b"]),
            call(["a"]),
            call(["b"]),
        ]

    def test_raises_tts_error_on_non_oom(self, audio_dir: Path) -> None:
        texts = ["hello"]
        engine = _engine_mock([RuntimeError("model weights corrupted")])

        with pytest.raises(TTSSynthesisError, match="model weights corrupted"):
            _run(texts, engine, audio_dir)

    def test_raises_tts_error_when_batch1_oom(self, audio_dir: Path) -> None:
        """OOM at batch_size=1 raises TTSSynthesisError instead of infinite retry."""
        texts = ["hello"]
        engine = _engine_mock([RuntimeError("out of memory")])

        with pytest.raises(TTSSynthesisError):
            _run(texts, engine, audio_dir, batch_size=1)

    def test_all_cached_skips_synthesis(self, audio_dir: Path) -> None:
        """When all clips are already cached, synthesize_batch is never called."""
        from src.core.cache import hash_text

        texts = ["hello"]
        # pre-create the cache file
        key = hash_text("hello", salt=None)
        cached = audio_dir / f"{key}.wav"
        import wave

        with wave.open(str(cached), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00" * 2000)

        engine = _engine_mock([])

        result = _run(texts, engine, audio_dir)

        engine.synthesize_batch.assert_not_called()
        assert result == 0
