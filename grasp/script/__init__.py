"""Step 3: one concept -> one or more video scripts, as JSON."""

from grasp.script.write import (
    MAX_BEAT_WORDS,
    MIN_BEATS,
    SOURCE_BUDGET_CHARS,
    WORD_TOLERANCE,
    part_count,
    target_words,
    write_script,
)

__all__ = [
    "MAX_BEAT_WORDS",
    "MIN_BEATS",
    "SOURCE_BUDGET_CHARS",
    "WORD_TOLERANCE",
    "part_count",
    "target_words",
    "write_script",
]
