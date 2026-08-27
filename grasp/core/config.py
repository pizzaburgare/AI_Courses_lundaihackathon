"""Every knob the pipeline has, in one place. Imports nothing from grasp."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COURSES = ROOT / "courses"

DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
MODEL_ENV = "GRASP_MODEL"  # set by `grasp --model`, read on every call
OPENROUTER_URL = "https://openrouter.ai/api/v1"

MINUTES_PER_VIDEO = 8  # a topic longer than this is split into parts
WORDS_PER_MINUTE = 150  # spoken narration, used to size a script
