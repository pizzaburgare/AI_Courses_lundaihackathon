"""One TTS engine, called directly. Qwen, batched, cached on disk by text.

The whole video's audio is synthesised before Manim starts, so the scene only ever looks
up a finished WAV. The cache key is the text, which means an edit to one beat re-costs
one clip and nothing else.
"""

import hashlib
import wave
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

import numpy as np

from grasp.core import ROOT

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
QWEN_LANGUAGE = "English"
QWEN_SPEAKER = "Ryan"
QWEN_REF_AUDIO = ROOT / "grasp" / "render" / "clone.wav"

BATCH_SIZE = 8
MAX_SECONDS_PER_WORD = 1.0
MIN_CLIP_SECONDS = 3.0  # floor, so a one-word clip is not rejected for being 1.2s
TIMEOUT_SECONDS_PER_CLIP = 300
SAMPLE_WIDTH = 2
STEREO = 2
INT16_MAX = 32767

_model: Any = None  # one model per process, loaded on first use


def clip_path(audio_dir: Path, text: str) -> Path:
    """WAV path for *text*. One engine, so the key needs no salt."""
    return audio_dir / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.wav"


def synthesize(texts: list[str], audio_dir: Path) -> list[Path]:
    """Synthesise each of *texts* into *audio_dir*, keeping any WAV that already exists.

    Batches go through a one-worker pool purely for the timeout: a runaway generation
    otherwise hangs a whole course run with no way to interrupt it.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    paths = [clip_path(audio_dir, text) for text in texts]
    missing = [(t, p) for t, p in zip(texts, paths, strict=True) if not p.exists()]

    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start : start + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(generate, [text for text, _ in batch])
            try:
                results = future.result(timeout=TIMEOUT_SECONDS_PER_CLIP * len(batch))
            except FuturesTimeoutError as err:
                raise RuntimeError(f"TTS synthesis timed out on {len(batch)} clips") from err

        for (text, path), (audio, rate) in zip(batch, results, strict=True):
            words = max(len(text.split()), 1)
            seconds = len(audio) / rate
            limit = max(words * MAX_SECONDS_PER_WORD, MIN_CLIP_SECONDS)
            if seconds > limit:
                raise RuntimeError(
                    f"TTS output rejected: {seconds:.1f}s for {words} words "
                    f"(limit {limit:.1f}s). Likely runaway model output."
                )
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(SAMPLE_WIDTH)
                handle.setframerate(rate)
                handle.writeframes(
                    (np.clip(audio, -1.0, 1.0) * INT16_MAX).astype(np.int16).tobytes()
                )
    return paths


def generate(texts: list[str]) -> list[tuple[np.ndarray, int]]:
    """Qwen native batch synthesis. Loads the model on first use, once per process."""
    global _model  # one model per process is the point
    import torch

    if _model is None:
        from qwen_tts import Qwen3TTSModel

        if torch.cuda.is_available():
            device, dtype = "cuda:0", torch.bfloat16
        elif torch.backends.mps.is_available():
            device, dtype = "mps", torch.bfloat16
        else:
            device, dtype = "cpu", torch.float32
        _model = Qwen3TTSModel.from_pretrained(QWEN_MODEL, device_map=device, dtype=dtype)

    kind = _model.model.tts_model_type
    count = len(texts)
    with torch.inference_mode():
        if kind == "base":
            waves, rate = _model.generate_voice_clone(
                text=texts,
                language=[QWEN_LANGUAGE] * count,
                ref_audio=[str(QWEN_REF_AUDIO)] * count,
                ref_text=[None] * count,
                x_vector_only_mode=[True] * count,
            )
        elif kind == "custom_voice":
            waves, rate = _model.generate_custom_voice(
                text=texts, language=[QWEN_LANGUAGE] * count, speaker=[QWEN_SPEAKER] * count
            )
        elif kind == "voice_design":
            waves, rate = _model.generate_voice_design(
                text=texts, instruct=[QWEN_SPEAKER] * count, language=[QWEN_LANGUAGE] * count
            )
        else:
            raise ValueError(f"unsupported Qwen TTS model type: {kind!r}")

    out: list[tuple[np.ndarray, int]] = []
    for wave_data in waves:
        array = wave_data.detach().cpu().numpy() if hasattr(wave_data, "detach") else wave_data
        array = np.asarray(array, dtype=np.float32)
        out.append((array[0] if array.ndim == STEREO else array, rate))
    return out
