"""Step 3: one concept -> an outline of its videos, then one script per video."""

from grasp.script.outline import plan_parts
from grasp.script.sources import SOURCE_BUDGET_CHARS
from grasp.script.write import part_count, target_words, write_script

__all__ = [
    "SOURCE_BUDGET_CHARS",
    "part_count",
    "plan_parts",
    "target_words",
    "write_script",
]
