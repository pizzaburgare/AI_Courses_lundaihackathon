"""Narration timing for generated Manim scenes. Imported by every ``videos/*/scene.py``.

The one deliberately stateful thing in the pipeline: it exists inside a render, wrapping a
live Manim scene, and its whole job is to hold audio and wall-clock time together. Every
clip is synthesised before Manim starts, so ``say()`` only has to look up a file and know
how long it is.

On the way out it writes ``runtime.json``: what the scene observed about itself, which is
the only thing :mod:`grasp.render` needs from inside the render.
"""

import hashlib
import wave
from pathlib import Path
from types import TracebackType

import numpy as np
from manim import Scene, config

from grasp.core import Chapter, Runtime, Violation, write_json
from grasp.narration.layout import check_layout

TIMELINE_TAIL_SECONDS = 1.0  # headroom at the end of the merged timeline


def clip_path(audio_dir: Path, text: str) -> Path:
    """Path of the pre-synthesised WAV for *text*. The same key the synthesiser uses."""
    return audio_dir / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.wav"


class Slot:
    """Holds one narration slot open; leaving it waits out whatever audio is left."""

    def __init__(self, narrator: "Narrator", start: float, duration: float) -> None:
        self.narrator, self.start, self.duration = narrator, start, duration

    def __enter__(self) -> "Slot":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            return
        left = self.duration - (self.narrator.scene.renderer.time - self.start)
        if left > 1.0 / config.frame_rate:
            self.narrator.scene.wait(left)


class Narrator:
    """Plays pre-synthesised narration clips in sync with a Manim scene."""

    def __init__(self, scene: Scene, video_dir: Path | str) -> None:
        self.scene = scene
        self.video_dir = Path(video_dir)
        self.audio_dir = self.video_dir / "audio"
        self.clips: list[tuple[Path, float, float]] = []  # (wav, start, duration)
        self.chapters: list[Chapter] = []
        self.violations: list[Violation] = []
        self.play = scene.play
        scene.play = self.checked_play  # every play boundary is a layout checkpoint

    def checked_play(self, *args, **kwargs) -> None:
        """``scene.play``, plus the geometric check on the frame it leaves behind."""
        self.play(*args, **kwargs)
        self.violations.extend(check_layout(self.scene))

    def new_section(self, name: str) -> None:
        """Record a chapter marker at the current scene time, for YouTube timestamps."""
        self.chapters.append(Chapter(name=name, at=float(self.scene.renderer.time)))

    def say(self, text: str) -> Slot:
        """Start the clip for *text* now. Use as ``with narrator.say(...): self.play(...)``."""
        path = clip_path(self.audio_dir, text)
        with wave.open(str(path), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
        start = float(self.scene.renderer.time)
        self.clips.append((path, start, duration))
        return Slot(self, start, duration)

    def finish(self) -> None:
        """Merge every clip onto one timeline, attach it at t=0, write ``runtime.json``."""
        write_json(
            self.video_dir / "runtime.json",
            Runtime(
                speech_seconds=sum(duration for _, _, duration in self.clips),
                chapters=self.chapters,
                violations=self.violations,
            ),
        )
        if not self.clips:
            return

        with wave.open(str(self.clips[0][0]), "rb") as handle:
            rate, channels, width = (
                handle.getframerate(),
                handle.getnchannels(),
                handle.getsampwidth(),
            )
        _, last_start, last_duration = self.clips[-1]
        total = int((last_start + last_duration + TIMELINE_TAIL_SECONDS) * rate)
        timeline = np.zeros(total, dtype=np.int16)
        for path, start, _ in self.clips:
            with wave.open(str(path), "rb") as handle:
                chunk = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
            begin = int(start * rate)
            if begin >= total:
                continue
            end = min(begin + len(chunk), total)
            timeline[begin:end] = chunk[: end - begin]

        merged = self.video_dir / "narration.wav"
        with wave.open(str(merged), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(width)
            handle.setframerate(rate)
            handle.writeframes(timeline.tobytes())

        # file_writer.add_sound, not scene.add_sound: the latter is a no-op whenever the
        # renderer is skipping animations, and t=0 avoids a negative offset.
        self.scene.renderer.file_writer.add_sound(str(merged), time=0)
