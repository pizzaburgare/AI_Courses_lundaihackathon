"""Step 3, first half: one topic -> which of its videos teaches what.

A topic longer than :data:`grasp.core.MINUTES_PER_VIDEO` becomes several videos, and the
division is decided here, in one call, before any narration exists. Writing part 2 with
part 1 merely in front of it does not work: the model can see what was said and still has
no material of its own, so it re-teaches the worked example and the misconceptions. An
outline gives every part a disjoint brief instead.

The part count this returns is authoritative and may be smaller than the estimate allows.
A concept with one idea and one worked example in it is one video however many minutes
``topics.json`` guessed at.

Data in, data out. :mod:`grasp.pipeline` writes the answer.
"""

from pathlib import Path

from grasp.core import LANGUAGE_RULE, Outline, Topic, ask_valid
from grasp.script.sources import neighbour_block, source_block

PROMPT = (Path(__file__).parent / "outline.md").read_text(encoding="utf-8")
INSTRUCTIONS = PROMPT + "\n" + LANGUAGE_RULE

MIN_COVERS, MAX_COVERS = 3, 12


def plan_parts(
    topic: Topic, sources: dict[str, str], max_parts: int, neighbours: list[Topic]
) -> Outline:
    """How *topic* divides into videos: between one part and *max_parts* of them.

    *sources* maps each corpus-relative path in ``topic.sources`` to that document's
    markdown, exactly as :func:`grasp.script.write_script` takes it. *neighbours* is every
    other topic of the course, so the division can lean on what came before instead of
    re-deriving it, and can leave what comes later alone.
    """
    missing = [path for path in topic.sources if path not in sources]
    if missing:
        raise ValueError(f"topic {topic.id} is missing source text for {', '.join(missing)}")

    lines = [
        f"# Topic {topic.id} - {topic.title}",
        "",
        topic.summary.strip(),
        "",
        (
            f"This concept may become at most {max_parts} videos. Use fewer if the "
            f"material does not honestly fill {max_parts}."
        ),
        *neighbour_block(topic, neighbours),
        *source_block(topic.sources, sources),
    ]

    def check(result: Outline) -> list[str]:
        problems: list[str] = []
        if not 1 <= len(result.parts) <= max_parts:
            return [f"{len(result.parts)} parts; the range is 1 to {max_parts}"]

        numbers = [part.part for part in result.parts]
        if numbers != list(range(1, len(result.parts) + 1)):
            problems.append(f"parts are numbered {numbers}; number them 1..{len(result.parts)}")

        seen: dict[str, int] = {}
        for part in result.parts:
            label = f"part {part.part}"
            if not part.title.strip():
                problems.append(f"{label} has no title")
            if not MIN_COVERS <= len(part.covers) <= MAX_COVERS:
                problems.append(
                    f"{label} covers {len(part.covers)} points; the range is "
                    f"{MIN_COVERS}-{MAX_COVERS}. Merge a thin part into its neighbour."
                )
            for point in part.covers:
                key = " ".join(point.lower().split())
                if key in seen:
                    problems.append(
                        f"{label} repeats a point already given to part {seen[key]}: "
                        f"{point!r}. Every point belongs to exactly one video - if the "
                        f"material will not divide, answer with fewer parts."
                    )
                seen[key] = part.part
        return problems

    result = ask_valid(INSTRUCTIONS, "\n".join(lines), Outline, check)
    return result.model_copy(update={"topic_id": topic.id})
