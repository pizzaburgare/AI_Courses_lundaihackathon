"""Step 5: ``scene.py`` -> ``lesson.mp4``, and the free checks on what came out.

Synthesise the narration, render into the video's own media directory, then check the
result. There is no vision review and no fix agent: Manim's exit code, the durations, and
the geometry the scene reported in ``runtime.json`` are the whole check.

One render, one :class:`Check`. Deciding whether to try again is
:mod:`grasp.pipeline`'s job, not this module's.
"""

import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from grasp.core import Check, Runtime, read_json
from grasp.render.tts import synthesize
from grasp.scene import narration_texts, scene_class

RENDER_TIMEOUT_SECONDS = 1800
TIMEOUT_RETURNCODE = 124
STDERR_TAIL_LINES = 25
MIN_SPEECH_RATIO = 0.5  # below this the video is mostly dead air
VIDEO_REPORT = re.compile(r"File ready at '(.+?\.mp4)'", re.DOTALL)


def render_video(video: Path, quality: str = "l") -> Check:
    """Render ``<video>/scene.py`` once at *quality* and check the result.

    Publishes ``lesson.mp4`` and ``chapters.txt`` whenever Manim produced a video, even a
    flagged one: a human wants to watch what failed. The returned :class:`Check` says
    whether it is good enough to keep.
    """
    source = (video / "scene.py").read_text(encoding="utf-8")
    clips = synthesize(narration_texts(source), video / "audio")
    media = video / "manim"
    media.mkdir(parents=True, exist_ok=True)
    (video / "runtime.json").unlink(missing_ok=True)

    command = [
        sys.executable,
        "-m",
        "manim",
        f"-q{quality}",
        "--media_dir",
        str(media),
        str(video / "scene.py"),
        scene_class(source),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(
            command, TIMEOUT_RETURNCODE, "", f"manim timed out after {RENDER_TIMEOUT_SECONDS}s"
        )
    (video / "render.log").write_text(f"{result.stdout}\n{result.stderr}", encoding="utf-8")

    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        return Check(render_error=f"manim exited {result.returncode}\n\n{tail}")

    # Manim reports the path as `File ready at '<path>'`, but rich wraps it across a dozen
    # lines inside a narrow log column, so the parse depends on terminal width. Globbing
    # is safe as a fallback only because the media dir belongs to this one video.
    found = VIDEO_REPORT.search(f"{result.stdout}\n{result.stderr}")
    reported = Path(re.sub(r"\s+", "", found.group(1))) if found else None
    if reported is None or not reported.is_file():
        candidates = [
            p
            for p in media.rglob("*.mp4")
            if "partial_movie_files" not in p.parts and "sections" not in p.parts
        ]
        if not candidates:
            return Check(render_error=f"manim exited 0 but produced no mp4 under {media}")
        reported = max(candidates, key=lambda p: p.stat().st_mtime)

    import av

    with av.open(str(reported), "r") as container:
        seconds = float(container.duration or 0) / 1_000_000
        fps = float(container.streams.video[0].average_rate or 15)

    runtime = read_json(video / "runtime.json", Runtime)
    merged = video / "narration.wav"
    narration_seconds = 0.0
    if merged.exists():
        with wave.open(str(merged), "rb") as handle:
            narration_seconds = handle.getnframes() / handle.getframerate()

    problems: list[str] = []
    if seconds < narration_seconds - 1.0 / fps:
        problems.append(
            f"the video is {seconds:.1f}s but the narration is {narration_seconds:.1f}s, so "
            "the end is cut off. Give the last beats animations long enough to cover them."
        )
    ratio = runtime.speech_seconds / seconds if seconds else 0.0
    if ratio <= MIN_SPEECH_RATIO:
        problems.append(
            f"only {ratio:.0%} of the video has narration over it ({len(clips)} clips in "
            f"{seconds:.1f}s), so most of it is dead air. Shorten the waits and the "
            "animations between beats."
        )

    shutil.copy2(reported, video / "lesson.mp4")
    (video / "chapters.txt").write_text(
        "\n".join(f"{int(c.at) // 60:02d}:{int(c.at) % 60:02d} {c.name}" for c in runtime.chapters),
        encoding="utf-8",
    )
    return Check(
        ok=not problems and not runtime.violations,
        video_seconds=seconds,
        speech_seconds=runtime.speech_seconds,
        problems=problems,
        violations=runtime.violations,
    )
