"""Step 3: one concept -> an outline of its videos, then one script per video."""

from grasp.script.outline import plan_parts
from grasp.script.sources import SOURCE_BUDGET_CHARS
from grasp.script.write import (
    MAX_BEAT_WORDS,
    MIN_BEAT_WORDS,
    MIN_BEATS,
    WORD_TOLERANCE,
    part_count,
    target_words,
    write_script,
)

__all__ = [
    "MAX_BEAT_WORDS",
    "MIN_BEATS",
    "MIN_BEAT_WORDS",
    "SOURCE_BUDGET_CHARS",
    "WORD_TOLERANCE",
    "part_count",
    "plan_parts",
    "target_words",
    "write_script",
]
