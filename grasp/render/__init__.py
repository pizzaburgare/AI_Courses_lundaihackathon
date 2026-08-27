"""Step 5: one Manim scene -> one rendered, checked video."""

from grasp.render.tts import clip_path, synthesize
from grasp.render.video import MIN_SPEECH_RATIO, render_video

__all__ = ["MIN_SPEECH_RATIO", "clip_path", "render_video", "synthesize"]
