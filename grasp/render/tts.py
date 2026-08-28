"""One TTS engine, called directly. Qwen, batched, cached on disk by text.

The whole video's audio is synthesised before Manim starts, so the scene only ever looks
up a finished WAV. The cache key is the text, which means an edit to one beat re-costs
one clip and nothing else.
"""

import hashlib
import wave
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from grasp.core import ROOT

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
QWEN_LANGUAGE = "English"
QWEN_SPEAKER = "Ryan"
QWEN_REF_AUDIO = ROOT / "grasp" / "render" / "clone.wav"

BATCH_SIZE = 4  # peak memory is per batch, and 8 reserves ~11 GB of a 16 GB Mac
MAX_SECONDS_PER_WORD = 1.0
MIN_CLIP_SECONDS = 3.0  # floor, so a one-word clip is not rejected for being 1.2s
TIMEOUT_SECONDS_PER_CLIP = 300
SAMPLE_WIDTH = 2
STEREO = 2
INT16_MAX = 32767


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
            with wave.Wave_write(str(path)) as handle:
                handle.setnchannels(1)
                handle.setsampwidth(SAMPLE_WIDTH)
                handle.setframerate(rate)
                handle.writeframes(
                    (np.clip(audio, -1.0, 1.0) * INT16_MAX).astype(np.int16).tobytes()
                )
        release_cache()
    return paths


def release_cache() -> None:
    """Hand the allocator's cached blocks back to the driver, between batches.

    Torch keeps every block it has ever allocated in a pool of its own, so the reservation
    climbs with each batch even though the live tensors do not: on a 16 GB Mac, 10.9 GB
    after one batch of eight and 14.4 GB after two, against 4.2 GB actually in use. The
    machine then swaps until the disk fills. Giving the blocks back costs one re-request at
    the start of the next batch.

    Called after a batch is written rather than inside :func:`generate`, because the
    tensors are still alive until that function returns.
    """
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()


@cache
def load_model() -> Any:
    """The Qwen model, loaded on the best available device. Once per process."""
    import torch
    from qwen_tts import Qwen3TTSModel

    if torch.cuda.is_available():
        device, dtype = "cuda:0", torch.bfloat16
    elif torch.backends.mps.is_available():
        device, dtype = "mps", torch.bfloat16
    else:
        device, dtype = "cpu", torch.float32
    return Qwen3TTSModel.from_pretrained(QWEN_MODEL, device_map=device, dtype=dtype)


def generate(texts: list[str]) -> list[tuple[np.ndarray, int]]:
    """Qwen native batch synthesis."""
    import torch

    model = load_model()
    kind = model.model.tts_model_type
    count = len(texts)
    with torch.inference_mode():
        if kind == "base":
            waves, rate = model.generate_voice_clone(
                text=texts,
                language=[QWEN_LANGUAGE] * count,
                ref_audio=[str(QWEN_REF_AUDIO)] * count,
                ref_text=[None] * count,
                x_vector_only_mode=[True] * count,
            )
        elif kind == "custom_voice":
            waves, rate = model.generate_custom_voice(
                text=texts, language=[QWEN_LANGUAGE] * count, speaker=[QWEN_SPEAKER] * count
            )
        elif kind == "voice_design":
            waves, rate = model.generate_voice_design(
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
