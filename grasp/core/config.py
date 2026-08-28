"""Every knob the pipeline has, in one place. Imports nothing from grasp."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COURSES = ROOT / "courses"

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
MODEL_ENV = "GRASP_MODEL"  # set by `grasp --model`, read on every text call
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# DEFAULT_MODEL is text-only, so it cannot read the PDFs and images ingest is handed.
FILE_MODEL = "google/gemini-3.1-flash-lite"

# Writing the Manim scene is a coding task, not a teaching one: it is judged by whether
# the file runs. That one step gets a model chosen for code, whatever the run's model is.
CODE_MODEL = "moonshotai/kimi-k3"

MINUTES_PER_VIDEO = 8  # a topic longer than this is split into parts
WORDS_PER_MINUTE = 150  # spoken narration, used to size a script


LANGUAGE = "English"
LANGUAGE_RULE = f"""## Language

Write in {LANGUAGE}, whatever language the source material is in. Translate as you read
it; never carry a word or a phrase through untranslated.
"""
