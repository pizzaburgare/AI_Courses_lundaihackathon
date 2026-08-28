"""Every knob the pipeline has, in one place. Imports nothing from grasp."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COURSES = ROOT / "courses"

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
MODEL_ENV = "GRASP_MODEL"  # set by `grasp --model`, read on every text call
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# DEFAULT_MODEL is text-only, so it cannot read the PDFs and images ingest is handed.
# Those two branches always use this model instead, whatever the run's model is.
FILE_MODEL = "google/gemini-3.1-flash-lite"

MINUTES_PER_VIDEO = 8  # a topic longer than this is split into parts
WORDS_PER_MINUTE = 150  # spoken narration, used to size a script

# The language of the finished video: topic titles, narration, on-screen text and the
# voice. Source material may be in any language; every step translates into this one.
LANGUAGE = "English"
LANGUAGE_RULE = f"""## Language

Write in {LANGUAGE}, whatever language the source material is in. Translate as you read
it; never carry a word or a phrase through untranslated. This covers every word you
produce, including anything the viewer reads on screen or hears spoken.

Mathematical notation is the exception: symbols, formulas and variable names are the same
in every language, so copy them exactly as the source writes them.
"""
