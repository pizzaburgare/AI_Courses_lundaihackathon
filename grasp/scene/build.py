"""Step 4: one script.json -> the Manim source for one video.

The script is the whole interface. The corpus is not re-inlined here: if the script is not
enough to write the scene, the fix belongs in step 3.

There is no separate fix agent. When a render fails, :mod:`grasp.pipeline` calls
:func:`build_scene` again with the failure text, so the prompt that already knows how to
write this file is the one that sees what went wrong.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from grasp.core import Script, ask_valid
from grasp.scene.source import check_scene

HERE = Path(__file__).parent
INSTRUCTIONS = "\n\n".join(
    (HERE / name).read_text(encoding="utf-8") for name in ("api.md", "style.md")
)

FAILURE_TAIL_CHARS = 6_000  # of a failure report, the end is the part that says why


class SceneSource(BaseModel):
    """The generated scene, as the model returns it. A field, so there is nothing to strip."""

    source: str = Field(
        description=(
            "The complete contents of scene.py: valid Python 3.13, runnable as-is. "
            "No markdown fences, no prose, no explanation."
        )
    )


def build_scene(script: Script, failure: str = "") -> str:
    """The Python source of the Manim scene for *script*.

    *failure* is the previous attempt's ``check.json`` report, passed straight into the
    generation prompt when :mod:`grasp.pipeline` re-samples this step.
    """
    beats = [
        f"## Beat {number} - {beat.title}"
        + (f"\nSECTION: {beat.section}" if beat.section else "")
        + f"\nNARRATION: {beat.narration}"
        + f"\nON SCREEN: {beat.on_screen}"
        for number, beat in enumerate(script.beats, start=1)
    ]
    lines = [
        f"# {script.title}",
        "",
        script.summary.strip(),
        "",
        f"Video {script.part} of {script.parts} for topic {script.topic_id}. "
        f"{len(script.beats)} beats, {script.words()} narration words.",
        "",
        *beats,
    ]
    if failure:
        lines += [
            "",
            "---",
            "",
            "# A previous attempt at this scene failed",
            "",
            "Write the scene again from the beats above, avoiding whatever caused this.",
            "You are writing a fresh file, not patching the old one.",
            "",
            failure.strip()[-FAILURE_TAIL_CHARS:],
        ]

    result = ask_valid(
        INSTRUCTIONS,
        "\n".join(lines),
        SceneSource,
        lambda answer: check_scene(answer.source, script),
    )
    return result.source.rstrip() + "\n"
